"""Read-only, receipt-based breakdown of tools; never invent separate tool calls."""
from collections import Counter
from sqlalchemy import select
from . import models as m
from .permissions import permissions

MAIL={'prepare_report_email','prepare_revenue_email','prepare_employee_email','open_employee_email'}

def execution_graph(db,user,wf,steps):
    if wf.result.get('conversation_deleted') or wf.result.get('mock_data_removed'):
        return {'stages':[],'tool_count':0,'basis':'saved_results'}
    stages=[]
    def add(id,label,status,description='',position=None,href=None,basis='tool_result'):
        stages.append({'id':id,'label':label,'status':status,'description':description,'tool_position':position,'href':href,'basis':basis})
    if wf.result.get('execution_mode')=='llm_agent':
        state='completed' if wf.plan or wf.result.get('clarification') else ('failed' if wf.status=='failed' else 'cancelled' if wf.status=='cancelled' else 'running')
        add('planning','AI phân tích yêu cầu và lập kế hoạch',state,'Kế hoạch do model tạo; các giai đoạn bên dưới được đối chiếu từ kết quả công cụ.',basis='workflow')
    by_position={s.position:s for s in steps}
    for i,plan in enumerate(wf.plan):
        tool=plan['tool'];record=by_position.get(i);status=record.status if record else 'queued';output=record.output if record else {}
        prefix='tool-'+str(i)
        # Without a successful receipt the exact internal phase is unknown.
        if status!='completed':
            add(prefix,plan.get('label') or tool,status,'Chưa có kết quả hoàn tất để xác nhận từng giai đoạn nội bộ.',i);continue
        if tool in MAIL:
            campaign=db.get(m.MailCampaign,output.get('campaign_id')) if output.get('campaign_id') else None
            if not campaign or campaign.user_id!=wf.user_id or campaign.workspace_id!=user.workspace_id:
                add(prefix,plan.get('label') or tool,'completed','Công cụ đã hoàn tất; không có bản email trong phạm vi được xem.',i);continue
            href='/mail/campaigns/'+campaign.id if campaign.user_id==user.id and 'mail.send' in permissions(db,user) else None
            if tool=='open_employee_email':
                labels=['Tìm email trong hội thoại','Đọc trạng thái và tệp của email đã có']
            elif tool=='prepare_report_email':
                labels=['Kiểm tra quyền và kỳ báo cáo','Tìm báo cáo Word hoặc Excel trong hội thoại','Kiểm tra tệp đính kèm','Kiểm tra danh sách người nhận','Lưu bản nháp email vào database']
            elif tool=='prepare_revenue_email':
                labels=['Kiểm tra quyền đọc doanh thu','Tổng hợp doanh thu theo tháng','Chuẩn bị nội dung email','Kiểm tra danh sách người nhận','Lưu bản nháp email vào database']
            else:
                labels=['Kiểm tra nội dung và quyền gửi','Kiểm tra danh sách người nhận','Kiểm tra tệp đính kèm','Lưu bản nháp email vào database']
            deliveries=list(db.scalars(select(m.MailDelivery.status).where(m.MailDelivery.campaign_id==campaign.id)))
            counts=Counter(deliveries);total=len(deliveries)
            for j,label in enumerate(labels):
                detail='Được xác nhận từ kết quả công cụ và bản email đã lưu.'
                if 'tệp' in label.lower():detail=f'{len(campaign.attachment_ids or [])} tệp gắn với bản email; tái sử dụng tệp đã có, không tạo lại.'
                if 'người nhận' in label:detail=f'{total} người nhận trong đợt thư; bỏ qua {len(campaign.skipped or [])} địa chỉ không phù hợp hoặc trùng.'
                add(prefix+'-'+str(j),label,'completed',detail,i)
            approved=bool(campaign.approved_at)
            review='completed' if approved else 'cancelled' if campaign.status=='cancelled' else 'failed' if campaign.status=='failed' else 'waiting_approval'
            add(prefix+'-review','Người dùng xác nhận nội dung và người nhận',review,'Chỉ người dùng mới xác nhận gửi trên trang email; AI không tự xác nhận.',i,href,basis='live_email')
            if campaign.status=='draft':send='queued'
            elif campaign.status=='queued':send='queued'
            elif campaign.status=='sending':send='running'
            elif campaign.status=='cancelled':send='cancelled'
            elif campaign.status=='completed':send='completed' if total and counts['sent']==total else 'failed'
            else:send='failed'
            detail=(f"{counts['sent']}/{total} thư được Gmail chấp nhận; {counts['failed']} lỗi, {counts['unknown']} chưa xác định." if campaign.status not in ('draft','queued') else 'Chỉ bắt đầu sau khi bạn xác nhận. Tạo bản nháp không có nghĩa là đã gửi thư.')
            add(prefix+'-send','Gửi email qua Gmail và lưu kết quả',send,detail,i,href,basis='live_email')
        elif tool in ('create_word_file','create_excel_file'):
            kind='Word' if tool=='create_word_file' else 'Excel'
            source=(plan.get('arguments') or {}).get('source')
            labels=['Kiểm tra quyền và nguồn dữ liệu','Chuẩn bị nội dung được yêu cầu' if source=='custom' else 'Đọc dữ liệu nguồn được cấp quyền','Tạo tệp '+kind,'Lưu tệp và trả liên kết tải']
            for j,label in enumerate(labels):add(prefix+'-'+str(j),label,'completed','Đối chiếu từ biên nhận tạo tệp của công cụ; không phải một lượt gọi AI riêng.',i)
        elif tool=='search_internal_documents':
            for j,label in enumerate(['Kiểm tra phạm vi tài liệu','Tìm các đoạn nội dung liên quan','Trả kết quả và nguồn trích dẫn']):
                add(prefix+'-'+str(j),label,'completed',f"{len(output.get('sources',[]))} đoạn tài liệu được trả về; không tự bổ sung nội dung ngoài nguồn.",i)
        elif tool in ('query_financial_summary','query_sales','compare_revenue_periods','query_declining_products','get_inventory_status','lookup_products','generate_business_report','get_company_profile'):
            query_label='Đọc hồ sơ doanh nghiệp' if tool=='get_company_profile' else 'Truy vấn dữ liệu được cấp quyền'
            for j,label in enumerate(['Kiểm tra quyền và tham số truy vấn',query_label,'Tổng hợp và lưu kết quả công cụ']):add(prefix+'-'+str(j),label,'completed','Giai đoạn được đối chiếu từ kết quả đã lưu trong lượt chạy.',i)
        else:add(prefix,plan.get('label') or tool,'completed','Kết quả công cụ đã được lưu.',i)
    analysis=wf.result.get('business_analysis')
    if analysis:
        add('analysis','AI tổng hợp câu trả lời','completed' if analysis.get('status')=='completed' else 'failed',('Câu trả lời được tổng hợp từ kết quả công cụ.' if analysis.get('status')=='completed' else analysis.get('reason','Chưa có câu trả lời AI hoàn chỉnh.')),basis='workflow')
    # Email confirmation and delivery happen after the Agent has drafted its reply.
    followups=[s for s in stages if s['basis']=='live_email']
    stages=[s for s in stages if s['basis']!='live_email']+followups
    return {'stages':stages,'tool_count':len(wf.plan),'basis':'saved_results','note':'Các giai đoạn được đối chiếu từ kết quả đã lưu, không phải các lần gọi công cụ riêng. Trạng thái xác nhận và gửi thư được cập nhật từ đợt email.'}
