import {test,expect} from '@playwright/test';

test('catalog images render, upload persists and mobile layout fits',async({page})=>{
 test.setTimeout(125000);
 await page.goto('/login');await page.getByRole('button',{name:'Admin',exact:true}).click();
 for(let attempt=0;attempt<2;attempt++){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/auth/login')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  const result=await response;
  if(result.status()!==429){expect(result.status()).toBe(200);break;}
  expect(attempt,'Login still rate limited after a full cooldown').toBe(0);
  // The full suite shares a test account; honor the real one-minute limit.
  // This wait is only for an explicit 429, never to mask a rendering failure.
  await page.waitForTimeout(61000);
 }
 await expect(page.locator('main h1')).toBeVisible();await page.goto('/data');
 await expect(page.locator('.product-card')).toHaveCount(10);
 await expect.poll(()=>page.locator('.product-card img').evaluateAll(images=>images.every(image=>(image as HTMLImageElement).complete&&(image as HTMLImageElement).naturalWidth>0))).toBe(true);
 await page.screenshot({path:'.test-tmp/product-catalog-desktop.png',fullPage:true});
 await page.locator('.product-card').first().click();
 let dialog=page.getByRole('dialog');await expect(dialog).toContainText(/Ảnh minh họa sản phẩm|Ảnh do doanh nghiệp cung cấp/);
 await expect(page.locator('.modal-overlay')).toHaveCSS('opacity','1');
 await page.screenshot({path:'.test-tmp/product-detail-desktop.png',animations:'disabled'});
 const raw=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=120;canvas.height=90;const c=canvas.getContext('2d')!;c.fillStyle='#4c6970';c.fillRect(0,0,120,90);return canvas.toDataURL('image/png').split(',')[1]});
 await dialog.getByLabel('Tải ảnh sản phẩm').setInputFiles({name:'test-product.png',mimeType:'image/png',buffer:Buffer.from(raw,'base64')});
 await expect(dialog).toContainText('Ảnh do doanh nghiệp cung cấp');
 await dialog.getByRole('button',{name:'Đóng hộp thoại'}).click();await page.reload();await page.locator('.product-card').first().click();
 dialog=page.getByRole('dialog');await expect(dialog).toContainText('Ảnh do doanh nghiệp cung cấp');
 await dialog.getByRole('button',{name:'Đóng hộp thoại'}).click();
 await page.setViewportSize({width:390,height:844});
 await expect(page.locator('.app-main')).toHaveCSS('margin-left','0px');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'.test-tmp/product-catalog-mobile.png',fullPage:true,animations:'disabled'});
 await page.locator('.product-card').first().click();await expect(page.getByRole('dialog')).toContainText('Tồn kho');
 expect(await page.getByRole('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 await expect(page.locator('.modal-overlay')).toHaveCSS('opacity','1');
 await page.screenshot({path:'.test-tmp/product-detail-mobile.png',animations:'disabled'});
});
