import {test,expect} from '@playwright/test';

test('chat header exposes configured models and sends the selected model',async({page})=>{
 const model='llm:provider-test:gpt-6-luna';let sent:any;
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url()),path=url.pathname;
  if(path==='/api/auth/me')return route.fulfill({json:{id:'manager-ui',name:'Quản lý',role:'Manager',email:'manager@company.vn',permissions:['agents.run','inventory.read'],model:'deepseek-v4-flash-vision',provider_label:'Intern AI / DeepSeek',demo_mode:false,sample_data:false}});
  if(path==='/api/llm/models')return route.fulfill({json:{items:[{id:'deepseek-v4-flash-vision',model_id:'deepseek-v4-flash-vision',label:'deepseek-v4-flash-vision · Intern AI',provider:'Intern AI / DeepSeek'},{id:model,model_id:'gpt-6-luna',label:'gpt-6-luna · X-APIKey',provider:'X-APIKey'}]}});
  if(path==='/api/workflows'&&route.request().method()==='POST'){
   sent=route.request().postDataJSON();return route.fulfill({json:{id:'workflow-ui',conversation_id:'chat-ui',request:sent.request,model_ref:sent.model,status:'completed',plan:[],result:{summary:'Chào bạn!'}}});
  }
  if(path==='/api/workflows/workflow-ui')return route.fulfill({json:{id:'workflow-ui',conversation_id:'chat-ui',model_ref:sent?.model,status:'completed',plan:[],steps:[],result:{summary:'Chào bạn!'}}});
  if(path==='/api/conversations/chat-ui')return route.fulfill({json:{messages:[],workflows:[]}});
  if(path==='/api/company')return route.fulfill({json:{name:'Nova Commerce'}});
  return route.fulfill({json:{items:[],workflows:[],messages:[],unread:0,total:0}});
 });
 await page.goto('/workspace');
 const picker=page.getByRole('combobox',{name:'Model trong chat',exact:true});
 await expect(picker).toBeVisible();
 await expect(picker.locator('option')).toContainText(['Mặc định','deepseek-v4-flash-vision','gpt-6-luna']);
 await picker.selectOption(model);
 await expect(page.locator('.chat-top')).toContainText('X-APIKey');
 await page.locator('.composer textarea').fill('chào');
 await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();
 await expect.poll(()=>sent?.model).toBe(model);
 await page.setViewportSize({width:390,height:844});
 await expect(picker).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/chat-model-header-mobile.png',fullPage:true});
});
