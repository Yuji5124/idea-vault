const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const assert=require('node:assert/strict');

const root=path.resolve(__dirname,'..');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAGAAAABACAIAAABqVuVZAAABE0lEQVR42u3bwQ3CMBBEUWK5UDqgAw50QAc0QifcaYMDl0goEgre2TH79wpy5OexE8XO8njeD9R2NQgAAggggAAC6F+rb/1wPJ1LQdyuFxLEFAPIaA1ymP8OS2G3pVn/IZGp29KYMHVzmnSmNovOwBZ8gUb1TWnUptMRG7UZdZRGPCgaAMUNtSBEJCgbKHqQo9snQalAmhtN6FVIEEAAAQQQQAABBFBEaV6Phl6FBGUDRYcoun0SZAAUN8iCNY4EeQBFDLXmFqlL0Nj+yPZXpVNsVK+Uu8/qNej3von35hMOL7x7uOM9aZXTHTuYKp4P+pKp+gkzEwUeFAECCCCAAAIIIOqjFr6bJ0EAAQQQQAABVLReT4lR3nlUYhYAAAAASUVORK5CYII=','base64');
const records=Array.from({length:61},(_,index)=>({
  id:`record-${index+1}`,title:`Record ${String(index+1).padStart(2,'0')}`,type:'IDEA',inbox:false,
  jima_filter:'未評価',tags:[],body:'A display fixture',summary:'',category:'',relations:[],
  record_date:'2026-10-20',imported_at:'2026-10-20T00:00:00Z',created_at:'2026-10-20T00:00:00Z',updated_at:'2026-10-20T00:00:00Z',
  files:[{id:`original-${index+1}`,name:`image-${index+1}.png`,original_name:`image-${index+1}.png`,mime:'image/png',size:png.length,text:'',path:`images/image-${index+1}.png`,thumbnail:{id:`thumb-${index+1}`,name:`thumb-${index+1}.png`,original_name:'thumbnail.png',mime:'image/png',size:png.length,path:`images/thumb-${index+1}.png`}}]
}));
const requests=[];
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  if(url.pathname==='/api/config'){res.writeHead(200,{'content-type':'application/json'});res.end('{"storage":"local"}');return;}
  if(url.pathname==='/api/records'){res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({records}));return;}
  const fileMatch=url.pathname.match(/^\/api\/file\/(record-\d+)\/(thumb-\d+|original-\d+)$/);
  if(fileMatch){requests.push({record:fileMatch[1],file:fileMatch[2]});res.writeHead(200,{'content-type':'image/png','content-length':png.length});res.end(png);return;}
  const name=url.pathname==='/'?'index.html':url.pathname.slice(1);
  const full=path.resolve(root,'web',name);
  if(!full.startsWith(path.resolve(root,'web')+path.sep)&&full!==path.resolve(root,'web','index.html')){res.writeHead(404);res.end();return;}
  fs.readFile(full,(error,body)=>{if(error){res.writeHead(404);res.end();return;}res.writeHead(200,{'content-type':mime[path.extname(full)]||'application/octet-stream'});res.end(body);});
});

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>document.querySelectorAll('#records .card').length===60);
    assert.equal(await page.locator('#pagination').isVisible(),true);
    assert.equal(await page.locator('#pagination').textContent(),'前へ1 / 2次へ');
    assert.equal(await page.locator('#records .card').count(),60);
    assert.equal(await page.locator('#records .thumbnail img').count(),60);
    assert((await page.locator('#records .thumbnail img[src]').count())<60,'the initial render eagerly loaded every thumbnail');
    assert(requests.every(item=>item.file.startsWith('thumb-')),'the initial render fetched an original image');
    await page.locator('#records .card').first().scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>document.querySelector('#records .thumbnail img[src]')?.complete);
    assert(requests.length>0);
    assert(requests.every(item=>item.file.startsWith('thumb-')),'list fetched an original image');
    const layout=await page.locator('#records .grid').first().evaluate(node=>({columns:getComputedStyle(node).gridTemplateColumns.split(' ').length,ratio:getComputedStyle(node.querySelector('.thumbnail')).aspectRatio,fit:getComputedStyle(node.querySelector('img')).objectFit}));
    assert.equal(layout.columns,4);
    assert.equal(layout.ratio,'3 / 2');
    assert.equal(layout.fit,'contain');
    await page.screenshot({path:'/tmp/idea-vault-list-display.png'});
    const originalResponse=page.waitForResponse(response=>response.url().endsWith('/api/file/record-1/original-1'));
    await page.locator('#records .card').first().click();
    await originalResponse;
    assert(requests.some(item=>item.file==='original-1'),'opening details did not fetch the original image');
    await page.waitForFunction(()=>{const image=document.querySelector('#detailPreview img');return image?.complete&&image.naturalWidth===96;});
    await page.locator('#closeDetail').click();
    await page.locator('#pagination button').nth(1).click();
    assert.equal(await page.locator('#records .card').count(),1);
    assert.match(await page.locator('#pagination').textContent(),/2 \/ 2/);
    assert.deepEqual(errors,[]);
    console.log(`PASS: 60-card pages, lazy saved-thumbnail requests (${requests.filter(item=>item.file.startsWith('thumb-')).length}), detail-only original request, four-column 3:2 layout`);
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
