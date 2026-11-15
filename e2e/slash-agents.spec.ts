import {test,expect} from '@playwright/test';

test('slash selects a permitted published Agent and keeps subsequent messages in its conversation',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 const caps=await (await page.request.get('/api/agents/capabilities')).json(),stamp=Date.now();
 async function agent(name:string,tool:string,permissions:string[],publish=true){
  const response=await page.request.post('/api/agents',{data:{name,visibility:'private',description:'Slash picker test',config:{model:caps.models[0],tools:[tool],permissions}}});expect(response.status()).toBe(201);const a=await response.json();
  if(publish)expect((await page.request.post('/api/agents/'+a.id+'/publish',{data:{revision:1}})).ok()).toBeTruthy();return a;
 }
 const finance=await agent('Slash Tài chính '+stamp,'query_financial_summary',['sales.read','inventory.read']);
 await agent('Slash Tồn kho '+stamp,'get_inventory_status',['inventory.read']);await agent('Unpublished '+stamp,'get_inventory_status',['inventory.read'],false);
 let sends=0;page.on('request',r=>{if(r.method()==='POST'&&(/\/agents\/[^/]+\/runs$/.test(r.url())||r.url().endsWith('/api/workflows')))sends++});
 await page.goto('/workspace');const input=page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}),options=page.getByRole('listbox',{name:'Agent có sẵn'}).getByRole('option');
 await input.fill('/');await expect(page.getByRole('listbox',{name:'Agent có sẵn'})).toBeVisible();await expect(options.filter({hasText:String(stamp)})).toHaveCount(2);
 await expect(page.getByRole('button',{name:'Gửi yêu cầu',exact:true})).toBeDisabled();await input.press('ArrowDown');await expect(options.nth(1)).toHaveAttribute('aria-selected','true');
 await input.press('Escape');await expect(page.getByRole('listbox')).toHaveCount(0);expect(sends).toBe(0);
 await input.fill('/khong-co-'+stamp);await expect(page.getByRole('status')).toContainText('Không có Agent phù hợp');await input.press('Enter');expect(sends).toBe(0);
 await input.fill('/tai chinh '+stamp);await expect(options).toHaveCount(1);
 await page.screenshot({path:'.test-tmp/slash-agents-desktop.png',fullPage:true,animations:'disabled'});
 await input.press('Enter');await expect(input).toHaveValue('');await expect(page.locator('.selected-chat-agent')).toContainText(finance.name);
 await input.fill('Tính lời lỗ tháng 07/2026');const firstRun=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/agents/'+finance.id+'/runs'));await input.press('Enter');const first=await (await firstRun).json();
 await expect(page.locator('.result-heading .badge')).toHaveText('Hoàn tất',{timeout:30000});
 await input.fill('Tính lời lỗ tháng trước');const nextRun=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/agents/'+finance.id+'/runs'));await input.press('Enter');const next=await (await nextRun).json();
 expect(next.conversation_id).toBe(first.conversation_id);await expect(page.locator('.result-heading .badge')).toHaveText('Hoàn tất',{timeout:30000});
 const conversation=await (await page.request.get('/api/conversations/'+first.conversation_id)).json();expect(conversation.workflows).toHaveLength(2);expect(conversation.workflows.every((w:any)=>w.agent_id===finance.id&&w.agent_version_id)).toBe(true);
 await page.getByRole('button',{name:'Bỏ chọn Agent',exact:true}).click();await expect(page.locator('.selected-chat-agent')).toHaveCount(0);
 await page.getByRole('button',{name:'Hội thoại mới',exact:true}).click();await page.setViewportSize({width:390,height:844});await input.fill('/ton kho '+stamp);await expect(options).toHaveCount(1);
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'.test-tmp/slash-agents-mobile.png',fullPage:true,animations:'disabled'});
 await options.click();await expect(page.locator('.selected-chat-agent')).toContainText('Tồn kho');
});
