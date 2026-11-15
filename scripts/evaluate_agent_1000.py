"""Exercise the workflow against synthetic records. Use SQLite only."""
import argparse
import csv
import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, select, text
from cryptography.fernet import Fernet

from app.config import settings

# Load only the selected provider configuration. The evaluation workflow
# itself always starts with a fresh in-memory database.
if os.environ.get('QA_MODEL') in ('deepseek','luna'):
    if os.environ['QA_MODEL']=='luna':
        source_engine = create_engine(settings.database_url)
        with source_engine.connect() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            provider = connection.execute(text("""
                SELECT base_url, api_key_ciphertext, json_mode, timeout_seconds
                FROM llm_providers
                WHERE enabled AND model_ids::jsonb ? 'gpt-6-luna'
                ORDER BY name LIMIT 1
            """)).mappings().one()
        source_engine.dispose()
        master = settings.llm_encryption_key.get_secret_value() or settings.mail_encryption_key.get_secret_value()
        key = Fernet(master.encode()).decrypt(provider['api_key_ciphertext'].encode()).decode()
        settings.ai_api_key = type(settings.ai_api_key)(key)
        del key, master
        settings.provider = 'openai_compatible'
        settings.ai_model = 'gpt-6-luna'
        settings.ai_base_url = provider['base_url']
        settings.ai_json_mode = provider['json_mode']
        settings.ai_timeout_seconds = provider['timeout_seconds']
    else:
        settings.ai_model = os.environ.get('QA_DEEPSEEK_MODEL','deepseek-v4-flash-vision')
    settings.database_url = 'sqlite://'
    settings.agent_database_url = ''
    settings.redis_url = 'redis://localhost:6399/0'
    settings.llm_encryption_key = type(settings.ai_api_key)('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=')

from app import models as m
from app.db import Base, Session, engine
from app.llm_models import protect
from app.permissions import DEFAULT_PERMISSIONS
from app.retrieval import index_document
from app.shop_connection import KEY, TZ
from app.workflows import process


def seed(db):
    db.add(m.Workspace(id='primary', name='Nova Commerce QA'))
    db.add_all(m.Role(name=role, permissions=values) for role, values in DEFAULT_PERMISSIONS.items())
    users = {}
    for role in ('Manager', 'Employee'):
        user = m.User(email=role.lower()+'@example.test', name=role, role=role, password_hash='unused')
        db.add(user)
        users[role] = user
    db.flush()
    document = m.Document(user_id=users['Manager'].id, name='Chính sách nghỉ phép QA.txt',
                          content='Chính sách nghỉ phép năm. Nhân viên gửi yêu cầu qua bộ phận nhân sự.')
    db.add(document)
    db.flush()
    index_document(db, document)
    orders = []
    for n in range(1, 101):
        product = m.Product(sku=f'QA-{n:03}', name=f'Sản phẩm kiểm thử {n}', category='Điện tử', price=100_000+n*1_000)
        db.add(product)
        db.flush()
        db.add(m.Inventory(product_id=product.id, quantity=n, threshold=5))
        day = m.now().astimezone(TZ).date() if n % 2 else (m.now().astimezone(TZ)-timedelta(days=1)).date()
        status = ('pending', 'confirmed', 'shipping', 'delivered', 'cancelled')[n % 5]
        orders.append(dict(id=n, created_at=f'{day}T01:00:00+07:00', status=status,
                           payment_status='unpaid', total=100_000+n*1_000, lines=[{'quantity':1}]))
    for n in range(1, 11):
        month = f'2025-{n:02}'
        db.add(m.Sale(product_id=product.id, date=datetime(2025,n,5,tzinfo=TZ), quantity=2,
                      revenue=n*1_000_000, unit_cost=n*300_000, order_number=f'QA-ORDER-{n}'))
        db.add(m.Expense(reference=f'QA-E-{n}', date=datetime(2025,n,6,tzinfo=TZ), category='Vận hành', amount=n*100_000))
        db.add(m.FinancePeriod(month=month, expenses_confirmed=n % 2 == 1))
    db.add(m.SystemSetting(key=KEY,value={'enabled':True,'last_sync':m.now().isoformat(),'api_key_ciphertext':protect('nova-qa-test-key')}))
    db.add(m.SystemSetting(key='nova-shop-orders-v1',value={'orders':[],'synced_at':m.now().isoformat()}))
    db.add(m.SystemSetting(key='limits',value={'token_budget':10_000_000,'timeout':90}))
    db.commit()
    return users, document.id, orders


def scenarios():
    intros = ['Cho tôi biết', 'Hãy kiểm tra', 'Vui lòng xem', 'Tra cứu giúp tôi', 'Tôi cần biết',
              'Có thể xem giúp', 'Tìm giúp tôi', 'Xem giúp', 'Xin cho biết', 'Phân tích giúp']
    statuses = [('chờ xác nhận','pending'),('đã xác nhận','confirmed'),('đang giao','shipping'),
                ('đã giao','delivered'),('đã hủy','cancelled')]
    for i in range(1,101):
        number = (i-1)%10+1
        month = f'2025-{number:02}'
        sku = f'QA-{i:03}'
        start = intros[(i-1)//10]
        phrase,status = statuses[(i-1)//2%5]
        day = 'hôm nay' if i % 2 else 'hôm qua'
        suffix = intros[(i-1)%10].lower()
        yield 'giá', f'{start} giá bán SKU {sku}.', 'lookup_products', {'query':sku}, 'Manager', 100_000+i*1_000
        yield 'tồn kho', f'{start} sản phẩm {sku} còn bao nhiêu trong kho?', 'get_inventory_status', {'query':sku}, 'Employee', i
        yield 'đơn theo ngày', f'{start} có bao nhiêu đơn {phrase} {day}? {suffix}.', 'query_shop_orders', {'query':'today','month':'2025-05'}, 'Manager', (status,i%2)
        yield 'đơn theo mã', f'{start} tình trạng và giá trị đơn NOVA-{i}.', 'query_shop_orders', {'query':f'NOVA-{i}'}, 'Manager', i
        yield 'doanh thu', f'{start} doanh thu tháng {month}.', 'query_sales', {'month':month}, 'Manager', number*1_000_000
        yield 'lãi lỗ', f'{start} kết quả vận hành tháng {month} có bao gồm chi phí chưa?', 'query_financial_summary', {'month':month}, 'Manager', number*300_000 if number%2 else None
        kind = 'word' if i % 2 else 'excel'
        yield 'Word/Excel', f'{start} và tạo file {kind} tài chính tháng {month}.', f'create_{kind}_file', {'month':month,'source':'finance'}, 'Manager', kind
        yield 'kho tri thức', f'{start} quy trình nghỉ phép năm và nguồn tài liệu. {suffix}.', 'search_internal_documents', {'query':'chính sách nghỉ phép năm'}, 'Employee', None
        yield 'email nháp', f'{start} và soạn email cho nhân viên. Tiêu đề: Kiểm thử {i}. Nội dung: Lịch họp tuần tới.', 'prepare_employee_email', {'subject':f'Kiểm thử {i}','body_text':'Lịch họp tuần tới.'}, 'Manager', None
        yield 'phân quyền', f'{start} doanh thu tháng {month} bằng vai trò nhân viên.', 'query_sales', {'month':month}, 'Employee', None


def check(db,wf,case,document_id,orders,live):
    group, _, tool, args, _, expected = case
    steps = list(db.scalars(select(m.WorkflowStep).where(m.WorkflowStep.workflow_id==wf.id)))
    if group=='phân quyền':
        rejected = wf.status=='failed' and 'quyền' in (wf.error or '') and not steps
        clarified = wf.status=='completed' and not steps and wf.result.get('clarification')
        assert rejected or (live and clarified), 'Quyền đọc doanh thu chưa được kiểm tra đúng'
        return
    assert wf.status=='completed', wf.error or wf.status
    step = next((s for s in steps if s.tool==tool and s.status=='completed'),None)
    assert step, f'Thiếu bước {tool}'
    out = step.output
    assert wf.result.get('business_analysis',{}).get('status')=='completed', wf.result.get('business_analysis',{}).get('reason','Thiếu câu trả lời AI')
    if group=='giá':
        assert [(p['sku'],p['price']) for p in out['products']]==[(args['query'],expected)], 'Sai giá hoặc SKU'
    elif group=='tồn kho':
        assert [(p['sku'],p['quantity']) for p in out['rows']]==[(args['query'],expected)], 'Sai tồn kho'
    elif group=='đơn theo ngày':
        status,today = expected
        date = (m.now().astimezone(TZ).date()-timedelta(days=not today)).isoformat()
        expected_count = sum(o['status']==status and o['created_at'].startswith(date) for o in orders)
        assert out['date']==date and out['order_status']==status and out['created_order_count']==expected_count, 'Sai ngày, trạng thái hoặc tổng đơn'
    elif group=='đơn theo mã':
        assert [r['order_number'] for r in out['rows']]==[f'NOVA-{expected}'], 'Sai mã đơn'
    elif group=='doanh thu':
        assert out['month']==args['month'] and out['total']==expected, 'Sai doanh thu theo kỳ'
    elif group=='lãi lỗ':
        assert out['month']==args['month'] and out['operating_profit']==expected, 'Sai lợi nhuận hoặc cờ thiếu chi phí'
    elif group=='Word/Excel':
        file = db.scalar(select(m.GeneratedFile).where(m.GeneratedFile.workflow_id==wf.id))
        assert file and file.kind==('docx' if expected=='word' else 'xlsx') and file.content.startswith(b'PK') and file.source['month']==args['month'], 'Sai định dạng hoặc kỳ báo cáo'
    elif group=='kho tri thức':
        assert any(s['document_id']==document_id for s in out['sources']), 'Không tìm được đúng tài liệu'
    elif group=='email nháp':
        draft = db.get(m.MailCampaign,out['campaign_id'])
        assert draft.status=='draft', 'Email phải ở trạng thái nháp'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--live',type=int,default=0,help='Number of representative prompts using configured real model')
    parser.add_argument('--offset',type=int,default=0)
    args = parser.parse_args()
    if settings.database_url!='sqlite://' or settings.agent_database_url:
        raise SystemExit('Use a fresh sqlite:// database without AGENT_DATABASE_URL')
    settings.demo_mode = False
    settings.embedding_provider = 'lexical'
    cases = list(scenarios())
    assert len(cases)==len({c[1] for c in cases})==1000
    indexed = list(enumerate(cases,1))
    if args.live:
        indexed = indexed[args.offset:args.offset+args.live]
    else:
        settings.provider = 'openai_compatible'
        settings.ai_base_url = 'https://qa-model.example/v1'
        settings.ai_api_key = type(settings.ai_api_key)('test-only')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    progress_path = args.output.with_suffix('.jsonl')
    progress_path.write_text('',encoding='utf-8')
    Base.metadata.create_all(engine)
    results = []
    native_client = httpx.Client
    with Session() as db:
        users, document_id, orders = seed(db)
        for case_id,case in indexed:
            group,request,tool,arguments,role,_ = case
            def model_reply(req):
                payload = json.loads(req.content)
                context = json.loads(payload['messages'][1]['content'])['context']
                if 'evidence' in context:
                    content = {'steps':[], 'clarification':'Kết quả được đối chiếu với nguồn kiểm thử.'}
                else:
                    content = {'steps':[{'tool':tool,'arguments':arguments,'label':'Kiểm thử nghiệp vụ'}]}
                return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)},'finish_reason':'stop'}],'usage':{'total_tokens':32}})

            def nova_reply(req):
                page = int(req.url.params.get('page','1'))
                size = int(req.url.params.get('page_size','100'))
                return httpx.Response(200,json={'total':len(orders),'items':orders[(page-1)*size:page*size]})

            def transport(req):
                if req.url.host=='nova-commerce-neon.vercel.app':
                    return nova_reply(req)
                if not args.live and req.url.host=='qa-model.example':
                    return model_reply(req)
                raise AssertionError('Unexpected external endpoint: '+str(req.url.host))

            def client(*values,**options):
                if args.live and options.get('base_url') != 'https://nova-commerce-neon.vercel.app':
                    return native_client(*values,**options)
                return native_client(*values,transport=httpx.MockTransport(transport),**options)

            user = users[role]
            conv = m.Conversation(user_id=user.id,title='Kiểm thử cô lập',context={'month':'2025-05'} if group=='đơn theo ngày' else {})
            db.add(conv)
            db.flush()
            wf = m.Workflow(user_id=user.id,conversation_id=conv.id,request=request,idempotency_key=str(uuid4()))
            db.add(wf)
            db.commit()
            start = perf_counter()
            error = ''
            with patch('httpx.Client', client):
                try:
                    process(db,wf)
                    check(db,wf,case,document_id,orders,args.live)
                except AssertionError as exc:
                    error=str(exc) or 'Kết quả khác giá trị kỳ vọng'
            analysis = wf.result.get('business_analysis') or {}
            provider_error = analysis.get('reason') or wf.error or ''
            results.append(dict(id=case_id,group=group,question=request,workflow_status=wf.status,
                                tool=','.join(s['tool'] for s in wf.plan),passed=not error,
                                seconds=round(perf_counter()-start,3),tokens=wf.tokens,reason=error,
                                workflow_error=provider_error))
            with progress_path.open('a',encoding='utf-8') as progress:
                progress.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
            if args.live or len(results)%100==0:
                print(f'{len(results)}/{len(indexed)} checked, {sum(r["passed"] for r in results)} passed',flush=True)
            limits = ('HTTP 429', 'HTTP 401', 'HTTP 403', 'HTTP 404', 'token budget', 'Chưa cấu hình')
            if args.live and any(reason in provider_error or reason in error for reason in limits):
                break
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    stats = {group:dict(Counter('pass' if r['passed'] else 'fail' for r in results if r['group']==group)) for group in dict.fromkeys(r['group'] for r in results)}
    times=sorted(r['seconds'] for r in results)
    summary={'mode':'real model with synthetic business sources' if args.live else 'mock model and shop API, real workflow and SQLite',
             'model':settings.ai_model if args.live else None,
             'planned':len(indexed),'run':len(results),'passed':sum(r['passed'] for r in results),
             'p50_seconds':times[math.ceil(len(times)*.5)-1],'p95_seconds':times[math.ceil(len(times)*.95)-1],
             'groups':stats,'failures':dict(Counter(r['reason'] for r in results if not r['passed']))}
    args.output.with_suffix('.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
