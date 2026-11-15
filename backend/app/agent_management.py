"""Agent drafts and immutable publication; runs reuse the existing Workflow/Job runtime."""
import copy,re
import unicodedata
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import Field,field_validator
from sqlalchemy import select,delete,func,or_
from . import models as m
from .db import get_db
from .auth import current_user
from .permissions import require,permissions
from .schemas import StrictModel
from .config import settings
from .audit import audit
from .tools import REGISTRY
from .retrieval import allowed_scopes
from .usage import quota
from .llm_models import catalog

router=APIRouter(prefix='/api/agents')
AVATARS=['sparkles','chart','book','box','shield','briefcase']

def models(db,user):
    return [m['id'] for m in catalog(db,user)]

class Config(StrictModel):
    instructions:str=Field(default='Trả lời bằng tiếng Việt, dựa trên dữ liệu được phép truy cập.',max_length=6000)
    model:str=Field(max_length=256)
    temperature:float=Field(default=0,ge=0,le=1)
    max_output_tokens:int=Field(default=1800,ge=128,le=1800)
    max_steps:int=Field(default=8,ge=1,le=12)
    token_budget:int=Field(default=12000,ge=6000,le=100000)
    tools:list[str]=Field(default_factory=list,max_length=30)
    knowledge_ids:list[str]=Field(default_factory=list,max_length=100)
    permissions:list[str]=Field(default_factory=list,max_length=50)
    @field_validator('instructions')
    @classmethod
    def no_credentials(cls,value):
        if re.search(r'(?:sk-[\w-]{12,}|Bearer\s+[\w.-]{16,}|-----BEGIN .*PRIVATE KEY|(?:api[_ -]?key|password|secret)\s*[:=]\s*["\']?\S{8,})',value,re.I):
            raise ValueError('Không lưu API key, mật khẩu hoặc token trong chỉ dẫn Agent.')
        return value

class AgentInput(StrictModel):
    name:str=Field(min_length=2,max_length=120)
    description:str=Field(default='',max_length=1000)
    avatar:Literal['sparkles','chart','book','box','shield','briefcase']='sparkles'
    visibility:Literal['private','workspace']='private'
    config:Config
    revision:int=Field(default=1,ge=1)

class Revision(StrictModel):
    revision:int=Field(ge=1)

class RunInput(StrictModel):
    request:str=Field(min_length=3,max_length=4000)
    idempotency_key:str=Field(min_length=10,max_length=100)
    version:int | None=Field(default=None,ge=1)
    revision:int | None=Field(default=None,ge=1)
    conversation_id:str | None=Field(default=None,min_length=1,max_length=36)

def can_manage(user,agent):return user.workspace_id==agent.workspace_id and (user.id==agent.owner_id or user.role=='Admin')

def owned(db,user,id,manage=False,include_deleted=False,locked=False):
    query=select(m.Agent).where(m.Agent.id==id)
    if locked:query=query.with_for_update()
    agent=db.scalar(query)
    if not agent or agent.workspace_id!=user.workspace_id or (agent.status=='deleted' and not include_deleted):raise HTTPException(404,'Không tìm thấy Agent.')
    if manage:
        require(db,user,'agents.manage')
        if not can_manage(user,agent):raise HTTPException(404,'Không tìm thấy Agent.')
    else:
        require(db,user,'agents.run')
        if not can_manage(user,agent) and not (agent.visibility=='workspace' and agent.published_version is not None and agent.status=='published'):
            raise HTTPException(404,'Không tìm thấy Agent.')
    return agent

def validate(db,user,config):
    from .llm_models import authorize_model
    authorize_model(db,user,config.model)
    if len(set(config.tools))!=len(config.tools) or len(set(config.knowledge_ids))!=len(config.knowledge_ids):raise HTTPException(422,'Danh sách công cụ/tài liệu bị trùng.')
    allowed=set(permissions(db,user))
    if not set(config.permissions).issubset(allowed):raise HTTPException(403,'Agent không được cấp quyền cao hơn tài khoản cấu hình.')
    for name in config.tools:
        if name not in REGISTRY or name=='apply_approved_inventory_adjustment':raise HTTPException(422,'Công cụ không hợp lệ hoặc chỉ được gọi sau phê duyệt.')
        required={REGISTRY[name]['permission']}|({'inventory.read'} if name=='query_financial_summary' else set())
        if name=='prepare_revenue_email':required.add('sales.read')
        if not required.issubset(set(config.permissions)):raise HTTPException(422,'Công cụ thiếu quyền trong cấu hình Agent: '+name)
        if user.workspace_id!='primary' and name!='search_internal_documents':raise HTTPException(403,'Nguồn dữ liệu kinh doanh chưa được cấu hình cho workspace này.')
    for id in config.knowledge_ids:
        doc=db.get(m.Document,id)
        if not doc or doc.workspace_id!=user.workspace_id or doc.scope not in allowed_scopes(user) or doc.status!='indexed':raise HTTPException(403,'Tài liệu không sẵn sàng hoặc ngoài phạm vi truy cập.')
    if config.knowledge_ids and 'search_internal_documents' not in config.tools:raise HTTPException(422,'Cần bật công cụ tìm tài liệu khi gắn kho tri thức.')
    return config.model_dump()

def snapshot(agent,config):
    return {'name':agent.name,'description':agent.description,'avatar':agent.avatar,'visibility':agent.visibility,**copy.deepcopy(config)}

def output(db,agent,full=False):
    draft=db.get(m.AgentConfig,agent.id)
    version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==agent.id,m.AgentVersion.number==agent.published_version)) if agent.published_version else None
    result={'id':agent.id,'name':agent.name,'description':agent.description,'avatar':agent.avatar,'status':agent.status,'visibility':agent.visibility,
            'owner_id':agent.owner_id,'published_version':agent.published_version,'revision':draft.revision,
            'has_draft_changes':not version or version.draft_revision!=draft.revision,'updated_at':agent.updated_at.isoformat()}
    if full:result['config']=draft.config
    result['published_model']=version.snapshot['model'] if version else None
    return result

def listing_output(db,user,agent):
    result=output(db,agent)
    if not can_manage(user,agent):
        v=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==agent.id,m.AgentVersion.number==agent.published_version))
        for k in ['name','description','avatar']:result[k]=v.snapshot[k]
    return {**result,'can_manage':can_manage(user,agent) and 'agents.manage' in permissions(db,user)}

def save_relations(db,agent,config):
    db.execute(delete(m.AgentTool).where(m.AgentTool.agent_id==agent.id));db.execute(delete(m.AgentKnowledge).where(m.AgentKnowledge.agent_id==agent.id))
    db.add_all([m.AgentTool(agent_id=agent.id,tool=t) for t in config['tools']])
    db.add_all([m.AgentKnowledge(agent_id=agent.id,document_id=id) for id in config['knowledge_ids']])

@router.get('/capabilities')
def capabilities(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'agents.run')
    own=set(permissions(db,user))
    docs=db.scalars(select(m.Document).where(m.Document.workspace_id==user.workspace_id,m.Document.status=='indexed',m.Document.scope.in_(allowed_scopes(user))).order_by(m.Document.name).limit(101)).all()
    return {'models':models(db,user),'model_options':catalog(db,user),'avatars':AVATARS,'permissions':sorted(own),'tools':[{'name':k,**v} for k,v in REGISTRY.items() if k!='apply_approved_inventory_adjustment' and v['permission'] in own and (user.workspace_id=='primary' or k=='search_internal_documents')],
            'knowledge':[{'id':d.id,'name':d.name,'scope':d.scope} for d in docs[:100]],'knowledge_truncated':len(docs)>100}

@router.get('/available')
def available(user=Depends(current_user),db=Depends(get_db),q:str=Query(default='',max_length=120)):
    require(db,user,'agents.run')
    query=select(m.Agent).where(m.Agent.workspace_id==user.workspace_id,m.Agent.status=='published')
    if user.role!='Admin':query=query.where(or_(m.Agent.owner_id==user.id,m.Agent.visibility=='workspace'))
    items=[]
    fold=lambda value:''.join(c for c in unicodedata.normalize('NFD',value.casefold().replace('đ','d')) if not unicodedata.combining(c))
    # Names, permissions and tools come from the deployed version, never an
    # unpublished edit. Search after authorization so it cannot expose drafts.
    for agent in db.scalars(query.order_by(m.Agent.updated_at.desc())):
        version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==agent.id,m.AgentVersion.number==agent.published_version))
        if not version or fold(q) not in fold(version.snapshot['name']+' '+version.snapshot.get('description','')):continue
        try:config=validate(db,user,Config.model_validate({k:v for k,v in version.snapshot.items() if k not in ('name','description','avatar','visibility')}))
        except HTTPException:continue
        if not config['tools']:continue
        items.append({'id':agent.id,'name':version.snapshot['name'],'description':version.snapshot.get('description',''),
                      'avatar':version.snapshot.get('avatar','sparkles'),'published_version':version.number,'model':version.snapshot['model']})
        if len(items)>100:break
    return {'items':items[:100],'truncated':len(items)>100}

@router.get('')
def listing(user=Depends(current_user),db=Depends(get_db),q:str=Query(default='',max_length=120),status:str='',page_number:int=1):
    require(db,user,'agents.run')
    query=select(m.Agent).where(m.Agent.workspace_id==user.workspace_id,m.Agent.status!='deleted',m.Agent.name.ilike('%'+q+'%'))
    if user.role!='Admin':query=query.where(or_(m.Agent.owner_id==user.id,(m.Agent.visibility=='workspace')&(m.Agent.status=='published')))
    if status:query=query.where(m.Agent.status==status)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(m.Agent.updated_at.desc()).offset((max(1,page_number)-1)*12).limit(12))
    return {'items':[listing_output(db,user,a) for a in rows],'total':total,'page':max(1,page_number),'size':12}

@router.post('',status_code=201)
def create(body:AgentInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'agents.manage');config=validate(db,user,body.config)
    agent=m.Agent(owner_id=user.id,workspace_id=user.workspace_id,**body.model_dump(exclude={'config','revision'}));db.add(agent);db.flush()
    db.add(m.AgentConfig(agent_id=agent.id,config=config,revision=1));save_relations(db,agent,config)
    db.add(m.AgentDraftRevision(agent_id=agent.id,revision=1,snapshot=snapshot(agent,config),created_by=user.id))
    audit(db,user,'agent.created',agent.id,{'name':agent.name});db.commit();return output(db,agent,True)

@router.get('/{id}')
def detail(id:str,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id)
    result=output(db,agent,can_manage(user,agent))
    if not can_manage(user,agent):
        version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==id,m.AgentVersion.number==agent.published_version))
        result['name']=version.snapshot['name'];result['description']=version.snapshot['description'];result['avatar']=version.snapshot['avatar']
    return {**result,'can_manage':can_manage(user,agent) and 'agents.manage' in permissions(db,user)}

@router.put('/{id}')
def edit(id:str,body:AgentInput,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True)
    if agent.status=='archived':raise HTTPException(409,'Khôi phục Agent lưu trữ trước khi chỉnh sửa.')
    draft=db.get(m.AgentConfig,id)
    if draft.revision!=body.revision:raise HTTPException(409,'Bản nháp vừa thay đổi. Tải lại trước khi lưu.')
    config=validate(db,user,body.config)
    for key,value in body.model_dump(exclude={'config','revision'}).items():setattr(agent,key,value)
    draft.config=config;draft.revision+=1;agent.updated_at=m.now();save_relations(db,agent,config)
    db.add(m.AgentDraftRevision(agent_id=id,revision=draft.revision,snapshot=snapshot(agent,config),created_by=user.id))
    audit(db,user,'agent.draft_updated',id,{'revision':draft.revision});db.commit();return output(db,agent,True)

@router.post('/{id}/publish')
def publish(id:str,body:Revision,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True);draft=db.get(m.AgentConfig,id)
    if agent.status=='archived' or draft.revision!=body.revision:raise HTTPException(409,'Bản nháp thay đổi hoặc Agent đã lưu trữ.')
    config=validate(db,user,Config.model_validate(draft.config))
    if not config['tools']:raise HTTPException(422,'Cần chọn ít nhất một công cụ trước khi xuất bản.')
    previous=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==id,m.AgentVersion.draft_revision==draft.revision))
    if previous and previous.number==agent.published_version:return output(db,agent,True)
    number=(db.scalar(select(func.max(m.AgentVersion.number)).where(m.AgentVersion.agent_id==id)) or 0)+1
    db.add(m.AgentVersion(agent_id=id,number=number,draft_revision=draft.revision,snapshot=snapshot(agent,config),created_by=user.id))
    agent.published_version=number;agent.status='published';agent.updated_at=m.now()
    audit(db,user,'agent.published',id,{'version':number,'draft_revision':draft.revision});db.commit();return output(db,agent,True)

@router.post('/{id}/duplicate',status_code=201)
def duplicate(id:str,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True)
    draft=db.get(m.AgentConfig,id)
    return create(AgentInput(name=agent.name[:108]+' (bản sao)',description=agent.description,avatar=agent.avatar,visibility='private',config=Config.model_validate(draft.config)),user,db)

@router.post('/{id}/archive')
def archive(id:str,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True);agent.status='archived';agent.updated_at=m.now()
    audit(db,user,'agent.archived',id);db.commit();return output(db,agent)

@router.post('/{id}/unarchive')
def unarchive(id:str,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True)
    agent.status='published' if agent.published_version else 'draft';agent.updated_at=m.now()
    audit(db,user,'agent.unarchived',id);db.commit();return output(db,agent)

@router.delete('/{id}')
def remove(id:str,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True);agent.status='deleted';agent.updated_at=m.now()
    audit(db,user,'agent.deleted',id,{'retained_versions':True});db.commit();return {'ok':True}

@router.get('/{id}/versions')
def versions(id:str,user=Depends(current_user),db=Depends(get_db)):
    owned(db,user,id,manage=True)
    rows=db.scalars(select(m.AgentVersion).where(m.AgentVersion.agent_id==id).order_by(m.AgentVersion.number.desc()).limit(100))
    drafts=db.scalars(select(m.AgentDraftRevision).where(m.AgentDraftRevision.agent_id==id).order_by(m.AgentDraftRevision.revision.desc()).limit(100))
    return {'items':[{'id':v.id,'number':v.number,'draft_revision':v.draft_revision,'created_by':v.created_by,'created_at':v.created_at.isoformat(),'snapshot':v.snapshot} for v in rows],
            'drafts':[{'revision':d.revision,'created_at':d.created_at.isoformat(),'created_by':d.created_by} for d in drafts]}

@router.post('/{id}/drafts/{revision}/restore')
def restore_draft(id:str,revision:int,body:Revision,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True);draft=db.get(m.AgentDraftRevision,(id,revision))
    if not draft:raise HTTPException(404,'Không tìm thấy bản nháp đã lưu.')
    snap=copy.deepcopy(draft.snapshot)
    metadata={k:snap.pop(k) for k in ['name','description','avatar','visibility']}
    return edit(id,AgentInput(**metadata,config=Config.model_validate(snap),revision=body.revision),user,db)

@router.get('/{id}/versions/{number}/compare')
def compare(id:str,number:int,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True);version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==id,m.AgentVersion.number==number))
    if not version:raise HTTPException(404,'Không tìm thấy phiên bản.')
    current=snapshot(agent,db.get(m.AgentConfig,id).config)
    return {'version':number,'draft_revision':db.get(m.AgentConfig,id).revision,'changes':[{'field':k,'published':version.snapshot.get(k),'draft':current.get(k)} for k in sorted(set(version.snapshot)|set(current)) if version.snapshot.get(k)!=current.get(k)]}

@router.post('/{id}/versions/{number}/restore')
def restore(id:str,number:int,body:Revision,user=Depends(current_user),db=Depends(get_db)):
    agent=owned(db,user,id,manage=True,locked=True);version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==id,m.AgentVersion.number==number))
    if not version:raise HTTPException(404,'Không tìm thấy phiên bản.')
    snap=copy.deepcopy(version.snapshot)
    visibility=snap.pop('visibility',agent.visibility)
    return edit(id,AgentInput(**{k:snap.pop(k) for k in ['name','description','avatar']},visibility=visibility,config=Config.model_validate(snap),revision=body.revision),user,db)

def enqueue(db,user,agent,body,draft=False):
    from .workflows import emit
    require(db,user,'agents.run')
    if agent.status in ('archived','deleted'):raise HTTPException(409,'Agent đã lưu trữ hoặc bị xóa.')
    version=None;revision=None
    if draft:
        require(db,user,'agents.manage')
        current=db.get(m.AgentConfig,agent.id)
        if body.revision!=current.revision:raise HTTPException(409,'Lưu/tải lại bản nháp trước khi kiểm thử.')
        snap=snapshot(agent,validate(db,user,Config.model_validate(current.config)));revision=current.revision
    else:
        number=body.version or agent.published_version
        version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==agent.id,m.AgentVersion.number==number)) if number else None
        if not version:raise HTTPException(409,'Agent chưa có phiên bản đã xuất bản.')
        snap=copy.deepcopy(version.snapshot)
        validate(db,user,Config.model_validate({k:v for k,v in snap.items() if k not in ('name','description','avatar','visibility')}))
    existing=db.scalar(select(m.Workflow).where(m.Workflow.idempotency_key==body.idempotency_key))
    if existing:
        if existing.user_id!=user.id or existing.agent_id!=agent.id or existing.request!=body.request or existing.agent_version_id!=(version.id if version else None) or existing.agent_draft_revision!=revision:
            raise HTTPException(409,'Idempotency key đã dùng cho nội dung hoặc phiên bản khác.')
        if body.conversation_id and existing.conversation_id!=body.conversation_id:raise HTTPException(409,'Idempotency key thuộc hội thoại khác.')
        return {'id':existing.id,'conversation_id':existing.conversation_id,'status':existing.status,'agent_version':version.number if version else None,'draft_revision':revision}
    if not snap['tools']:raise HTTPException(422,'Agent chưa được gán công cụ.')
    quota(db,user)
    if body.conversation_id:
        conv=db.scalar(select(m.Conversation).where(m.Conversation.id==body.conversation_id).with_for_update())
        if not conv or conv.user_id!=user.id:raise HTTPException(404,'Không tìm thấy hội thoại của bạn.')
        history=list(db.scalars(select(m.Workflow).where(m.Workflow.conversation_id==conv.id)))
        if not history or any(w.agent_id!=agent.id for w in history):raise HTTPException(409,'Chọn hội thoại của đúng Agent hoặc bắt đầu hội thoại mới.')
    else:
        conv=m.Conversation(user_id=user.id,title=f"{snap['name']}: {body.request}"[:90]);db.add(conv);db.flush()
    wf=m.Workflow(user_id=user.id,conversation_id=conv.id,request=body.request,idempotency_key=body.idempotency_key,
                  agent_id=agent.id,agent_version_id=version.id if version else None,agent_draft_revision=revision,agent_snapshot=snap)
    db.add(wf);db.flush();db.add(m.Message(conversation_id=conv.id,role='user',content=body.request));db.add(m.Job(resource=wf.id,kind='workflow'))
    emit(db,wf,'queued',{'message':'Agent đã vào hàng đợi worker.','agent_id':agent.id,'agent_version':version.number if version else None,'draft_revision':revision})
    audit(db,user,'agent.run_requested',wf.id,{'agent_id':agent.id,'version_id':wf.agent_version_id,'draft_revision':revision});db.commit()
    return {'id':wf.id,'conversation_id':conv.id,'status':wf.status,'agent_version':version.number if version else None,'draft_revision':revision}

@router.post('/{id}/playground',status_code=202)
def playground(id:str,body:RunInput,user=Depends(current_user),db=Depends(get_db)):
    return enqueue(db,user,owned(db,user,id,manage=True),body,True)

@router.post('/{id}/runs',status_code=202)
def run(id:str,body:RunInput,user=Depends(current_user),db=Depends(get_db)):
    return enqueue(db,user,owned(db,user,id),body)

@router.get('/{id}/runs')
def history(id:str,user=Depends(current_user),db=Depends(get_db),page_number:int=1):
    owned(db,user,id)
    query=select(m.Workflow).where(m.Workflow.agent_id==id)
    if not (user.role=='Admin' and 'agents.manage' in permissions(db,user)):query=query.where(m.Workflow.user_id==user.id)
    from .main import page
    result=page(db,query.order_by(m.Workflow.created_at.desc()),page_number)
    for item in result['items']:item['result']={};item['plan']=[]
    return result
