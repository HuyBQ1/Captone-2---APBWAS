"""Explicitly publish report-email support for the seeded file Agent only."""
import copy,json
from sqlalchemy import select
from . import models as m
from .db import Session
from .agent_management import edit,publish,AgentInput,Config,Revision

def upgrade(db,user,agent_id):
    a=db.get(m.Agent,agent_id);draft=db.get(m.AgentConfig,agent_id)
    if not a or not draft:raise ValueError('Không tìm thấy Agent tạo tệp.')
    version=db.scalar(select(m.AgentVersion).where(m.AgentVersion.agent_id==a.id,m.AgentVersion.number==a.published_version))
    additions=['prepare_report_email','open_employee_email']
    if all(t in version.snapshot['tools'] for t in additions) and 'mail.send' in version.snapshot['permissions']:
        return {'agent_id':a.id,'version':a.published_version,'changed':False}
    if draft.revision!=version.draft_revision:raise ValueError('Agent có bản nháp chưa xuất bản; giữ nguyên bản nháp để tránh ghi đè.')
    config=copy.deepcopy(draft.config)
    config['tools']=list(dict.fromkeys(config['tools']+additions))
    config['permissions']=list(dict.fromkeys(config['permissions']+['mail.send']))
    config['instructions']=config['instructions'].replace('Không gửi tệp ra ngoài.','')+' Có thể dùng prepare_report_email để soạn bản nháp đính kèm tệp trong hội thoại và open_employee_email để xem lại. Không tự xác nhận hay gửi email; người dùng phải kiểm tra và xác nhận trên trang email.'
    result=edit(a.id,AgentInput(name=a.name,description=a.description,avatar=a.avatar,visibility=a.visibility,revision=draft.revision,config=Config.model_validate(config)),user,db)
    result=publish(a.id,Revision(revision=result['revision']),user,db)
    return {'agent_id':a.id,'version':result['published_version'],'changed':True}

def run():
    with Session() as db:
        marker=db.get(m.SystemSetting,'file-agent-v1')
        if not marker:raise ValueError('Chưa có Agent tạo tệp mẫu; cần tạo trước khi nâng cấp.')
        a=db.get(m.Agent,marker.value['agent_id']);user=db.get(m.User,a.owner_id)
        return upgrade(db,user,a.id)

if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False))
