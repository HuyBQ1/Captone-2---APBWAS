import {test,expect} from '@playwright/test';

test('employee manages their contact and personal Gmail without bulk-send controls',async({page})=>{
 let delivery='';
 const user=()=>({id:'employee-ui',name:'Nhân viên',email:'staff@company.vn',role:'Employee',delivery_email:delivery,permissions:['agents.run','inventory.read','documents.read','mail.connect'],must_change_password:false,demo_mode:false,sample_data:false});
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/auth/profile'){
   const body=route.request().postDataJSON();delivery=body.delivery_email;
   return route.fulfill({json:user()});
  }
  if(path==='/api/auth/me')return route.fulfill({json:user()});
  if(path==='/api/mail/status')return route.fulfill({json:{configured:true,connected:false,sender:'staff@company.vn',email:null,can_send_campaigns:false,self_test_limit_per_hour:1,missing:[],redirect_uri:'http://localhost:4180/mail/callback'}});
  if(path==='/api/company')return route.fulfill({json:{name:'Nova Commerce'}});
  if(path==='/api/auth/sessions')return route.fulfill({json:{items:[]}});
  return route.fulfill({json:{items:[],unread:0,total:0}});
 });
 await page.goto('/account');
 await page.getByLabel('Email nhận thông báo',{exact:true}).fill('staff.personal@gmail.com');
 await page.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();
 await expect.poll(()=>delivery).toBe('staff.personal@gmail.com');
 await page.goto('/connections');
 await page.getByRole('link',{name:'Quản lý Gmail',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Kết nối Gmail',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Kết nối bằng Google',exact:true})).toBeEnabled();
 await expect(page.locator('main')).toContainText('tối đa 1 thư/giờ');
 await expect(page.getByRole('link',{name:'Soạn email cho nhân viên',exact:true})).toHaveCount(0);
 await expect(page.locator('main')).not.toContainText('GMAIL_CLIENT_SECRET');
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/personal-gmail-mobile.png',fullPage:true});
 await page.goto('/mail/employees');
 await expect(page.getByRole('heading',{name:'Soạn email cho nhân viên',exact:true})).toHaveCount(0);
});
