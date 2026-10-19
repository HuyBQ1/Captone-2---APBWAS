"""Measure the local HTTP/worker demo; never extrapolate to Connected Mode."""
import json,time,uuid
from pathlib import Path
import httpx

BASE='http://127.0.0.1:8000/api'
results=[]
with httpx.Client(base_url=BASE,timeout=40) as client:
    client.post('/auth/login',json={'email':'manager@apbwas.demo','password':'Demo@123456'}).raise_for_status()
    for request in ['Phân tích doanh thu tháng này và so sánh với tháng trước.','Kiểm tra sản phẩm sắp hết hàng.','Tóm tắt chính sách nghỉ phép và dẫn nguồn.','Tạo báo cáo doanh thu theo danh mục.']:
        start=time.perf_counter()
        response=client.post('/workflows',json={'request':request,'idempotency_key':str(uuid.uuid4())});response.raise_for_status()
        wf=response.json(); accepted=time.perf_counter()-start
        stream_start=time.perf_counter()
        with client.stream('GET','/workflows/'+wf['id']+'/events') as response:
            response.raise_for_status()
            first_byte=None;first_useful=None
            for line in response.iter_lines():
                if first_byte is None:first_byte=time.perf_counter()-stream_start
                if line.startswith('data: '):
                    event=json.loads(line[6:])
                    if first_useful is None and event['type']=='tool.completed':first_useful=time.perf_counter()-start
                    if event['type'] in ('completed','failed','cancelled'):break
        elapsed=time.perf_counter()-start
        final=client.get('/workflows/'+wf['id']).json()
        results.append({'request':request,'status':final['status'],'accept_seconds':round(accepted,3),'stream_first_byte_seconds':round(first_byte or 0,3),'first_useful_seconds':round(first_useful or 0,3),'complete_seconds':round(elapsed,3),'tool_calls':len(final['tools'])})
    retrieval=[]
    for q,expected in [('chính sách nghỉ phép','Chính sách nghỉ phép'),('ngưỡng cảnh báo tồn kho','Quy trình quản lý tồn kho'),('báo cáo doanh thu','Hướng dẫn báo cáo kinh doanh')]:
        started=time.perf_counter();response=client.get('/documents/search',params={'q':q});response.raise_for_status()
        retrieval.append({'query':q,'top5_contains_expected':any(expected in item['name'] for item in response.json()['items']),'seconds':round(time.perf_counter()-started,3)})
payload={'environment':'Windows local harness; SQLite test database; no Redis; demo hash embedding; no LLM API call','workflows':results,'retrieval':retrieval,'limitations':['Small fixed seed dataset only.','Not a 10,000 chunk pgvector benchmark.','No Connected Mode/provider latency claim.','No availability or concurrent PostgreSQL approval claim.']}
target=Path(__file__).resolve().parents[1]/'docs/evaluation.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(payload,ensure_ascii=False,indent=2))
