import {test,expect} from '@playwright/test';

test('public homepage links to real auth routes and changes its preview',async({page})=>{
 await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{error:{message:'Chưa đăng nhập'}}}));
 await page.route('**/api/auth/config',route=>route.fulfill({json:{demo_accounts:false}}));
 await page.goto('/');
 await expect(page.getByRole('heading',{level:1})).toContainText('Giao việc cho AI.');
 await page.getByRole('tab',{name:'Kho hàng',exact:true}).click();
 await expect(page.getByRole('tabpanel')).toContainText('Kiểm tra những sản phẩm sắp hết hàng.');
 await page.getByRole('tab',{name:'Tri thức',exact:true}).click();
 await expect(page.getByRole('tabpanel')).toContainText('Chính sách nội bộ');
 await page.screenshot({path:'.test-tmp/home-desktop.png',fullPage:true});
 await page.getByRole('link',{name:'Đăng nhập',exact:true}).click();
 await expect(page).toHaveURL(/\/login$/);
 await expect(page.getByRole('heading',{name:'Đăng nhập workspace'})).toBeVisible();
 await page.getByRole('link',{name:'Tạo tài khoản',exact:true}).click();
 await expect(page).toHaveURL(/\/register$/);
 await page.getByRole('link',{name:'Đã có tài khoản? Đăng nhập'}).click();
 await expect(page).toHaveURL(/\/login$/);
});

test('mobile homepage has usable menu and no horizontal overflow',async({page})=>{
 await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{error:{message:'Chưa đăng nhập'}}}));
 await page.setViewportSize({width:390,height:844});
 await page.goto('/home');
 await expect(page.getByRole('heading',{level:1})).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Mở điều hướng'}).click();
 await page.getByRole('link',{name:'Cách hoạt động',exact:true}).click();
 await expect(page).toHaveURL(/#home-how$/);
 await expect(page.getByRole('button',{name:'Mở điều hướng'})).toBeVisible();
 await page.goto('/home');
 await page.screenshot({path:'.test-tmp/home-mobile.png',fullPage:true});
});

test('signed in users can open homepage and enter their workspace',async({page})=>{
 await page.route('**/api/**',route=>{
  if(new URL(route.request().url()).pathname==='/api/auth/me')return route.fulfill({json:{id:'home-user',name:'Người dùng',email:'user@example.test',role:'Employee',permissions:['agents.run'],preferences:{},must_change_password:false}});
  return route.fulfill({json:{items:[],total:0,unread:0}});
 });
 await page.goto('/home');
 await page.getByRole('link',{name:'Vào workspace',exact:true}).click();
 await expect(page).toHaveURL(/\/workspace$/);
 await expect(page.locator('.sidebar nav').getByTitle('Trang chủ')).toBeVisible();
});
