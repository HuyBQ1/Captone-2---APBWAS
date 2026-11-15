import {test,expect} from '@playwright/test';

test('Gmail setup is honest when OAuth credentials are missing and explains redirect URI',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.getByRole('link',{name:'Kết nối',exact:true}).click();await page.getByRole('link',{name:'Quản lý Gmail',exact:true}).click();await expect(page.getByRole('heading',{name:'Kết nối Gmail',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Kết nối bằng Google',exact:true})).toBeDisabled();
 await expect(page.getByLabel('Gmail redirect URI',{exact:true})).toHaveValue('http://localhost:4181/mail/callback');
 await expect(page.locator('main')).toContainText('GMAIL_CLIENT_SECRET');
 await expect(page.locator('main')).toContainText('Không xin quyền đọc');
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.app-main')).toHaveCSS('margin-left','0px');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/gmail-mobile.png',fullPage:true,animations:'disabled'});
 await page.goto('/mail/callback?error=access_denied');await expect(page.locator('main')).toContainText('Bạn chưa cấp quyền Google');await expect(page).toHaveURL(/\/mail\/callback$/);
});
