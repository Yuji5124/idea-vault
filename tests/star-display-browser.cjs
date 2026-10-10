const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try{
 const page=await browser.newPage();await page.goto('http://127.0.0.1:8774');await page.waitForFunction(()=>document.querySelector('#loginDialog').open);
 assert.equal(await page.locator('.card').count(),0);
 await page.locator('#loginForm [name=email]').fill('owner@example.test');await page.locator('#loginForm [name=password]').fill('test-password');await page.locator('#loginForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#loginDialog').open);
 await page.waitForFunction(()=>document.querySelectorAll('.card').length>=2);
 const cards=page.locator('.card').filter({has:page.locator('img')});assert(await cards.count()>=1);
 await cards.first().click();await page.waitForFunction(()=>{const image=document.querySelector('#detailPreview img');return image&&image.complete&&image.naturalWidth>0;});
 assert.match(await page.locator('#editForm [name=body]').inputValue(),/Original image/);
 await page.locator('#closeDetail').click();await page.locator('#logout').click();assert.equal(await page.locator('.card').count(),0);
 console.log('PASS: worker-created Supabase mock records are read back through IDEA VAULT login; image renders; logout hides records');
 }finally{await browser.close();}
})().catch(e=>{console.error(e.name);console.error(e.stack);process.exitCode=1;});
