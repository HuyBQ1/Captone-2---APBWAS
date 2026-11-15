"""OpenAI-compatible workspace connections. No keys in browser responses or snapshots."""
import ipaddress,json,re,socket
from typing import Literal
from urllib.parse import urlsplit
import httpx
from cryptography.fernet import Fernet,InvalidToken
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,SecretStr,field_validator
from sqlalchemy import select
from . import models as m
from .db import get_db
from .auth import current_user
from .permissions import require
from .schemas import StrictModel,Plan
from .config import settings
from .audit import audit

router=APIRouter(prefix='/api/llm')
MODEL_PATTERN=r'[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,119}'

def vault():
    try:return Fernet((settings.llm_encryption_key.get_secret_value() or settings.mail_encryption_key.get_secret_value()).encode())
    except (ValueError,TypeError):raise HTTPException(503,'Cần cấu hình LLM_ENCRYPTION_KEY (Fernet) ở backend trước khi lưu API key.')

def protect(key):return vault().encrypt(key.encode()).decode()
def reveal(value):
    try:return vault().decrypt(value.encode()).decode()
    except (InvalidToken,ValueError,UnicodeError):raise HTTPException(503,'Không giải mã được API key. Kiểm tra khóa mã hóa của backend.')

def clean_url(value):
    if any(c.isspace() for c in value):raise ValueError('Base URL không được chứa khoảng trắng.')
    p=urlsplit(value.strip())
    try:port=p.port
    except ValueError:raise ValueError('Base URL không hợp lệ.') from None
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or port not in (None,443):raise ValueError('Base URL cần HTTPS, cổng 443 và không có thông tin đăng nhập/query/fragment.')
    host=p.hostname.lower()
    if host in ('localhost','metadata.google.internal') or host.endswith(('.localhost','.local','.internal')):raise ValueError('Chỉ hỗ trợ endpoint công khai.')
    try:
        if not ipaddress.ip_address(host).is_global:raise ValueError('Không cho phép địa chỉ IP nội bộ.')
    except ValueError as exc:
        if ':' in host or re.fullmatch(r'[\d.]+',host):raise ValueError('Không cho phép địa chỉ IP nội bộ hoặc không hợp lệ.') from None
    return value.strip().rstrip('/')

def public_host(base):
    host=urlsplit(base).hostname
    try:addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError:raise HTTPException(502,'Không phân giải được tên miền của nhà cung cấp.') from None
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):raise HTTPException(422,'Endpoint phải có địa chỉ mạng công khai, không được trỏ vào mạng nội bộ.')

class ProviderInput(StrictModel):
    name:str=Field(min_length=2,max_length=100)
    base_url:str=Field(min_length=8,max_length=500)
    api_key:SecretStr=SecretStr('')
    model_ids:list[str]=Field(default_factory=list,max_length=100)
    allowed_roles:list[Literal['Admin','Manager','Employee']]=Field(default_factory=lambda:['Admin','Manager'],min_length=1,max_length=3)
    enabled:bool=True
    json_mode:bool=True
    timeout_seconds:int=Field(default=45,ge=5,le=120)
    revision:int=Field(default=1,ge=1)
    @field_validator('base_url')
    @classmethod
    def url(cls,value):return clean_url(value)
    @field_validator('name')
    @classmethod
    def title(cls,value):
        if not value.strip():raise ValueError('Cần tên kết nối.')
        return value.strip()
    @field_validator('api_key')
    @classmethod
    def key(cls,value):
        raw=value.get_secret_value()
        if len(raw)>4096 or any(c.isspace() for c in raw):raise ValueError('API key không hợp lệ.')
        return value
    @field_validator('model_ids')
    @classmethod
    def ids(cls,values):
        if any(not re.fullmatch(MODEL_PATTERN,value) for value in values):raise ValueError('Model ID không hợp lệ.')
        return list(dict.fromkeys(values))

def view(p):
    return {'id':p.id,'name':p.name,'base_url':p.base_url,'model_ids':p.model_ids,'allowed_roles':p.allowed_roles,
            'enabled':p.enabled,'json_mode':p.json_mode,'timeout_seconds':p.timeout_seconds,'revision':p.revision,
            'key_configured':bool(p.api_key_ciphertext),'last_test_at':p.last_test_at.isoformat() if p.last_test_at else None,'last_test_status':p.last_test_status}

def owned(db,user,id,lock=False):
    q=select(m.LLMProvider).where(m.LLMProvider.id==id,m.LLMProvider.workspace_id==user.workspace_id)
    if lock:q=q.with_for_update()
    p=db.scalar(q.execution_options(populate_existing=True))
    if not p:raise HTTPException(404,'Không tìm thấy nhà cung cấp trong workspace.')
    return p

def environment_models():return list(dict.fromkeys([settings.ai_model]+[s.strip() for s in settings.agent_models.split(',') if s.strip()]))
def model_ref(p,id):return f'llm:{p.id}:{id}'

def catalog(db,user):
    items=[{'id':id,'label':f'{id} · {settings.ai_provider_label or settings.provider}','provider':settings.ai_provider_label or settings.provider,'model_id':id,'source':'environment'} for id in environment_models()]
    for p in db.scalars(select(m.LLMProvider).where(m.LLMProvider.workspace_id==user.workspace_id,m.LLMProvider.enabled.is_(True)).order_by(m.LLMProvider.name)):
        if user.role not in p.allowed_roles:continue
        items.extend({'id':model_ref(p,id),'label':f'{id} · {p.name}','provider':p.name,'model_id':id,'source':'database'} for id in p.model_ids)
    return items

def authorize_model(db,user,ref):
    if ref in environment_models():return None
    parts=ref.split(':',2)
    if len(parts)!=3 or parts[0]!='llm':raise HTTPException(422,'Model chưa được quản trị viên cấu hình.')
    p=owned(db,user,parts[1])
    if not p.enabled or user.role not in p.allowed_roles or parts[2] not in p.model_ids:raise HTTPException(403,'Model đã bị tắt hoặc bạn không còn quyền sử dụng.')
    return p

def runtime_route(db,user,ref):
    p=authorize_model(db,user,ref)
    if not p:return None
    return {'base_url':p.base_url,'api_key':reveal(p.api_key_ciphertext),'model':ref.split(':',2)[2],
            'json_mode':p.json_mode,'timeout':p.timeout_seconds}

@router.get('/models')
def models(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'agents.run');return {'items':catalog(db,user)}

@router.get('/providers')
def providers(user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    try:vault();ready=True
    except HTTPException:ready=False
    return {'items':[view(p) for p in db.scalars(select(m.LLMProvider).where(m.LLMProvider.workspace_id==user.workspace_id).order_by(m.LLMProvider.created_at.desc()))],
            'encryption_ready':ready,'environment':{'name':settings.ai_provider_label or settings.provider,'model_ids':environment_models()}}

def assign(p,b):
    for field in ('name','model_ids','allowed_roles','enabled','json_mode','timeout_seconds'):setattr(p,field,getattr(b,field))

@router.post('/providers',status_code=201)
def create(body:ProviderInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage')
    if not body.api_key.get_secret_value():raise HTTPException(422,'Cần API key để thêm nhà cung cấp.')
    p=m.LLMProvider(workspace_id=user.workspace_id,base_url=body.base_url,api_key_ciphertext=protect(body.api_key.get_secret_value()))
    assign(p,body);db.add(p);db.flush();audit(db,user,'llm.provider_created',p.id,{'name':p.name,'base_url':p.base_url,'model_ids':p.model_ids});db.commit();return view(p)

@router.put('/providers/{id}')
def edit(id:str,body:ProviderInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage');p=owned(db,user,id,True)
    if p.revision!=body.revision:raise HTTPException(409,'Kết nối đã thay đổi. Tải lại trước khi lưu.')
    if p.base_url!=body.base_url:raise HTTPException(422,'Base URL đã cố định. Tạo kết nối mới để đổi nhà cung cấp của model.')
    assign(p,body)
    if body.api_key.get_secret_value():p.api_key_ciphertext=protect(body.api_key.get_secret_value())
    p.revision+=1;p.last_test_status=None;p.last_test_at=None
    audit(db,user,'llm.provider_updated',p.id,{'name':p.name,'revision':p.revision,'enabled':p.enabled,'model_ids':p.model_ids,'allowed_roles':p.allowed_roles});db.commit();return view(p)

@router.post('/providers/{id}/discover')
def discover(id:str,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage');p=owned(db,user,id);public_host(p.base_url)
    try:
        with httpx.Client(timeout=min(p.timeout_seconds,30),follow_redirects=False,trust_env=False) as client:
            response=client.get(p.base_url+'/models',headers={'Authorization':'Bearer '+reveal(p.api_key_ciphertext)})
        if response.status_code!=200:raise HTTPException(502,f'Không lấy được danh sách model (HTTP {response.status_code}). Bạn có thể nhập Model ID thủ công.')
        if len(response.content)>2_000_000:raise ValueError()
        values=response.json()['data']
        if not isinstance(values,list):raise ValueError()
        ids=sorted({item['id'] for item in values if isinstance(item,dict) and isinstance(item.get('id'),str) and re.fullmatch(MODEL_PATTERN,item['id'])})
    except httpx.HTTPError:raise HTTPException(502,'Không thể kết nối để lấy danh sách model. Kiểm tra Base URL và API key.') from None
    except (ValueError,KeyError,TypeError):raise HTTPException(502,'Nhà cung cấp không trả danh sách model tương thích. Có thể nhập Model ID thủ công.') from None
    audit(db,user,'llm.models_discovered',p.id,{'count':len(ids)});db.commit()
    return {'items':ids[:500],'truncated':len(ids)>500,'provider_revision':p.revision}

class TestInput(StrictModel):
    model_id:str=Field(min_length=1,max_length=120)
    confirmed:bool

@router.post('/providers/{id}/test')
def test(id:str,body:TestInput,user=Depends(current_user),db=Depends(get_db)):
    require(db,user,'settings.manage');p=owned(db,user,id)
    revision=p.revision
    if not body.confirmed:raise HTTPException(422,'Cần xác nhận kiểm thử có sử dụng token của nhà cung cấp.')
    if body.model_id not in p.model_ids:raise HTTPException(422,'Lưu model vào kết nối trước khi kiểm thử.')
    from .provider import _post,ProviderError
    public_host(p.base_url)
    request={'model':body.model_id,'max_tokens':512,'stream':False,'messages':[{'role':'user','content':'Return only this JSON, with no other text: {"steps":[],"clarification":"APBWAS connection test"}'}]}
    if p.json_mode:request['response_format']={'type':'json_object'}
    try:
        with httpx.Client(timeout=p.timeout_seconds,follow_redirects=False,trust_env=False) as client:
            result=_post(client,p.base_url+'/chat/completions',headers={'Authorization':'Bearer '+reveal(p.api_key_ciphertext)},json=request)
        Plan.model_validate_json(result['choices'][0]['message']['content'])
        ok=True;message='Model phản hồi JSON đúng schema. Chưa chạy công cụ nghiệp vụ.'
    except ProviderError as exc:ok=False;message=str(exc)
    except (KeyError,IndexError,TypeError,ValueError):ok=False;message='Model chưa trả kế hoạch JSON đúng schema. Kiểm tra Model ID và chế độ JSON.'
    db.refresh(p)
    if p.revision!=revision:raise HTTPException(409,'Kết nối đã thay đổi trong lúc kiểm thử. Kiểm thử lại cấu hình mới.')
    p.last_test_at=m.now();p.last_test_status='passed' if ok else 'failed'
    audit(db,user,'llm.connection_tested',p.id,{'model':body.model_id,'ok':ok});db.commit()
    return {'ok':ok,'message':message,'model_id':body.model_id}
