// Run `python3 tests/test_cloud.py` first. Uses only the in-memory provider double.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
  const context=await browser.newContext(),page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base='http://127.0.0.1:8770';
  const login=async p=>{await p.locator('#loginForm [name=email]').fill('owner@example.test');await p.locator('#loginForm [name=password]').fill('test-password');await p.locator('#loginForm [type=submit]').click();await p.waitForFunction(()=>!document.querySelector('#loginDialog').open);};
  try{
    assert.equal((await page.request.get(base+'/api/records')).status(),401);
    await page.goto(base);await page.waitForFunction(()=>document.querySelector('#loginDialog').open);
    await page.locator('#loginForm [name=email]').fill('owner@example.test');await page.locator('#loginForm [name=password]').fill('wrong');await page.locator('#loginForm [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#loginError').textContent.length>0);
    await login(page);console.log('PASS: private API requires login, wrong password rejected, owner login');
    await page.locator('#fileInput').setInputFiles([{name:'2026-10-07_private.txt',mimeType:'text/plain',buffer:Buffer.from('private memo')},{name:'preview.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5WQAAAAASUVORK5CYII=','base64')}]);
    await page.waitForFunction(()=>document.querySelectorAll('.card').length===2);
    await page.waitForFunction(()=>[...document.querySelectorAll('.thumbnail img')].some(i=>i.complete&&i.naturalWidth>0&&i.src.startsWith('blob:')));
    console.log('PASS: cloud upload and authenticated thumbnail blob');
    await page.getByRole('button',{name:'private の詳細',exact:true}).click();await page.locator('#editForm [name=jima_filter]').selectOption('GOOD');await page.locator('#editForm [name=comment]').fill('shared safely');await page.locator('#editForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#detail').open);
    const secondContext=await browser.newContext(),second=await secondContext.newPage();await second.goto(base);await second.waitForFunction(()=>document.querySelector('#loginDialog').open);assert.equal(await second.locator('.card').count(),0);await login(second);assert.equal(await second.locator('.card').count(),2);assert.equal(await second.locator('.rating-GOOD').count(),1);await secondContext.close();
    console.log('PASS: second browser session sees the same saved files and evaluation');
    await page.getByRole('button',{name:'private の詳細',exact:true}).click();const download=page.waitForEvent('download');await page.locator('.file-link').click();assert.equal((await download).suggestedFilename(),'2026-10-07_private.txt');await page.locator('#closeDetail').click();
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    let release, reached;
    const held=new Promise(resolve=>release=resolve), intercepted=new Promise(resolve=>reached=resolve);
    await page.route('**/api/records',async route=>{const response=await route.fetch();reached();await held;await route.fulfill({response});});
    const inflight=page.evaluate(()=>refresh());await intercepted;
    await page.locator('#logout').click();release();await inflight;await page.unroute('**/api/records');
    assert.equal(await page.locator('.card').count(),0);
    assert.equal(await page.locator('#detailPreview').textContent(),'');
    assert.equal(await page.locator('#editForm [name=comment]').inputValue(),'');
    console.log('PASS: logout clears private details and ignores a delayed records response');
    await page.waitForFunction(()=>document.querySelector('#loginDialog').open);assert.equal(await page.locator('.card').count(),0);await page.reload();await page.waitForFunction(()=>document.querySelector('#loginDialog').open);assert.equal(await page.locator('.card').count(),0);
    assert.deepEqual(errors,[]);console.log('PASS: authenticated file download, no tokens in browser storage, logout and reload hide records');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
