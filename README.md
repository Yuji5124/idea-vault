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

## Renderでの公開（ログイン必須）

`render.yaml` にWeb ServiceとPersistent DiskのBlueprintを用意しています。RenderのアカウントでGitHubリポジトリを接続し、New → Blueprintからこのファイルを含むブランチを選んで作成してください。

- **有料のStarterプランと1GBのPersistent Diskを使用します。** Render画面で現在の料金を確認してから作成してください。無料サービスの一時ディスクには個人データを保存しません。
- RenderがHTTPS URLを発行します。URLは作成完了後のサービス画面に表示されます。クラウド環境のPublishとは別の操作です。
- ユーザー名は **jima**。パスワードはRenderの環境変数 `IDEA_VAULT_PASSWORD` に自動生成されます。Renderの管理画面で確認し、パスワードマネージャーへ保管してください。チャット・Git・URLには記載しないでください。
- アクセスするとブラウザ標準のログインダイアログが出ます。画面、JavaScript、metadata API、添付ダウンロード、更新APIすべてに認証が必要です。`/healthz` のみデータを含まないヘルス確認用に公開します。
- `/var/data/vault` に保存し、データをアプリのコードや公開ディレクトリに置きません。ログにファイル名や検索内容を出しません。HTTPSのRenderホストのみを許可し、別サイトからの書き込みを拒否します。
- 公開環境でパスワードが未設定／24文字未満、またはPersistent Diskがマウントされていない場合は起動を拒否します。パスワードを変更して再起動すれば、古い認証情報は使えなくなります。ブラウザが認証を保持するため、共有PCでは使わず、利用後はブラウザを終了してください。
- 再デプロイ時にもディスク上のファイルは残ります。ただし、サービス／ディスク削除や故障に備えて別のバックアップを保持してください。Render上ではSSHなどの管理機能から保存先全体を安全に取得してバックアップします。

Render運営者／アカウント管理者には保存先への管理アクセスがあります。これはエンドツーエンド暗号化ではありません。個人情報をさらに暗号化して保存する機能、アカウントごとの権限、MFAは未実装です。Renderアカウント自身のMFAも有効にしてください。

## 今後の拡張

基本機能はAIなしで動きます。次の段階で、任意のAI分類、画像／PDFのOCR、全文索引、JIMA FILTER履歴・選択傾向の分析、PRINCIPLE LOOP / PIXVAULT / SOUNDVAULT / NEXUSとのJSON連携を追加できます。現時点ではファイル名によるタイトル候補とMIME判定のみを行い、AI解析やGitHub同期は実装していません。
