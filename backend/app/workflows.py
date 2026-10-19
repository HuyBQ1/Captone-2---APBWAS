from datetime import timedelta
import time
from sqlalchemy import select, func
from fastapi import HTTPException
from .models import WorkflowEvent, WorkflowStep, ToolExecution, Approval, Conversation, Message, UsageRecord, User, now
from .schemas import Plan
from .agent import make_plan
from .audit import audit
from .tools import run_tool, REGISTRY
from .permissions import require
from .usage import configuration, context_get, context_set
from .auth import utc

def emit(db,wf,type,payload):
    if db.bind.dialect.name == 'postgresql':
        from sqlalchemy import text
        db.execute(text('SELECT pg_advisory_xact_lock(730020)'))
    sequence = (db.scalar(select(func.max(WorkflowEvent.sequence))) or 0)+1
    db.add(WorkflowEvent(sequence=sequence,workflow_id=wf.id,type=type,payload=payload))
    db.flush()

def fail(db,wf,message):
    wf.status='failed'
    wf.error=message
    emit(db,wf,'failed',{'message':message})
    audit(db,wf.user_id,'workflow.failed',wf.id,{'message':message})
    db.commit()

def process(db,wf):
    user=db.get(User,wf.user_id)
    if not user or not user.active:
        return fail(db,wf,'Tài khoản bị khóa hoặc không tồn tại.')
    if wf.status in ('completed','cancelled','waiting_approval'):
        return
    config=configuration(db)
    started=time.monotonic()
    conv=db.get(Conversation,wf.conversation_id) if wf.conversation_id else None
    try:
        if not wf.plan:
            wf.status='planning'
            if not wf.deadline:
                wf.deadline=now()+timedelta(seconds=config['timeout'])
            emit(db,wf,'planning',{'message':'Đang lập kế hoạch có cấu trúc.'})
            db.commit()
            plan,tokens=make_plan(wf.request,context_get(db,conv))
            wf.tokens=tokens
            usage=db.scalar(select(UsageRecord).where(UsageRecord.workflow_id==wf.id))
            if not usage:
                db.add(UsageRecord(user_id=user.id,workflow_id=wf.id,tokens=tokens))
            if plan.clarification:
                wf.status='completed'
                wf.result={'summary':plan.clarification,'clarification':True}
                emit(db,wf,'completed',wf.result)
                audit(db,user,'agent.clarification',wf.id,wf.result)
                if conv:
                    db.add(Message(conversation_id=conv.id,role='assistant',content=plan.clarification))
                db.commit()
                return
            if not plan.steps or len(plan.steps)>config['max_steps']:
                raise ValueError('Kế hoạch vượt giới hạn số bước hoặc rỗng.')
            for step in plan.steps:
                if step.tool not in REGISTRY or step.tool=='apply_approved_inventory_adjustment':
                    raise ValueError('Kế hoạch chứa công cụ ngoài allowlist.')
                require(db,user,REGISTRY[step.tool]['permission'])
            wf.plan=[step.model_dump() for step in plan.steps]
            for position,step in enumerate(wf.plan):
                db.add(WorkflowStep(workflow_id=wf.id,position=position,tool=step['tool']))
            emit(db,wf,'plan',{'steps':wf.plan})
            audit(db,user,'agent.plan',wf.id,{'steps':wf.plan})
            db.commit()
        Plan.model_validate({'steps':wf.plan})
        wf.status='running'
        db.commit()
        for position in range(wf.checkpoint,len(wf.plan)):
            db.refresh(wf)
            if wf.cancel_requested:
                wf.status='cancelled'
                emit(db,wf,'cancelled',{'message':'Workflow đã được hủy tại checkpoint.'})
                audit(db,user,'workflow.cancelled',wf.id)
                db.commit()
                return
            if wf.deadline and now()>utc(wf.deadline):
                raise ValueError('Workflow vượt thời gian cho phép. Có thể retry các bước chỉ đọc.')
            step=wf.plan[position]
            record=db.scalar(select(WorkflowStep).where(WorkflowStep.workflow_id==wf.id,WorkflowStep.position==position))
            record.status='running'
            emit(db,wf,'tool.started',{'position':position,'tool':step['tool']})
            db.commit()
            tool_started=time.monotonic()
            output=run_tool(db,user,wf,step)
            ms=int((time.monotonic()-tool_started)*1000)
            record.status='completed'
            record.output=output
            wf.result={**wf.result,**output}
            wf.checkpoint=position+1
            db.add(ToolExecution(workflow_id=wf.id,position=position,tool=step['tool'],arguments=step['arguments'],output=output,duration_ms=ms))
            audit(db,user,'tool.completed',wf.id,{'tool':step['tool'],'arguments':step['arguments'],'output':output})
            emit(db,wf,'tool.completed',{'position':position,'tool':step['tool'],'duration_ms':ms,'output':output})
            if step['tool']=='propose_inventory_adjustment':
                approval=Approval(workflow_id=wf.id,user_id=user.id,arguments=output,expires_at=now()+timedelta(hours=config['approval_hours']))
                db.add(approval)
                db.flush()
                wf.status='waiting_approval'
                wf.result={**wf.result,'approval_id':approval.id}
                emit(db,wf,'waiting_approval',{'approval_id':approval.id})
                audit(db,user,'approval.requested',approval.id,output,wf.id)
                db.commit()
                return
            if output.get('month'):
                context_set(conv,{'month':output['month']})
            db.commit()
        wf.status='completed'
        wf.duration_ms+=int((time.monotonic()-started)*1000)
        wf.result={**wf.result,'summary':wf.result.get('summary','Đã hoàn tất xử lý dựa trên dữ liệu doanh nghiệp.')}
        emit(db,wf,'completed',wf.result)
        audit(db,user,'workflow.completed',wf.id,wf.result)
        if conv:
            db.add(Message(conversation_id=conv.id,role='assistant',content=wf.result['summary']))
        db.commit()
    except Exception as exc:
        db.rollback()
        message=exc.detail if isinstance(exc,HTTPException) else str(exc)
        # Don't log upstream exception URLs/headers or potential secrets.
        if 'HTTP' in type(exc).__name__:
            message='AI provider không phản hồi hợp lệ. Kiểm tra cấu hình và kết nối; không chuyển sang mô phỏng.'
        fail(db,wf,message[:1000])
