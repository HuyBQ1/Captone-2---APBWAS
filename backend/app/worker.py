import time
from datetime import timedelta
from sqlalchemy import select, or_
from .db import Session
from .models import Job, Workflow, Document, Approval, SystemSetting, now
from .workflows import process, emit
from .retrieval import index_document
from .audit import audit

def tick():
    with Session() as db:
        heartbeat=db.get(SystemSetting,'worker_heartbeat')
        if not heartbeat:
            heartbeat=SystemSetting(key='worker_heartbeat',value={})
            db.add(heartbeat)
        heartbeat.value={'at':now().isoformat()}
        db.commit()
        # Expire approval requests even when nobody opens the UI.
        expired=db.scalars(select(Approval).where(Approval.status=='pending',Approval.expires_at<=now()).with_for_update(skip_locked=True)).all()
        for approval in expired:
            approval.status='expired'
            wf=db.get(Workflow,approval.workflow_id)
            if wf.status=='waiting_approval':
                wf.status='failed'
                wf.error='Phê duyệt hết hạn.'
                emit(db,wf,'failed',{'message':wf.error})
                audit(db,'worker','approval.expired',approval.id,correlation=wf.id)
        db.commit()
        job=db.scalar(select(Job).where(or_(Job.status=='queued',(Job.status=='running') & (Job.lease_until<now())))
                      .order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return False
        job.status='running'
        job.lease_until=now()+timedelta(minutes=10)
        db.commit()
        try:
            if job.kind=='workflow':
                wf=db.get(Workflow,job.resource)
                process(db,wf)
            else:
                doc=db.get(Document,job.resource)
                if doc:
                    index_document(db,doc)
                    audit(db,'worker','document.indexed',doc.id,{'chunks':doc.chunks})
            job.status='done'
        except Exception:
            db.rollback()
            job=db.get(Job,job.id)
            job.status='failed'
            doc=db.get(Document,job.resource) if job.kind=='document' else None
            if doc:
                doc.status='failed'
                doc.error='Indexing thất bại. Kiểm tra định dạng, văn bản và cấu hình embedding rồi re-index.'
                audit(db,'worker','document.failed',doc.id,{'message':doc.error})
        db.commit()
        return True

if __name__=='__main__':
    while True:
        try:
            if not tick():
                time.sleep(.5)
        except Exception as exc:
            print('Worker database connection unavailable:',type(exc).__name__,flush=True)
            time.sleep(3)
