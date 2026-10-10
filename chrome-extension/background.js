class UserError extends Error {}
const TARGET = 'https://idea-vault-cmgl.onrender.com';
const MAX_IMAGE = 20 * 1024 * 1024;
const inFlight = new Map();
const ready = chrome.storage.session.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
function optionsSender(sender) { return sender.id === chrome.runtime.id && sender.url?.startsWith(chrome.runtime.getURL('options.html')); }
function chatSender(sender) { try { return sender.id === chrome.runtime.id && sender.tab && new URL(sender.url).origin === 'https://chatgpt.com'; } catch { return false; } }
async function config() { return {enabled: false, target: TARGET, ...(await chrome.storage.local.get(['enabled','target']))}; }
async function call(path, payload, auth = true, retry = true) {
  const cfg = await config();
  if (cfg.target !== TARGET) throw new UserError('接続先が許可されていません。');
  let session = (await chrome.storage.session.get('auth')).auth;
  if (auth && !session) throw new UserError('拡張機能の設定で本人ログインしてください。');
  let response;
  try { response = await fetch(TARGET + path, {method:'POST', credentials:'omit', redirect:'error', headers:{'Content-Type':'application/json', ...(auth ? {Authorization:'Bearer '+session.access_token} : {})}, body:JSON.stringify(payload), signal:AbortSignal.timeout(120000)}); }
  catch { throw new UserError('IDEA VAULTへ接続できません。通信・Renderの起動を確認して再試行してください。'); }
  if (response.status === 401 && auth && retry) {
    try { session = await call('/api/refresh',{refresh_token:session.refresh_token},false,false); await chrome.storage.session.set({auth:session}); }
    catch { await chrome.storage.session.remove('auth'); throw new UserError('ログイン期限切れです。設定画面で再ログインしてください。'); }
    return call(path,payload,true,false);
  }
  if (!response.ok) throw new UserError(response.status === 403 ? '拡張機能IDの許可設定を確認してください（HTTP 403）。' : response.status === 401 ? '本人ログインに失敗しました。' : `保存先が操作を拒否しました（HTTP ${response.status}）。`);
  return response.json();
}
async function hash(raw) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join(''); }
function originalURL(value) {
  if(typeof value!=='string'||value.length>16384)throw new UserError('画像URLの形式が不正です。');
  const url = new URL(value);
  if(url.protocol !== 'https:' || url.username || url.password || !/(^|\.)oaiusercontent\.com$/.test(url.hostname) || /(^|\/)(backend-api|api)(\/|$)/.test(url.pathname) || /thumbnail|thumb|preview/i.test(url.pathname) || [...url.searchParams.keys()].some(k=>/^(w|h|width|height|resize|format|quality)$/i.test(k))) throw new UserError('元画像の公開URLを取得できません。非公開API・縮小画像・Cookieは使用しません。');
  return url.href;
}
async function imageFile(value) {
  const url = originalURL(value);
  if (!await chrome.permissions.contains({origins:['https://*.oaiusercontent.com/*']})) throw new UserError('設定画面で画像取得権限を許可してください。');
  let response;
  try { response = await fetch(url,{credentials:'omit',redirect:'error',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(60000)}); }
  catch { throw new UserError('元画像を取得できません。通信または画像URLの期限を確認してください。'); }
  if(!response.ok) throw new UserError('元画像を取得できません。URLが期限切れか、公開取得できない画像です。');
  const reader=response.body.getReader(); const chunks=[];let total=0;
  for (;;) { const {done,value}=await reader.read(); if(done)break;total+=value.length;if(total>MAX_IMAGE){await reader.cancel();throw new UserError('画像が20MBを超えています。');}chunks.push(value); }
  const raw=new Uint8Array(total);let offset=0;for(const chunk of chunks){raw.set(chunk,offset);offset+=chunk.length;}
  let mime='';if(raw[0]===137&&raw[1]===80&&raw[2]===78&&raw[3]===71)mime='image/png';else if(raw[0]===255&&raw[1]===216&&raw[2]===255)mime='image/jpeg';else if(new TextDecoder().decode(raw.slice(0,4))==='RIFF'&&new TextDecoder().decode(raw.slice(8,12))==='WEBP')mime='image/webp';
  if(!mime)throw new UserError('元画像の形式に対応していません。PNG・JPEG・WebPが必要です。');
  let binary='';for(let i=0;i<raw.length;i+=8192)binary+=String.fromCharCode(...raw.subarray(i,i+8192));
  return {mime,data:btoa(binary),sha:await hash(raw),bytes:total};
}
async function save(payload) {
  const cfg=await config();if(!cfg.enabled)throw new UserError('自動保存はOFFです。設定画面でONにしてください。');
  if(!(await chrome.storage.session.get('auth')).auth)throw new UserError('拡張機能の設定で本人ログインしてください。');
  if(typeof payload.body!=='string'||!payload.body.trim()||new TextEncoder().encode(payload.body).length>2*1024*1024||typeof payload.title!=='string'||payload.title.length>200||!Array.isArray(payload.imageUrls)||payload.imageUrls.length>8)throw new UserError('取得対象の形式・サイズを確認してください。');
  const urls=[...new Set(payload.imageUrls)];const files=[];let bytes=0;
  // Fail before creating any record if an image cannot be retrieved. No silent text-only success.
  for(const url of urls){const item=await imageFile(url);bytes+=item.bytes;if(bytes>30*1024*1024)throw new UserError('画像合計が30MBを超えています。');files.push(item);}
  const expected=[await hash(new TextEncoder().encode(payload.body)),...files.map(i=>i.sha)];
  const result=await call('/api/star-save',{title:payload.title,body:payload.body,source_url:payload.source_url,images:files.map(({mime,data})=>({mime,data}))});
  const status=await call('/api/star-status',{id:result.id});
  if(JSON.stringify(status.hashes)!==JSON.stringify(expected)||!result.verified)throw new UserError('保存ファイルの再取得検証に失敗しました。同じ※で再試行できます。');
  return {ok:true,texts:result.texts,images:result.images,already_saved:result.already_saved};
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  (async()=>{await ready;
    if(chatSender(sender)) {
      if(message?.type==='state')return {ok:true,enabled:(await config()).enabled};
      if(message?.type!=='save')throw new UserError('許可されていない操作です。');
      const source=new URL(sender.url);if(!/^\/c\/[a-zA-Z0-9-]{1,100}$/.test(source.pathname))throw new UserError('保存済みの通常会話ページで実行してください。');
      const payload={...message.capture,source_url:source.origin+source.pathname};
      const key=await hash(new TextEncoder().encode(JSON.stringify(payload)));
      if(!inFlight.has(key))inFlight.set(key,save(payload).finally(()=>inFlight.delete(key)));
      return inFlight.get(key);
    }
    if(!optionsSender(sender))throw new UserError('許可されていない送信元です。');
    if(message.type==='status')return {ok:true,...await config(),loggedIn:!!(await chrome.storage.session.get('auth')).auth,extensionId:chrome.runtime.id};
    if(message.type==='settings'){if(message.target!==TARGET)throw new UserError('この版の接続先は既存のIDEA VAULTのみです。');await chrome.storage.local.set({enabled:!!message.enabled,target:TARGET});return {ok:true};}
    if(message.type==='login'){const auth=await call('/api/login',{email:message.email,password:message.password},false);await chrome.storage.session.set({auth});return {ok:true};}
    if(message.type==='logout'){try{await call('/api/logout',{});}finally{await chrome.storage.session.remove('auth');}return {ok:true};}
    if(message.type==='test'){const auth=(await chrome.storage.session.get('auth')).auth;if(!auth)throw new UserError('ログインしてください。');const refreshed=await call('/api/refresh',{refresh_token:auth.refresh_token},false);await chrome.storage.session.set({auth:refreshed});return {ok:true};}
    throw new UserError('操作を確認してください。');
  })().then(respond,error=>respond({ok:false,error:error instanceof UserError ? error.message : '処理に失敗しました。設定・ログイン・通信を確認してください。'}));
  return true;
});
