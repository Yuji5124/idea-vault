// Uses only the in-memory provider: python3 tests/test_cloud.py
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium', args:['--no-sandbox']});
  const base = 'http://127.0.0.1:8770';
  const context = await browser.newContext();
  const page = await context.newPage();
  const requests=[], logs=[], errors=[];
  page.on('request',r=>requests.push(r.url()));
  page.on('console',m=>logs.push(m.text()));
  page.on('pageerror',e=>errors.push(e.message));
  async function open(fragment) {
    await page.goto('about:blank');
    requests.length=0;
    await page.goto(base+'/#'+fragment);
    await page.waitForFunction(()=>document.querySelector('#recoveryDialog').open);
    assert.equal(await page.evaluate(()=>location.hash+location.search),'');
    assert.equal(await page.locator('.card').count(),0);
    assert.equal(await page.locator('#loginDialog').evaluate(d=>d.open),false);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    assert(!requests.some(url=>url.includes('owner-token')||url.includes('refresh-secret')||url.includes('token_hash')||url.includes('/api/records')||url.includes('/api/file/')));
  }
  async function submit() {
    await page.locator('#recoveryForm [name=password]').fill('new-test-password-456');
    await page.locator('#recoveryForm [name=confirm]').fill('new-test-password-456');
    await page.locator('#recoveryForm [type=submit]').click();
  }
  try {
    await open('type=recovery&access_token=owner-token&refresh_token=refresh-secret');
    await page.waitForFunction(()=>!document.querySelector('#recoveryForm [type=submit]').disabled);
    await page.locator('#recoveryForm [name=password]').fill('new-test-password-456');
    await page.locator('#recoveryForm [name=confirm]').fill('not-matching-password');
    await page.locator('#recoveryForm [type=submit]').click();
    assert.match(await page.locator('#recoveryStatus').textContent(),/一致しません/);
    await submit();
    await page.waitForFunction(()=>document.querySelector('#recoveryStatus').textContent.includes('パスワードを変更しました'));
    assert.equal(await page.locator('#recoveryForm [name=password]').inputValue(),'');
    await page.locator('#recoveryBack').click();
    await page.locator('#loginForm [name=email]').fill('owner@example.test');
    await page.locator('#loginForm [name=password]').fill('new-test-password-456');
    await page.locator('#loginForm [type=submit]').click();
    await page.waitForFunction(()=>!document.querySelector('#loginDialog').open);
    await page.locator('#logout').click();
    console.log('PASS: fragment removed, owner verified, confirmation validated, password updated, normal login');
    for (const fragment of ['type=recovery&access_token=invalid','type=recovery&access_token=expired','type=recovery&access_token=other-token','error=access_denied&error_code=otp_expired','type=signup&access_token=owner-token']) {
      await open(fragment);
      await page.waitForFunction(()=>document.querySelector('#recoveryStatus').textContent.includes('無効'));
      assert.equal(await page.locator('#recoveryForm [type=submit]').isDisabled(),true);
    }
    console.log('PASS: invalid, expired, other-user and non-recovery links rejected; vault stays empty');
    for (const hashed of ['expired-recovery-hash-123456789','other-recovery-hash-123456789','owner-recovery-hash-123456789']) {
      await open('type=recovery&token_hash='+hashed);
      await page.waitForFunction(()=>!document.querySelector('#recoveryForm [type=submit]').disabled);
      await submit();
      await page.waitForFunction(()=>!document.querySelector('#recoveryStatus').textContent.includes('登録しています'));
      assert.match(await page.locator('#recoveryStatus').textContent(),hashed.startsWith('owner-')?/パスワードを変更しました/:/無効/);
      assert.equal(await page.locator('.card').count(),0);
    }
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#loginDialog').open);
    assert.equal(await page.locator('.card').count(),0);
    await page.evaluate(()=>{location.hash='type=recovery&access_token=owner-token';});
    await page.waitForFunction(()=>document.querySelector('#recoveryDialog').open&&!document.querySelector('#recoveryForm [type=submit]').disabled);
    assert.equal(await page.evaluate(()=>location.hash),'');
    await page.locator('#recoveryBack').click();
    await page.goto(base+'/?code=unsupported-pkce');
    await page.waitForFunction(()=>document.querySelector('#recoveryDialog').open);
    assert.equal(await page.evaluate(()=>location.search),'');
    assert.match(await page.locator('#recoveryStatus').textContent(),/非対応/);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    assert.deepEqual(errors,[]);
    for(const secret of ['owner-token','refresh-secret','new-test-password-456','owner-recovery-hash-123456789'])assert(!logs.some(line=>line.includes(secret)));
    console.log('PASS: token_hash verified on submission, no recovery auto-login, PKCE rejected, no storage/URL/console token leakage');
  } finally {await browser.close();}
})().catch(error=>{console.error('Recovery browser verification failed:',error.name);console.error(error.stack.split('\n').filter(line=>line.trim().startsWith('at ')).join('\n'));process.exit(1);});
