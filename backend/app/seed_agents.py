"""Optional usable Agent examples; creates real configs/versions, no executions or AI calls."""
import json
from sqlalchemy import select
from .db import Session
from . import models as m
from .config import settings
from .agent_management import create,publish,AgentInput,Config,Revision

KEY='agent-builder-examples-v1'

def seed():
    with Session() as db:
        existing=db.get(m.SystemSetting,KEY)
        if existing:return existing.value
        user=db.scalar(select(m.User).where(m.User.role=='Manager',m.User.active.is_(True),m.User.workspace_id=='primary').order_by(m.User.created_at.desc()))
        if not user:user=db.scalar(select(m.User).where(m.User.role=='Admin',m.User.active.is_(True),m.User.workspace_id=='primary'))
        if not user:raise ValueError('Cần tài khoản Admin hoặc Manager đang hoạt động.')
        docs=list(db.scalars(select(m.Document.id).where(m.Document.workspace_id=='primary',m.Document.scope=='all',m.Document.status=='indexed').order_by(m.Document.name).limit(100)))
        examples=[('Phân tích tài chính','Tính doanh thu, giá vốn, chi phí, số đơn và lãi/lỗ theo tháng.',['query_financial_summary'],['sales.read','inventory.read'],[],'chart'),
                  ('Tra cứu tồn kho','Tra cứu hàng hóa, giá bán và số lượng tồn kho hiện tại.',['lookup_products','get_inventory_status'],['inventory.read'],[],'box')]
        if docs:examples.append(('Trợ lý tri thức','Tra cứu các quy trình nội bộ được gắn và dẫn nguồn.',['search_internal_documents'],['documents.read'],docs,'book'))
        ids=[]
        for name,description,tools,perms,knowledge,avatar in examples:
            # Never overwrite an existing Agent with the same identity/title.
            existing_agent=db.scalar(select(m.Agent).where(m.Agent.workspace_id=='primary',m.Agent.name==name,m.Agent.status!='deleted'))
            if existing_agent:ids.append(existing_agent.id);continue
            agent=create(AgentInput(name=name,description=description,avatar=avatar,visibility='workspace',config=Config(
                model=settings.ai_model,instructions='Trả lời bằng tiếng Việt. Chỉ dùng công cụ và tài liệu được cấp quyền; nói rõ khi thiếu dữ liệu.',
                tools=tools,permissions=perms,knowledge_ids=knowledge)),user,db)
            publish(agent['id'],Revision(revision=1),user,db);ids.append(agent['id'])
        value={'agent_ids':ids,'created_examples':True}
        db.add(m.SystemSetting(key=KEY,value=value));db.commit();return value

if __name__=='__main__':print(json.dumps(seed()))
