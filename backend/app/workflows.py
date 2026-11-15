from datetime import timedelta
import time
from sqlalchemy import select, func
from fastapi import HTTPException
from .models import WorkflowEvent, WorkflowStep, ToolExecution, Approval, Conversation, Message, UsageRecord, User, Notification, now
from .schemas import Plan
from .agent import make_plan
from .audit import audit
from .tools import run_tool, REGISTRY
from .permissions import require,permissions
from .usage import configuration, context_get, context_set
from .auth import utc
from .config import settings

def emit(db,wf,type,payload):
    if db.bind.dialect.name == 'postgresql':
        from sqlalchemy import text
        # Audit and event writers share one lock order, including paths that
        # emit before auditing. Otherwise approval and enqueue can deadlock.
        db.execute(text('SELECT pg_advisory_xact_lock(730019)'))
        db.execute(text('SELECT pg_advisory_xact_lock(730020)'))
    sequence = (db.scalar(select(func.max(WorkflowEvent.sequence))) or 0)+1
    titles={'completed':'Workflow đã hoàn tất','failed':'Workflow cần kiểm tra','cancelled':'Workflow đã hủy','waiting_approval':'Đề xuất đang chờ phê duyệt'}
    if type in titles and not db.scalar(select(Notification.id).where(Notification.user_id==wf.user_id,Notification.workflow_id==wf.id,Notification.kind==type)):
        db.add(Notification(user_id=wf.user_id,workflow_id=wf.id,kind=type,title=titles[type]))
    db.add(WorkflowEvent(sequence=sequence,workflow_id=wf.id,type=type,payload=payload))
    db.flush()

def fail(db,wf,message):
    wf.status='failed'
    wf.error=message
    for step in db.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id==wf.id,WorkflowStep.status=='running')):
        step.status='failed';step.output={'error':message}
    emit(db,wf,'failed',{'message':message})
    audit(db,wf.user_id,'workflow.failed',wf.id,{'message':message})
    db.commit()

def process(db,wf):
    if wf.result.get('conversation_deleted') or wf.result.get('mock_data_removed'):return
    user=db.get(User,wf.user_id)
    if not user or not user.active:
        return fail(db,wf,'Tài khoản bị khóa hoặc không tồn tại.')
    if wf.status in ('completed','cancelled','waiting_approval'):
        return
    config=configuration(db)
    started=time.monotonic()
    conv=db.get(Conversation,wf.conversation_id) if wf.conversation_id else None
    try:
        from .agent_runtime import configuration_for_run,assert_tool
        agent_config=configuration_for_run(db,user,wf)
        from .llm_models import authorize_model,runtime_route
        selected_model=agent_config['model'] if agent_config else wf.model_ref
        if selected_model:authorize_model(db,user,selected_model)
        if agent_config:config={**config,'max_steps':min(config['max_steps'],agent_config['max_steps'])}
        if not wf.deadline:wf.deadline=now()+timedelta(seconds=config['timeout'])
        if not wf.plan:
            wf.status='planning'
            wf.result={**wf.result,'execution_mode':'demo' if settings.demo_mode else 'llm_agent'}
            emit(db,wf,'planning',{'message':'Đang lập kế hoạch có cấu trúc.'})
            db.commit()
            remaining=max(.1,(utc(wf.deadline)-now()).total_seconds())
            allowed=permissions(db,user)
            planner_config=dict(agent_config) if agent_config else {'tools':[name for name,meta in REGISTRY.items() if meta['permission'] in allowed and name!='apply_approved_inventory_adjustment'],'permissions':allowed,**({'model':selected_model} if selected_model else {})}
            from .models import SystemSetting
            switches=db.get(SystemSetting,'tools',populate_existing=True)
            if switches:planner_config['tools']=[name for name in planner_config['tools'] if switches.value.get(name,True)]
            if selected_model and selected_model.startswith('llm:'):planner_config['_llm_connection']=runtime_route(db,user,selected_model)
            context=context_get(db,conv)
            if conv:
                from .models import GeneratedFile,Workflow
                from sqlalchemy.orm import defer
                latest_file=db.scalar(select(GeneratedFile).options(defer(GeneratedFile.content)).join(Workflow,GeneratedFile.workflow_id==Workflow.id).where(Workflow.conversation_id==conv.id,GeneratedFile.user_id==user.id,GeneratedFile.workspace_id==user.workspace_id).order_by(GeneratedFile.created_at.desc()).limit(1))
                if latest_file:
                    from .office_files import check_access
                    try:check_access(db,user,latest_file)
                    except HTTPException:latest_file=None
                if latest_file:
                    context={**context,'file_source':latest_file.source.get('type')}
                    context['latest_file']={'title':latest_file.title,'kind':latest_file.kind,'month':latest_file.source.get('month')}
                    if not context.get('month') and latest_file.source.get('month'):context['month']=latest_file.source['month']
                recent=list(db.scalars(select(Message).where(Message.conversation_id==conv.id,Message.role=='user').order_by(Message.created_at.desc(),Message.id.desc()).limit(3)))
                prior=[r.content for r in recent if r.content!=wf.request]
                if prior:context={**context,'previous_request':prior[0]}
            if planner_config:plan,tokens=make_plan(wf.request,context,remaining,agent_config=planner_config)
            else:plan,tokens=make_plan(wf.request,context,remaining)
            wf.tokens=tokens
            wf.result={**wf.result,'execution_mode':'demo' if settings.demo_mode else 'llm_agent','planner_tokens':tokens}
            usage=db.scalar(select(UsageRecord).where(UsageRecord.workflow_id==wf.id))
            if not usage:
                db.add(UsageRecord(user_id=user.id,workflow_id=wf.id,tokens=tokens))
            # The provider call has already consumed tokens even if RBAC or plan
            # validation below rejects its proposed tools.
            db.commit()
            if agent_config and tokens>agent_config['token_budget']:raise ValueError('Agent vượt token budget đã cấu hình; chưa thực thi công cụ.')
            if plan.clarification:
                wf.status='completed'
                wf.duration_ms+=int((time.monotonic()-started)*1000)
                wf.result={**wf.result,'summary':plan.clarification,'clarification':True}
                emit(db,wf,'completed',wf.result)
                audit(db,user,'agent.clarification',wf.id,wf.result)
                if conv:
                    db.add(Message(conversation_id=conv.id,role='assistant',content=plan.clarification))
                db.commit()
                return
            if not plan.steps:
                raise ValueError('Model chưa trả lời hoặc đề xuất công cụ. Vui lòng thử lại.')
            if len(plan.steps)>config['max_steps']:
                raise ValueError('Kế hoạch vượt giới hạn số bước cho phép.')
            proposals=[i for i,step in enumerate(plan.steps) if step.tool=='propose_inventory_adjustment']
            if proposals and proposals!=[len(plan.steps)-1]:
                raise ValueError('Đề xuất cần phê duyệt phải xuất hiện đúng một lần ở cuối kế hoạch.')
            for step in plan.steps:
                if step.tool not in REGISTRY or step.tool=='apply_approved_inventory_adjustment':
                    raise ValueError('Kế hoạch chứa công cụ ngoài allowlist.')
                require(db,user,REGISTRY[step.tool]['permission'])
                assert_tool(db,user,wf,step.tool)
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
            db.refresh(user)
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
                wf.duration_ms+=int((time.monotonic()-started)*1000)
                wf.result={**wf.result,'approval_id':approval.id}
                if conv:
                    db.add(Message(conversation_id=conv.id,role='assistant',content=output['summary']))
                emit(db,wf,'waiting_approval',{'approval_id':approval.id})
                audit(db,user,'approval.requested',approval.id,output,wf.id)
                db.commit()
                return
            if output.get('month'):
                context_set(conv,{'month':output['month']})
            db.commit()
        # The LLM receives only results of tools already authorized and executed.
        # Keep verified calculations/files usable if the language provider is down.
        from .business_ai import analyze
        from .provider import ProviderError
        remaining=(utc(wf.deadline)-now()).total_seconds()
        if remaining>2 and not wf.result.get('business_analysis'):
            answer_config=dict(agent_config or {})
            if selected_model:answer_config['model']=selected_model
            if selected_model and selected_model.startswith('llm:'):answer_config['_llm_connection']=runtime_route(db,user,selected_model)
            used=db.scalar(select(func.coalesce(func.sum(UsageRecord.tokens),0)).where(UsageRecord.user_id==user.id,UsageRecord.created_at>=now()-timedelta(days=30))) or 0
            allowance=min(config['token_budget']-used,(agent_config['token_budget']-wf.tokens) if agent_config else 6000)
            if allowance>=1000:
                # Synthesis is limited to four short paragraphs, not a new
                # document. Reserve fewer output tokens without truncating the
                # planner's custom Word/Excel content or changing model choice.
                answer_config['max_output_tokens']=min(answer_config.get('max_output_tokens',1200),1200,allowance)
                emit(db,wf,'business.analysis.started',{'message':'Đang phân tích kết quả công cụ bằng AI.'})
                db.commit()
                try:analysis,extra_tokens=analyze(db,user,wf,answer_config,min(remaining,settings.ai_timeout_seconds))
                except ProviderError as exc:
                    analysis,extra_tokens={'status':'unavailable','reason':str(exc)[:500]+' Số liệu đã tính vẫn được giữ nguyên.'},0
                if analysis:
                    wf.tokens+=extra_tokens
                    usage=db.scalar(select(UsageRecord).where(UsageRecord.workflow_id==wf.id))
                    if usage:usage.tokens=wf.tokens
                    if wf.tokens>(agent_config['token_budget'] if agent_config else config['token_budget']):analysis={'status':'unavailable','reason':'Phân tích vượt ngân sách token của lần chạy.'}
                    summary=analysis['text'] if analysis['status']=='completed' else 'AI chưa trả lời hoàn chỉnh: '+analysis['reason']+' Kết quả công cụ vẫn được lưu trong chi tiết lượt chạy.'
                    wf.result={**wf.result,'business_analysis':analysis,'summary':summary}
                    audit(db,user,'agent.business_analysis',wf.id,{'status':analysis['status'],'tokens':extra_tokens})
                    emit(db,wf,'business.analysis',{'status':analysis['status'],'tokens':extra_tokens})
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
        message=exc.detail if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,ValueError) else 'Xử lý thất bại. Hãy kiểm tra trạng thái dịch vụ và thử lại.'
        wf.duration_ms+=int((time.monotonic()-started)*1000)
        # Don't log upstream exception URLs/headers or potential secrets.
        if not isinstance(exc,HTTPException) and 'HTTP' in type(exc).__name__:
            message='AI provider không phản hồi hợp lệ. Kiểm tra cấu hình và kết nối; không chuyển sang mô phỏng.'
        fail(db,wf,message[:1000])
