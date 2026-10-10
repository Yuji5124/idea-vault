const {chromium}=require('playwright');const assert=require('node:assert/strict');const path=require('node:path');const fs=require('node:fs');const os=require('node:os');
(async()=>{
 const profile=fs.mkdtempSync(path.join(os.tmpdir(),'idea-vault-extension-'));
 const extension=path.resolve('chrome-extension');
 const context=await chromium.launchPersistentContext(profile,{headless:process.env.HEADLESS!=='false',ignoreDefaultArgs:['--disable-extensions'],executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox',`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
 try{
 const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker',{timeout:10000});
 const id=new URL(worker.url()).host;
 const page=await context.newPage();await page.goto(`chrome-extension://${id}/options.html`);await page.waitForFunction(()=>document.querySelector('#extensionId').textContent.length===32);
 assert.equal(await page.locator('#state').textContent(),'未ログイン');await page.locator('#settings [name=enabled]').check();await page.locator('#settings button').click();
 await page.waitForFunction(()=>document.querySelector('#settings [name=enabled]').checked);
 const access=await worker.evaluate(async()=>({local:await chrome.storage.local.get(null),session:await chrome.storage.session.get(null)}));assert.equal(access.local.enabled,true);assert.equal(access.session.auth,undefined);
 await context.route('https://chatgpt.com/**',route=>route.fulfill({contentType:'text/html',body:'<html><body><textarea id="prompt-textarea"></textarea><main id="conversation"><div data-message-author-role="assistant"><div class="markdown"><h1>MV3 idea</h1><p>原文</p></div></div></main></body></html>'}));
 await page.goto('https://chatgpt.com/c/mv3-fixture');
 await page.waitForTimeout(300);
 await page.locator('#prompt-textarea').fill('※');await page.locator('#prompt-textarea').press('Enter');
 await page.evaluate(()=>{const n=document.createElement('div');n.dataset.messageAuthorRole='user';n.textContent='※';document.querySelector('#conversation').append(n);});
 await page.waitForFunction(()=>document.querySelector('#idea-vault-notice')?.textContent.includes('ログイン'));
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 console.log('PASS: actual Manifest V3 loads in Chromium, options and trusted session storage work, real isolated content script detects marker and reports unauthenticated save');
 }finally{await context.close();fs.rmSync(profile,{recursive:true,force:true});}
})().catch(e=>{console.error(e.name);console.error(e.stack);process.exitCode=1;});
