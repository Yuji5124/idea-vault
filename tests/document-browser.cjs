// Start python3 tests/test_document_import.py; uses only synthetic data.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.name));
  const base='http://127.0.0.1:8771';
  const github='https://github.com/Yuji5124/idea-vault/blob/main/ideas/2026-10-10_example.md';
  try{
    await page.goto(base);await page.waitForFunction(()=>document.querySelector('#loginDialog').open);
    assert.equal(await page.locator('.card').count(),0);
    await page.locator('#loginForm [name=email]').fill('owner@example.test');await page.locator('#loginForm [name=password]').fill('test-password');await page.locator('#loginForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#loginDialog').open);
    const githubImport=async()=>{await page.locator('#githubImport').click();await page.locator('#githubForm [name=url]').fill(github);await page.locator('#githubForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#githubDialog').open);};
    await githubImport();assert.equal(await page.locator('.card').count(),1);
    assert.equal(await page.locator('.card h3').textContent(),'Example');assert.match(await page.locator('.card-bottom').textContent(),/2026-10-10/);
    await page.getByRole('button',{name:'Example の詳細',exact:true}).click();
    assert.match(await page.locator('#editForm [name=body]').inputValue(),/実験の本文/);
    assert.equal(await page.locator('#editForm [name=record_date]').inputValue(),'2026-10-10');assert.equal(await page.locator('#detailPreview img').count(),0);
    const downloadEvent=page.waitForEvent('download');await page.locator('.file-link').click();const download=await downloadEvent;
    const fs=require('node:fs/promises');assert.match(await fs.readFile(await download.path(),'utf8'),/画像ファイルは未添付/);
    await page.locator('#editForm [name=title]').fill('B edited');await page.locator('#editForm [name=record_date]').fill('2026-10-11');await page.locator('#editForm [name=category]').fill('ゲーム');await page.locator('#editForm [type=submit]').click();await page.locator('#approveEdit').click();await page.waitForFunction(()=>!document.querySelector('#detail').open);
    await githubImport();assert.equal(await page.locator('.card').count(),1);assert.equal(await page.locator('.card h3').textContent(),'B edited');assert.match(await page.locator('#toast').textContent(),/取り込み済み/);
    console.log('PASS: GitHub import, original Markdown download, metadata edit, no imaginary images, duplicate import preserves edits');
    await page.locator('#dropzone').evaluate(zone=>{const dt=new DataTransfer();dt.items.add(new File(['# A earlier\n\n保存日：2026年10月9日\n\nDropped body'],'2026-10-09_drop.md',{type:'text/markdown'}));zone.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));});
    await page.waitForFunction(()=>document.querySelectorAll('.card').length===2);
    assert.deepEqual(await page.locator('.card h3').allTextContents(),['B edited','A earlier']);
    await page.locator('#sortOrder').selectOption('oldest');assert.deepEqual(await page.locator('.card h3').allTextContents(),['A earlier','B edited']);
    await page.locator('#sortOrder').selectOption('title');assert.deepEqual(await page.locator('.card h3').allTextContents(),['A earlier','B edited']);
    await page.locator('#dateFrom').fill('2026-10-10');assert.equal(await page.locator('.card').count(),1);assert.equal(await page.locator('.card h3').textContent(),'B edited');
    await page.locator('#dateTo').fill('2026-10-10');assert.equal(await page.locator('.card').count(),0);
    await page.locator('#clearOrganization').click();assert.equal(await page.locator('.card').count(),2);
    await page.locator('#search').fill('A earlier');assert.equal(await page.locator('.card').count(),1);await page.locator('#search').fill('');
    await page.reload();await page.waitForFunction(()=>document.querySelector('#loginDialog').open);assert.equal(await page.locator('.card').count(),0);
    await page.locator('#loginForm [name=email]').fill('owner@example.test');await page.locator('#loginForm [name=password]').fill('test-password');await page.locator('#loginForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#loginDialog').open);assert.equal(await page.locator('.card').count(),2);
    await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:'/tmp/idea-vault-documents-mobile.png',fullPage:true});
    await page.locator('#logout').click();assert.equal(await page.locator('.card').count(),0);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);assert.deepEqual(errors,[]);
    console.log('PASS: Markdown drop, date filters and sorting, title sorting, title search, reload isolation, mobile layout, logout');
  }finally{await browser.close();}
})().catch(e=>{console.error('Document browser verification failed:',e.name);console.error(e.stack.split('\n').filter(line=>line.trim().startsWith('at ')).join('\n'));process.exit(1);});
