const $=s=>document.querySelector(s);
async function send(data){const response=await chrome.runtime.sendMessage(data);if(!response?.ok)throw Error(response?.error||'処理に失敗しました。');return response;}
async function refresh(){const state=await send({type:'status'});$('#extensionId').textContent=state.extensionId;$('#settings').elements.enabled.checked=state.enabled;$('#state').textContent=state.loggedIn?'本人ログイン済み':'未ログイン';}
$('#settings').onsubmit=async e=>{e.preventDefault();try{await send({type:'settings',enabled:e.target.elements.enabled.checked,target:e.target.elements.target.value});await refresh();}catch(error){$('#state').textContent=error.message;}};
$('#login').onsubmit=async e=>{e.preventDefault();const form=e.target;const email=form.elements.email.value,password=form.elements.password.value;form.elements.password.value='';try{await send({type:'login',email,password});await refresh();}catch(error){$('#state').textContent=error.message;}};
for(const type of ['test','logout'])$('#'+type).onclick=async()=>{try{await send({type});await refresh();if(type==='test')$('#state').textContent='本人認証・接続テスト成功';}catch(error){$('#state').textContent=error.message;}};
$('#images').onclick=async()=>{try{const allowed=await chrome.permissions.request({origins:['https://*.oaiusercontent.com/*']});$('#state').textContent=allowed?'画像取得権限を許可しました':'画像取得権限を許可していません';}catch{$('#state').textContent='画像取得権限を設定できません';}};
refresh().catch(()=>$('#state').textContent='設定を読み込めません');
