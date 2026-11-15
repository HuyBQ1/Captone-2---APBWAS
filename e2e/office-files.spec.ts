import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

test('AI creates real Word and Excel finance files and keeps download buttons in conversation history',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.goto('/workspace');await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('Tạo file Word và Excel báo cáo tài chính tháng 07/2026');
 await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();await expect(page.locator('.result-heading .badge')).toHaveText('Hoàn tất',{timeout:30000});
 await expect(page.getByRole('region',{name:'Tệp đã tạo trong hội thoại'})).toBeVisible();await expect(page.getByRole('link',{name:'Tải Word',exact:true})).toBeVisible();await expect(page.getByRole('link',{name:'Tải Excel',exact:true})).toBeVisible();
 await expect(page.locator('.plan-metadata')).toContainText('Luồng xử lý');await expect(page.locator('.plan-metadata')).toContainText('Demo');
 const excelCard=page.locator('.chat-file').filter({has:page.getByRole('link',{name:'Tải Excel',exact:true})});
 await excelCard.getByRole('button',{name:'Xem trước',exact:true}).click();await expect(page.getByRole('region',{name:'Bảng xem trước Excel'})).toContainText('Doanh thu');
 const dialog=page.getByRole('dialog');await expect(dialog).not.toHaveClass(/preview-expanded/);await expect(page.getByLabel('Vừa chiều ngang',{exact:true})).toBeChecked();
 await page.getByRole('button',{name:'Toàn màn hình',exact:true}).click();await expect(dialog).toHaveClass(/preview-expanded/);
 await expect.poll(()=>dialog.evaluate(el=>Math.round(el.getBoundingClientRect().top))).toBeLessThanOrEqual(25);
 const grid=page.getByRole('region',{name:'Bảng xem trước Excel'});await expect.poll(()=>grid.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await page.getByRole('button',{name:'Thu gọn',exact:true}).click();await expect(dialog).not.toHaveClass(/preview-expanded/);await page.getByRole('button',{name:'Toàn màn hình',exact:true}).click();await expect(dialog).toHaveClass(/preview-expanded/);
 await mkdir('.test-tmp',{recursive:true});await page.screenshot({path:'.test-tmp/full-preview-desktop.png',fullPage:true,animations:'disabled'});
 await page.getByLabel('Hiện công thức',{exact:true}).check();await expect(page.getByRole('region',{name:'Bảng xem trước Excel'})).toContainText('=SUM(');
 await page.getByRole('tab',{name:'BanHang',exact:true}).click();await expect(page.getByRole('region',{name:'Bảng xem trước Excel'})).toContainText('SKU');
 await page.getByRole('button',{name:'Trang dữ liệu sau',exact:true}).click();await expect(page.getByRole('dialog')).toContainText('Trang 2/');
 await page.getByRole('button',{name:'Đóng hộp thoại',exact:true}).click();
 await page.locator('.chat-file').filter({has:page.getByRole('link',{name:'Tải Word',exact:true})}).getByRole('button',{name:'Xem trước',exact:true}).click();await expect(page.getByRole('region',{name:'Nội dung xem trước Word'})).toContainText('Lãi vận hành');await page.getByRole('button',{name:'Đóng hộp thoại',exact:true}).click();
 await mkdir('.test-tmp/office-qa',{recursive:true});
 for(const [kind,extension] of [['Word','docx'],['Excel','xlsx']]){
  const pending=page.waitForEvent('download');await page.getByRole('link',{name:'Tải '+kind,exact:true}).click();const download=await pending;expect(download.suggestedFilename()).toMatch(new RegExp('\\.'+extension+'$'));await download.saveAs('.test-tmp/office-qa/finance-july.'+extension);
 }
 await page.reload();await page.getByRole('button',{name:/Tạo file Word và Excel báo cáo tài chính tháng 07\/2026/}).first().click();await expect(page.locator('.chat-file')).toHaveCount(2);
 await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('Tạo file Word và Excel tồn kho');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();await expect(page.locator('.result-heading .badge')).toHaveText('Hoàn tất',{timeout:30000});await expect(page.locator('.chat-file')).toHaveCount(4);
 const stockWord=page.waitForEvent('download');await page.locator('.chat-file').filter({hasText:'Báo cáo tồn kho hiện tại'}).getByRole('link',{name:'Tải Word',exact:true}).click();await (await stockWord).saveAs('.test-tmp/office-qa/inventory.docx');
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('.chat-file').filter({hasText:'Báo cáo tồn kho hiện tại'}).filter({has:page.getByRole('link',{name:'Tải Excel',exact:true})}).getByRole('button',{name:'Xem trước',exact:true}).click();await expect(page.getByRole('region',{name:'Bảng xem trước Excel'})).toContainText('AP-001');await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/file-preview-mobile.png',fullPage:true,animations:'disabled'});await page.getByRole('button',{name:'Đóng hộp thoại',exact:true}).click();
 await page.screenshot({path:'.test-tmp/office-files-mobile.png',fullPage:true,animations:'disabled'});
});
