import {test,expect} from '@playwright/test';

test('company dataset fills reports, knowledge and searchable sales with reconciled records',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(page.locator('main h1')).toContainText('AI Workspace');
 const reports=await (await page.request.get('/api/reports?q=Nova%20Commerce')).json();expect(reports.total).toBe(11);
 await page.goto('/reports/'+reports.items[0].id);
 await expect(page.getByRole('heading',{name:'Doanh thu theo danh mục',exact:true})).toBeVisible();
 await expect(page.locator('main')).toContainText('NCV1');
 const pdf=await page.request.get('/api/reports/'+reports.items[0].id+'/export?format=pdf');expect(pdf.ok()).toBeTruthy();expect((await pdf.body()).subarray(0,4).toString()).toBe('%PDF');
 await page.goto('/knowledge');await page.getByRole('textbox',{name:'Tìm tên tài liệu…'}).fill('NC-WH-001');
 const doc=page.getByRole('row').filter({hasText:'[NC-WH-001] Quy trình nhập'});await expect(doc).toContainText('Đã lập chỉ mục');await doc.getByRole('link',{name:'Xem tài liệu'}).click();
 await expect(page.locator('.document-content')).toContainText('Kho vận');await expect(page.getByRole('link',{name:'Tải file gốc'})).toBeVisible();
 await page.goto('/data');await page.getByRole('button',{name:'Giao dịch bán hàng',exact:true}).click();
 await page.getByRole('textbox',{name:'Tìm kiếm…'}).fill('NC-EL-001');await page.getByLabel('Kỳ doanh thu',{exact:true}).fill('2026-10');
 await expect(page.getByRole('row').filter({hasText:'NC-EL-001'})).toHaveCount(8);
 await expect(page.getByRole('row').filter({hasText:'NC-EL-001'}).first()).toContainText('Màn hình NovaView');
});
