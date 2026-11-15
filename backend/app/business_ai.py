"""Ground the language model in authorized tool results, never a database credential."""
import json,math,re,time
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import defer
from . import models as m
from .config import settings
from .permissions import require
from .agent_runtime import assert_tool
from .provider import connected_plan,ProviderError

READS={'query_financial_summary','query_sales','compare_revenue_periods','query_declining_products','get_inventory_status','lookup_products','generate_business_report'}
FIELDS={'month','as_of','synthetic_finance','revenue','sale_lines','units_sold','known_orders','unassigned_order_lines','order_count','missing_cost_lines','known_cost','cost_of_goods','gross_profit','expenses','expenses_confirmed','operating_profit','margin','stock_units','out_of_stock','low_stock','basis','total','previous_total','change_percent','source','truncated','rows'}
ROW_FIELDS={'sku','name','category','quantity','threshold','price','revenue','previous_revenue','change_percent'}
FIELDS.update({'average_order_value','average_unit_revenue','gross_margin_percent','operating_margin_percent','expense_ratio_percent'})
FIELDS.update({'created_order_count','synced_at'})
FIELDS.add('unfinished_order_count')
FIELDS.update({'date','order_status','live_source'})
READS.add('query_shop_orders');FIELDS.add('order_status_counts');ROW_FIELDS.update({'order_number','date','status','payment_status','total','units'})

def collect(db,user,wf):
    from .tools import REGISTRY
    from .office_files import check_access
    evidence=[];order_groups={}
    count_only=bool(re.search(r'bao nhiêu|số (?:lượng )?đơn|how many|\bcount\b',wf.request,re.I))
    for record in db.scalars(select(m.WorkflowStep).where(m.WorkflowStep.workflow_id==wf.id,m.WorkflowStep.status=='completed').order_by(m.WorkflowStep.position)):
        if record.tool=='get_company_profile':
            assert_tool(db,user,wf,record.tool);require(db,user,'agents.run')
            if record.output.get('workspace_id')!=user.workspace_id:raise HTTPException(403,'Workspace đã thay đổi trước khi tổng hợp hồ sơ.')
            if record.output.get('categories'):require(db,user,'inventory.read')
            evidence.append({'tool':record.tool,'data':{k:record.output[k] for k in ('company_profile','categories','sample_data','source') if k in record.output}})
        elif record.tool=='search_internal_documents':
            from .retrieval import allowed_scopes
            assert_tool(db,user,wf,record.tool);require(db,user,'documents.read')
            sources=[]
            for item in record.output.get('sources',[])[:5]:
                doc=db.get(m.Document,item['document_id'],populate_existing=True)
                if not doc or doc.workspace_id!=user.workspace_id or doc.scope not in allowed_scopes(user) or doc.status!='indexed':
                    raise HTTPException(403,'Quyền đọc tài liệu đã thay đổi trước khi tổng hợp.')
                if wf.agent_id and doc.id not in wf.agent_snapshot.get('knowledge_ids',[]):
                    raise HTTPException(403,'Tài liệu không thuộc kho tri thức của Agent.')
                sources.append({'name':doc.name,'content':str(item.get('content',''))[:1400],'page':item.get('page'),'truncated':len(str(item.get('content','')))>1400})
            evidence.append({'tool':record.tool,'data':{'sources':sources,'matched_chunks':len(sources),'no_matches':not sources}})
        elif record.tool in READS:
            assert_tool(db,user,wf,record.tool);require(db,user,REGISTRY[record.tool]['permission'])
            if record.tool=='query_financial_summary':require(db,user,'inventory.read')
            output={k:v for k,v in record.output.items() if k in FIELDS}
            if record.tool=='query_shop_orders':
                args=wf.plan[record.position].get('arguments',{}) if wf.plan and record.position<len(wf.plan) else {}
                status=args.get('query')
                if status in ('pending','confirmed','shipping') and record.output.get('synced_at'):
                    group=order_groups.setdefault((args.get('month'),record.output['synced_at']),{})
                    group[status]=record.output['created_order_count']
                if count_only:
                    output.pop('rows',None)
                    output['details_omitted']=True
            if 'rows' in output:output['rows']=[{k:v for k,v in row.items() if k in ROW_FIELDS} for row in output['rows'][:20]]
            if record.tool=='lookup_products':output['products']=[{k:v for k,v in row.items() if k in ROW_FIELDS} for row in record.output.get('products',[])[:20]]
            if 'rows' in output:output['returned_rows']=len(output['rows'])
            if 'products' in output:output['returned_products']=len(output['products'])
            evidence.append({'tool':record.tool,'data':output})
        elif record.tool in ('create_word_file','create_excel_file'):
            assert_tool(db,user,wf,record.tool)
            files=db.scalars(select(m.GeneratedFile).options(defer(m.GeneratedFile.content)).where(m.GeneratedFile.workflow_id==wf.id,m.GeneratedFile.user_id==user.id,m.GeneratedFile.workspace_id==user.workspace_id))
            for f in files:
                check_access(db,user,f)
                if f.source.get('metrics'):
                    item={'tool':'file_financial_snapshot','data':{k:v for k,v in f.source['metrics'].items() if k in FIELDS}}
                    if item not in evidence:evidence.append(item)
                receipt={'tool':'created_file','data':{'filename':f.filename,'kind':f.kind,'status':'created'}}
                if receipt not in evidence:evidence.append(receipt)
        elif record.tool in ('prepare_report_email','prepare_revenue_email','prepare_employee_email','open_employee_email'):
            assert_tool(db,user,wf,record.tool);require(db,user,'mail.send')
            c=db.get(m.MailCampaign,record.output.get('campaign_id')) if record.output.get('campaign_id') else None
            if c and (c.user_id!=user.id or c.workspace_id!=user.workspace_id):raise HTTPException(403,'Email không thuộc workspace của bạn.')
            data={'mail_status':c.status if c else 'not_found','subject':c.subject if c else '', 'recipient_count':db.scalar(select(func.count()).select_from(m.MailDelivery).where(m.MailDelivery.campaign_id==c.id)) if c else 0,'attachment_count':len(c.attachment_ids or []) if c else 0}
            evidence.append({'tool':record.tool,'data':data})
    for (month,synced_at),counts in order_groups.items():
        if set(counts)=={'pending','confirmed','shipping'}:
            evidence.append({'tool':'query_shop_orders','data':{'month':month,'synced_at':synced_at,'unfinished_order_count':sum(counts.values()),'order_status_counts':counts,'basis':'Tổng backend của ba trạng thái không trùng nhau: pending, confirmed, shipping. Không gồm đơn đã giao, hủy hoặc hoàn.'}})
    return evidence

def grounded_context(evidence):
    values={};texts={};document_numbers={}
    def verified(text):
        if text not in texts:
            key='t'+str(len(texts));texts[text]=key;values[key]=text
    def walk(value,field=None):
        if isinstance(value,dict):return {k:walk(v,k) for k,v in value.items()}
        if isinstance(value,list):return [walk(v,field) for v in value]
        if isinstance(value,bool) or value is None:return value
        if isinstance(value,(int,float)):
            if not math.isfinite(value):raise ValueError('Chỉ tiêu không hữu hạn.')
            key='v'+str(len(values));values[key]=value
            return {'value':value,'reference':'{{'+key+'}}'}
        text=str(value)[:1000]
        if field in {'as_of','date','synced_at'}:
            try:source_date=datetime.fromisoformat(text.replace('Z','+00:00'))
            except ValueError:pass
            else:
                if source_date.tzinfo:text=source_date.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()
        if field=='content':
            for number in re.findall(r'(?<![\w])\d+(?:[.,]\d+)*(?![\w])',text):
                if number not in document_numbers and len(document_numbers)<60:
                    key='d'+str(len(document_numbers));document_numbers[number]=key;values[key]=number
        if field=='name':
            for code in re.findall(r'(?<![\w-])[A-Z]{2,8}(?:-[A-Z]{1,8})?-\d{2,8}(?![\w-])',text):
                if code not in texts:
                    key='t'+str(len(texts));texts[code]=key;values[key]=code
        if field in {'sku','month','as_of','name','category','email','phone','address','tax_code','filename','subject','order_number','date','synced_at'} and re.search(r'\d',text) and len(text)<=300 and not re.search(r'https?://|[\[\]{}<>`\n\r]',text):
            verified(text)
            # Date display alternatives are derived by the backend from the
            # exact source timestamp, never admitted as arbitrary digits.
            if field in {'as_of','date','synced_at'}:
                try:date=datetime.fromisoformat(text.replace('Z','+00:00'))
                except ValueError:pass
                else:
                    local=date.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')) if date.tzinfo else date
                    verified(local.strftime('%Y-%m-%d'));verified(local.strftime('%d/%m/%Y'))
                    verified(local.strftime('%d/%m/%Y %H:%M'));verified(local.strftime('%H:%M %d/%m/%Y'))
        return text
    data=walk(evidence)
    return {'evidence':data,'values':values,'verified_texts':[{ 'text':text,'reference':'{{'+key+'}}'} for text,key in texts.items()],'document_references':[{'text':text,'reference':'{{'+key+'}}'} for text,key in document_numbers.items()]}

def render_answer(text,values,files_created=False,allow_prose=False,citation_count=0):
    if not text or len(text)>12000:raise ProviderError('AI chưa trả lời phân tích hợp lệ.')
    if files_created and re.search(r'(?:chưa|không).{0,40}tạo.{0,15}(?:tệp|file)|(?:xác nhận).{0,35}tạo.{0,15}(?:tệp|file)',text,re.I):
        raise ProviderError('Phần diễn giải AI mô tả sai trạng thái tệp; các tệp đã tạo vẫn được giữ nguyên.')
    def replace(match):
        key=match[1]
        if key not in values:raise ProviderError('AI dẫn chỉ tiêu không tồn tại.')
        value=values[key]
        if isinstance(value,str):return re.sub(r'([\\`*_\[\]{}<>])',r'\\\1',value)
        return f'{value:,}'.replace(',','.') if isinstance(value,int) else f'{value:,.2f}'.translate(str.maketrans({',':'.','.':','}))
    # Reject invented numeric claims before inserting database values.
    without=re.sub(r'\{\{([vtd]\d+)\}\}','',text)
    # Markdown list ordinals and valid source labels are formatting, not business facts.
    without=re.sub(r'(?m)^[ \t]{0,3}(?:[1-9]|1\d|20)[.)][ \t]+','',without)
    without=re.sub(r'\[(\d{1,2})\]',lambda match:'' if 1<=int(match[1])<=citation_count else match[0],without)
    if re.search(r'https?://|\]\(',without):raise ProviderError('Phần diễn giải AI chứa liên kết chưa được cho phép; kết quả công cụ vẫn được giữ nguyên.')
    # Entity names/codes/dates from the authorized evidence are not invented numbers.
    for literal in sorted({v for k,v in values.items() if k.startswith('t') and isinstance(v,str)},key=len,reverse=True):
        without=re.sub(r'(?<![\w.-])'+re.escape(literal)+r'(?![\w-]|\.\w)','',without)
    aliases=set()
    for key,value in values.items():
        if key.startswith('d') and isinstance(value,str):aliases.add(value)
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            aliases.add(str(value))
            aliases.add(f'{value:,}'.replace(',','.') if isinstance(value,int) else f'{value:,.2f}'.translate(str.maketrans({',':'.','.':','})))
    validated_numbers=[]
    def verify_number(match):
        if match[0] not in aliases:raise ProviderError('Phần diễn giải AI có số chưa đối chiếu được với nguồn; số liệu công cụ vẫn được giữ nguyên.')
        validated_numbers.append(match[0]);return ''
    without=re.sub(r'(?<![\w])[-+]?\d+(?:[.,]\d+)*(?![\w])',verify_number,without)
    if re.search(r'\d',without) or '{{' in without or '}}' in without:
        raise ProviderError('Phần diễn giải AI có số chưa đối chiếu được với nguồn; số liệu công cụ vẫn được giữ nguyên.')
    if not allow_prose and not re.search(r'\{\{[vtd]\d+\}\}',text) and not validated_numbers:raise ProviderError('AI chưa dẫn chỉ tiêu từ dữ liệu doanh nghiệp.')
    return re.sub(r'\{\{([vtd]\d+)\}\}',replace,text)

def validate_order_answer(text,evidence):
    for item in evidence:
        if item['tool']=='query_shop_orders' and item['data'].get('created_order_count',0)>0:
            if re.search(r'(?:không(?: có| ghi nhận| cho thấy)|chưa (?:có|ghi nhận)).{0,35}đơn(?: hàng| nào)',text,re.I):
                raise ProviderError('Công cụ đã có đơn tạo trong phạm vi này; không được kết luận không có đơn. Thời gian nguồn đã chuẩn hóa theo Asia/Ho_Chi_Minh.')
    return text

def analyze(db,user,wf,config,timeout):
    evidence=collect(db,user,wf)
    if settings.demo_mode or not evidence:return None,0
    context=grounded_context(evidence)
    context['files_created']=[{'filename':f['filename'],'kind':f['kind']} for f in (wf.result or {}).get('files',[])]
    if len(json.dumps(context,ensure_ascii=False))>20000:
        return {'status':'unavailable','reason':'Phạm vi dữ liệu quá lớn để diễn giải trong một lượt; hãy thu hẹp tháng hoặc sản phẩm.'},0
    started=time.monotonic()
    answer,tokens=connected_plan(wf.request,context,{},timeout=timeout,agent_config=config,purpose='business_answer')
    if answer.steps:return {'status':'unavailable','reason':'AI trả thao tác thay vì phân tích dữ liệu.'},tokens
    prose=all(e['tool'] in ('get_company_profile','search_internal_documents') for e in evidence)
    source_count=sum(len(e['data'].get('sources',[])) for e in evidence)
    try:text=validate_order_answer(render_answer(answer.clarification,context['values'],files_created=bool(context['files_created']),allow_prose=True,citation_count=source_count),evidence)
    except ProviderError as exc:
        remaining=timeout-(time.monotonic()-started)
        if remaining<4:return {'status':'unavailable','reason':str(exc)},tokens
        db.refresh(user);fresh=collect(db,user,wf)
        context=grounded_context(fresh);context['files_created']=[{'filename':f['filename'],'kind':f['kind']} for f in (wf.result or {}).get('files',[])]
        context['validation_feedback']=str(exc);context['previous_answer']=str(answer.clarification or '')[:2000]
        if len(json.dumps(context,ensure_ascii=False))>20000:return {'status':'unavailable','reason':str(exc)},tokens
        try:
            revised,used=connected_plan(wf.request,context,{},timeout=remaining,agent_config=config,purpose='business_answer');tokens+=used
            if revised.steps:raise ProviderError('AI chưa trả lời đúng dạng tổng hợp.')
            text=validate_order_answer(render_answer(revised.clarification,context['values'],files_created=bool(context['files_created']),allow_prose=True,citation_count=sum(len(e['data'].get('sources',[])) for e in fresh)),fresh)
        except ProviderError as retry_error:return {'status':'unavailable','reason':str(retry_error)},tokens
    return {'status':'completed','text':text,'answer_kind':'sourced_text' if prose else 'analysis','source':'Kết quả công cụ đọc database và tài liệu được cấp quyền.','evidence_tools':list(dict.fromkeys(e['tool'] for e in evidence))},tokens
