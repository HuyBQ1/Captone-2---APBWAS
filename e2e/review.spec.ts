import {test,expect,Page} from '@playwright/test';

async function login(page:Page,role='Manager'){
 await page.goto('/login');
 await page.getByRole('button',{name:role,exact:true}).click();
 await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(page.getByRole('heading',{name:/AI Workspace/})).toBeVisible();
}

test('product lookup answers with the stored price and SKU search works',async({page})=>{
 await login(page);
 const response=await page.request.get('/api/data/products?q=AP-001');
 const product=(await response.json()).items[0];expect(product.sku).toBe('AP-001');
 await page.goto('/workspace');
 await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill(`${product.name} có giá là bao nhiêu`);
 await page.getByRole('button',{name:'Gửi yêu cầu'}).click();
 await expect(page.locator('.workflow-result')).toContainText('lookup_products',{timeout:30000});
 await expect(page.locator('.message.assistant .markdown')).toContainText(product.sku,{timeout:30000});
 await expect(page.locator('.message.assistant .markdown')).toContainText(Number(product.price).toLocaleString('vi-VN'));
 await page.goto('/data');
 await page.getByRole('button',{name:'Danh sách',exact:true}).click();
 await page.getByRole('textbox',{name:'Tìm kiếm…'}).fill(product.sku);
 await expect(page.getByRole('row').filter({hasText:product.name})).toHaveCount(1);
});

test('stock answers contain the actual quantity and only the requested product',async({page})=>{
 await login(page,'Employee');
 const response=await page.request.get('/api/data/products?q=AP-001');const product=(await response.json()).items[0];
 await page.goto('/workspace');
 await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill(`Tồn kho ${product.sku} còn bao nhiêu?`);
 await page.getByRole('button',{name:'Gửi yêu cầu'}).click();
 await expect(page.locator('.message.assistant .markdown')).toContainText(`${product.quantity} đơn vị`,{timeout:30000});
 await expect(page.locator('.message.assistant .markdown')).toContainText(product.sku);
 await expect(page.locator('.message.assistant .markdown')).not.toContainText('AP-002');
});

test('upload is indexed and can be opened and deleted',async({page})=>{
 await login(page);
 await page.goto('/knowledge');
 const filename=`review-${Date.now()}.txt`;
 await page.getByLabel('Tải tài liệu').setInputFiles({name:filename,mimeType:'text/plain',buffer:Buffer.from('Quy trình kiểm tra: mỗi sản phẩm có một mã SKU duy nhất.','utf8')});
 const row=page.getByRole('row').filter({hasText:filename});
 await expect(row).toContainText('Đã lập chỉ mục',{timeout:30000});
 await row.getByRole('link',{name:'Xem tài liệu'}).click();
 await expect(page.locator('.document-content')).toContainText('SKU duy nhất');
 const id=page.url().split('/').pop();
 const deleted=await page.request.delete('/api/documents/'+id);expect(deleted.ok()).toBeTruthy();
 await page.reload();await expect(page.locator('.error-box, .error-state, [role=alert]').first()).toBeVisible();
});

test('an open session closes protected views after its role loses permission',async({page,browser})=>{
 test.setTimeout(120000);
 await login(page);
 await page.goto('/reports');
 const admin=await browser.newContext({baseURL:new URL(page.url()).origin});
 let logged=await admin.request.post('/api/auth/login',{data:{email:'admin@apbwas.demo',password:'Demo@123456'}});
 // The full suite can exhaust the real login limiter. Respect its one-minute
 // window; never relax production authentication to make browser tests pass.
 if(logged.status()===429)await expect.poll(async()=>{
  logged=await admin.request.post('/api/auth/login',{data:{email:'admin@apbwas.demo',password:'Demo@123456'}});return logged.status();
 },{timeout:65000,intervals:[10000]}).not.toBe(429);
 expect(logged.ok()).toBeTruthy();
 const roles=await (await admin.request.get('/api/admin/roles')).json();
 const original=roles.items.find((r:any)=>r.name==='Manager').permissions;
 try{
  const changed=await admin.request.patch('/api/admin/roles/Manager',{data:{permissions:original.filter((p:string)=>p!=='sales.read')}});
  expect(changed.ok()).toBeTruthy();
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('heading',{name:'Quyền truy cập bị giới hạn'})).toBeVisible();
  await expect(page.locator('nav a[href="/reports"]')).toHaveCount(0);
  await page.goto('/reports');
  await expect(page.getByRole('heading',{name:'Quyền truy cập bị giới hạn'})).toBeVisible();
 }finally{
  await admin.request.patch('/api/admin/roles/Manager',{data:{permissions:original}});
  await admin.close();
 }
});
