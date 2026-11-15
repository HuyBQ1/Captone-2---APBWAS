import {test,expect} from '@playwright/test';

test('mail command reuses generated report attachments and opens preview without sending',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.goto('/workspace');const input=page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'});
 await input.fill('Tạo Word và Excel báo cáo doanh thu tháng 7 năm 2026');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();await expect(page.locator('.chat-file')).toHaveCount(2,{timeout:30000});
 await input.fill('gửi mail về file báo cáo này cho toàn bộ nhân viên');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();
 const link=page.getByRole('link',{name:/^Mở bản nháp email/});await expect(link).toBeVisible({timeout:30000});await link.click();
 const attachments=page.getByRole('region',{name:'Tệp đính kèm email'});await expect(attachments).toContainText('2026');await expect(attachments.getByRole('button',{name:'Xem trước tệp',exact:true})).toHaveCount(2);
 await expect(page.locator('main')).toContainText('Bản nháp');await attachments.getByRole('button',{name:'Xem trước tệp',exact:true}).first().click();await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByRole('button',{name:'Đóng hộp thoại',exact:true}).click();await expect(page.getByRole('button',{name:'Xác nhận gửi ngay',exact:true})).toHaveCount(0);
});

test('selected file Agent adds Excel to the existing report then drafts its email',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 const identity=await (await page.request.get('/api/auth/me')).json();const name='Tệp và email E2E '+Date.now();
 const created=await page.request.post('/api/agents',{data:{name,description:'Kiểm thử tạo tệp và soạn email',visibility:'private',config:{model:identity.model,tools:['create_word_file','create_excel_file','prepare_report_email','open_employee_email'],permissions:['agents.run','sales.read','inventory.read','mail.send']}}});expect(created.status()).toBe(201);const agent=await created.json();
 expect((await page.request.post('/api/agents/'+agent.id+'/publish',{data:{revision:1}})).ok()).toBe(true);
 await page.goto('/workspace');const input=page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'});await input.fill('/'+name);await page.getByRole('option',{name:new RegExp(name)}).click();
 await input.fill('Tạo Word báo cáo doanh thu tháng 7 năm 2026');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();await expect(page.locator('.chat-file')).toHaveCount(1,{timeout:30000});
 await input.fill('cho tôi thêm file exel');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();await expect(page.locator('.chat-file')).toHaveCount(2,{timeout:30000});await expect(page.getByRole('link',{name:'Tải Excel',exact:true})).toBeVisible();
 await input.fill('Gửi mail file báo cáo tháng 7 cho toàn bộ nhân viên.');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();const link=page.getByRole('link',{name:/^Mở bản nháp email/});await expect(link).toBeVisible({timeout:30000});await link.click();
 await expect(page.getByRole('region',{name:'Tệp đính kèm email'}).getByRole('button',{name:'Xem trước tệp',exact:true})).toHaveCount(2);await expect(page.locator('main')).toContainText('Bản nháp');
});
