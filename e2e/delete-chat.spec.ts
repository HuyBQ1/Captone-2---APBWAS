import {test,expect} from '@playwright/test';

test('delete chat requires confirmation, removes current chat and generated files permanently',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.goto('/workspace');const prompt='Tạo Excel tồn kho '+Date.now();await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill(prompt);
 const queued=page.waitForResponse(r=>r.url().endsWith('/api/workflows')&&r.request().method()==='POST');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();const run=await (await queued).json();
 await expect(page.locator('.chat-file')).toHaveCount(1,{timeout:30000});const fileUrl=await page.getByRole('link',{name:'Tải Excel',exact:true}).getAttribute('href');
 const row=page.locator('.conversation-item').filter({has:page.getByRole('button',{name:new RegExp(prompt)})});
 await row.getByRole('button',{name:'Xóa hội thoại',exact:true}).click();await expect(page.getByRole('dialog',{name:'Xóa hội thoại?'})).toBeVisible();await page.getByRole('button',{name:'Giữ lại',exact:true}).click();await expect(row).toBeVisible();
 await row.getByRole('button',{name:'Xóa hội thoại',exact:true}).click();await page.getByRole('button',{name:'Xóa vĩnh viễn',exact:true}).click();
 await expect(row).toHaveCount(0);await expect(page.locator('.chat-file')).toHaveCount(0);await expect(page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'})).toHaveValue('');
 expect((await page.request.get('/api/conversations/'+run.conversation_id)).status()).toBe(404);expect((await page.request.get(fileUrl!)).status()).toBe(404);
 await page.reload();await expect(page.getByRole('button',{name:new RegExp(prompt)})).toHaveCount(0);
});
