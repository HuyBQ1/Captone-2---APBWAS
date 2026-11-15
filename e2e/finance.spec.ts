import {test,expect} from '@playwright/test';

test('monthly finance exports formula workbook and previews before database import',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Admin',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(page.locator('main h1')).toBeVisible();await page.goto('/data');await page.getByRole('button',{name:'Excel & lời lỗ',exact:true}).click();
 await page.getByLabel('Tháng báo cáo',{exact:true}).fill('2026-10');
 await expect(page.locator('.finance-metrics')).toContainText('Lợi nhuận vận hành');
 const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Xuất Excel có công thức'}).click()]);
 expect(download.suggestedFilename()).toBe('NovaCommerce-2026-10.xlsx');const path=await download.path();expect(path).toBeTruthy();
 await page.getByLabel('Nhập Excel tài chính').setInputFiles(path!);
 const modal=page.getByRole('dialog');await expect(modal).toContainText('Kỳ: 2026-10');
 await modal.getByRole('button',{name:'Xác nhận nhập vào database'}).click();await expect(modal).not.toBeVisible();
 await expect(page.locator('.finance-metrics')).toContainText('Lợi nhuận vận hành');
 const form=page.locator('form').filter({has:page.getByLabel('Mã chi phí',{exact:true})});
 await form.getByLabel('Mã chi phí',{exact:true}).fill('QA-CP-'+Date.now());await form.getByLabel('Ngày chi phí',{exact:true}).fill('2026-10-30');
 await form.getByLabel('Danh mục chi phí',{exact:true}).fill('Vận hành kiểm thử');await form.getByLabel('Số tiền VND',{exact:true}).fill('30000');
 await form.getByRole('button',{name:'Lưu chi phí',exact:true}).click();
 await expect.poll(async()=> (await (await page.request.get('/api/finance/summary?month=2026-10')).json()).expenses).toBeGreaterThanOrEqual(30000);
 await page.getByRole('button',{name:'Tôi đã kiểm tra đủ chi phí tháng này',exact:true}).click();await expect(page.getByRole('button',{name:'Mở lại kiểm tra chi phí',exact:true})).toBeVisible();
 await page.screenshot({path:'.test-tmp/finance-desktop.png',fullPage:true,animations:'disabled'});
 await page.reload();await page.getByRole('button',{name:'Excel & lời lỗ',exact:true}).click();await page.getByLabel('Tháng báo cáo',{exact:true}).fill('2026-10');
 await expect(page.getByRole('button',{name:'Mở lại kiểm tra chi phí',exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.app-main')).toHaveCSS('margin-left','0px');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/finance-mobile.png',fullPage:true,animations:'disabled'});
 await page.goto('/workspace');await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('Tính lời lỗ và số đơn hàng tháng 2026-10');await page.getByRole('button',{name:'Gửi yêu cầu'}).click();
 await expect(page.locator('.message.assistant .markdown')).toContainText('Phép tính:',{timeout:30000});
});
