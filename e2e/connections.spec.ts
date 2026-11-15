import {test,expect} from '@playwright/test';
import {resolve} from 'node:path';

test('connection icons open Gmail, upload Word, and export Excel with honest file-based status',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.getByRole('link',{name:'Kết nối',exact:true}).click();await expect(page).toHaveURL(/\/connections$/);
 await expect(page.locator('.connection-card')).toHaveCount(7);await expect(page.locator('.connection-icon.word')).toBeVisible();await expect(page.locator('main')).toContainText('Chưa đồng bộ trực tiếp');
 await page.getByRole('link',{name:'Quản lý Gmail',exact:true}).click();await expect(page.getByRole('heading',{name:'Kết nối Gmail',exact:true})).toBeVisible();
 await expect(page.locator('nav a[href="/connections"]')).toHaveClass(/active/);await page.getByRole('link',{name:'Tất cả kết nối',exact:false}).click();
 const [chooser]=await Promise.all([page.waitForEvent('filechooser'),page.getByRole('button',{name:'Thêm tệp Word',exact:true}).click()]);
 await chooser.setFiles(resolve('docs/company-word/NC-WH-001_Quy_trinh_nhap_kho_va_kiem_dem_hang_hoa_v1.1.docx'));
 await expect(page).toHaveURL(/\/knowledge\//);await expect(page.locator('main .badge.indexed')).toBeVisible({timeout:30000});await expect(page.locator('.document-content')).toContainText('NC-WH-001');
 await page.goto('/connections');await page.getByRole('link',{name:'Mở Excel tài chính',exact:true}).click();await expect(page).toHaveURL(/\/connections\/excel$/);
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Xuất Excel có công thức',exact:true}).click();expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
 await expect(page.getByLabel('Nhập Excel tài chính',{exact:true})).toHaveCount(0);
 await page.goto('/connections');await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/connections-mobile.png',fullPage:true,animations:'disabled'});expect(errors).toEqual([]);
});

test('employee sees file access without email or finance privileges',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Employee',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.getByRole('link',{name:'Kết nối',exact:true}).click();await expect(page.locator('.connection-card')).toHaveCount(7);
 await expect(page.getByRole('link',{name:'Quản lý Gmail',exact:true})).toBeVisible();
 await expect(page.getByRole('link',{name:/Soạn email/})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Thêm tệp Word',exact:true})).toHaveCount(0);
 await page.goto('/connections/excel');await expect(page.getByRole('heading',{name:'Cần quyền truy cập tài chính',exact:true})).toBeVisible();
});
