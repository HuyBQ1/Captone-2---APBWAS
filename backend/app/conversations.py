"""Delete private chat content while retaining business and usage ledgers."""
from fastapi import HTTPException
from sqlalchemy import select,delete,func
from sqlalchemy.orm import defer
from . import models as m
from .audit import audit

def remove(db,user,id):
    conv=db.scalar(select(m.Conversation).where(m.Conversation.id==id,m.Conversation.user_id==user.id).with_for_update())
    if not conv:raise HTTPException(404,'Không tìm thấy hội thoại của bạn.')
    runs=list(db.scalars(select(m.Workflow).where(m.Workflow.conversation_id==id).order_by(m.Workflow.id).with_for_update()))
    if any(w.user_id!=user.id for w in runs):raise HTTPException(409,'Hội thoại có lịch sử không hợp lệ; chưa thể xóa.')
    if any(w.status in ('queued','planning','running','waiting_approval') for w in runs):
        raise HTTPException(409,'Hội thoại có workflow đang chạy hoặc chờ phê duyệt. Hoàn tất hoặc hủy trước khi xóa.')
    ids=[w.id for w in runs]
    if ids and db.scalar(select(m.Job.id).where(m.Job.resource.in_(ids),m.Job.kind=='workflow',m.Job.status.in_(['queued','running'])).limit(1)):
        raise HTTPException(409,'Worker chưa hoàn tất xử lý hội thoại. Vui lòng thử lại sau.')
    files=list(db.scalars(select(m.GeneratedFile).options(defer(m.GeneratedFile.content)).where(m.GeneratedFile.workflow_id.in_(ids),m.GeneratedFile.user_id==user.id).with_for_update())) if ids else []
    referenced=set()
    for attached in db.scalars(select(m.MailCampaign.attachment_ids).where(m.MailCampaign.user_id==user.id)):
        referenced.update(attached or [])
    disposable=[f for f in files if f.id not in referenced]
    stats={'messages_deleted':db.scalar(select(func.count()).select_from(m.Message).where(m.Message.conversation_id==id)) or 0,
           'files_deleted':len(disposable),'file_bytes_deleted':sum(f.size for f in disposable),'email_files_retained':len(files)-len(disposable),'workflows_pruned':len(runs)}
    # Only a small deletion receipt enters the immutable audit chain.
    audit(db,user,'conversation.deleted',id,stats)
    if disposable:db.execute(delete(m.GeneratedFile).where(m.GeneratedFile.id.in_([f.id for f in disposable])))
    if ids:
        for table in (m.WorkflowStep,m.ToolExecution,m.Notification):db.execute(delete(table).where(table.workflow_id.in_(ids)))
        # Keep the global event high-water mark so SSE sequence numbers do not go backwards.
        last=db.scalar(select(m.WorkflowEvent).order_by(m.WorkflowEvent.sequence.desc()).limit(1))
        query=delete(m.WorkflowEvent).where(m.WorkflowEvent.workflow_id.in_(ids))
        if last:
            query=query.where(m.WorkflowEvent.id!=last.id)
            if last.workflow_id in ids:last.payload={};last.type='conversation.deleted'
        db.execute(query)
        db.execute(delete(m.Job).where(m.Job.resource.in_(ids),m.Job.kind=='workflow'))
        for w in runs:
            w.conversation_id=None;w.request='[Hội thoại đã xóa]';w.plan=[];w.result={'conversation_deleted':True};w.error=None;w.agent_snapshot=None
    db.execute(delete(m.Message).where(m.Message.conversation_id==id))
    db.delete(conv);db.commit()
    try:
        from .usage import cache
        cache.delete('memory:'+id)
    except __import__('redis').RedisError:pass
    return {'ok':True,**stats}
