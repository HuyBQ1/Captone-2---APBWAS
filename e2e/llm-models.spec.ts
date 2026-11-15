import {test,expect} from '@playwright/test';

test('Admin adds a compatible provider and model choices appear in Agent editor and chat without exposing keys',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Admin',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.getByRole('link',{name:'Mô hình AI',exact:true}).click();await page.getByRole('button',{name:'Thêm nhà cung cấp',exact:true}).click();
 const providerName='QA LLM Provider '+Date.now(),dialog=page.getByRole('dialog');await dialog.getByLabel('Tên nhà cung cấp',{exact:true}).fill(providerName);await dialog.getByLabel('Base URL',{exact:true}).fill('https://provider.example/v1');
 await dialog.getByLabel('API key',{exact:true}).fill('qa-only-private-key');await dialog.getByLabel('Model ID',{exact:true}).fill('model-one\nmodel-two');await dialog.getByRole('button',{name:'Lưu nhà cung cấp',exact:true}).click();
 await expect(dialog).toHaveCount(0);const card=page.locator('.llm-provider').filter({hasText:providerName});await expect(card).toContainText('2 model');
 const providers=await (await page.request.get('/api/llm/providers')).json();expect(JSON.stringify(providers)).not.toContain('qa-only-private-key');const provider=providers.items.find((p:any)=>p.name===providerName);
 await card.getByRole('button',{name:'Chỉnh sửa',exact:true}).click();await expect(dialog.getByLabel('API key',{exact:true})).toHaveValue('');await dialog.getByLabel('Tên nhà cung cấp',{exact:true}).fill(providerName+' Updated');await dialog.getByRole('button',{name:'Lưu nhà cung cấp',exact:true}).click();await expect(dialog).toHaveCount(0);
 await page.goto('/agents/new');const id='llm:'+provider.id+':model-two';await page.getByLabel('LLM model',{exact:true}).selectOption(id);await expect(page.getByLabel('LLM model',{exact:true})).toHaveValue(id);
 await page.goto('/workspace');await page.getByLabel('Model trong chat',{exact:true}).selectOption(id);await expect(page.getByLabel('Model trong chat',{exact:true})).toHaveValue(id);
 // Finance is computed locally in Demo Mode. The selected model is still
 // persisted; no remote AI request is permitted by this browser test.
 await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('Tính lời lỗ tháng 07/2026');const created=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/workflows'));await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();const workflow=await (await created).json();expect(workflow.model_ref).toBe(id);
 await expect(page.locator('.result-heading .badge')).toHaveText('Hoàn tất',{timeout:30000});
 await page.goto('/models');await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'.test-tmp/llm-models-mobile.png',fullPage:true,animations:'disabled'});
});

test('Employee cannot manage providers or select models restricted to other roles',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Employee',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 expect((await page.request.get('/api/llm/providers')).status()).toBe(403);await page.goto('/workspace');await expect(page.getByLabel('Model trong chat')).toBeVisible();await expect(page.getByLabel('Model trong chat').locator('option')).not.toContainText(['model-two']);
});
