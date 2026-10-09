'use strict';
// Runs synchronously before app.js or any application network request.
// Fragments are never sent to the HTTP server. Keep only the needed fields
// in this closure, then replace the history entry immediately.
const passwordRecovery = (() => {
  let material = null;
  let invalid = false;
  let hasLink = false;
  function capture() {
    material = null;
    invalid = false;
    hasLink = Boolean(location.hash || location.search);
    if (!hasLink) return;
    const fragment = new URLSearchParams(location.hash.slice(1));
    invalid = Boolean(location.search) || fragment.get('type') !== 'recovery';
    if (!invalid) {
      if (fragment.has('token_hash') && !fragment.has('access_token') && /^[A-Za-z0-9_-]{20,512}$/.test(fragment.get('token_hash'))) {
        material = {type: 'recovery', token_hash: fragment.get('token_hash')};
      } else if (fragment.has('access_token') && !fragment.has('token_hash') && fragment.get('access_token').length <= 12000 && fragment.get('access_token')) {
        material = {type: 'recovery', access_token: fragment.get('access_token')};
      } else invalid = true;
    }
    history.replaceState(null, '', location.pathname);
  }
  capture();
  addEventListener('hashchange', () => {
    capture();
    if (hasLink) dispatchEvent(new Event('vault-recovery'));
  });
  addEventListener('pagehide', () => {material = null; document.querySelector('#recoveryForm')?.reset();});
  const failure = '再設定リンクが無効・期限切れ、または本人用ではありません。新しいメールを発行してください。PKCEコードやURLクエリのリンクは非対応です。';
  async function post(path, body) {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), cache: 'no-store'});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || failure);
    return result;
  }
  return {
    async open() {
      if (!hasLink) return false;
      const dialog = document.querySelector('#recoveryDialog');
      const form = document.querySelector('#recoveryForm');
      const status = document.querySelector('#recoveryStatus');
      const submit = form.querySelector('[type=submit]');
      const fields = [...form.querySelectorAll('input')];
      const disable = value => {submit.disabled = value; fields.forEach(field => field.disabled = value);};
      disable(true);
      dialog.addEventListener('cancel', event => event.preventDefault());
      document.querySelector('#recoveryBack').onclick = () => {
        material = null;
        form.reset();
        dialog.close();
        document.querySelector('#loginDialog').showModal();
      };
      dialog.showModal();
      if (invalid || !material) {status.textContent = failure; return true;}
      status.textContent = material.token_hash ? '新しいパスワードの登録時に、リンクの有効期限と本人確認を検証します。' : '再設定リンクを確認しています…';
      try {
        if (material.access_token) await post('/api/recovery-check', material);
        if (!material) return true; // User may have returned to login while checking.
        disable(false);
        if (material.access_token) status.textContent = '本人確認が完了しました。新しいパスワードを入力してください。';
      } catch {material = null; status.textContent = failure; return true;}
      form.onsubmit = async event => {
        event.preventDefault();
        if (!material || submit.disabled) return;
        if (form.elements.password.value !== form.elements.confirm.value) {status.textContent = '確認用パスワードが一致しません。'; return;}
        disable(true);
        const body = {...material, password: form.elements.password.value};
        material = null; // One explicit attempt; require a fresh mail on failure.
        form.reset();
        status.textContent = '登録しています…';
        try {
          const result = await post('/api/reset-password', body);
          status.textContent = result.sessions_revoked ? 'パスワードを変更しました。ログイン画面へ戻って新しいパスワードでログインしてください。' : 'パスワードを変更しましたが、既存セッションの終了に失敗しました。Supabaseでセッションを確認してください。新しいパスワードでログインできます。';
        } catch (error) {status.textContent = error.message;}
        finally {delete body.password; delete body.access_token; delete body.token_hash;}
      };
      return true;
    }
  };
})();
