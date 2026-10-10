/* DOM adapter only: no network, tokens, ChatGPT private API or cookies. */
(() => {
  const ignored='button,svg,script,style,[aria-hidden="true"],.sr-only';
  function inline(node) {
    if(node.nodeType===3)return node.textContent;
    if(node.nodeType!==1||node.matches(ignored))return '';
    const text=[...node.childNodes].map(inline).join('');
    const tag=node.tagName.toLowerCase();
    if(tag==='br')return '\n';if(tag==='img')return '';if(tag==='strong'||tag==='b')return '**'+text+'**';if(tag==='em'||tag==='i')return '*'+text+'*';
    if(tag==='code')return '`'+text+'`';if(tag==='a')return '['+text+']('+node.getAttribute('href')+')';
    return text;
  }
  function block(node) {
    if(node.nodeType===3)return node.textContent;
    if(node.nodeType!==1||node.matches(ignored))return '';
    const tag=node.tagName.toLowerCase();
    if(/^h[1-6]$/.test(tag))return '#'.repeat(+tag[1])+' '+inline(node)+'\n\n';
    if(tag==='p')return inline(node)+'\n\n';
    if(tag==='pre'){const code=node.querySelector('code');const match=(code?.className||'').match(/language-([\w+-]+)/);const raw=(code||node).textContent;let fence='```';while(raw.includes(fence))fence+='`';return fence+(match?.[1]||'')+'\n'+raw.replace(/\n$/,'')+'\n'+fence+'\n\n';}
    if(tag==='ul'||tag==='ol')return [...node.children].map((item,index)=>(tag==='ol'?(index+1)+'. ':'- ')+[...item.childNodes].map(n=>n.nodeType===1&&['UL','OL'].includes(n.tagName)?'\n'+block(n).trimEnd().split('\n').map(t=>'  '+t).join('\n'):inline(n)).join('')+'\n').join('')+'\n';
    if(tag==='blockquote')return [...node.childNodes].map(block).join('').trimEnd().split('\n').map(t=>'> '+t).join('\n')+'\n\n';
    if(tag==='table'){const rows=[...node.querySelectorAll('tr')].map(r=>[...r.querySelectorAll('th,td')].map(c=>inline(c).replace(/\|/g,'\\|').replace(/\n/g,'<br>')));if(!rows.length)return '';const line=r=>'| '+r.join(' | ')+' |\n';return line(rows[0])+line(rows[0].map(()=> '---'))+rows.slice(1).map(line).join('')+'\n';}
    if(tag==='hr')return '---\n\n';
    return [...node.childNodes].map(block).join('');
  }
  function messages(root=document){return [...root.querySelectorAll('[data-message-author-role]')].filter(n=>['user','assistant'].includes(n.dataset.messageAuthorRole));}
  function text(message){if(message.querySelector('math,.katex,.MathJax'))throw Error('数式の原文をDOMから取得できません。');const rendered=message.querySelector('.markdown');return rendered?[...rendered.childNodes].map(block).join('').trim():message.innerText?.trim()||message.textContent.trim();}
  function images(message){return [...message.querySelectorAll('img')].filter(img=>!img.closest('[aria-hidden="true"]')&&!/avatar|icon/i.test(img.alt||'')).map(img=>({url:img.dataset.originalSrc||img.closest('a[download]')?.href||img.currentSrc||img.src,alt:img.alt||'生成画像'}));}
  function capture(marker,root=document){
    const list=messages(root);const end=list.indexOf(marker);if(end<0||marker.dataset.messageAuthorRole!=='user'||marker.textContent.trim()!=='※')throw Error('単独の※ではありません。');
    let prior=list.slice(0,end);
    const lastNormalUser=prior.map(n=>n.dataset.messageAuthorRole==='user'&&n.textContent.trim()!=='※').lastIndexOf(true);
    const earlierMarker=prior.findIndex((n,i)=>i>lastNormalUser&&n.dataset.messageAuthorRole==='user'&&n.textContent.trim()==='※');
    if(earlierMarker>=0)prior=prior.slice(0,earlierMarker);
    const answers=prior.filter(n=>n.dataset.messageAuthorRole==='assistant');const latest=answers.at(-1);
    if(!latest||latest.matches('[data-is-streaming="true"]')||latest.querySelector('[data-is-streaming="true"]'))throw Error('完成済みの回答が見つかりません。');
    let target=latest;let body=text(target);let ambiguous=false;
    if(!body){target=answers.slice(0,-1).reverse().find(n=>text(n));body=target?text(target):'';ambiguous=true;}
    if(!body)throw Error('保存する文章がありません。');
    const direct=images(latest);
    // Never attach a prior answer's images silently. Limit candidates to the recent 3 answers.
    const candidates=direct.length?direct:answers.slice(-3).reverse().flatMap(n=>images(n));
    if(candidates.length&&!direct.length)ambiguous=true;
    if(target!==latest)ambiguous=true;
    const heading=target.querySelector('.markdown h1,.markdown h2,.markdown h3');
    const title=(heading?.textContent.trim()||body.split('\n').find(t=>t.trim())?.replace(/^#+\s*/, '')||'ChatGPTアイデア').slice(0,200);
    return {title,body,imageUrls:[...new Set(candidates.map(i=>i.url))],ambiguous};
  }
  globalThis.VaultDOM={messages,text,images,capture};
})();
