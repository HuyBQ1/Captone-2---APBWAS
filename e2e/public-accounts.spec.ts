import {test,expect} from '@playwright/test';

test('login offers registration and email recovery with usable mobile forms',async({page})=>{
 let registration:any,forgot:any,reset:any;
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/auth/me')return route.fulfill({status:401,json:{error:{message:'Chưa đăng nhập'}}});
  if(path==='/api/auth/config')return route.fulfill({json:{demo_accounts:false}});
  if(path==='/api/auth/register'){registration=route.request().postDataJSON();return route.fulfill({status:202,json:{ok:true,message:'Yêu cầu đã được ghi nhận. Tài khoản mới cần quản trị viên duyệt trước khi đăng nhập.'}})}
  if(path==='/api/auth/forgot-password'){forgot=route.request().postDataJSON();return route.fulfill({status:202,json:{ok:true,message:'Nếu email thuộc tài khoản đang hoạt động, liên kết đặt lại mật khẩu sẽ được gửi tới email đăng nhập.'}})}
  if(path==='/api/auth/redeem'){reset=route.request().postDataJSON();return route.fulfill({json:{ok:true}})}
  return route.fulfill({json:{items:[]}});
 });
 await page.goto('/login');
 await page.getByRole('link',{name:'Tạo tài khoản',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tạo tài khoản',exact:true})).toBeVisible();
 await page.getByLabel('Họ và tên',{exact:true}).fill('Nhân viên mới');
 await page.getByLabel('Email đăng nhập',{exact:true}).fill('new.staff@gmail.com');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('PersonalPassword@123');
 await page.getByLabel('Xác nhận mật khẩu',{exact:true}).fill('PersonalPassword@123');
 await page.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('quản trị viên duyệt');
 expect(registration.email).toBe('new.staff@gmail.com');expect(registration.role).toBeUndefined();
 await page.getByRole('link',{name:'Trở về đăng nhập',exact:true}).click();
 await page.getByRole('link',{name:'Quên mật khẩu?',exact:true}).click();
 await page.setViewportSize({width:390,height:844});
 await page.getByLabel('Email đăng nhập',{exact:true}).fill('new.staff@gmail.com');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/forgot-password-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Gửi liên kết khôi phục',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Nếu email thuộc tài khoản');
 expect(forgot).toEqual({email:'new.staff@gmail.com'});
 await page.goto('/reset-password#token='+'a'.repeat(54));
 await page.getByLabel('Mật khẩu mới',{exact:true}).fill('NewPersonalPassword@123');
 await page.getByLabel('Xác nhận mật khẩu',{exact:true}).fill('NewPersonalPassword@123');
 await page.getByRole('button',{name:'Lưu mật khẩu',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Đã thiết lập mật khẩu',exact:true})).toBeVisible();
 expect(reset.token).toBe('a'.repeat(54));expect(page.url()).not.toContain('token=');
});

test('admin can approve a pending employee registration',async({page})=>{
 let approved=false;
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/auth/me')return route.fulfill({json:{id:'admin-ui',name:'Admin',email:'admin@company.vn',role:'Admin',permissions:['users.manage','settings.manage'],must_change_password:false}});
  if(path==='/api/admin/registrations/staff-ui/approve'){approved=true;return route.fulfill({json:{ok:true}})}
  const employee={id:'staff-ui',name:'Nhân viên đăng ký',email:'new.staff@gmail.com',role:'Employee',active:approved,registration_pending:!approved,created_at:'2026-11-08T06:00:00Z'};
  if(path==='/api/admin/registrations')return route.fulfill({json:{items:approved?[]:[employee]}});
  if(path==='/api/admin/users')return route.fulfill({json:{items:[employee],total:1,page:1,size:10}});
  if(path==='/api/company')return route.fulfill({json:{name:'Nova Commerce'}});
  return route.fulfill({json:{items:[],total:0,unread:0}});
 });
 await page.goto('/admin');
 await expect(page.getByRole('heading',{name:'Đăng ký chờ duyệt',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Duyệt tài khoản',exact:true}).click();
 await expect.poll(()=>approved).toBe(true);
 await expect(page.getByRole('heading',{name:'Đăng ký chờ duyệt',exact:true})).toHaveCount(0);
 await expect(page.locator('table')).toContainText('Đang hoạt động');
});
