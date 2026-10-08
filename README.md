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

基本機能はAIなしで動きます。次の段階で、任意のAI分類、画像／PDFのOCR、全文索引、JIMA FILTER履歴・選択傾向の分析、PRINCIPLE LOOP / PIXVAULT / SOUNDVAULT / NEXUSとのJSON連携を追加できます。現時点ではファイル名によるタイトル候補とMIME判定のみを行い、AI解析やGitHub同期は実装していません。
