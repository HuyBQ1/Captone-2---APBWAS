import io,json,uuid,zipfile
from xml.etree import ElementTree as ET
import pytest
from docx import Document
from sqlalchemy import select,func
from conftest import login,create,execute
from app import models as m
from app.schemas import Plan,PlanStep,ToolArgs
from app.office_files import create_file,N
from app.office_math import cached_formulas

def prepared(client,factory,monkeypatch,tool,args):
    from app import workflows
    monkeypatch.setattr(workflows,'make_plan',lambda *a,**kw:(Plan(steps=[PlanStep(tool=tool,label='Create file',arguments=ToolArgs(**args))]),0))
    w=create(client,'Tạo tài liệu theo yêu cầu');execute(factory,w['id'])
    return client.get('/api/workflows/'+w['id']).json()

def test_finance_word_and_excel_are_real_durable_owned_outputs(env):
    client,factory,users,*_=env;login(client)
    w=create(client,'Tạo file Word và Excel báo cáo tài chính tháng này');execute(factory,w['id'])
    result=client.get('/api/workflows/'+w['id']).json();assert result['status']=='completed',result['error']
    files=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items'];assert {f['kind'] for f in files}=={'docx','xlsx'}
    assert len(result['result']['files'])==2
    for f in files:
        response=client.get(f['download_url']);assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
        assert response.content.startswith(b'PK') and len(response.content)==f['size']
        if f['kind']=='docx':
            text='\n'.join(p.text for p in Document(io.BytesIO(response.content)).paragraphs)
            assert '400.000' in text and 'Chưa đủ dữ liệu' in text
        else:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                assert root.find("s:sheetData/s:row/s:c[@r='B9']/s:v",N).text=='400000'
                assert root.find("s:sheetData/s:row/s:c[@r='B9']/s:f",N) is not None
    with factory() as db:
        a=db.scalar(select(m.GeneratedFile).where(m.GeneratedFile.kind=='docx'));wid=a.workflow_id;raw=a.content
        wf=db.get(m.Workflow,wid);again=create_file(db,db.get(m.User,users['Manager']),wf,wf.plan[0]['arguments'],'docx');db.commit()
        assert again['files'] and db.scalar(select(func.count()).select_from(m.GeneratedFile))==2 and db.get(m.GeneratedFile,a.id).content==raw
    login(client,'Admin');assert client.get(files[0]['download_url']).status_code==404

def test_custom_excel_formulas_are_cached_and_formula_like_text_stays_literal(env,monkeypatch):
    client,factory,*_=env;login(client)
    args={'source':'custom','title':'Dự toán','columns':['Hạng mục','Số lượng','Đơn giá','Thành tiền'],'rows':[['Bàn',2,100,None],['=WEBSERVICE("https://example.com")',3,50,None],['Tổng',None,None,None]],'formulas':[{'cell':'D2','expression':'=B2*C2'},{'cell':'D3','expression':'=B3*C3'},{'cell':'D4','expression':'=SUM(D2:D3)'}]}
    result=prepared(client,factory,monkeypatch,'create_excel_file',args);assert result['status']=='completed',result['error']
    response=client.get(result['result']['files'][0]['download_url'])
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert not any('externalLinks' in n or 'vbaProject' in n for n in z.namelist())
        root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        assert root.find("s:sheetData/s:row/s:c[@r='D4']/s:v",N).text=='350'
        literal=root.find("s:sheetData/s:row/s:c[@r='A3']",N);assert literal.attrib['t']=='inlineStr' and literal.find('s:f',N) is None
        assert 'WEBSERVICE' in ''.join(literal.itertext())

@pytest.mark.parametrize('formulas',[
 [{'cell':'B2','expression':'=WEBSERVICE(A2)'}],
 [{'cell':'B2','expression':'=SUM(Z2:Z99)'}],
 [{'cell':'B2','expression':'=B3'},{'cell':'B3','expression':'=B2'}],
 [{'cell':'B2','expression':'=1/0'}],
 [{'cell':'B2','expression':"='[external.xlsx]Sheet'!A2"}],
])
def test_unsafe_or_invalid_formulas_are_rejected(formulas):
    with pytest.raises(ValueError):cached_formulas(['A','B'],[[1,None],[2,None]],formulas)

def test_round_cache_matches_excel_half_away_from_zero():
    result=cached_formulas(['A','B'],[[1,None],[2,None]],[{'cell':'B2','expression':'=ROUND(2.5,0)'},{'cell':'B3','expression':'=ROUND(-2.5,0)'}])
    assert result['B2']['value']==3 and result['B3']['value']==-3

def test_explicit_word_content_is_preserved_through_connected_agent_plan(env,monkeypatch):
    from app.config import settings
    from app import agent
    client,factory,*_=env;login(client)
    monkeypatch.setattr(settings,'demo_mode',False)
    calls=[]
    def planner(request,context,registry,**kwargs):
        calls.append(request)
        return Plan(steps=[PlanStep(tool='create_word_file',label='Tạo Word',arguments=ToolArgs(source='custom',title='Thư nhắc báo cáo',body_text='Đề nghị chuẩn bị số liệu doanh thu cho cuộc họp lúc 9 giờ.'))]),11
    monkeypatch.setattr(agent,'connected_plan',planner)
    from app import business_ai
    monkeypatch.setattr(business_ai,'connected_plan',lambda *a,**kw:(Plan(steps=[],clarification='Đã chuẩn bị tệp Word theo nội dung bạn cung cấp.'),5))
    w=create(client,'Tạo file Word\nTiêu đề: Thư nhắc báo cáo\nNội dung: Đề nghị chuẩn bị số liệu doanh thu cho cuộc họp lúc 9 giờ.');execute(factory,w['id'])
    result=client.get('/api/workflows/'+w['id']).json();assert result['status']=='completed',result['error']
    raw=client.get(result['result']['files'][0]['download_url']).content
    assert 'Đề nghị chuẩn bị số liệu doanh thu' in '\n'.join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
    assert len(calls)==1 and result['tokens']==16 and result['result']['execution_mode']=='llm_agent'

def test_custom_word_preserves_vietnamese_and_can_be_downloaded_again(env,monkeypatch):
    client,factory,*_=env;login(client)
    result=prepared(client,factory,monkeypatch,'create_word_file',{'source':'custom','title':'Thông báo họp nội bộ','body_text':'## Lịch họp\nMời nhân viên tham dự lúc 9 giờ.\n- Chuẩn bị báo cáo công việc.'})
    assert result['status']=='completed',result['error']
    f=result['result']['files'][0];one=client.get(f['download_url']);two=client.get(f['download_url']);assert one.content==two.content
    doc=Document(io.BytesIO(one.content));assert doc.paragraphs[0].style.name=='Title'
    assert 'Thông báo họp nội bộ' in doc.paragraphs[0].text and any('9 giờ' in p.text for p in doc.paragraphs)

def test_business_source_and_download_recheck_permissions_and_workspace(env):
    client,factory,users,*_=env;login(client,'Employee')
    w=create(client,'Tạo Word báo cáo tài chính tháng này');execute(factory,w['id'])
    with factory() as db:assert db.get(m.Workflow,w['id']).status=='failed' and not list(db.scalars(select(m.GeneratedFile)))
    login(client);w=create(client,'Xuất file Excel tồn kho');execute(factory,w['id'])
    f=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items'][0]
    with factory() as db:
        role=db.get(m.Role,'Manager');role.permissions=[p for p in role.permissions if p!='inventory.read'];db.commit()
    assert client.get(f['download_url']).status_code==403
    with factory() as db:
        db.add(m.Workspace(id='foreign',name='Foreign'));db.commit();db.get(m.User,users['Manager']).workspace_id='foreign';db.commit()
    assert client.get(f['download_url']).status_code==404 and not client.get('/api/files').json()['items']

def test_file_agent_cannot_read_finance_outside_pinned_permissions(env):
    from test_agents import create_agent,body,start
    client,factory,*_=env;login(client)
    payload=body(['create_word_file']);payload['config']['permissions']=['agents.run']
    a=create_agent(client,payload);client.post('/api/agents/'+a['id']+'/publish',json={'revision':1})
    w=start(client,a,'Tạo Word báo cáo tài chính tháng này');execute(factory,w['id'])
    with factory() as db:
        wf=db.get(m.Workflow,w['id']);assert wf.status=='failed' and 'Agent thiếu quyền' in wf.error
        assert not list(db.scalars(select(m.GeneratedFile)))

def test_preview_word_and_excel_cached_results_and_sheet_navigation(env):
    client,factory,*_=env;login(client)
    w=create(client,'Tạo Word và Excel báo cáo tài chính tháng này');execute(factory,w['id'])
    files=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items']
    excel=next(f for f in files if f['kind']=='xlsx');word=next(f for f in files if f['kind']=='docx')
    response=client.get('/api/files/'+excel['id']+'/preview');assert response.status_code==200,response.text
    assert response.headers['cache-control']=='private, no-store'
    result=response.json();assert len(result['sheets'])==4 and result['sheets'][0]['name']=='TongHop'
    revenue=next(r for r in result['rows'] if r['number']==9)['cells'][1]
    assert revenue['value']==400000 and revenue['display']=='400.000' and revenue['formula'].startswith('=SUM(')
    sales=client.get('/api/files/'+excel['id']+'/preview?sheet=1&page_size=10').json()
    assert next(r for r in sales['rows'] if r['number']==6)['cells'][1]['display'].count('/')==2
    doc=client.get('/api/files/'+word['id']+'/preview').json()
    assert doc['kind']=='docx' and doc['blocks'][0]['style']=='Title'
    assert any('400.000' in b.get('text','') for b in doc['blocks'])
    assert client.get('/api/files/'+excel['id']+'/preview?sheet=999').status_code==422
    assert client.get('/api/files/'+excel['id']+'/preview?page=999').status_code==422
    assert client.get('/api/files/'+excel['id']+'/preview?page_size=100000').status_code==422
    login(client,'Admin');assert client.get('/api/files/'+excel['id']+'/preview').status_code==404

def test_preview_is_snapshot_and_rechecks_source_permissions(env):
    client,factory,users,pid=env;login(client)
    w=create(client,'Xuất Excel tồn kho');execute(factory,w['id'])
    f=client.get('/api/files?conversation_id='+w['conversation_id']).json()['items'][0]
    with factory() as db:db.get(m.Inventory,pid).quantity=777;db.commit()
    result=client.get('/api/files/'+f['id']+'/preview').json()
    assert next(r for r in result['rows'] if r['number']==2)['cells'][3]['value']==10
    with factory() as db:
        role=db.get(m.Role,'Manager');role.permissions=[p for p in role.permissions if p!='inventory.read'];db.commit()
    assert client.get('/api/files/'+f['id']+'/preview').status_code==403

def test_missing_formula_cache_is_not_misrepresented_as_zero():
    from app.office_files import workbook
    from app.office_preview import excel
    raw=workbook('Calculation',(['Total'],[[None]],[{'cell':'A2','expression':'=1+1'}]),{'type':'custom','as_of':'2026-11-05T00:00:00Z'})
    with zipfile.ZipFile(io.BytesIO(raw)) as z:parts={name:z.read(name) for name in z.namelist()}
    root=ET.fromstring(parts['xl/worksheets/sheet1.xml']);cell=root.find("s:sheetData/s:row/s:c[@r='A2']",N);cell.remove(cell.find('s:v',N));parts['xl/worksheets/sheet1.xml']=ET.tostring(root)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)
    preview=excel(out.getvalue());value=next(r for r in preview['rows'] if r['number']==2)['cells'][0]
    assert value['value'] is None and value['display']=='' and value['missing_cache'] and value['formula']=='=1+1'

@pytest.mark.parametrize('prompt,context,expected',[
 ('tạo báo cáo doanh thu tháng 8 bằng exel',{},'2026-08'),
 ('tạo báo cáo doanh thu tháng 8 bằng exel',{'month':'2026-11'},'2026-08'),
 ('Tạo Excel tháng 08',{'month':'2025-11'},'2025-08'),
 ('Tạo Excel tháng 8 năm 2024',{'month':'2026-11'},'2024-08'),
 ('Tạo Excel tháng 8 2024',{},'2024-08'),
 ('Tạo Excel 08/2024',{},'2024-08'),
 ('Tạo Excel 2024-08',{},'2024-08'),
 ('Tạo Excel tháng này',{'month':'2025-08'},'2026-11'),
 ('Tạo Excel tháng trước',{'month':'2025-08'},'2026-10'),
 ('Xuất lại Excel',{'month':'2025-08'},'2025-08'),
 ('tao bao cao thang 8 bang excel',{},'2026-08'),
])
def test_request_month_prioritizes_explicit_month_over_history_and_current(prompt,context,expected):
    from app.agent import request_month
    from datetime import datetime
    assert request_month(prompt,context,datetime(2026,11,5))==expected


def test_month_only_finance_request_uses_requested_month_in_published_agent(env,monkeypatch):
    from app.config import settings
    from app import agent
    from test_agents import create_agent,body,start
    client,factory,*_=env;login(client)
    monkeypatch.setattr(settings,'demo_mode',False)
    from app import business_ai
    monkeypatch.setattr(business_ai,'analyze',lambda *a,**kw:(None,0))
    calls=[]
    def planner(request,context,registry,**kwargs):
        calls.append(registry)
        return Plan(steps=[PlanStep(tool='create_excel_file',label='Tạo Excel',arguments=ToolArgs(source='finance',month=context['month']))]),17
    monkeypatch.setattr(agent,'connected_plan',planner)
    payload=body(['create_excel_file']);payload['config']['permissions']=['agents.run','inventory.read','sales.read']
    a=create_agent(client,payload)
    assert client.post('/api/agents/'+a['id']+'/publish',json={'revision':1}).status_code==200
    w=start(client,a,'tạo báo cáo doanh thu tháng 8 bằng exel');execute(factory,w['id'])
    result=client.get('/api/workflows/'+w['id']).json();assert result['status']=='completed',result['error']
    from datetime import datetime
    from zoneinfo import ZoneInfo
    expected=f"{datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).year}-08"
    assert result['plan'][0]['arguments']['month']==expected
    assert len(calls)==1 and set(calls[0])=={'create_excel_file'} and result['tokens']==17
    files=client.get('/api/files?conversation_id='+result['conversation_id']).json()['items']
    assert len(files)==1 and '08' in files[0]['title']
    with factory() as db:
        saved=db.get(m.GeneratedFile,files[0]['id']);assert saved.source['month']==expected
    preview=client.get('/api/files/'+files[0]['id']+'/preview').json()
    assert next(r for r in preview['rows'] if r['number']==3)['cells'][1]['display']==expected
