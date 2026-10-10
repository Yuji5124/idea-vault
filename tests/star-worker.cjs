const vm=require('node:vm');const fs=require('node:fs');const assert=require('node:assert/strict');const {webcrypto}=require('node:crypto');
const {Blob}=require('node:buffer');
const base=process.env.STAR_FIXTURE||'http://127.0.0.1:8774';
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5WQAAAAASUVORK5CYII=','base64');
(async()=>{
 let listener,failImage=false,offline=false;const local={},session={};let imageCalls=0,saveCalls=0;
 const area=obj=>({get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).filter(k=>k in obj).map(k=>[k,obj[k]])),set:async data=>Object.assign(obj,data),remove:async key=>delete obj[key]});
 const chrome={runtime:{id:'a'.repeat(32),getURL:p=>'chrome-extension://'+'a'.repeat(32)+'/'+p,onMessage:{addListener:l=>listener=l}},storage:{local:area(local),session:{...area(session),setAccessLevel:async ({accessLevel})=>assert.equal(accessLevel,'TRUSTED_CONTEXTS')}},permissions:{contains:async()=>true}};
 const context=vm.createContext({chrome,URL,TextEncoder,TextDecoder,Uint8Array,crypto:webcrypto,AbortSignal,btoa:s=>Buffer.from(s,'binary').toString('base64'),fetch:async (url,opts)=>{
   assert.equal(opts.credentials,'omit');assert.equal(opts.redirect,'error');
   if(url.includes('oaiusercontent.com')){imageCalls++;if(failImage)return new Response('',{status:403});return new Response(png,{headers:{'Content-Type':'image/png'}});}
   if(offline)throw Error('synthetic network failure');if(url.endsWith('/api/star-save'))saveCalls++;
   return fetch(base+new URL(url).pathname,{...opts,headers:{...opts.headers,Origin:'chrome-extension://'+'a'.repeat(32)}});
 }});
 vm.runInContext(fs.readFileSync('chrome-extension/background.js','utf8'),context);
 const options={id:chrome.runtime.id,url:chrome.runtime.getURL('options.html')};const chat={id:chrome.runtime.id,url:'https://chatgpt.com/c/worker-fixture',tab:{id:1}};
 const send=(message,sender=options)=>new Promise(resolve=>listener(message,sender,resolve));
 assert.equal((await send({type:'login',email:'owner@example.test',password:'test-password'})).ok,true);
 assert.equal((await send({type:'settings',target:'https://idea-vault-cmgl.onrender.com',enabled:true})).ok,true);
 const capture={title:'Worker原文',body:'# Worker\n\n原文そのまま',imageUrls:[]};
 let result=await send({type:'save',capture},chat);assert.equal(result.ok,true);assert.equal(result.images,0);
 result=await send({type:'save',capture},chat);assert.equal(result.already_saved,true);
 const withImage={...capture,body:'Original image',imageUrls:['https://assets.oaiusercontent.com/original.png']};
 result=await send({type:'save',capture:withImage},chat);assert.equal(result.ok,true);assert.equal(result.images,1);
 failImage=true;const before=saveCalls;result=await send({type:'save',capture:{...withImage,body:'must not partially save'}},chat);assert.equal(result.ok,false);assert.match(result.error,/元画像/);assert.equal(saveCalls,before);failImage=false;
 for(const url of ['https://chatgpt.com/backend-api/image','https://evil.example/image.png','https://assets.oaiusercontent.com/image.png?width=200','blob:https://chatgpt.com/abc']){const count=imageCalls;result=await send({type:'save',capture:{...capture,imageUrls:[url]}},chat);assert.equal(result.ok,false);assert.equal(imageCalls,count);}
 offline=true;result=await send({type:'save',capture},chat);assert.equal(result.ok,false);assert.match(result.error,/接続できません/);offline=false;
 result=await send({type:'status'},chat);assert.equal(result.ok,false);assert(!JSON.stringify(result).includes('owner-token'));
 result=await send({type:'save',capture},{...chat,url:'https://evil.example/c/abc'});assert.equal(result.ok,false);
 assert(!JSON.stringify(local).includes('owner-token'));assert(!JSON.stringify(local).includes('test-password'));
 await send({type:'logout'});result=await send({type:'save',capture},chat);assert.equal(result.ok,false);assert.match(result.error,/ログイン/);
 console.log('PASS: worker-only auth, original image bytes/Storage re-fetch, duplicate, image failure blocks all save, no private API/cookie/external/thumbnail fetch, network retry, sender isolation, no persistent credentials');
})().catch(e=>{console.error(e.name);console.error(e.stack);process.exitCode=1;});
