(() => {
  const seen=new WeakSet();const ids=new Set();let url=location.href;let armedUntil=0;
  const key=m=>location.pathname+':' +(m.dataset.messageId||VaultDOM.messages().indexOf(m));
  const remember=m=>{seen.add(m);ids.add(key(m));};
  const composer=()=>document.querySelector('#prompt-textarea');
  const arm=()=>{const input=composer();if((input?.value||input?.innerText||'').trim()==='※')armedUntil=Date.now()+15000;};
  document.addEventListener('keydown',e=>{if(e.isTrusted&&e.key==='Enter'&&!e.shiftKey&&!e.isComposing)arm();},true);
  document.addEventListener('click',e=>{if(e.isTrusted&&e.target.closest('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="プロンプトを送信する"]'))arm();},true);
  const markExisting=()=>VaultDOM.messages().filter(m=>m.dataset.messageAuthorRole==='user'&&m.textContent.trim()==='※').forEach(remember);
  markExisting();
  function notice(message,retry){const old=document.getElementById('idea-vault-notice');old?.remove();const box=document.createElement('div');box.id='idea-vault-notice';box.setAttribute('role','status');Object.assign(box.style,{position:'fixed',right:'20px',bottom:'20px',zIndex:'2147483647',padding:'16px',maxWidth:'380px',background:'#173c35',color:'white',borderRadius:'10px',boxShadow:'0 2px 12px #0005',font:'14px sans-serif'});box.textContent=message;const close=document.createElement('button');close.textContent='閉じる';close.onclick=()=>box.remove();box.append(' ',close);if(retry){const button=document.createElement('button');button.textContent='再試行';button.onclick=()=>{box.remove();retry();};box.append(' ',button);}document.body.append(box);if(!retry)setTimeout(()=>box.remove(),8000);}
  async function run(marker){let capture;
    try{capture=VaultDOM.capture(marker);}catch(error){notice(error.message||'保存対象を特定できません。完成済み回答を確認してください。');return;}
    if(capture.ambiguous&&!confirm(`IDEA VAULT：直近3回答内の画像候補を別回答の文章と組み合わせます。関連が不明な場合はキャンセルしてください。\nタイトル：${capture.title}\n画像候補：${capture.imageUrls.length}枚\nこの組み合わせを保存しますか？（無関係ならキャンセル）`))return;
    try{const response=await chrome.runtime.sendMessage({type:'save',capture});if(!response?.ok){notice(response?.error||'保存できませんでした。',()=>run(marker));return;}notice(`IDEA VAULTに保存しました${response.already_saved?'（取り込み済み）':''}。文章${response.texts}件・画像${response.images}枚。`);}
    catch{notice('拡張機能に接続できません。ページを再読み込みしてください。',()=>run(marker));}
  }
  let timer;
  new MutationObserver(()=>{if(timer)return;timer=setTimeout(async()=>{timer=null;
    if(location.href!==url){url=location.href;markExisting();return;}
    const markers=VaultDOM.messages().filter(m=>m.dataset.messageAuthorRole==='user'&&m.textContent.trim()==='※'&&!seen.has(m)&&!ids.has(key(m)));
    for(const marker of markers){remember(marker);if(Date.now()>armedUntil)continue;armedUntil=0;try{const state=await chrome.runtime.sendMessage({type:'state'});if(state?.enabled)await run(marker);}catch{notice('拡張機能の設定を確認してください。');}}
  },400);}).observe(document.body,{childList:true,subtree:true,characterData:true});
})();
