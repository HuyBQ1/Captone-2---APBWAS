"""Publish one file-creation Agent without modifying existing Agent versions."""
import json
from sqlalchemy import select
from .db import Session
from . import models as m
from .config import settings
from .permissions import permissions
from .retrieval import allowed_scopes
from .agent_management import create,publish,AgentInput,Config,Revision

def seed():
    with Session() as db:
        marker=db.get(m.SystemSetting,'file-agent-v1')
        if marker:return marker.value
        user=db.scalar(select(m.User).where(m.User.active.is_(True),m.User.workspace_id=='primary',m.User.role=='Manager').order_by(m.User.created_at.desc()))
        if not user:user=db.scalar(select(m.User).where(m.User.active.is_(True),m.User.workspace_id=='primary',m.User.role=='Admin'))
        if not user:raise ValueError('Cần Admin hoặc Manager đang hoạt động.')
        required=['agents.run','sales.read','inventory.read','documents.read','mail.send']
        if not set(required).issubset(permissions(db,user)):raise ValueError('Tài khoản tạo Agent thiếu quyền nguồn dữ liệu.')
        docs=list(db.scalars(select(m.Document.id).where(m.Document.workspace_id==user.workspace_id,m.Document.status=='indexed',m.Document.scope.in_(allowed_scopes(user))).order_by(m.Document.name).limit(100)))
        a=create(AgentInput(name='Tạo Word và Excel',description='Soạn tài liệu Word và tạo bảng tính Excel có công thức; xuất báo cáo tài chính, tồn kho và tài liệu nội bộ thành file tải xuống.',avatar='briefcase',visibility='workspace',config=Config(model=settings.ai_model,
            instructions='Trả lời bằng tiếng Việt. Khi được yêu cầu tạo tệp, tạo DOCX hoặc XLSX thật bằng công cụ tương ứng. Dùng source database cho số liệu doanh nghiệp, không tự bịa dữ liệu. Nội dung mới là bản dự thảo. Khi được yêu cầu gửi file, dùng prepare_report_email tạo nháp có tệp đính kèm; không tự xác nhận gửi.',tools=['create_word_file','create_excel_file','search_internal_documents','prepare_report_email','open_employee_email'],permissions=required,knowledge_ids=docs)),user,db)
        result=publish(a['id'],Revision(revision=1),user,db)
        value={'agent_id':result['id'],'name':result['name'],'version':result['published_version']}
        db.add(m.SystemSetting(key='file-agent-v1',value=value));db.commit();return value

if __name__=='__main__':print(json.dumps(seed(),ensure_ascii=False))
