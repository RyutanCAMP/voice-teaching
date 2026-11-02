# 音声入力機能の引き継ぎ資料

確定日：2026-11-02（JST）。対象：シクロ側MVPへの組込み担当者。

## 1. 引き継ぐ範囲と最小の組込み方

音声入力は **`voice_teaching/static/speech.js` の `SpeechInput` だけで独立して動く**。外部JavaScriptライブラリ・Pythonサーバー・Claude API・Three.jsへの依存はない。

**最小案：この1ファイルとテストを取り込み、`final(text)` を既存MVPの文字入力欄へ接続する。** 位置変更・検査・承認・合成JOB出力はシクロ側MVPの既存処理を使用する。本ブランチのプレビュー画面やJBI処理への置換は不要。

この資料の作成に際して、シクロ側MVPは参照・変更していない。統合済みとは扱わない。追加機能の開発を停止し、以下の実装コミットを確定版とする。

## 2. リポジトリ・ブランチ・コミット

| 項目 | 値 |
|---|---|
| リポジトリ | `https://github.com/RyutanCAMP/voice-teaching.git` |
| ローカル作業ブランチ | `feat/preview-workflow` |
| 音声を含む実装確定コミット | `fd03d84cc862006464cc07275b558e4f8bbfad09` |
| 音声追加の親コミット | `fe44f46`（プレビュー・Claude接続・比較承認） |
| 開発の基点 | `43c5472`（既存の安全ガード） |
| リモート公開の状態 | 本担当からpush・PR作成・mainへのマージは行っていない。GitHubだけから音声コミットを取得できるとは限らない |

同梱するGit bundleで履歴ごと引き渡せる。ZIPは実装確定コミットの追跡ファイルだけを収録する。`.env`、実機JOB、参考映像、キャッシュ、画面画像は収録しない。引き継ぎ資料・テストログはZIPの外にも別添する。

既存MVPの作業中ブランチを切り替えずに内容を確認する例：

```powershell
git bundle verify <受け取ったvoice-teaching.bundleのパス>
git fetch <受け取ったvoice-teaching.bundleのパス> feat/preview-workflow:refs/remotes/voice-handoff/preview
git show fd03d84:voice_teaching/static/speech.js
```

`fd03d84` の一括cherry-pickは推奨しない。画面・サーバー・文書も変更しており、MVPと競合する可能性がある。音声モジュールだけを抽出する場合はZIP内の該当ファイルを使用する。bundleの参照先には資料追加コミットが含まれていても、実装確定点は上記SHAで特定できる。

## 3. ソースとファイル構成

```text
voice_teaching/
  static/
    speech.js             ← 必須：独立した音声認識モジュール
    app.js                ← 参考：位置固定・入力欄・ボタンと音声の接続
    index.html            ← 参考：処理方法、録音・終了・取消、認識文のUI
    style.css             ← 参考：表示
    vendor/               ← プレビュー用Three.js。音声だけなら不要
  claude_interpreter.py    ← 任意：Claudeへの接続。既存MVPの解析器があれば不要
  preview.py               ← 参考：入力照合、候補・版・枠の検査
  web.py                   ← 単体デモ用HTTPサーバー。既存MVPへ移植不要
  jbi.py                   ← 既存JBI処理。音声統合のための置換不要
tests/
  speech.test.mjs          ← 音声制御13件。speech.jsのimport先を合わせれば使用可能
  test_claude_interpreter.py ← API接続のモックテスト3件
  test_preview.py          ← プレビュー・指示照合31件
  test_web.py              ← 単体サーバー4件
  test_jbi.py              ← 既存JBI38件
package.json              ← type: module／音声テスト用。依存パッケージなし
requirements.txt          ← pytest>=8（Pythonのテスト用）
.env.example              ← 設定の項目名だけ。秘密情報なし
```

既存MVPではJavaScriptモジュールとして配信できればよい。importのURLはMVP側の静的ファイル配置に合わせる。本デモでは `/speech.js` を明示的に配信している。

## 4. 起動と依存

単体デモはリポジトリ直下で次を実行する。

```powershell
python -m voice_teaching.web
```

`http://127.0.0.1:8765/` を開き、「公開用ダミーで試す」→位置選択→音声処理方法→「マイクで話す」。端末に複数のサーバーがある場合は `--port 8766` などを指定する。サーバーは127.0.0.1だけで待ち受け、入力はメモリー内に保持する。

| 用途 | 必要なもの |
|---|---|
| 音声モジュールのみ | SpeechRecognitionまたはwebkitSpeechRecognitionに対応するブラウザー、マイク許可、日本語認識の対応 |
| ブラウザー標準モード | ブラウザー提供の認識サービス。外部通信が必要な方式がある |
| 端末内のみモード | processLocallyの対応、日本語言語パック。自動インストールしない |
| 単体デモのPython | 標準ライブラリのみ。実測環境はPython 3.13.1 |
| Claude接続 | Python標準のurllib.request。Anthropic SDKの追加は不要 |
| プレビュー画面全体 | 同梱Three.js 0.187.0（MIT）。CDN接続なし |
| Pythonテスト | pytest>=8。実測はpytest 9.1.1 |
| 音声制御テスト | Node.js。実測v22.14.0。npm installは不要 |

既存READMEはPython 3.10以降と記載しているが、`web.py` の例外処理にPython 3.11追加の `sys.exception()` を使用している。単体デモをそのまま使う場合は **Python 3.11以降** を使用する。今回の引き継ぎでは実装は変更せず、この互換性上の制約を記録する。独立したspeech.jsには関係しない。

## 5. 音声モジュールの接続口

```javascript
import { SpeechInput } from '<配置先>/speech.js';

const voice = new SpeechInput(
  window.SpeechRecognition || window.webkitSpeechRecognition,
  {
    state: value => { /* 録音状態を表示し、必要な操作を無効化 */ },
    partial: text => { /* 未確定欄に表示するだけ。解析に渡さない */ },
    final: text => { /* 既存の文字入力欄に代入。自動送信しない */ },
    error: message => { /* 固定のエラー文を表示。旧認識文・候補を破棄 */ }
  }
);

// MVP側で対象位置を固定し旧候補を破棄した後、利用者のクリックで開始
voice.start('browser'); // または利用者が選んだ 'local'
voice.stop();           // 終了を要求し、確定結果を待つ
voice.cancel();         // 結果を採用せず取り消す
```

上記は接続口の説明例。既存MVPへの実装は行っていない。

| コールバック／状態 | データ・意味 |
|---|---|
| `state(value)` | `starting` → `listening` → `stopping` → `idle`。通常終了ではstoppingを経ずidleになることもある |
| `partial(text)` | その時点の全文。確定済み部分と未確定部分を含む。追記せず置換して表示する |
| `final(text)` | 終了時の確定した文字列1つ。自動の解析・承認・出力は行わない |
| `error(message)` | 固定の日本語エラー。APIキー・ブラウザーの生エラーを含めない |
| `voice.active` | 録音開始から終了までtrue。別途callbacksで状態表示する |

設定：`lang='ja-JP'`、`continuous=false`、`interimResults=true`、候補数1。開始応答の期限12秒、認識開始後30秒で終了要求、終了応答の期限5秒。30秒は実録音時間を厳密に測る保証ではなく、開始イベントからの上限処理。遅延した旧イベントは世代番号で破棄する。取消は確定結果も採用しない。

## 6. 認識から指示解析までのデータ形式

```text
マイク → ブラウザー音声認識
      → partial(string)：表示のみ
      → final(string)：文字入力欄へ
      → 人が認識文を確認・修正
      → 人が「解釈」を押す
      → 既存MVPの文字入力と同じ解析・検査
      → 差分確認 → ボタン承認 → MVP既存の合成JOB出力
```

`SpeechInput` は音声バイト列、位置番号、JSONの指示オブジェクトを返さない。認識文字列を返すだけで、位置番号の読みや漢数字を独自補正しない。例えば音声認識が「シーゼロ…」を返したら、そのまま確認対象とする。

単体デモでのHTTP形式（MVPが既存のAPIを持つなら合わせる必要なし）：

```json
POST /api/begin
{"selected":"C00004"}

応答の主要部
{"input_token":"不透明な一回限りのトークン","state":{}}

POST /api/propose
{"input_token":"上記トークン","text":"この位置を上に10ミリ"}
```

JSON例のstateは省略表記。実際のHTTP応答はプレビュー状態を含む。各POSTには `Content-Type: application/json`、タブごとの `X-Session` を付ける。このセッションは単体デモ用であり、MVPの認証・セッションを置き換えない。

Claudeへ渡すユーザーデータ：

```json
{
  "utterance":"この位置を上に10ミリ",
  "selected_position":"C00004",
  "available_positions":["C00000","C00001","C00004"]
}
```

Claudeが `propose_position` のtool_useで返す入力：

```json
{"position":"C00004","direction":"上","amount_mm":10}
```

方向は右／左／上／下。amount_mmは正の有限数。軸と符号の決定はMVP側の専門家設定で行う。速度変更、複数点、%指定を音声モジュール側で新しく解釈しない。

単体デモの `request_facts()` はNFKC正規化し、算用数字＋mm／ミリ、位置番号か「この位置」等、1方向・1量の限定文型だけを受け付ける。Claudeの結果と対象・方向・量の完全一致を検査し、合わなければ拒否する。汎用的な自然言語対応の保証はない。MVPに同等以上の照合があればそちらを使用する。

## 7. Claude APIの接続（秘密情報なし）

MVPがClaude接続を持つ場合は、その既存の接続を使えばよい。音声入力のために別のAPIキーやモデルを追加する必要はない。

本デモの接続：

- `POST https://api.anthropic.com/v1/messages`。サーバーのPythonから送信。
- ヘッダー：`Content-Type: application/json`、`anthropic-version: 2023-06-01`、`x-api-key`（サーバーで設定）。
- 環境変数：`ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL`。モデルIDのデフォルトはなく、両方が必要。
- デモの起動時だけ、ルートの `.env` からこの2項目を読み込む。環境変数が既にあれば優先。`.env` はGit対象外。`make_server()` を直接使う場合は環境設定を呼び出し側が行う。
- `max_tokens=512`、HTTP timeout=30秒、応答読込の上限1,000,000バイト。
- 道具：`propose_position` と `ask_user`。tool_choiceはany、parallel tool use無効。tool_use終了、tool_useが1件、propose_positionであることを確認してinputだけを返す。自由文は採用しない。
- 未設定・通信失敗・異常な応答・聞き返しはエラーで止まり、別モデルやモックへ自動で切り替えない。APIキーと生エラーは画面に返さない。
- 実APIでは未検証。API設定済みの表示は疎通成功を意味しない。

`claude_interpreter.py` は例外型を `.preview.PreviewError` からimportしており、そのまま単独コピーするとpreview.pyとjbi.pyにも依存する。既存MVPの解析器を使うのが最小。接続クラスだけ移す場合は、この例外型をMVP共通のエラー型に合わせることが組込み時の変更点となる。

## 8. 組込み時に守る境界

1. 録音開始時に選択位置とJOBの版を固定し、旧候補・旧承認状態を無効にする。
2. 録音中はJOB読込・枠変更・位置切替・解析・承認を無効にする。取消と終了だけを有効にする。
3. partialは解析に使わない。finalも入力欄への代入だけにする。
4. 人が認識文を修正した場合は解析済みトークン・候補を無効にし、同じ固定対象で新たに検査する。
5. 失敗・取消・JOB切替・新しい録音で、古い認識文・候補を再利用しない。録音の自動再試行はしない。
6. 解釈結果は既存MVPの文法・許可対象・量・累積・丸め等の検査へ渡す。音声経由だけ検査を省かない。
7. 音声で承認・合成JOB出力・転送・実機起動を呼ばない。MVPのボタン承認と承認版の照合を維持する。

`app.js` 内のSpeechInput生成、microphone／voice-cancel／interpretのハンドラー、voiceState／voiceToken、updateButtonsが参考箇所。画面全体のコピーは不要。

## 9. 89件の再実行結果

2026-11-02に実装確定コミットfd03d84で再実行。失敗0、skip0。

| テスト | 件数 | 結果 | 対象 |
|---|---:|---|---|
| tests/test_jbi.py | 38 | PASS | 既存の読込・変更・保持・拒否 |
| tests/test_preview.py | 31 | PASS | 座標・命令の拒否、指示照合、枠、累積、候補と承認版 |
| tests/test_claude_interpreter.py | 3 | PASS | 未設定、送信形式とtool_use抽出、通信失敗の非公開化 |
| tests/test_web.py | 4 | PASS | セッション分離、出力経路なし、外部origin拒否、読込失敗時の破棄 |
| tests/speech.test.mjs | 13 | PASS | 下記の音声制御 |
| 合計 | **89** | **PASS** | 全て実マイク・実APIなしで実行 |

音声13件：途中結果の不採用／途中結果の置換／マイク拒否／audio-capture失敗／通信失敗／無音／言語非対応／取消後の旧イベント破棄／端末内非対応時の外部処理禁止／processLocally指定／方式未選択・API非対応／終了要求後の確定／空結果。

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
node --test tests/speech.test.mjs
```

添付ログ：`pytest-results.txt`、`speech-test-results.txt`。Python 76件とNode 13件は別のテスト群で、89件全てが音声認識の精度テストという意味ではない。

別途、模擬SpeechRecognitionと偽Claudeを使ったPlaywrightで、位置固定、途中／確定文、明示的な解釈操作、旧候補の破棄、マイク拒否、取消、非対応時の文字入力を画面上で確認した。この確認用スクリプトは一時実行で、89件には含めず、再実行可能な自動テストとしては同梱していない。

## 10. 実装状態

| 区分 | 内容 |
|---|---|
| 実装済み | 日本語音声の開始・終了・取消、途中／確定の分離、固定のエラー表示、古いイベント破棄、文字入力への受渡し、対象固定、操作ロック、Claude接続クラス、構造化結果と指示文の照合 |
| 未検証 | 実マイク、実際の日本語認識精度、Chrome等の実サービス、端末内日本語パック、社内ネットワーク、実Claude APIの疎通と解釈、MVPへの統合動作、実機 |
| 音声側で未実装 | 音声番号の読みの補正、語彙登録、音声ファイル保存／アップロード、別の文字起こしAPI、言語パック自動導入、自動解析、自動承認、速度変更の新規解釈 |
| 本ブランチのプレビューで未実装 | HC20本体の関節動作、実機用の枠確定・永続履歴、JBI／合成JOB出力、USB／Ethernet転送、実機起動 |
| シクロ側MVP | ユーザー申告では読込→変更→承認→合成JOB出力が完成。本担当ではそのコードを変更せず、上記の未実装をシクロ側の欠落とは扱わない |

3D表示は位置関係と変更前後の確認用であり、実機の干渉・到達性・安全を保証しない。

## 11. 外部へ音声・文字が送られる条件

| 操作・モード | 外部への音声送信 | Claudeへの文字送信 |
|---|---|---|
| ページ表示・方式未選択・マイク未開始 | 本アプリは開始しない | なし |
| browserを選び、利用者が録音開始・マイク許可 | ブラウザー提供元の方式によって発生。Chromeではサーバー処理の方式がある。宛先URLを本コードでは指定しない | 録音だけではなし |
| localを選んで録音開始 | processLocally=trueを要求。非対応・言語パック不足は止め、browserへ自動変更しない | 録音だけではなし |
| 認識文の確認・修正のみ | 認識サービスが既に受け取った音声の撤回はできない | なし |
| 「Claudeで解釈」を押し、入力・枠の事前検査を通過、キーとモデルを設定済み | Claudeには音声を送らない | 認識文／入力文、固定位置番号、位置番号一覧をAnthropicへ送信 |
| 録音取消・エラー | それまでに外部で処理された音声を削除する機能はない。以降の本アプリの処理を中止し、文を不採用にする | 自動送信なし |

本アプリ側には音声バイト列の取得・アップロード・保存の処理を持たない。これはブラウザー提供サービス側が音声を処理・保持しないという保証ではない。処理方法は利用者が明示的に選び、サービスの利用条件を確認する。ローカル認識のブラウザー実装自体も実機未検証。

参照：[SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)、[processLocally](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/processLocally)。

## 12. 統合担当者の最初の確認

既存の文字入力欄へfinalを接続し、ダミーJOBで「この位置を上に10ミリ」を試す。認識文の確認後、文字入力と同じ解析・検査・差分・承認・合成JOB出力へ進むことを確認する。次に取消・マイク拒否・無音・録音中の操作ロック・JOB版変更後の古い候補拒否を確認する。実機JOBやAPIキーをこの資料やリポジトリに追加しない。
