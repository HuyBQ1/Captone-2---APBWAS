import {test,expect} from '@playwright/test';

test('assistant calculates July profit inside chat from complete sample financial data',async({page})=>{
 await page.goto('/login');await page.getByRole('button',{name:'Manager',exact:true}).click();await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.locator('main h1')).toBeVisible();
 const data=await (await page.request.get('/api/finance/summary?month=2026-07')).json();
 expect(data.missing_cost_lines).toBe(0);expect(data.unassigned_order_lines).toBe(0);expect(data.expenses_confirmed).toBe(true);
 expect(data.operating_profit).toBe(data.revenue-data.cost_of_goods-data.expenses);
 await page.goto('/workspace');await page.getByRole('textbox',{name:'Yêu cầu nghiệp vụ'}).fill('tính lời lỗ Doanh thu 07/2026');await page.getByRole('button',{name:'Gửi yêu cầu'}).click();
 const answer=page.locator('.message.assistant .markdown');await expect(answer).toContainText('Phép tính:',{timeout:30000});
 for(const value of [data.revenue,data.cost_of_goods,data.expenses])await expect(answer).toContainText(Number(value).toLocaleString('vi-VN'));
 await expect(answer).toContainText('mô phỏng');await expect(answer).toContainText('Đơn hàng:');await expect(answer).not.toContainText('Chưa đủ dữ liệu');await expect(answer).not.toContainText('Tải Excel');
 await expect(answer).toContainText('Tồn kho hiện tại');await page.screenshot({path:'.test-tmp/chat-finance-complete.png',fullPage:true,animations:'disabled'});
});
