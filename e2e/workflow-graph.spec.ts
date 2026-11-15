import {test,expect} from '@playwright/test';

test('one saved email tool displays its phases and waits for manual sending',async({page})=>{
 let mutations=0;
 const labels=['AI phân tích yêu cầu và lập kế hoạch','Kiểm tra quyền và kỳ báo cáo','Tìm báo cáo Word hoặc Excel trong hội thoại','Kiểm tra tệp đính kèm','Kiểm tra danh sách người nhận','Lưu bản nháp email vào database','AI tổng hợp câu trả lời','Người dùng xác nhận nội dung và người nhận','Gửi email qua Gmail và lưu kết quả'];
 const stages=labels.map((label,i)=>({id:'stage-'+i,label,status:i===7?'waiting_approval':i===8?'queued':'completed',description:i===8?'Chỉ bắt đầu sau khi bạn xác nhận.':'Được đối chiếu từ kết quả công cụ đã lưu.',basis:i>6?'live_email':'tool_result',href:i>6?'/mail/campaigns/mail-ui':null}));
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()!=='GET')mutations++;
  if(path==='/api/auth/me')return route.fulfill({json:{id:'manager-ui',name:'Manager',email:'manager@company.vn',role:'Manager',permissions:['agents.run','inventory.read','mail.send'],must_change_password:false,preferences:{theme:'dark'}}});
  if(path==='/api/workflows/graph-ui')return route.fulfill({json:{id:'graph-ui',request:'Soạn email báo cáo tháng 01/2026 kèm file Excel',status:'completed',created_at:'2026-11-08T06:00:00Z',tokens:100,duration_ms:2000,checkpoint:1,plan:[{tool:'prepare_report_email',label:'Soạn email kèm Excel'}],steps:[{position:0,status:'completed'}],tools:[],events:[],result:{summary:'Đã tạo bản nháp, chưa gửi thư.'},execution_graph:{tool_count:1,stages,note:'Các giai đoạn được đối chiếu từ kết quả đã lưu, không phải các lần gọi công cụ riêng.'}}});
  if(path==='/api/company')return route.fulfill({json:{name:'Nova Commerce'}});
  return route.fulfill({json:{items:[],unread:0,total:0}});
 });
 await page.setViewportSize({width:1440,height:1080});
 await page.goto('/workflows/graph-ui');
 await expect(page.locator('.react-flow__node')).toHaveCount(9);
 await expect(page.locator('.react-flow__edge')).toHaveCount(8);
 await expect(page.locator('.workflow-graph .card-head')).toContainText('1 công cụ · 9 giai đoạn');
 await expect(page.locator('.workflow-stage-canvas')).toContainText('Chờ bạn xác nhận');
 await page.screenshot({path:'.test-tmp/workflow-stages-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await expect(page.locator('.stage-mobile-list')).toBeVisible();
 await expect(page.locator('.stage-mobile-list li')).toHaveCount(9);
 await expect(page.locator('.stage-mobile-list')).toContainText('Chưa gửi');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/workflow-stages-mobile.png',fullPage:true});
 expect(mutations).toBe(0);
});
