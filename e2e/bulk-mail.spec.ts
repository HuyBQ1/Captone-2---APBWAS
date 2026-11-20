import {test,expect} from '@playwright/test';

test('Admin adds a delivery address, previews a draft and cannot send without Gmail',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Admin',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.goto('/mail');await page.getByRole('link',{name:'Soạn email cho nhân viên',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Email cho nhân viên',exact:true})).toBeVisible();
 const contact=page.locator('.mail-contact').filter({has:page.getByText('employee@apbwas.demo',{exact:false})});
 await contact.locator('input').fill('staff-bulk-preview@gmail.com');await contact.getByRole('button',{name:'Lưu',exact:true}).click();
 await expect(contact).toContainText('Nhận thư tại: staff-bulk-preview@gmail.com');
 await page.getByLabel('Tiêu đề',{exact:true}).fill('Thông báo họp nhân viên');await page.getByLabel('Nội dung',{exact:true}).fill('Mời nhân viên tham dự họp lúc 9 giờ sáng.');
 await page.getByRole('button',{name:'Lưu và xem trước',exact:true}).click();await expect(page).toHaveURL(/\/mail\/campaigns\//);
 await expect(page.locator('main')).toContainText('staff-bulk-preview@gmail.com');
 await expect(page.getByRole('button',{name:'Xem xác nhận gửi',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Chỉnh sửa nội dung',exact:true}).click();
 await page.getByRole('dialog').getByLabel('Nội dung',{exact:true}).fill('Họp lúc 10 giờ sáng.');
 await page.getByRole('button',{name:'Lưu thay đổi',exact:true}).click();await expect(page.locator('.mail-preview')).toContainText('Họp lúc 10 giờ sáng.');
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/bulk-mail-mobile.png',fullPage:true,animations:'disabled'});
 await page.getByRole('button',{name:'Dừng đợt gửi',exact:true}).click();await expect(page.locator('main')).toContainText('Trạng thái: Đã dừng');
});

test('revenue email command creates a database-backed draft for review without sending',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 await page.goto('/workspace');await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('soạn thư doanh thu tháng này và gửi cho nhân viên');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();
 await expect(page.getByRole('region',{name:'Email trong hội thoại'})).toContainText('Đã soạn bản nháp · Chưa gửi');
 await expect(page.getByRole('link',{name:'Mở bản nháp email',exact:false})).toBeVisible();
 await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('Xem người nhận và xác nhận gửi');await page.getByRole('button',{name:'Gửi yêu cầu',exact:true}).click();
 await expect(page.locator('.workflow-result')).toContainText('open_employee_email');
 await page.getByRole('link',{name:'Mở bản nháp email',exact:false}).click();
 await expect(page).toHaveURL(/\/mail\/campaigns\//);await expect(page.locator('main')).toContainText('Trạng thái: Bản nháp');
 await expect(page.locator('.mail-preview')).toContainText('Tổng doanh thu ghi nhận:');
 await expect(page.getByRole('button',{name:'Xem xác nhận gửi',exact:true})).toBeDisabled();
});
