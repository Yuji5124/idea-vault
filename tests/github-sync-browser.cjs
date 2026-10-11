// python3 tests/test_github_sync.py; synthetic GitHub listing and Supabase.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[],syncRequests=[];
 page.on('pageerror',e=>errors.push(e.name));page.on('request',r=>{if(r.url().endsWith('/api/sync-github'))syncRequests.push(r);});
 const base='http://127.0.0.1:8772';
 async function login(){await page.locator('#loginForm [name=email]').fill('owner@example.test');await page.locator('#loginForm [name=password]').fill('test-password');await page.locator('#loginForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#loginDialog').open);}
 async function complete(){await page.waitForFunction(()=>/取り込みました|取り込み済み|完了できません/.test(document.querySelector('#githubSyncStatus').textContent));}
 try{
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#loginDialog').open);
  assert.equal(syncRequests.length,0);assert.equal(await page.locator('.card').count(),0);
  await login();await page.waitForFunction(()=>document.querySelector('#githubConfirm').open);assert.equal(syncRequests.length,0);await page.locator('#githubLater').click();assert.equal(await page.locator('.card').count(),0);await page.locator('#logout').click();await login();await page.waitForFunction(()=>document.querySelector('#githubConfirm').open);await page.locator('#githubYes').click();await complete();assert.match(await page.locator('#githubSyncStatus').textContent(),/画像1枚/);assert.equal(await page.locator('.card h3').textContent(),'Example');assert.match(await page.locator('.card-bottom').textContent(),/2026-10-10/);
  assert.equal(syncRequests.length,1);assert.equal(await page.locator('#githubDialog').evaluate(d=>d.open),false);
  await page.getByRole('button',{name:'Example の詳細',exact:true}).click();await page.waitForFunction(()=>{const i=document.querySelector('#detailPreview img');return i&&i.complete&&i.naturalWidth>0;});await page.locator('#editForm [name=title]').fill('Edited automatically imported idea');await page.locator('#editForm [name=body]').fill('My notes');await page.locator('#editForm [type=submit]').click();await page.locator('#approveEdit').click();await page.waitForFunction(()=>!document.querySelector('#detail').open);
  await page.reload();await page.waitForFunction(()=>document.querySelector('#loginDialog').open);assert.equal(syncRequests.length,1);assert.equal(await page.locator('.card').count(),0);
  await login();await complete();assert.equal(await page.locator('.card').count(),1);assert.equal(await page.locator('.card h3').textContent(),'Edited automatically imported idea');
  console.log('PASS: confirmation skips or imports GitHub document and image, reload requires login, repeat preserves edits without duplicate');
  await page.locator('#logout').click();
  await page.route('**/api/github-pending',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'GitHub listing unavailable'})}));
  await login();await complete();assert.equal(await page.locator('.card').count(),1);assert.match(await page.locator('#githubSyncStatus').textContent(),/既存資料は利用できます/);
  await page.unroute('**/api/github-pending');await page.locator('#logout').click();
  await page.route('**/api/github-pending',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({pending:1,already_imported:1})}));
  let release,reached;const hold=new Promise(r=>release=r),intercepted=new Promise(r=>reached=r);
  await page.route('**/api/sync-github',async route=>{const response=await route.fetch();reached();await hold;await route.fulfill({response});});
  await login();await page.waitForFunction(()=>document.querySelector('#githubConfirm').open);await page.locator('#githubYes').click();await intercepted;await page.locator('#logout').click();release();
  await page.waitForFunction(()=>document.querySelector('#githubSyncStatus').hidden);
  await page.unroute('**/api/sync-github');await page.unroute('**/api/github-pending');assert.equal(await page.locator('.card').count(),0);
  const before=syncRequests.length;await page.goto('about:blank');await page.goto(base+'/#type=recovery&access_token=owner-token');await page.waitForFunction(()=>document.querySelector('#recoveryDialog').open);assert.equal(syncRequests.length,before);assert.equal(await page.locator('.card').count(),0);
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);assert.deepEqual(errors,[]);
  console.log('PASS: GitHub failure preserves normal vault use; logout discards late sync UI; unauthenticated and recovery pages never synchronize');
 }finally{await browser.close();}
})().catch(e=>{console.error('Auto-sync browser verification failed:',e.name);console.error(e.stack.split('\n').filter(s=>s.trim().startsWith('at ')).join('\n'));process.exit(1);});
