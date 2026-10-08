// Optional browser test: requires Playwright and a running server using an EMPTY test vault.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

(async () => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(),'idea-vault-ui-'));
  const browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {}), args:['--no-sandbox']});
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.VAULT_TEST_URL || 'http://127.0.0.1:8765';
  const data=async()=> (await (await page.request.get(base+'/api/records')).json()).records;
  const waitCount=async count=>{await page.waitForFunction(async expected=>(await(await fetch('/api/records')).json()).records.length===expected,count);await page.waitForTimeout(150);};
  try {
    await page.goto(base);
    assert.equal((await data()).length,0,'Use an empty temporary vault, never personal data');
    await page.locator('#fileInput').setInputFiles([{name:'2026-10-07_蜘蛛.txt',mimeType:'text/plain',buffer:Buffer.from('痕跡から見えない対象を推測する')},{name:'memo.md',mimeType:'text/markdown',buffer:Buffer.from('# コンセプト')}]);
    await waitCount(2);
    let records=await data();
    assert(records.some(r=>r.files[0].name==='2026-10-07_蜘蛛.txt'));
    console.log('PASS: multiple file selection, date prefix and existing prefix');

    const folder=path.join(temp,'蜘蛛ゲーム');await fs.mkdir(folder);
    await fs.writeFile(path.join(folder,'memo.md'),'# 蜘蛛ゲーム');
    const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5WQAAAAASUVORK5CYII=','base64');
    await fs.writeFile(path.join(folder,'game.png'),pixel);
    await page.locator('#folderInput').setInputFiles(folder);
    await waitCount(3);
    records=await data();const grouped=records.find(r=>r.title==='蜘蛛ゲーム');
    assert.equal(grouped.files.length,2);assert.match(grouped.folder,/inbox\/\d{4}-\d{2}-\d{2}_蜘蛛ゲーム/);
    await page.waitForFunction(()=>[...document.querySelectorAll('.thumbnail img')].some(i=>i.complete&&i.naturalWidth>0));
    console.log('PASS: actual folder picker, grouped IDEA, thumbnail');

    await page.locator('#dropzone').evaluate(zone=>{const dt=new DataTransfer();dt.items.add(new File(['one'],'same.txt',{type:'text/plain'}));dt.items.add(new File(['two'],'same.txt',{type:'text/plain'}));zone.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt}));});
    await waitCount(5);
    console.log('PASS: multiple-file drag and drop');

    // The browser cannot attach a real directory to synthetic DataTransfer. Exercise
    // the directory-entry API with realistic paginated/nested entries separately.
    await page.locator('#dropzone').evaluate(zone=>{
      const f=(name,text)=>({name,isFile:true,isDirectory:false,file:ok=>ok(new File([text],name,{type:'text/plain'}))});
      const dir=(name,children)=>({name,isFile:false,isDirectory:true,createReader:()=>{let done=false;return{readEntries:ok=>{ok(done?[]:children);done=true;}};}});
      const root=dir('ドロップフォルダ',[f('same.txt','first'),dir('nested',[f('same.txt','second')])]);
      const event=new Event('drop',{bubbles:true});Object.defineProperty(event,'dataTransfer',{value:{items:[{webkitGetAsEntry:()=>root}],files:[]}});zone.dispatchEvent(event);
    });
    await waitCount(6);
    const directory=(await data()).find(r=>r.title==='ドロップフォルダ');
    assert.equal(directory.files.length,2);assert(directory.files.some(f=>/_01\.txt$/.test(f.name)));
    console.log('PASS: directory-entry drop traversal, nested folder, collision numbering');

    await page.locator('#newNote').click();await page.locator('#noteForm [name=title]').fill('痕跡の原理');await page.locator('#noteForm [name=type]').selectOption('PRINCIPLE');await page.locator('#noteForm [name=body]').fill('見えない対象を痕跡から推測する');await page.locator('#noteForm [type=submit]').click();await waitCount(7);
    const principle=(await data()).find(r=>r.title==='痕跡の原理');
    await page.getByRole('button',{name:'蜘蛛ゲーム の詳細',exact:true}).click();
    await page.locator('#editForm [name=tags]').fill('蜘蛛, 探索');await page.locator('#editForm [name=jima_filter]').selectOption('GOOD');await page.locator('#editForm [name=comment]').fill('ルールが一文で伝わる');await page.locator('#editForm [name=inbox]').uncheck();await page.locator(`#relations input[value="${principle.id}"]`).check();await page.locator('#editForm [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#detail').open);
    await page.locator('#search').fill('痕跡');assert.equal(await page.locator('.card').count(),3); // text upload, principle, linked IDEA
    await page.locator('#rating').selectOption('GOOD');assert.equal(await page.locator('.card').count(),1);
    await page.locator('#search').fill('');await page.locator('#rating').selectOption('');
    console.log('PASS: note, classification, links, JIMA FILTER, related search');

    await page.getByRole('button',{name:'蜘蛛ゲーム の詳細',exact:true}).click();await page.locator('summary').click();await page.locator('#transferFiles input').first().check();page.once('dialog',dialog=>dialog.accept('分離したアイデア'));await page.locator('#splitFiles').click();await waitCount(8);await page.waitForFunction(()=>document.querySelector('#editForm [name=title]').value==='分離したアイデア');
    const split=(await data()).find(r=>r.title==='分離したアイデア');assert.equal(split.files.length,1);assert.equal((await data()).find(r=>r.id===grouped.id).files.length,1);
    await page.locator('#transferFiles input').first().check();await page.locator('#transferTarget').selectOption(grouped.id);await page.locator('#moveFiles').click();await page.waitForFunction(()=>document.querySelector('#editForm [name=title]').value==='蜘蛛ゲーム');assert.equal((await data()).find(r=>r.id===grouped.id).files.length,2);
    await page.locator('#closeDetail').click();console.log('PASS: split and merge through UI, files retained');

    await page.reload();await page.waitForSelector('.card');assert.equal((await data()).length,8);
    await page.screenshot({path:path.join(temp,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(temp,'mobile.png'),fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'mobile must not overflow');
    assert.deepEqual(errors,[]);console.log('PASS: reload, mobile layout, no page errors');console.log('Screenshots: '+temp);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
