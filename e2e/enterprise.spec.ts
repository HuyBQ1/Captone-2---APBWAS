import {test,expect,Page} from '@playwright/test';
async function login(page:Page,role='Admin'){
 await page.goto('/login');await page.getByRole('button',{name:role,exact:true}).click();
 await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toContainText('AI Workspace');
}
test('invite employee, activate once, and persist personal profile',async({page,browser})=>{
 await login(page);await page.goto('/admin');await page.getByRole('button',{name:'Mời nhân viên',exact:true}).click();
 const dialog=page.getByRole('dialog'),email=`invite-${Date.now()}@company.test`;
 await dialog.getByLabel('Họ và tên').fill('Invited Employee');await dialog.getByLabel('Email',{exact:true}).fill(email);
 await dialog.getByRole('button',{name:'Tạo lời mời',exact:true}).click();
 const link=dialog.getByLabel('Liên kết riêng');await expect(link).toHaveValue(/reset-password#token=/);
 const url=await link.inputValue(),context=await browser.newContext(),staff=await context.newPage();
 await staff.goto(url);await staff.getByLabel('Mật khẩu mới',{exact:true}).fill('EmployeePassword@123');
 await staff.getByLabel('Xác nhận mật khẩu',{exact:true}).fill('EmployeePassword@123');await staff.getByRole('button',{name:'Lưu mật khẩu',exact:true}).click();
 await expect(staff.getByRole('heading',{name:'Đã thiết lập mật khẩu'})).toBeVisible();
 await staff.getByRole('link',{name:'Đăng nhập',exact:true}).click();
 await staff.getByLabel('Email',{exact:true}).fill(email);await staff.getByLabel('Mật khẩu',{exact:true}).fill('EmployeePassword@123');
 await staff.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(staff.locator('main h1')).toContainText('AI Workspace');
 await staff.goto(new URL('/account',url).href);await staff.getByLabel('Số điện thoại',{exact:true}).fill('0901234567');
 await staff.getByLabel('Phòng ban',{exact:true}).fill('Operations');await staff.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();
 await expect.poll(async()=> (await (await staff.request.get(new URL('/api/auth/me',url).href)).json()).phone).toBe('0901234567');
 await staff.reload();await expect(staff.getByLabel('Số điện thoại',{exact:true})).toHaveValue('0901234567');
 await expect(staff.getByRole('heading',{name:'Phiên đăng nhập',exact:true})).toBeVisible();
 await context.close();
});

test('temporary-password accounts must change password before opening business data',async({page,browser})=>{
 await login(page);const email=`temporary-${Date.now()}@company.test`;
 const created=await page.request.post('/api/admin/users',{data:{email,name:'Temporary Employee',role:'Employee',password:'TemporaryPassword@123'}});expect(created.ok()).toBeTruthy();
 const context=await browser.newContext({baseURL:new URL(page.url()).origin}),staff=await context.newPage();await staff.goto('/login');
 await staff.getByLabel('Email',{exact:true}).fill(email);await staff.getByLabel('Mật khẩu',{exact:true}).fill('TemporaryPassword@123');
 await staff.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(staff.getByRole('heading',{name:'Cài đặt tài khoản',exact:true})).toBeVisible();
 expect((await staff.request.get('/api/data/products')).status()).toBe(403);
 await staff.getByLabel('Mật khẩu hiện tại',{exact:true}).fill('TemporaryPassword@123');await staff.getByLabel('Mật khẩu mới',{exact:true}).fill('PersonalPassword@123');
 await staff.getByLabel('Xác nhận mật khẩu',{exact:true}).fill('PersonalPassword@123');await staff.getByRole('button',{name:'Đổi mật khẩu',exact:true}).click();
 await expect(staff.getByRole('heading',{name:'Đăng nhập workspace'})).toBeVisible();
 await staff.getByLabel('Email',{exact:true}).fill(email);await staff.getByLabel('Mật khẩu',{exact:true}).fill('PersonalPassword@123');await staff.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(staff.locator('main h1')).toContainText('AI Workspace');await context.close();
});

test('company and display preferences survive a fresh login',async({page})=>{
 await login(page);const original=await (await page.request.get('/api/company')).json();
 try{
  await page.goto('/admin');await page.getByRole('button',{name:'Doanh nghiệp',exact:true}).click();
  await page.getByLabel('Tên doanh nghiệp',{exact:true}).fill('Enterprise Verification');await page.getByRole('button',{name:'Lưu doanh nghiệp',exact:true}).click();
  await expect(page.locator('.workspace-label')).toContainText('Enterprise Verification');
  await page.request.put('/api/auth/preferences',{data:{theme:'dark',sidebar_collapsed:false}});await page.request.post('/api/auth/logout');
  await login(page);await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await expect(page.locator('.workspace-label')).toContainText('Enterprise Verification');
 }finally{await page.request.put('/api/company',{data:original});await page.request.put('/api/auth/preferences',{data:{theme:'light',sidebar_collapsed:false}})}
});

test('manage product, approve stock and post a real sale with durable inventory history',async({page})=>{
 await login(page);await page.goto('/data');await page.getByRole('button',{name:'Thêm sản phẩm',exact:true}).click();
 const modal=page.getByRole('dialog'),sku=`QA-${Date.now()}`;
 await modal.getByLabel('Mã SKU',{exact:true}).fill(sku);await modal.getByLabel('Tên sản phẩm',{exact:true}).fill('Enterprise Product');
 await modal.getByLabel('Danh mục',{exact:true}).fill('Verification');await modal.getByLabel('Đơn giá VND',{exact:true}).fill('125000');
 await modal.getByRole('button',{name:'Lưu sản phẩm',exact:true}).click();await expect(modal).not.toBeVisible();
 let product=(await (await page.request.get('/api/data/products?q='+sku)).json()).items[0];expect(product.quantity).toBe(0);
 const created=await page.request.post('/api/workflows',{data:{request:`Đề xuất điều chỉnh tồn kho product_id=${product.id} quantity=10`,idempotency_key:crypto.randomUUID()}});expect(created.ok()).toBeTruthy();
 const wf=await created.json();await expect.poll(async()=> (await (await page.request.get('/api/workflows/'+wf.id)).json()).status,{timeout:30000}).toBe('waiting_approval');
 const result=await (await page.request.get('/api/workflows/'+wf.id)).json();
 const decision=await page.request.post('/api/approvals/'+result.result.approval_id+'/decision',{data:{decision:'approved',revision:1}});expect(decision.ok()).toBeTruthy();
 await page.getByRole('button',{name:'Ghi nhận bán hàng',exact:true}).click();
 await modal.getByLabel('Tìm sản phẩm theo SKU hoặc tên',{exact:true}).fill(sku);
 await expect(modal.locator('select option')).toHaveCount(2);await modal.getByRole('combobox',{name:'Sản phẩm',exact:true}).selectOption(product.id);
 await modal.getByLabel('Số lượng',{exact:true}).fill('2');await modal.getByRole('checkbox').check();await modal.getByRole('button',{name:'Xác nhận bán hàng',exact:true}).click();
 await expect(modal).not.toBeVisible();product=(await (await page.request.get('/api/data/products?q='+sku)).json()).items[0];expect(product.quantity).toBe(8);
 const movements=await (await page.request.get('/api/business/movements')).json();expect(movements.items.filter((r:any)=>r.product_id===product.id)).toHaveLength(2);
 await page.getByRole('button',{name:'Lịch sử tồn kho',exact:true}).click();await expect(modal.getByRole('row').filter({hasText:sku})).toHaveCount(2);
 await modal.getByRole('button',{name:'Đóng hộp thoại'}).click();
 await page.reload();await page.getByRole('button',{name:'Danh sách',exact:true}).click();await page.getByRole('textbox',{name:'Tìm kiếm…'}).fill(sku);await expect(page.getByRole('row').filter({hasText:sku})).toContainText('8 đơn vị');
});
