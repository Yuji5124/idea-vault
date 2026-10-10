# IDEA VAULT｜ChatGPT ※保存（試作）

通常のChatGPT回答を、追加のAI処理なしで本人専用SupabaseのINBOXへ保存するManifest V3拡張です。ChatGPT API／OpenAI API／有料AIサービスは使いません。GitHubへの資料保存・取り込みを経由せず、既存CloudVaultへ直接保存します。

この版は作業ブランチ `codex/chatgpt-star-save` にのみあります。main・現在のRenderデプロイは変更していません。**実ChatGPT・Windows Chrome・実Supabaseでの完了確認はまだできていません。**

## インストール（Windows / Chrome）

1. 作業ブランチのコードをダウンロードして展開します。拡張機能ZIPの場合も展開してください。
2. Chromeで `chrome://extensions` を開き、「デベロッパーモード」をONにします。
3. 「パッケージ化されていない拡張機能を読み込む」で、`manifest.json` がある `chrome-extension` フォルダを選択します。
4. 拡張機能詳細に表示される32文字のIDを控えます。同じフォルダを移動するとIDが変わることがあるため、設置場所は固定します。
5. **このブランチのサーバーを別の試験用サービスへデプロイするか、mainへの反映を別途判断してください。現在の本番サーバーは新APIに対応していません。** mainを変更しない条件のため、今回の作業ではデプロイしていません。
6. 対象サーバーの環境変数 `IDEA_VAULT_EXTENSION_IDS` に拡張機能IDを設定して起動し直します。複数ならカンマ区切り。未設定では拡張Originを許可しません。RenderのFreeプランは変更不要です。Supabaseの既存設定・RLS・非公開Storageは変更しません。
7. 現版の接続先は `https://idea-vault-cmgl.onrender.com` に固定しています。別の試験用サービスを使う場合は `manifest.json` のhost_permissions、background.jsのTARGET、options.htmlの接続先をそろえて変更してください。任意の接続先へ認証トークンを転送させないため、設定画面から自由には変更できません。
8. 拡張アイコンから設定を開き、本人メール・パスワードでログインします。IDEA VAULTのWeb画面のログインとは別です。「接続テスト」を実行します。
9. 画像を保存する場合は「画像取得権限を許可」を押し、`*.oaiusercontent.com` の取得権限を許可します。
10. 「自動保存ON」をチェックし設定を保存します。ChatGPTの既存タブを再読み込みしてください。

パスワードは保存しません。認証トークンは拡張の `chrome.storage.session` のTRUSTED_CONTEXTSだけに保持し、ChatGPT側のcontent scriptから読めない設定です。localStorage・sessionStorage・chrome.storage.local・URL・ログには入れません。Chromeを完全終了すると再ログインが必要です。接続先やON/OFFだけはstorage.localに保持します。

## 操作

整理済みの回答が完成してから、ChatGPTの入力欄に単独の `※` を送信します。Enterまたは既知の送信ボタン操作と、新しいuserメッセージの両方を検知します。文中の※、履歴の読み込み、ページ再読み込みだけでは保存しません。送信をキャンセルしてメッセージが追加されなければ保存しません。

- 通常：直前の完成済みassistant回答の文章と画像を保存します。
- 別回答の画像・画像だけの回答に対する文章：直近3回答から候補を探し、保存前に確認します。AIで関連性を推測しません。候補が無関係ならキャンセルしてください。範囲外の画像は取得しません。
- 成功：Storageの実ファイルを再取得してSHA-256照合後、「IDEA VAULTに保存しました。文章1件・画像N枚」を表示します。
- 失敗：理由と再試行ボタンを表示します。画像取得が失敗した場合は**文章も新規保存しません**。この試作は全対象をそろえて保存し、画像を省いた部分成功を作りません。保存途中の通信断では確定状態が不明になる場合があり、同じ対象の再試行は決定的IDで重複を防止します。
- 保存済み：原文と画像ハッシュ、会話URLで重複を判定し、IDEA VAULT側の編集内容を上書きしません。本文だけ同じでも画像が違えば別記録です。画像順も判定に含みます。

本文は取得した内容をそのままUTF-8 Markdown添付とメモに保存します。タイトル・保存日（日本時間）・ChatGPT会話URL・IDEA・inbox:trueをmetadataに保持し、添付名は `YYYY-MM-DD_タイトル` です。タイトルには先頭の見出し、なければ最初の行を使います。画像は再圧縮せず、取得した元バイト列のまま保存します（PNG/JPEG/WebP、最大8枚、1枚20MB、合計30MB）。本文上限はUTF-8 2MBです。

## 正確な制約

- ChatGPTのDOMには元Markdownソースが必ずしもありません。見出し・改行・リスト・コード・表・強調をDOMからMarkdownへ変換します。表示された文字は追加要約せず取得しますが、**元のMarkdown記法・全空白と完全一致する保証はありません**。数式は原文を正しく取得できないため保存を止めます。特殊な埋め込み・引用・UI部品は未対応です。
- 画像は `data-original-src`、downloadリンク、表示画像URLの順で取得元を探します。元画像として利用できる公開 `*.oaiusercontent.com` URLだけをバックグラウンドから通常のfetchで取得します。Cookieを付けず、リダイレクトを追わず、縮小用パラメータ・外部URL・blob・ChatGPT非公開APIを拒否します。
- **ChatGPTの生成画像が `/backend-api/estuary/content` 等にしか存在しない場合、現在の禁止条件の下では自動取得できません。** ログインCookieや非公開APIを使わずに取得できる元URLが必要です。縮小画像やスクリーンショットには置き換えません。DOMの画像URLが真の原本かどうかも、実ChatGPTでの検証が必要です。
- 関連画像の確認は候補全体に対する承認です。画像を個別選択するUIは未実装です。
- 通常の `https://chatgpt.com/c/...` 会話だけに対応します。一時チャット、別のChatGPTドメイン、スマホ、Chrome以外は対象外です。
- DOM構造が変わればDOMアダプタの修正が必要です。ストリーミング・送信ボタンの実DOM対応は実機で確認してください。
- Render Freeの起動待ちやSupabaseの利用枠で失敗する場合があります。認証とRLSを通すため、別ユーザーの保存は拒否します。

## 構成と安全性

- dom.js：画面のメッセージ／Markdown／画像候補取得。独立モジュール。
- content.js：実操作と単独マーカーの検知、確認、通知。認証情報を持ちません。
- background.js：本人ログイン、トークンのセッション保持、画像取得、保存と再取得検証。content scriptには成功件数／安全な失敗理由だけ返します。
- options.html/js：設定・ログイン・接続テスト・任意の画像取得権限。
- server.py：拡張IDのOrigin完全一致許可。CORSは専用保存／確認／ログイン／更新／ログアウトAPIのPOSTだけ。既存APIをすべて開放しません。
- star_save.py：入力検証・決定的ID・保存原本のハッシュ照合。サーバーが外部画像URLを取得することはありません。
- cloud_store.py：既存の本人JWT・RLS・非公開StorageとASCIIオブジェクトキーを再利用。Renderディスクへ個人データは書きません。

拡張にexternally_connectableやwindow.postMessageによる認証連携はありません。コンテンツ側の要求は送信タブのoriginで検査し、ログイン等は拡張設定ページからだけ受け付けます。service_role／sb_secretや追加AIサービスを使いません。

## 検証

```sh
python3 -m unittest discover -s tests -v
node tests/star-extension-browser.cjs
```

別ターミナルで `python3 tests/test_star_save.py` を起動してから：

```sh
node tests/star-worker.cjs
node tests/star-display-browser.cjs
```

これらは合成ChatGPT DOM・模擬Supabaseを使用します。workerテストはブラウザ拡張APIを模擬します。ブラウザテストはChromiumの実DOMでcontent scriptを実行しますが、実ChatGPTではありません。実MV3ロード用 `tests/star-mv3-browser.cjs` はこの環境でserviceworker起動待ちがタイムアウトし、成功していません。既存アプリの64件のPythonテストは成功しました。実Windows Chrome、実ChatGPT、実Supabase、Render上の新APIは未検証です。
