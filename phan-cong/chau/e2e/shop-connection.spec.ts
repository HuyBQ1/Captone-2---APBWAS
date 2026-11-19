import {test,expect} from '@playwright/test';

test('reports show synced Nova sales even without a saved report',async({page})=>{
 await page.route('**/api/**',route=>route.fulfill({json:{items:[],total:0,unread:0}}));
 await page.route('**/api/auth/me',route=>route.fulfill({json:{id:'manager',name:'Quản lý',email:'manager@example.test',role:'Manager',permissions:['agents.run','sales.read'],preferences:{},must_change_password:false}}));
 await page.route('**/api/reports?*',route=>route.fulfill({json:{items:[],total:0}}));
 await page.route('**/api/reports/nova-sales',route=>route.fulfill({json:{
  synced_at:'2026-11-15T18:56:52Z',sync_failed:false,
  periods:[{month:'2026-10',revenue:1342764000,orders_created:62}],
 }}));
 await page.route('**/api/reports/nova-sales/2026-10',route=>route.fulfill({json:{
  month:'2026-10',synced_at:'2026-11-15T18:56:52Z',sync_failed:false,
  revenue:1342764000,orders_created:62,sales_amount:1343764000,refund_amount:1000000,cost_of_goods:1055365000,
  expenses:27300000,operating_profit:null,categories:[{category:'Điện tử',revenue:1342764000}],
  products:[{sku:'NC-EL-001',name:'Màn hình NovaView',category:'Điện tử',sold:63,returned:1,sales_amount:1343764000,refund_amount:1000000,revenue:1342764000}],
 }}));
 await page.goto('/reports');
 const sales=page.getByRole('table',{name:'Doanh số theo tháng từ Nova Commerce'});
 await expect(sales.getByRole('cell',{name:'10/2026',exact:true})).toBeVisible();
 await expect(sales.getByRole('cell',{name:/1\.342\.764\.000/})).toBeVisible();
 await expect(sales.getByRole('cell',{name:'62',exact:true})).toBeVisible();
 await expect(page.getByText('Báo cáo đã lưu',{exact:true})).toBeVisible();
 await sales.getByRole('link',{name:'Xem chi tiết doanh số tháng 10/2026'}).click();
 await expect(page.getByRole('heading',{name:'Doanh số tháng 10/2026'})).toBeVisible();
 await expect(page.getByText('Chưa đủ dữ liệu',{exact:false})).toBeVisible();
 await expect(page.getByRole('table',{name:'Doanh thu theo danh mục'})).toContainText('Điện tử');
 const products=page.getByRole('table',{name:'Doanh số theo sản phẩm'});
 await expect(products).toContainText('Màn hình NovaView');
 const search=page.getByRole('textbox',{name:'Tìm sản phẩm trong báo cáo'});
 await search.fill('SKU-không-tồn-tại');
 await expect(products).toHaveCount(0);
 await search.fill('nc-el-001');
 await expect(products).toContainText('NC-EL-001');
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('link',{name:'Hỏi AI',exact:true}).click();
 await expect(page.locator('textarea')).toHaveValue('Phân tích doanh thu website Nova Commerce tháng 2026-10.');
});

test('website connection shows source counts and manual refresh without returning a key',async({page})=>{
 let refreshed=false;
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/auth/me')return route.fulfill({json:{id:'admin',name:'Quản trị',email:'admin@example.test',role:'Admin',permissions:['agents.run','inventory.read','sales.read','settings.manage'],preferences:{},must_change_password:false}});
  if(path==='/api/connections/shop/sync'){refreshed=true;return route.fulfill({json:{ok:true}})}
  if(path==='/api/connections/shop')return route.fulfill({json:{configured:true,last_sync:'2026-11-10T20:33:00Z',counts:{products:56,orders:385},last_error:''}});
  return route.fulfill({json:{items:[],total:0,unread:0}});
 });
 await page.goto('/connections');
 const card=page.locator('article').filter({has:page.getByRole('heading',{name:'Nova Commerce',exact:true})});
 await expect(card).toContainText('56 sản phẩm');await expect(card).toContainText('385 đơn hàng');
 await card.getByRole('button',{name:'Đồng bộ ngay'}).click();await expect.poll(()=>refreshed).toBe(true);
 await page.screenshot({path:'.test-tmp/nova-connections.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('source banner replaces local business editing actions',async({page})=>{
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/auth/me')return route.fulfill({json:{id:'admin',name:'Quản trị',email:'admin@example.test',role:'Admin',permissions:['agents.run','inventory.read','sales.read','settings.manage','business.manage'],preferences:{},must_change_password:false}});
  if(path==='/api/connections/shop')return route.fulfill({json:{configured:true,last_sync:'2026-11-10T20:33:00Z',counts:{products:56,orders:385},last_error:''}});
  return route.fulfill({json:{items:[],total:0,unread:0}});
 });
 await page.goto('/data');
 await expect(page.getByText('Nguồn dữ liệu: website Nova Commerce')).toBeVisible();
 await expect(page.getByRole('button',{name:'Thêm sản phẩm',exact:true})).toHaveCount(0);
 await expect(page.getByRole('link',{name:'Quản lý kết nối',exact:true}).first()).toBeVisible();
});
