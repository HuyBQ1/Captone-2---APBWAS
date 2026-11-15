"""Explicit, backed-up removal of the known Nova Commerce sample dataset."""
import argparse,copy,hashlib,json
from pathlib import Path
from sqlalchemy import select,delete,func
from . import models as m
from .db import Session
from .audit import audit

KEY='sample-data-removed-v1'
PACKS=('nova-commerce-business-v1','nova-commerce-word-library-1.1','nova-finance-sample-v1')
LEGACY=('Chính sách nghỉ phép 2026.txt','Quy trình quản lý tồn kho.txt','Hướng dẫn báo cáo kinh doanh.txt')

def tagged_sample_mail(c):
    return c.workspace_id=='primary' and c.subject.startswith('Báo cáo doanh thu tháng ') and 'dữ liệu mẫu/mô phỏng Nova Commerce' in c.body_text

def finish_mail_cleanup(db):
    marker=db.get(m.SystemSetting,KEY)
    if not marker:raise ValueError('Chỉ dọn bản sao email sau khi đã xóa bộ dữ liệu mẫu.')
    before=protected(db);changed=[]
    for c in db.scalars(select(m.MailCampaign).where(m.MailCampaign.workspace_id=='primary').with_for_update()):
        if not tagged_sample_mail(c):continue
        if c.status in ('queued','sending'):raise ValueError('Cần dừng đợt gửi mẫu trước khi dọn nội dung.')
        c.body_text='Nội dung báo cáo mô phỏng đã được xóa theo yêu cầu. Giữ lịch sử gửi thư.';c.revision+=1
        if c.status=='draft':c.status='cancelled';c.cancel_requested=True
        for d in db.scalars(select(m.MailDelivery).where(m.MailDelivery.campaign_id==c.id,m.MailDelivery.status=='pending')):d.status='skipped';d.error='Dữ liệu mô phỏng đã bị xóa.'
        db.execute(delete(m.Job).where(m.Job.resource==c.id,m.Job.kind=='mail'));changed.append(c.id)
    if before!=protected(db):raise ValueError('Tài khoản/kết nối thay đổi ngoài dự kiến.')
    if changed:
        marker.value={**marker.value,'mail_copies_redacted':marker.value.get('mail_copies_redacted',0)+len(changed)}
        audit(db,'operator','dataset.sample_mail_redacted',KEY,{'copies':len(changed)});db.commit()
    return {'additional_mail_copies_redacted':len(changed),'accounts_and_connections_preserved':True}

def protected(db):
    result={}
    for table in (m.User,m.AuthSession,m.GmailConnection,m.LLMProvider):
        rows=[{c.name:str(getattr(row,c.name)) for c in table.__table__.columns} for row in db.scalars(select(table))]
        result[table.__tablename__]=hashlib.sha256(json.dumps(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True)),sort_keys=True).encode()).hexdigest()
    return result

def selection(db):
    manifests={key:(db.get(m.SystemSetting,key).value if db.get(m.SystemSetting,key) else {}) for key in PACKS}
    pack,word,finance=[manifests[k] for k in PACKS]
    pids=set(pack.get('product_ids',[]))
    if pack or finance:
        pids.update(db.scalars(select(m.Product.id).where(m.Product.sku.in_([f'AP-{i:03}' for i in range(1,9)]))))
    pids=set(db.scalars(select(m.Product.id).where(m.Product.id.in_(pids))))
    docs=set(pack.get('document_ids',[]))|set(word.get('archived_ids',[]))
    for item in word.get('documents',[]):docs.update([item['old_id'],item['new_id']])
    docs.update(db.scalars(select(m.Document.id).where(m.Document.workspace_id=='primary',m.Document.name.in_(LEGACY))))
    docs=set(db.scalars(select(m.Document.id).where(m.Document.id.in_(docs),m.Document.workspace_id=='primary')))
    all_products=db.scalar(select(func.count()).select_from(m.Product)) or 0
    all_mock=bool(pids) and len(pids)==all_products
    expenses=set(finance.get('expense_ids',[]))|set(db.scalars(select(m.Expense.id).where(m.Expense.reference.like('NC-FIN-V1-%'))))
    files=[]
    for f in db.scalars(select(m.GeneratedFile).where(m.GeneratedFile.workspace_id=='primary')):
        source=f.source or {}
        if (all_mock and source.get('type') in ('finance','inventory','products')) or set(source.get('document_ids',[]))&docs:files.append(f.id)
    runs=set()
    business={'query_sales','query_financial_summary','compare_revenue_periods','query_declining_products','get_inventory_status','lookup_products','generate_business_report','prepare_revenue_email'}
    for w in db.scalars(select(m.Workflow)):
        sources=(w.result or {}).get('sources',[])
        file_ids={f['id'] for f in (w.result or {}).get('files',[])}
        if w.idempotency_key.startswith(('seed-','NCV1-REPORT-')) or file_ids&set(files) or any(s.get('document_id') in docs for s in sources) or any((all_mock and step['tool'] in business) or step.get('arguments',{}).get('product_id') in pids for step in (w.plan or [])):runs.add(w.id)
    runs.update(db.scalars(select(m.GeneratedFile.workflow_id).where(m.GeneratedFile.id.in_(files))))
    runs.update(c.workflow_id for c in db.scalars(select(m.MailCampaign)) if tagged_sample_mail(c) and c.workflow_id)
    reports=set(pack.get('report_ids',[]))|set(db.scalars(select(m.Report.id).where(m.Report.workflow_id.in_(runs))))
    return {'products':pids,'documents':docs,'expenses':expenses,'files':set(files),'workflows':runs,'reports':reports,'periods':set(finance.get('confirmed_months',[])),'all_products_mock':all_mock}

def counts(db,items):
    return {**{k:len(v) for k,v in items.items() if isinstance(v,set)},'sales':db.scalar(select(func.count()).select_from(m.Sale).where(m.Sale.product_id.in_(items['products']))) or 0,'active_workflows':db.scalar(select(func.count()).select_from(m.Workflow).where(m.Workflow.status.in_(['queued','running','planning','waiting_approval']))) or 0}

def remove(db):
    prior=db.get(m.SystemSetting,KEY)
    if prior:return {**prior.value,'already_removed':True}
    items=selection(db);stats=counts(db,items)
    if stats['active_workflows']:raise ValueError('Còn workflow đang chạy/chờ duyệt; dừng hoặc xử lý trước khi xóa dữ liệu mẫu.')
    before=protected(db)
    admin=db.scalar(select(m.User).where(m.User.role=='Admin',m.User.active.is_(True)).limit(1))
    if not admin:raise ValueError('Cần Admin đang hoạt động để ghi nhận dọn dữ liệu.')
    pids,docs,wids=items['products'],items['documents'],items['workflows']
    # Preserve configuration, publish only the removal of deleted knowledge bindings.
    changed_agents=[]
    for a in db.scalars(select(m.Agent)):
        draft=db.get(m.AgentConfig,a.id)
        published=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==a.id,m.AgentVersion.number==a.published_version)) if a.published_version else None
        draft_changed=draft and bool(set(draft.config.get('knowledge_ids',[]))&docs)
        pub_changed=published and bool(set(published.snapshot.get('knowledge_ids',[]))&docs)
        had_pending=bool(published and draft and published.draft_revision!=draft.revision)
        if draft_changed:
            config=copy.deepcopy(draft.config);config['knowledge_ids']=[id for id in config.get('knowledge_ids',[]) if id not in docs]
            draft.config=config;draft.revision+=1
            snap={'name':a.name,'description':a.description,'avatar':a.avatar,'visibility':a.visibility,**config}
            db.add(m.AgentDraftRevision(agent_id=a.id,revision=draft.revision,snapshot=snap,created_by=admin.id))
        if pub_changed:
            snap=copy.deepcopy(published.snapshot);snap['knowledge_ids']=[id for id in snap.get('knowledge_ids',[]) if id not in docs]
            number=(db.scalar(select(func.max(m.AgentVersion.number)).where(m.AgentVersion.agent_id==a.id)) or 0)+1
            db.add(m.AgentVersion(agent_id=a.id,number=number,draft_revision=published.draft_revision if had_pending else draft.revision,snapshot=snap,created_by=admin.id));a.published_version=number;a.updated_at=m.now()
        if draft_changed or pub_changed:changed_agents.append(a.id);audit(db,admin,'agent.sample_knowledge_removed',a.id,{'published_version':a.published_version})
    # Local copies of mock reports must not remain in drafts or be sent later.
    changed_mail=[]
    for c in db.scalars(select(m.MailCampaign)):
        if c.workflow_id not in wids and not (set(c.attachment_ids or [])&items['files']) and not tagged_sample_mail(c):continue
        c.attachment_ids=[id for id in (c.attachment_ids or []) if id not in items['files']]
        c.body_text='Nội dung báo cáo và tệp mô phỏng đã được xóa theo yêu cầu. Giữ lịch sử gửi thư.';c.revision+=1
        if c.status in ('draft','queued','sending'):c.status='cancelled';c.cancel_requested=True
        for d in db.scalars(select(m.MailDelivery).where(m.MailDelivery.campaign_id==c.id,m.MailDelivery.status.in_(['pending','sending']))):d.status='skipped';d.error='Dữ liệu mô phỏng của đợt gửi đã bị xóa.'
        db.execute(delete(m.Job).where(m.Job.resource==c.id,m.Job.kind=='mail'));changed_mail.append(c.id)
    db.flush()
    affected_conversations=set()
    for w in db.scalars(select(m.Workflow).where(m.Workflow.id.in_(wids))):
        if w.conversation_id:
            affected_conversations.add(w.conversation_id)
            old=(w.result or {}).get('summary')
            if old:db.execute(delete(m.Message).where(m.Message.conversation_id==w.conversation_id,m.Message.role=='assistant',m.Message.content==old))
            c=db.get(m.Conversation,w.conversation_id)
            if c:c.context={}
        w.result={'mock_data_removed':True,'summary':'Dữ liệu mô phỏng của lượt chạy này đã bị xóa theo yêu cầu.'};w.plan=[];w.agent_snapshot=None;w.error=None
    for table in (m.WorkflowStep,m.ToolExecution,m.Notification):db.execute(delete(table).where(table.workflow_id.in_(wids)))
    last=db.scalar(select(m.WorkflowEvent).order_by(m.WorkflowEvent.sequence.desc()).limit(1))
    q=delete(m.WorkflowEvent).where(m.WorkflowEvent.workflow_id.in_(wids))
    if last:
        q=q.where(m.WorkflowEvent.id!=last.id)
        if last.workflow_id in wids:last.payload={};last.type='sample_data.removed'
    db.execute(q)
    db.execute(delete(m.Job).where(m.Job.resource.in_(wids),m.Job.kind=='workflow'))
    approvals=list(db.scalars(select(m.Approval)))
    aids=[a.id for a in approvals if a.workflow_id in wids or a.arguments.get('product_id') in pids]
    db.execute(delete(m.ApprovalDecision).where(m.ApprovalDecision.approval_id.in_(aids)));db.execute(delete(m.Approval).where(m.Approval.id.in_(aids)))
    db.execute(delete(m.Report).where(m.Report.id.in_(items['reports'])))
    db.execute(delete(m.GeneratedFile).where(m.GeneratedFile.id.in_(items['files'])))
    for table in (m.InventoryMovement,m.Sale,m.ProductImage,m.Inventory):db.execute(delete(table).where(table.product_id.in_(pids)))
    db.execute(delete(m.Product).where(m.Product.id.in_(pids)))
    db.execute(delete(m.Expense).where(m.Expense.id.in_(items['expenses'])))
    for month in items['periods']:
        from .finance import dates
        start,end=dates(month)
        remaining=db.scalar(select(func.count()).select_from(m.Sale).where(m.Sale.date>=start,m.Sale.date<end))
        expenses=db.scalar(select(func.count()).select_from(m.Expense).where(m.Expense.date>=start,m.Expense.date<end))
        if not remaining and not expenses:db.execute(delete(m.FinancePeriod).where(m.FinancePeriod.month==month))
        else:
            period=db.get(m.FinancePeriod,month)
            if period:period.expenses_confirmed=False;period.version+=1
    db.execute(delete(m.AgentKnowledge).where(m.AgentKnowledge.document_id.in_(docs)))
    for table in (m.DocumentChunk,m.DocumentFile):db.execute(delete(table).where(table.document_id.in_(docs)))
    db.execute(delete(m.Job).where(m.Job.resource.in_(docs),m.Job.kind=='document'))
    db.execute(delete(m.Document).where(m.Document.id.in_(docs)))
    db.execute(delete(m.SystemSetting).where(m.SystemSetting.key.in_(PACKS)))
    result={'removed':stats,'agents_rebound':len(changed_agents),'mail_copies_redacted':len(changed_mail),'accounts_and_connections_preserved':before==protected(db),'removed_at':m.now().isoformat()}
    if not result['accounts_and_connections_preserved']:raise ValueError('Tài khoản hoặc kết nối thay đổi ngoài dự kiến; hủy transaction.')
    db.add(m.SystemSetting(key=KEY,value=result));audit(db,admin,'dataset.sample_removed',KEY,result);db.commit()
    try:
        from .usage import cache
        for id in affected_conversations:cache.delete('memory:'+id)
    except __import__('redis').RedisError:pass
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--backup');parser.add_argument('--finish-mail',action='store_true');args=parser.parse_args()
    if args.apply:
        if not args.backup:raise SystemExit('Cần backup đã xác minh trước khi xóa.')
        with Path(args.backup).open('rb') as stream:
            if stream.read(5)!=b'PGDMP':raise SystemExit('Backup PostgreSQL không hợp lệ.')
    with Session() as db:print(json.dumps(finish_mail_cleanup(db) if args.finish_mail else remove(db) if args.apply else counts(db,selection(db)),ensure_ascii=False))
