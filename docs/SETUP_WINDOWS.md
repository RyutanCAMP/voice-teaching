# WindowsのPCでの準備（家のPC・会社のPC 共通）

所要時間：20〜30分。上から順に進めてください。分からなくなったら、その画面の写真をクロに送ってください。

> **大事**：APIキーは「クレジットを使うための鍵」です。**チャット・GitHub・メールに貼らない**でください。PCの `.env` ファイルにだけ書きます。

---

## 1. 必要なソフトがあるか確かめる
1. スタートメニューで「**PowerShell**」と入力して開きます（黒か青の文字の画面）
2. 次の3行を1行ずつ貼り付けて、Enterを押します
   ```
   python --version
   git --version
   code --version
   ```
3. それぞれ数字（例：`Python 3.12.4`）が出ればOKです
   - `python` が出ない → https://www.python.org/downloads/ から入れます。**インストールの最初の画面で「Add python.exe to PATH」にチェック**を入れてください
   - `git` が出ない → https://git-scm.com/download/win から入れます（全部「Next」のままでOK）
   - `code` が出ない → VS Codeが入っていれば無くても進められます
4. 入れたあとは、PowerShellを**一度閉じて開き直して**から、もう一度確かめます

## 2. リポジトリを取り込む
1. PowerShellで、作業用のフォルダに移ります（例：ドキュメント）
   ```
   cd $HOME\Documents
   ```
2. リポジトリを取り込みます
   ```
   git clone https://github.com/RyutanCAMP/voice-teaching.git
   cd voice-teaching
   ```
3. 開発中の版に切り替えます（今は `feat/jbi-core` という名前です）
   ```
   git checkout feat/jbi-core
   ```

## 3. Pythonの部品を入れる
```
python -m pip install -r requirements.txt
```
最後に `Successfully installed …` と出ればOKです。

## 4. テストを動かしてみる（APIキーはまだ要りません）
```
python -m pytest
```
`13 passed` のように「passed」と出ればOKです。

## 5. APIキーを作って、PCに入れる
1. https://platform.claude.com を開き、ログインします（クレジットを受け取ったときと同じアカウント）
2. 右上の「**APIキーを取得**」ボタンを押します
3. キーの名前を入れます（例：家のPCなら `voice-teaching-home`、会社のPCなら `voice-teaching-office`）
4. 「作成」を押すと、`sk-ant-…` で始まる長い文字が表示されます。**この画面でしか表示されません**。コピーボタンでコピーします
5. PowerShellに戻り、次を実行してメモ帳を開きます
   ```
   copy .env.example .env
   notepad .env
   ```
6. メモ帳で `ANTHROPIC_API_KEY=ここに自分のAPIキーを入れる` の「ここに自分のAPIキーを入れる」を消して、コピーしたキーを貼り付けます
   ```
   ANTHROPIC_API_KEY=sk-ant-…（貼り付けたキー）
   ```
7. 上書き保存して、メモ帳を閉じます

`.env` は、GitHubに上がらない設定になっています（`.gitignore`）。

## 6. Claudeにつながるか確かめる
```
python tools/check_api.py
```
- `○ つながりました。` と出れば成功です
- `×` が出たら、その表示をクロに送ってください（**キーそのものは送らないでください**）

---

## 困ったとき
| 表示 | 意味と対処 |
|---|---|
| `python は、内部コマンドまたは外部コマンド…として認識されていません` | Pythonが入っていない、またはPATHのチェックを忘れた。1をやり直す |
| `× APIキーが正しくありません` | キーのコピーが途中で切れている。5をやり直す（新しいキーを作ってもよい） |
| `× インターネット経由でClaudeにつながりません` | 社内ネットワークの制限の可能性。家のPCで試す |
| キーが漏れたかもしれない | すぐに https://platform.claude.com の「キーとアクセス」でそのキーを無効にし、新しいキーを作る |
