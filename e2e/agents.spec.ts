import {test,expect} from '@playwright/test';

test('Agent draft publishes, executes, compares and restores through the existing runtime',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.getByRole('link',{name:'AI Agents',exact:true}).click();await page.getByRole('link',{name:'Tạo Agent',exact:true}).click();
 const name='Financial Analyst '+Date.now();await page.getByLabel('Tên Agent',{exact:true}).fill(name);await page.getByLabel('Mô tả',{exact:true}).fill('Monthly finance and stock analysis');
 await page.getByLabel('Tính số đơn, doanh thu và lời lỗ tháng',{exact:false}).check();
 await page.getByRole('button',{name:'Lưu bản nháp',exact:true}).click();await expect(page).toHaveURL(/\/agents\/.+\/edit/);
 const id=page.url().split('/').at(-2)!;
 await page.getByRole('button',{name:'Xuất bản Agent',exact:true}).click();await expect(page.getByRole('heading',{name:'Đang triển khai v1'})).toBeVisible();
 await page.screenshot({path:'.test-tmp/agent-editor-desktop.png',fullPage:true,animations:'disabled'});
 await page.getByRole('link',{name:'Playground',exact:true}).click();await page.getByLabel('Yêu cầu cho Agent',{exact:true}).fill('Tính lời lỗ tháng 07/2026');await page.getByRole('button',{name:'Chạy Agent',exact:true}).click();
 await expect(page.locator('.agent-result-text')).toContainText('Phép tính:',{timeout:30000});await expect(page.locator('.agent-result-text')).toContainText('mô phỏng');
 const runs=await (await page.request.get('/api/agents/'+id+'/runs')).json();expect(runs.total).toBe(1);const version=runs.items[0].agent_version_id;expect(version).toBeTruthy();
 await page.screenshot({path:'.test-tmp/agent-playground-desktop.png',fullPage:true,animations:'disabled'});
 await page.getByRole('link',{name:'Cấu hình Agent',exact:true}).click();await page.getByLabel('Chỉ dẫn Agent',{exact:true}).fill('Chỉ phân tích tài chính dựa trên dữ liệu cho phép.');await page.getByRole('button',{name:'Lưu bản nháp',exact:true}).click();
 await page.getByRole('link',{name:'Phiên bản',exact:true}).click();await page.getByRole('button',{name:'So sánh v1',exact:true}).click();await expect(page.locator('.agent-diff')).toContainText('instructions');
 await page.getByRole('button',{name:'Khôi phục v1 thành bản nháp mới',exact:true}).click();await page.getByRole('button',{name:'Xác nhận khôi phục bản nháp',exact:true}).click();await expect(page.getByRole('dialog')).not.toBeVisible();
 const a=await (await page.request.get('/api/agents/'+id)).json();expect(a.revision).toBe(3);expect(a.published_version).toBe(1);
 const run=await (await page.request.get('/api/workflows/'+runs.items[0].id)).json();expect(run.agent_version_id).toBe(version);expect(run.status).toBe('completed');
 await page.goto('/agents');await page.getByRole('textbox',{name:'Tìm Agent',exact:true}).fill(name);await expect(page.locator('.agent-card')).toHaveCount(1);
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.app-main')).toHaveCSS('margin-left','0px');await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/agent-list-mobile.png',fullPage:true,animations:'disabled'});
 const duplicate=await page.request.post('/api/agents/'+id+'/duplicate');expect(duplicate.status()).toBe(201);const copy=await duplicate.json();
 expect((await page.request.post('/api/agents/'+copy.id+'/archive')).ok()).toBeTruthy();expect((await page.request.post('/api/agents/'+copy.id+'/unarchive')).ok()).toBeTruthy();expect((await page.request.delete('/api/agents/'+copy.id)).ok()).toBeTruthy();
});
