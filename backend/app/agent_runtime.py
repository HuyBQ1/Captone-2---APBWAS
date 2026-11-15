"""Security adapter for the existing Agent runtime; no second execution engine."""
from fastapi import HTTPException
from . import models as m
from .permissions import require,permissions
from .retrieval import allowed_scopes

def configuration_for_run(db,user,wf):
    if not wf or not wf.agent_id:return None
    from .agent_management import Config
    agent=db.get(m.Agent,wf.agent_id,populate_existing=True)
    if not agent or agent.workspace_id!=user.workspace_id or agent.status in ('archived','deleted'):
        raise HTTPException(403,'Agent không còn hoạt động trong workspace của bạn.')
    require(db,user,'agents.run')
    if agent.owner_id!=user.id and user.role!='Admin' and not (agent.visibility=='workspace' and agent.status=='published'):
        raise HTTPException(403,'Quyền sử dụng Agent đã thay đổi.')
    snap=wf.agent_snapshot
    if not snap:raise ValueError('Lần chạy thiếu cấu hình Agent đã ghim.')
    if wf.agent_version_id:
        version=db.get(m.AgentVersion,wf.agent_version_id)
        if not version or version.agent_id!=agent.id or version.snapshot!=snap:raise ValueError('Phiên bản Agent không khớp snapshot của lần chạy.')
    elif wf.user_id!=agent.owner_id and user.role!='Admin':raise HTTPException(403,'Không được chạy bản nháp Agent của người khác.')
    config=Config.model_validate({k:v for k,v in snap.items() if k not in ('name','description','avatar','visibility')}).model_dump()
    from .llm_models import authorize_model
    authorize_model(db,user,config['model'])
    if not set(config['permissions']).issubset(set(permissions(db,user))):raise HTTPException(403,'Quyền thực thi của Agent đã bị thu hồi.')
    for id in config['knowledge_ids']:
        doc=db.get(m.Document,id,populate_existing=True)
        if not doc or doc.workspace_id!=user.workspace_id or doc.scope not in allowed_scopes(user) or doc.status!='indexed':
            raise HTTPException(403,'Quyền truy cập kho tri thức của Agent đã thay đổi.')
    return config

def assert_tool(db,user,wf,name):
    config=configuration_for_run(db,user,wf)
    if not config:return None
    from .tools import REGISTRY
    if name not in config['tools'] or name=='apply_approved_inventory_adjustment':
        if name in ('prepare_report_email','open_employee_email'):raise HTTPException(403,'Phiên bản Agent này chưa được bật công cụ email. Hãy chọn phiên bản mới đã có quyền soạn email hoặc dùng trợ lý mặc định.')
        raise HTTPException(403,'Công cụ không được bật cho phiên bản Agent này.')
    if REGISTRY[name]['permission'] not in config['permissions']:raise HTTPException(403,'Agent thiếu quyền công cụ.')
    if user.workspace_id!='primary' and name not in ('search_internal_documents','get_company_profile'):raise HTTPException(403,'Workspace chưa cấu hình nguồn dữ liệu kinh doanh.')
    if name=='query_financial_summary' and 'inventory.read' not in config['permissions']:raise HTTPException(403,'Agent thiếu quyền đọc tồn kho.')
    if name=='prepare_revenue_email' and 'sales.read' not in config['permissions']:raise HTTPException(403,'Agent thiếu quyền đọc doanh thu.')
    return config

def can_view_run(db,user,wf):
    if not wf.agent_id:return True
    agent=db.get(m.Agent,wf.agent_id)
    return bool('agents.run' in permissions(db,user) and agent and agent.workspace_id==user.workspace_id and (wf.user_id==user.id or user.role=='Admin'))
