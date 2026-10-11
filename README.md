# IDEA VAULT

思いついたものを、とにかく簡単に放り込める、自分専用のローカルWebアプリ。
画像・Markdown・TXT・PDF・HTML・動画などをINBOXへ保存し、あとから原理やアイデアを結び付けます。外部API・アカウント・Pythonパッケージのインストールは不要です。

## セットアップ・起動

Python **3.10以上**を用意し、このリポジトリで実行します。

```sh
python3 server.py
```

自分のPCのブラウザで `http://127.0.0.1:8765` を開きます。Windowsでは `py server.py` でも起動できます。終了はターミナルで Ctrl+C。
既定の起動はローカル専用です。Renderへの公開方法は下記を参照してください。個人用アプリで、複数ユーザーの権限管理には対応していません。

保存先やポートは変更できます。

```sh
python3 server.py --data-dir /path/to/my-private-vault --port 8765
```

`IDEA_VAULT_DATA` 環境変数でも保存先を指定できます。`--data-dir` が優先されます。クラウドで起動した場合も、データはサーバー側のディスクに保存されます。PCのローカルディスクへ保存するにはPCで実行してください。

## 使い方

- 中央へ複数ファイルをドロップ、または「ファイルを選択」。フォームなしでINBOXへ即保存します。通常の複数ファイルは各1記録になります。
- 「フォルダを選択」、またはフォルダをドロップすると、最上位フォルダ1つにつき1つのIDEA候補としてまとめます。サブフォルダの元のパスもmetadataに残ります。空のフォルダは対象外です。
- フォルダ選択・フォルダドロップはデスクトップ版Chrome / Edgeを推奨。ブラウザによって対応状況が異なります。
- 「メモを追加」でファイルなしのIDEA / SOURCE / PRINCIPLE / VISUALも登録できます。
- カードを開いてタイトル、分類、カテゴリー、タグ、メモ、関連、**JIMA FILTER**（GOOD / HOLD / BAD / 未評価）、コメントを編集します。INBOXチェックを外すと分類先へ整理します。
- キーワード検索はタイトル・タグ・カテゴリー・メモ・テキスト資料・日付・評価を対象に、直接関連付けた記録も横断します。SOURCEからPRINCIPLE、IDEA、VISUALを順に関連付けられます。検索は直接の関連先／関連元までを対象とし、無制限な推移検索はしません。
- 詳細の「ファイルの分離・統合」で選択ファイルを新しいIDEAや既存の記録へ移動できます。全ファイルを移動するとファイルを統合できます。元のメモ・評価・関連は消しません。
- 画像はサムネイル／拡大表示、動画・音声はブラウザが対応する形式を再生します。Markdown / TXT / HTMLは安全なテキスト表示です。HTMLを実行せず、PDFやその他の資料はダウンロードして開きます。

1回の投入はファイル合計140MBまで。読み込みにメモリを使うため、大きな動画は分けて投入してください。途中の失敗は保存済み件数と失敗内容を表示します。通信が切れたときは一覧を確認してから再投入してください（同じ内容の重複投入は自動削除しません）。

## 保存場所・ファイル構成

既定の保存先はリポジトリ直下の `vault/`。個人データを誤ってアプリのリポジトリへコミットしないよう `.gitignore` で除外しています。

```text
idea-vault/
├── server.py               # 標準ライブラリだけのHTTPサーバーと保存処理
├── web/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/test_vault.py      # 保存と実HTTP APIのテスト
└── vault/                  # 個人データ（Git対象外）
    ├── inbox/
    │   └── 2026-10-08_蜘蛛ゲーム/
    │       ├── metadata.json
    │       ├── idea.md
    │       ├── images/2026-10-08_game.png
    │       └── files/2026-10-08_memo.md
    ├── ideas/
    ├── sources/
    ├── principles/
    └── .staging/           # 保存途中の一時領域
```

保存日の `YYYY-MM-DD_` をファイル名と新規記録フォルダの先頭に付けます。先頭に同形式があればその日付を維持します。サーバーのローカル日付を使用します（PCが日本時間なら日本時間）。同名は `_01`, `_02` と採番し、既存ファイルを上書きしません。タイトル変更はフォルダ名を変更せず、metadataに反映します。

metadataには `schema_version`, `id`, `title`, `type`, `inbox`, `category`, `tags`, `body`, `relations`（記録IDの配列）, `jima_filter`, `comment`, `created_at`, `imported_at`, `updated_at`, `files` を保存します。各ファイルにもID・元名・元パス・保存名・相対パス・MIME・サイズ・作成日時・テキスト抜粋を持ちます。`created_at` はファイルの最終更新時刻を作成日の代用とし、ファイルなしの記録では登録時刻です。テキスト抜粋は最大200KBで、画像・PDFのOCRはしません。

JSONを正本として検索し、メモ本文を `idea.md` にも保存します。データベースは不要です。外部連携向けに `GET /api/records` でJSONを取得できます。更新・投入APIはローカルの同一オリジン専用です。手動でJSONを編集するときはサーバーを停止し、バックアップしてください。`idea.md` の直接編集は自動取り込みしません。

通常の投入は一時ディレクトリに書き込んでから公開し、JSONは一時ファイルと置換で保存します。移動はコピーとmetadata保存が完了してから元ファイルを削除します。異常終了時には `.staging` や重複ファイルが残る場合がありますが、既存ファイルの上書きはしません。強制終了やディスク故障に備え、バックアップしてください。1つの保存先につき起動するサーバーは1つにしてください。

## GitHub Private Repositoryへの接続

アプリのコードとは別に、**データ専用のPrivate Repository**をGitHubで作成する方法を推奨します。GitHub上でPrivateであることを確認してからデータをpushしてください。アプリからの自動pushやトークン保存は行いません。

既にデータがある場合、まずバックアップを作り、保存先で実行します。

```sh
cd /path/to/my-private-vault
git init
git branch -M main
printf '.staging/\n' >> .gitignore
git add .
git commit -m "Back up idea vault"
git remote add origin https://github.com/YOUR_NAME/YOUR_PRIVATE_DATA_REPO.git
git push -u origin main
```

以後はサーバーを止めて `git add .`, `git commit`, `git push` でバックアップします。既存のデータ用リポジトリがある場合はcloneした保存先を `--data-dir` に指定してください。GitHub認証はGitの認証機構を利用し、トークンをソースやmetadataへ入れないでください。

GitHubは100MiB超の通常ファイルを受け付けません。大きな動画にはGit LFS（利用枠・料金を確認）や別のバックアップ先を用い、同じ相対パスを保ってください。アプリのローカル保存上限とGitHubの上限は異なります。

## バックアップ・復元

サーバーを停止して**保存先全体**を別ディスクへコピーしてください。画像だけでなくmetadataとMarkdownも必要です。復元時はコピーしたフォルダを `--data-dir` に指定します。GitHubへのpushと別ディスクのバックアップを併用すると、コミット前のデータも保護できます。

## テスト

```sh
python3 -m unittest discover -s tests -v
```

テストは一時ディレクトリを使い、個人データには触れません。日付・二重日付防止・同名採番・元データ保持・フォルダ投入・失敗時の保存・分類と関連・再読み込み・分離／統合・HTTP API・クロスオリジン拒否を検証します。

画面操作テストは `tests/browser-smoke.cjs` にあります。任意の開発用ツールPlaywrightを別途用意し、**空のテスト用保存先**で起動して実行してください。個人データの保存先には実行しないでください。

```sh
# ターミナル1
python3 server.py --data-dir /tmp/idea-vault-ui-test --port 8766
# ターミナル2（Playwrightを利用できる環境）
VAULT_TEST_URL=http://127.0.0.1:8766 CHROMIUM_PATH=/usr/bin/chromium node tests/browser-smoke.cjs
```

`CHROMIUM_PATH` は任意です。省略時はPlaywrightのChromiumを使用します。実行結果と検証範囲は [TEST_RESULTS.md](TEST_RESULTS.md) を参照してください。

## Render無料構成＋Supabase無料枠での公開

`render.yaml` は **Render Free Web Service** を指定し、有料ディスクを作成しません。保存先は **Supabase Freeのデータベース＋非公開Storage**です。複数端末から本人のアカウントでログインすると、同じ記録と添付ファイルを参照できます。

無料枠は容量・転送量・稼働時間に制限があります。Renderは未使用時にスリープして初回表示が遅くなることがあり、Supabaseも無料プロジェクトの休止・利用枠制限があります。各サービスの現在の条件を管理画面で確認し、有料へのアップグレードは選択しないでください。無制限・常時稼働を保証する構成ではありません。

### 1. SupabaseのFreeプロジェクトを準備

1. 自分のSupabaseアカウントで **Free** プロジェクトを作成します。
2. SQL Editorでリポジトリの `supabase.sql` を実行します。`vault_records` テーブルと **private** な `idea-vault` バケットを作成し、本人のユーザーIDに限定するRow Level Securityポリシーを設定します。既に同名のテーブルやポリシーがある場合は内容を確認してから実行してください。
3. Authentication → Usersで本人用ユーザーを作成します。メールと十分に長い固有のパスワードを設定します。管理画面で作成する場合は確認済みユーザーにしてください。
4. Authenticationの設定で **新規ユーザーのサインアップを無効**にします。このアプリには新規登録画面はありません。
5. 本人ユーザーのUUID、プロジェクトURL（`https://PROJECT_ID.supabase.co`）、**publishableキーまたは旧anonキー**を確認します。`service_role` / `sb_secret_` キーは使用しません。
6. Storageの `idea-vault` が **Public OFF** であることと、SQLのテーブル／Storageポリシーが有効であることを確認します。他の既存ポリシーが広くアクセスを許可していないことも確認してください。

### 2. RenderのFreeサービスを作成

RenderのNew → Blueprintでこのリポジトリと `codex/idea-vault-render` ブランチを選び、`render.yaml` を読み込みます。**Free** であり、ディスクが追加されていないことを確認してください。環境変数の入力欄で次を設定します。

| 名前 | 設定内容 |
| --- | --- |
| `IDEA_VAULT_STORAGE` | `supabase`（Blueprintが設定） |
| `SUPABASE_URL` | 自分のプロジェクトのHTTPS URL（末尾のスラッシュなし） |
| `SUPABASE_PUBLISHABLE_KEY` | publishable / anonキー |
| `IDEA_VAULT_OWNER_ID` | 本人ユーザーのUUID |

環境変数はRenderの管理画面で設定し、ソースコードやチャットにパスワード・秘密キーを貼らないでください。接続情報が不足している場合、公開サーバーは起動を拒否します。**Renderの一時ディスクへ代替保存しません。**

作成完了後、Renderのサービス画面にHTTPS URLが表示されます。その画面で本人ユーザーのメールとパスワードを入力してログインします。従来の `jima` / `IDEA_VAULT_PASSWORD` 方式は無料公開では使用しません。

### 保護と保存範囲

- ログイン画面とアプリコードは公開ですが、記録一覧・添付・書き込みには認証が必要です。画面に個人データを埋め込みません。
- サーバーはSupabaseでJWTを検証し、`IDEA_VAULT_OWNER_ID` の本人だけを許可します。さらにテーブルとStorageにRLSを適用します。別ユーザーや匿名利用者が本人のデータを取得・変更できない構成です。
- 添付は非公開Storageから本人JWTで取得します。トークンをURLへ入れず、公開URLを発行しません。ブラウザでは認証済みのデータを一時的なBlob URLで表示します。HTMLは実行せずダウンロードします。
- パスワード／セッショントークンをlocalStorageやsessionStorageへ保存しません。再読み込み時は再ログインします。ログアウト時には表示とBlob URLを消し、Supabaseにもログアウトを要求します。Supabaseの既発行アクセストークンは期限まで有効な場合があるため、アカウント側のセッション有効期限も適切に設定してください。
- メモとmetadataはDBへ、画像などはStorageへ保存します。Renderの再起動・再デプロイでもRender側の一時ディスク消去に影響されません。クラウドでは `idea.md` はバックアップ時に生成します。
- クラウド版は **1ファイル50MBまで**。クラウド版の1回の投入合計上限も50MBです（ローカル版は140MB）。無料枠のStorage総容量・DB容量・転送量はSupabaseの管理画面で確認してください。
- 通信が途切れた場合、保存完了が不確かなデータを消さないため、非公開Storageに未参照ファイルが残る場合があります。分離・統合でも元の非公開コピーを復旧用に残します。容量に余裕がなくなった場合はバックアップ後、Storage管理画面で参照されていないファイルだけを整理してください。
- 同じ記録を別端末で同時に編集すると最後の保存が優先されます。共同編集・履歴管理は未実装です。
- SupabaseのFreeプロジェクトはバックアップや休止に制限があります。定期的に手元へバックアップしてください。Supabase／Renderのアカウント自体のMFAも有効にしてください。

この構成は通信のHTTPS保護・ログイン・RLSによるアクセス制限です。エンドツーエンド暗号化ではなく、ホスティングサービスやアカウント管理者は管理アクセスを持ちます。

### クラウドから手元へバックアップ

自分のPCで `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `IDEA_VAULT_OWNER_ID` を環境変数に設定して実行します。ログインパスワードは非表示の入力欄で入力します。コマンドライン引数・Git・チャットにパスワードを書かないでください。

```sh
python3 backup_cloud.py --destination /path/to/private-backups
```

成功したバックアップには `BACKUP_COMPLETE.json` が作られます。バックアップ先の親ディレクトリには新しい `cloud-...` フォルダが作成され、元ファイル・JSON・Markdownを保存します。途中で失敗したものは完了マーカーがないため、完全なバックアップとして扱わないでください。取得中の別端末からの変更は控えてください。復元には `python3 server.py --data-dir /path/to/private-backups/cloud-...` を使い、ローカル版で開けます。クラウドへの一括復元は未実装です。

バックアップデータをGitHubへ保存する場合は、別の **Private Repository** に保存してください。既定の `backups/` はアプリコードのGitから除外しています。

### 無料クラウド構成のテスト

```sh
python3 -m unittest discover -s tests -v
# 模擬Supabaseでブラウザ操作も検証する場合（Playwrightは任意）
python3 tests/test_cloud.py
# 別ターミナル
CHROMIUM_PATH=/usr/bin/chromium node tests/cloud-browser.cjs
```

模擬接続先のテストは実Supabaseの設定・RLS・利用枠・稼働を検証するものではありません。実プロジェクトを接続したあと、未ログイン／本人以外での拒否、ファイル保存とダウンロード、別端末からの取得を確認してください。クラウド開発環境で実Supabaseへ接続する場合は、そのプロジェクトの `PROJECT_ID.supabase.co` をネットワーク許可先へ追加する必要があります。

## 今後の拡張

基本機能はAIなしで動きます。次の段階で、任意のAI分類、画像／PDFのOCR、全文索引、JIMA FILTER履歴・選択傾向の分析、PRINCIPLE LOOP / PIXVAULT / SOUNDVAULT / NEXUSとのJSON連携を追加できます。現時点ではファイル名によるタイトル候補とMIME判定のみを行い、AI解析は実装していません。クラウド版は後述のGitHub取り込みに対応します。

## パスワード再設定（Render / Supabase）

本人用の再設定メールから新しいパスワード（12文字以上）を登録できます。確認入力が一致し、Supabaseで認証と本人UUIDの照合が成功した場合だけ更新します。再設定画面は保管庫を取得・表示せず、完了後は「ログイン画面へ戻る」から通常のログインをしてください。リンクの再読み込みや画面を離れる操作では認証情報を復元しません。失敗した場合は新しいメールを発行してください。

### メールとURL設定を確認する

今回、利用者から **Site URL = `https://idea-vault-cmgl.onrender.com`** と報告されています。現在のメールテンプレートと Redirect URLs は管理画面にアクセスできず、未確認です。設定済みとは扱っていません。

Supabase Authentication → Emails → Templates → Reset Password のリンク部分と、Authentication → URL Configuration を確認してください。アプリから再設定メールを発行する機能は今回追加していません。これまで利用している発行方法で、新しい本人用メールを送ってください。

対応するリンクは次の2種類です。

1. **標準の implicit フロー**：テンプレートの `href="{{ .ConfirmationURL }}"` を使用。Supabaseがワンタイムリンクを検証し、Site URL（または許可された redirect URL）へ `#access_token=…&refresh_token=…&type=recovery` を付けて戻します。アプリはフラグメントを直ちに消去し、必要なaccess tokenだけをメモリで保持します。Supabaseの `GET /auth/v1/user` でセッションの有効性・本人UUIDを検証し、`PUT /auth/v1/user` でパスワードを更新します。`type=recovery` という文字列だけを認証根拠にはしません。Supabaseの公式の認証済みパスワード更新と同じく、有効な本人セッションが権限の根拠です。セッション発行前のメールリンクの期限・一回性はSupabase、発行後のJWTの有効性は `/user` が検証します。
2. **token_hash フロー**：クエリではなくフラグメントにTokenHashを置くカスタムテンプレートを使用。以下のリンク部分をReset Passwordテンプレートに設定します（実トークンを手入力しません）。

   ```html
   <a href="{{ .SiteURL }}/#token_hash={{ .TokenHash }}&amp;type=recovery">パスワードを再設定</a>
   ```

   フラグメントを直ちに消去し、フォームの明示的な送信時だけ、サーバーから `POST /auth/v1/verify` に `token_hash` と固定の `type=recovery` を送ります。Supabaseが期限・一回性を検証したセッションで本人UUIDを照合し、パスワードを更新します。ページ表示やメールスキャナーのGETだけではリンクを消費しません。使用済み・期限切れのエラーは送信時に表示します。

Site URLの末尾はスラッシュなしの上記URLにしてください。メール発行側が `redirectTo` を指定する場合は、アプリのルートURL `https://idea-vault-cmgl.onrender.com/` を指定し、Redirect URLsに同じURLを許可してください。広いワイルドカードや未知のリダイレクト先は追加しないでください。標準リンクで `redirectTo` が未指定ならSite URLを使用します。

**PKCEの `?code=…`、`?token_hash=…` などのクエリ型リンクは非対応**です。PKCEのverifierを持つ対応クライアントがこのアプリにはなく、トークンをURLクエリへ置かない要件もあるため拒否し、クエリを消去してエラーを表示します。既存メールがこの方式なら上記のtoken_hashフラグメント用テンプレートに変更し、新しいメールを発行してください。クエリはブラウザ到着前にHTTP要求へ含まれるため、アプリで消去してもホスティング側のアクセスログを遡って消せません。実リンク・パスワード・トークンをチャットやログに貼らないでください。

### 保護と制限

- publishable / anonキーだけを使用し、既存の本人UUID照合、DBのRLS、private Storage、通常ログインを維持しています。Render Free設定とSupabase保存方式は変更していません。
- recoveryのトークン・パスワードはPOST本文と一時メモリだけで処理します。localStorage、sessionStorage、Cookie、URLクエリ、ログ、Render一時ディスクに保存せず、セッションをブラウザへ新規発行しません。更新結果に個人プロフィールや認証トークンを返しません。
- 再設定情報は通常の保管庫セッションに代入しません。フラグメントから来たrefresh tokenは保持しません。再設定完了後は通常のログインが必要です。
- 成功後はSupabaseにグローバルログアウトを要求します。失敗時は、パスワードは変更済みだが既存セッション終了に失敗した旨を画面に表示します。発行済みaccess JWTは期限まで有効な場合があり、即時無効化を保証しません。
- Supabase側の追加パスワード要件、MFAや再認証ポリシーによる拒否時は更新せず、エラーを表示します。実プロジェクトのポリシーとの整合性は未検証です。
- ログアウト時に一覧・詳細フォーム・添付Blob URLを消去し、ログアウト前の遅延応答でデータを再表示しないようにしています。

公式フローの確認元：[Password-based Auth](https://supabase.com/docs/guides/auth/passwords)、[Email Templates](https://supabase.com/docs/guides/auth/auth-email-templates)、[verifyOtp](https://supabase.com/docs/reference/javascript/auth-verifyotp)、[updateUser](https://supabase.com/docs/reference/javascript/auth-updateuser)。ドキュメントサイトへのアクセスは403だったため、Supabase公式GitHubの同ドキュメントと `auth-js` の実装（`POST /verify`、`GET/PUT /user`）も確認しています。

### 再設定の開発用検証

```sh
python3 -m unittest discover -s tests -v
# ターミナル1：実データを使わないメモリ内の模擬Supabase
python3 tests/test_cloud.py
# ターミナル2：Playwright / Chromiumが必要。順番に実行する
CHROMIUM_PATH=/usr/bin/chromium node tests/cloud-browser.cjs
CHROMIUM_PATH=/usr/bin/chromium node tests/recovery-browser.cjs
```

模擬サーバーはテストでパスワードやワンタイムハッシュを変更するため、再実行時は停止して起動し直してください。実Supabaseによるメール配信・リダイレクト・パスワード変更・ログインと、Render上での最新版の動作は未検証です。`render.yaml` の自動デプロイはOFFのままなので、push後の反映にはRenderから手動デプロイが必要です。

## ChatGPTがGitHubへ保存したMarkdown資料の取り込み

ChatGPTの「GitHubに保存しました」という案内は、GitHubへの保存を指します。IDEA VAULTのSupabase保管庫とは保存先が異なります。クラウド版は本人ログイン後、GitHubのmain/ideas内にある未取り込みのMarkdownを確認し、「はい、読み込み開始」で画像とともに保管庫へ取り込み、一覧へ表示します。リンク指定の手動取り込みも引き続き利用できます。

1. 本人アカウントでIDEA VAULTへログインします。
2. **「GitHub資料を取り込む」**を押します。
3. GitHubで資料を開いたページのリンクを貼り付け、**「保管庫に取り込む」**を押します。
4. INBOXに通常のカードとして表示されます。詳細画面でタイトル、資料の日付、分類、カテゴリー、タグ、本文、関連、JIMA FILTERを編集できます。

対応するリンクは `https://github.com/Yuji5124/idea-vault/blob/main/ideas/資料名.md` の形式です。`ideas/` のサブフォルダも利用できます。公開のUTF-8 Markdown（`.md` / `.markdown`）、1資料2MB以内に対応しています。リンクにクエリ、トークン、フラグメントを付けないでください。他のリポジトリや外部URL、READMEやアプリコードは取り込み対象にしません。

同じGitHubリンクを再度取り込むと、取り込み済みの記録を使い、編集したタイトルや本文を上書きしません。GitHub側での後日の更新は自動反映されません。非公開資料やリンクを取得できない資料は、GitHubからMarkdownをダウンロードして、アプリのドロップエリアへ投入してください。新たなGitHubトークンの保存・入力は不要です。ダウンロードしたファイルの再投入は通常のドラッグ＆ドロップと同じで、別の記録として保存されます。

### 日付・タイトル・表示

単体MarkdownをGitHubリンク・ファイル選択・ドラッグ＆ドロップで取り込むと、同じ処理で以下を読み取ります。

- タイトル：先頭20行内の最初の `# 見出し` を使い、末尾の `— アイデア保存` は表示タイトルから取り除きます。見出しがなければ簡単なfrontmatterの `title:`、または日付プレフィックスと拡張子を除いたファイル名を使います。
- 資料の日付：先頭20行内の `保存日：2026-10-10` / `保存日：2026年10月10日`、簡単なfrontmatterの `date: 2026-10-10`、ファイル名の `2026-10-10_` の順で採用します。日付がなければ取り込み日を使います。存在しない日付やUTF-8でない資料はエラーを表示します。
- 本文：Markdown全文をメモへ保存します。同時に元のMarkdownファイルを添付として保持し、ダウンロードできます。HTML、JavaScript、Markdown内の外部画像は実行・自動取得しません。本文に画像の説明があっても、画像ファイルがなければ画像プレビューは作りません。

フォルダ投入や複数添付のまとまりは従来通り維持し、個々のMarkdownからフォルダ全体のタイトル・本文を勝手に置き換えません。

一覧の **「資料の日付から」「資料の日付まで」** で期間を絞り、**「並び順」** で新しい日付順・古い日付順・タイトル順を選べます。「日付をリセット」で期間指定を解除できます。タイトル順は一覧全体で並べ、日付順では日付ごとのグループに分けます。

`record_date`（資料の日付）は、取り込み日時 `imported_at` やファイル由来の作成日時 `created_at` と別に保存します。日付を編集しても取り込み履歴と元ファイルは変わりません。既存の `record_date` がない記録は従来の取り込み日を表示します。新規資料の保存フォルダと日付なしの添付ファイルには資料の日付を付けますが、編集後に既存のフォルダやファイル名を変更しません。

### 保存と検証

クラウドでは本文・日付・タイトル・GitHub取得元URLをSupabase DBへ、元のMarkdownを非公開Storageへ保存します。Renderの一時ディスクに資料を保存・キャッシュしません。取り込みAPIも本人UUID照合を行い、SupabaseのRLS・Storage保護を維持します。GitHubへ保管庫のJWTを送信せず、固定の取得先、サイズ上限、タイムアウト、HTTPリダイレクト拒否を適用しています。

開発用の画面テストは模擬Supabaseと合成Markdown資料だけを使います。

```sh
# ターミナル1
python3 tests/test_document_import.py
# ターミナル2（Playwright / Chromiumが必要）
CHROMIUM_PATH=/usr/bin/chromium node tests/document-browser.cjs
```

Renderへの最新版の反映は手動デプロイが必要です。実Supabaseへの今回の資料取り込みとRenderからのGitHub取得は未検証で、開発環境でのGitHub取得成功だけでは実サービスの接続を保証しません。

### 日本語ファイル名とSupabase Storage

Supabase Storageのオブジェクトキーには日本語などのUnicode名を使用できないため、新しい添付は `本人UUID/記録ID/files/ファイルID.md` のような英数字のキーで保存します。画像も同様に `images/ファイルID.png` を使います。日本語の元名・表示名・バックアップ用の相対パスはmetadataに保持し、画面表示・ダウンロード名は変更しません。metadataの `storage_path` がクラウド用の保存キーです。既存の `storage_path` がない記録は以前のパスで読み込むため、既存データの移動や削除は行いません。

「クラウド保存先が操作を拒否しました（HTTP 400）」が表示された場合、旧バージョンの日本語ファイル名によるStorage拒否の可能性があります。最新版をRenderで手動デプロイして再度取り込んでください。最新版でも失敗する場合は、Storage（添付ファイル）、記録DB、認証のどの段階で拒否されたかを表示するので、そのエラー文で切り分けます。RLSを無効にしたり、バケットを公開にしたりする必要はありません。

## ログイン後のGitHub自動取り込み

ChatGPTが `Yuji5124/idea-vault` の **main → ideas/** にMarkdownを保存したあと、クラウド版IDEA VAULTを開いて本人ログインすると、新しい資料があれば「読み込みますか？」と表示します。「はい、読み込み開始」で取り込み、「あとで」で見送ります。「GitHub資料を取り込む」でリンクを貼り付ける操作は通常不要です。保管庫の既存一覧を先に表示し、自動取り込みの進行・結果を一覧の上に表示します。

- `ideas/` の下の通常ファイル（`.md` / `.markdown`）をGitHub APIで確認し、未取り込み資料のタイトル・保存日・本文を同じ解析処理で抽出します。サブフォルダにも対応します。画像はMarkdownの相対リンクから取得します。シンボリックリンクは一覧対象にしません。
- GitHubリンクの `source_url` が保存済みなら取り込まず、利用者が編集した本文・タイトル・日付・分類を維持します。GitHub側で同じファイルが更新・削除されても既存記録を上書き・削除しません。ダウンロードして手動投入したファイルは取得元URLがないため、自動取り込みとは別の記録になります。
- 未ログイン・再設定画面ではGitHubの一覧確認や資料取得を実行しません。ログアウト後は、遅れて返る結果を画面へ反映しません。認証情報をブラウザストレージへ保存しないため、再読み込み時には通常通りログインが必要です。
- 本文・metadataはSupabase DB、元Markdownは非公開Storageへ保存します。日本語表示名は維持し、Storageキーは英数字IDを使います。Render FreeとRLS・本人UUID照合を維持します。
- 一度に5資料ずつ、1ログインで最大100資料を処理します。失敗した資料は同じログイン中に繰り返さず、他の資料を続けます。100資料を超える残りや失敗資料は次のログイン時に再確認します。保管庫を開いている間の常時監視や、ログインしていない間のバックグラウンド同期は行いません。
- GitHubの一覧は `api.github.com`、資料は `raw.githubusercontent.com` から取得します。対象は公開資料で、保管庫JWTはGitHubへ転送しません。追加のGitHubトークンや有料サービスは使いません。非公開・API制限・ネットワーク障害時は自動取り込みの失敗を表示しますが、既存の保管庫と手動取り込みは引き続き使えます。

開発用ブラウザ検証は実データを使わず、専用のGitHub一覧／Supabase模擬接続先を使います。

```sh
# ターミナル1
python3 tests/test_github_sync.py
# ターミナル2
CHROMIUM_PATH=/usr/bin/chromium node tests/github-sync-browser.cjs
```

実GitHub APIによる一覧取得、実Supabaseへの保存、Render上の自動取り込みは未検証です。開発環境の許可先には `api.github.com` がなく、実APIの一覧取得は実施していません。Renderへ手動デプロイ後、新しい資料の確認ダイアログと承認後の表示を確認してください。


## ※保存と画像付き資料

「※保存」はこの会話での明示的な保存指示です。ChatGPT全体への自動設定ではありません。元画像を受け取ったら、画像を長辺1600px以下・2MB以下のWebPへ変換し、Markdownと一緒にGitHubのmain/ideasへ保存できます。変換補助ツールは `prepare_github_image.py 入力画像 ideas/assets/未使用名.webp` です。作業環境にPillowが必要で、Renderには導入不要です。元画像は変更せず、EXIF等を引き継ぎません。

Markdownには `![画面](assets/未使用名.webp)` のように、Markdown所在フォルダからの相対リンクを記載してください。PNG/JPEG/WebPに対応し、画像は1資料最大4枚・各2MBです。外部URL、親フォルダ参照、SVG、クエリやフラグメント付きリンクは拒否します。参照画像がない、取得できない、形式・サイズが不正な資料は成功扱いにせず失敗を表示します。画像の説明だけから画像を生成することはありません。

ログイン → 未取り込み資料数を確認 →「はい、読み込み開始」→ 本文・日付・タイトルと画像をSupabaseへ保存 → カード／詳細画面で表示 → 資料件数・画像件数・失敗件数を表示、という流れです。承認前は画像や本文を取得・保存しません。未ログイン時は一覧確認もしません。「あとで」は次のログイン時に再確認します。取り込み済み資料に後日画像を追加しても上書きしないため、画像とMarkdownをまとめて保存してから取り込んでください。

実画像の提供がないため、利用者の画像変換・GitHub保存は未実施です。実Supabaseへの画像保存とRender上での動作も未検証です。

## ChatGPTの「※」保存Chrome拡張（試作）

`chrome-extension/` にManifest V3の試作を追加しました。本人ログインした拡張機能から、完成済み回答の文章と取得可能な元画像をSupabaseへ直接保存し、Storageから再取得して原本ハッシュを検証します。追加AI処理は使いません。

導入手順、拡張IDのOrigin設定、取得できる画像の条件、Markdown復元の限界、実機未検証事項は [拡張機能README](chrome-extension/README.md) を参照してください。作業ブランチは `codex/chatgpt-star-save` で、main・現在のRenderデプロイは変更していません。

## 過去アイデア・画像の一括取り込み／更新履歴／ゴミ箱

作業ブランチ `codex/history-import-trash` に、確認付きChatGPT履歴インポート、説明の変更前後と履歴、画像追加・並べ替え・後日の関連付け、ソフトデリート・復元・1件ずつの完全削除、認証付きZIPバックアップを追加しました。

手順・対応形式・無料枠の上限・失敗時の扱い・実データ未取り込み事項は [HISTORY_IMPORT.md](HISTORY_IMPORT.md) を参照してください。SQLの変更や既存データの初期化は不要です。main・現在の本番環境には反映していません。

文章のみの過去履歴取り込み：対象期間の初期値は2026-09-11〜2026-10-11（日本時間）です。「文章のみで保存」は初期状態でONです。ZIP内に画像があってもアップロードせず、画像参照は未取得として残します。画像だけの候補は作りません。既存の画像は本文更新時も保持し、画像は後から追加できます。過去のChatGPT履歴を直接取得する接続はなく、実際の取り込みには本人のエクスポートZIPまたはJSONが必要です。
