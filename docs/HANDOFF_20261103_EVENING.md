# 引き継ぎ（2026-11-03 夜・最新）：会社のPC → 家のPC

書いた人：シクロ（会社のPCの Claude Code）。読む人：家のPCのシクロと唐川さん。
**この文書は `docs/frame-prep` ブランチのものが最新**（`fix/checker026` にある同じ名前の文書は 18時ごろの版。安全修正のブランチは今回変えない指示のため、新しい版はこちらに置いた）。
目標：**11月6日（金）から動画制作に入れる状態**。主役は「決めつけずに聞く → 人が教える → その意味で変更を提案する」Claude との会話。

> 安定ブランチ（`main`・`feat/mvp`）へのマージは一つもしていない。実機用の出力・転送・ロボットの起動は作っていない。`.env`（APIキー）は GitHub に入っていない。

---

## 1. 完成した機能と、まだの機能
| 機能 | 状態 | ブランチ |
|---|---|---|
| 安全修正（M1〜M3・MOVJ の表示・P0・FRAME ROBOT・上下の照合 K4・実機 JOB は確認のみ） | **完成**。クロちゃんの独立レビュー CHECKER_030 で **c41ebb7 が PASS** | `fix/checker026` |
| 唐川さんの決定（ATTR と FRAME の並び・ATTR の無い JOB は止める） | 完成。内部レビュー CONDITIONAL PASS。**独立レビューはまだ** | `fix/checker026` 7e6f4e8 |
| CHECKER_030 の SHOULD（〜ます は2択・ロボット名と確認者の常時表示・実機 JOB の承認後の案内）＋承認のあとの3つの状態 | できた（9d7434d。pytest 4171 passed・e2e OK 256・p0_split 0/26・frame_cases 0/17・b1 MUST 118/118）。内部 Safety **CONDITIONAL PASS**（P1＝消えていたテスト2件 → 3c7e182 で直した）。独立レビューはまだ | `fix/checker030-should` |
| 2回→3回（範囲をボタンで確定・2回→3回だけ・1回目／2回目／全体の範囲） | 動く。内部レビュー（f11279b）Safety・QA とも CONDITIONAL PASS → QA P1-A（範囲の確認の最中の声）ほかを **f7f871f で直した**（pytest 4016 passed・e2e NG 0）。f7f871f の差分の内部レビュー中 | `feat/repeat-count` |
| 3D の再生の表示（いま何行目・何回目）・2回と3回の比較の再生・動きの並びのカード・「1・2・3」 | 動く（f61bfd1。pytest 3988 passed・node 52/52・e2e OK 286）。QA レビュー中 | `feat/demo-3d` |
| Claude に聞く（読み取りだけ） | 動く。**本物の Claude で確かめた** | `feat/claude-explain` |
| 自然な会話（E1 やさしい言葉・E2 人が教えた意味・E4 自動で光らせる・E7 意地悪な会話） | できた（6e4328b。pytest 4082 passed・e2e OK）。**本物の Claude で通した結果**（DEMO_V6_FEASIBILITY.md 2-3）を受けて2点を修正中。内部レビューはまだ | `feat/claude-talk` |
| 画面の改善（テーマ・演出・音） | 案。内部レビューはまだ | `feat/ui-refresh` |
| 会話 → 範囲の確定 → 比較 → 承認 の一本の流れ（台本 3-3） | **まだ**（変更エンジンとの接続。安全修正の最新版の独立レビューのあと） | ― |
| MOVJ の目標位置の変更・JOB の解説 | 設計だけ | `docs/frame-prep` |

## 2. ブランチの最新コミット
（最後の更新の時点。11章の表で手元と GitHub が一致していることを確かめた）
| ブランチ | コミット | 中身 |
|---|---|---|
| `fix/checker026` | eb80ec2 | 安全修正（コード 7e6f4e8。c41ebb7 は CHECKER_030 PASS） |
| `fix/checker030-should` | 3c7e182 | CHECKER_030 の SHOULD 3件＋承認のあとの3つの状態（内部 Safety CONDITIONAL PASS） |
| `feat/repeat-count` | f7f871f | 2回→3回（P1-A を直した。差分の内部レビュー中） |
| `feat/demo-3d` | f61bfd1 | 3D の再生・比較・動きの並び（QA レビュー中） |
| `feat/claude-explain` | 2c921e6 | Claude に聞く（読み取りだけ） |
| `feat/claude-talk` | 6e4328b | 自然な会話（本物の結果を受けて修正中） |
| `feat/ui-refresh` | 2994ad7 | 画面の改善の案 |
| `docs/frame-prep` | （この文書） | 設計メモ・統合の計画・台本 Ver.6 の実現性・この引き継ぎ |
| `wip/integrate-trial` | dd64183 | 統合の試し（使わない） |
| `wip/backup-talk`・`wip/backup-demo3d`・`wip/backup-c030`・`wip/backup-repeat` | ― | **作業中の変更のバックアップ**（コミット前の作業フォルダを丸ごと写したもの。未レビュー・使わない。作業が途中で止まったときに、ここから続きを取り出す） |

## 3. テスト結果（会社のPC）
| ブランチ | pytest | node | e2e | クロのスクリプト |
|---|---|---|---|---|
| fix/checker026 eb80ec2 | 3989 passed, 1 skipped | 33/33 | NG 0 | p0_split 0/26・frame_cases 0/17・b1_rereview（上下の確認済み）MUST 118/118 |
| feat/repeat-count f7f871f | 4016 passed, 1 skipped | 37/37 | NG 0 | （f11279b で p0_split 0/26） |
| feat/claude-explain 2c921e6 | 3992 passed, 1 skipped | 37/37 | | |
| feat/ui-refresh 2994ad7 | 3796 passed, 1 skipped | 46/46 | NG 0 | |
| wip/integrate-trial dd64183 | 4179 passed, 1 skipped（e2e を除く） | | OK 256・NG 0 | |

## 4. レビューの状況
| 対象 | 内部（同じ Claude） | クロちゃんの独立レビュー |
|---|---|---|
| fix/checker026 c41ebb7 | Safety・QA CONDITIONAL PASS | **CHECKER_030 PASS** |
| fix/checker026 7e6f4e8（c41ebb7 のあと） | Safety CONDITIONAL PASS（S-1：「〜ます」が 17:14 の決定（2択）と食い違う → fix/checker030-should で直している） | **未** |
| feat/repeat-count f11279b → f7f871f | f11279b：Safety・QA CONDITIONAL PASS → QA P1-A を f7f871f で直した。**f7f871f：Safety（QA の観点も）CONDITIONAL PASS、P1 なし**。P2：［この範囲を繰り返す］を目立たせたことが前の決め（ボタンは同じ重さ）と食い違う＝唐川さんの判断、一覧に無い言い方（「はい、この範囲を繰り返す」など）では範囲の確認が捨てられる | **未** |
| feat/claude-explain 2c921e6 | 未 | CHECKER_031（設計の意見と確認項目 E1〜E7） |
| fix/checker030-should 9d7434d | Safety CONDITIONAL PASS（P1 は 3c7e182 で直した。P2：場所の言葉と位置番号が一緒の「〜ます」は位置のボタンだけで候補になる＝M3 と同じ道、上下の向きの表示が2行） | 未 |
| feat/demo-3d f61bfd1 | QA CONDITIONAL PASS（P1：1280×720 で操作ボタンが「→ ×3」を隠す → 修正中） | 未 |
| feat/claude-talk・feat/ui-refresh | 未 | 未 |

## 5. Claude API の動作状況
- 説明（読み取りだけ、feat/claude-explain）：2ターン成功、$0.0122（`records/api_usage.jsonl`）
- 台本 Scene 3 の会話（feat/claude-talk）：3ターン×2回。1ターン目の良い文が数の検査で表示されなかった・2ターン目で区間を聞き返した → 修正中（`docs/DEMO_V6_FEASIBILITY.md` 2-3）。$0.0196
- **料金の合計：約 $0.03**（説明の欄。位置の会話の分は記録が無く、数セントの見込み）
- 位置の会話（台本 Scene 5、fix/checker026）：成功。「置くところ」は候補が3つ出た。最初の応答に 11秒（`docs/DEMO_V6_FEASIBILITY.md` 2-2）
- モデル：`claude-sonnet-5-5`（`.env` の ANTHROPIC_MODEL、CLI の `--model`）。上限は累計 $5（`VOICE_TEACHING_API_BUDGET_USD`）

## 6. 台本 Ver.6.1 の実現状況
`docs/DEMO_V6_FEASIBILITY.md` を見る。要約：Scene 1・2・6・7 は撮影できる。Scene 5 は台本の言い方を2か所直せば撮影できる。Scene 3（主役）は feat/claude-talk と feat/demo-3d が完成すれば 3-1・3-2 を撮影でき、3-3 の一本の流れは統合のあと。Scene 4 は実機の別の撮影。

## 7. 統合の順番と注意
`docs/INTEGRATION_PLAN.md` を見る。順番：fix/checker026＋fix/checker030-should（独立レビューと唐川さんの承認）→ ＋feat/repeat-count → ＋feat/demo-3d → ＋feat/claude-talk（読み取りのまま）→ 会話と変更エンジンをつなぐ（CHECKER_031 3章の1〜8を守る）→ ＋feat/ui-refresh。

## 8. 家のPCで必要な環境
- Python 3.13、Git、Node.js、VS Code、Claude Code
- リポジトリ：`RyutanCAMP/voice-teaching`（仕様とレビュー：`RyutanCAMP/claude-hackathon-idea-lab` の `review/chatgpt-post-kickoff-spec-20261102`）
- 仮想環境（`.venv`）と、`requirements.txt` の中身（pytest・anthropic。会社のPCは anthropic 2.4.0）、ブラウザのテスト用の Playwright（requirements.txt に無いので別に入れる）と Chromium

## 9. 家のPCで再開するコマンド（PowerShell の例）
```powershell
# 1) リポジトリの場所へ（無ければ clone）
cd <家のPCの voice-teaching のフォルダ>
git status                      # 未保存の作業が無いか、先に確かめる（あれば消さない）
git fetch origin

# 2) 続けるブランチを取り出す（例：会話の改善）
git switch feat/claude-talk     # 無ければ： git switch -c feat/claude-talk origin/feat/claude-talk
git pull --ff-only

# 3) 仮想環境とライブラリ（初めてのときだけ）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
python -m pip install -r requirements.txt
python -m pip install playwright      # ブラウザのテスト用（requirements.txt には入っていない。会社のPCは 1.64.1）
python -m playwright install chromium

# 4) テスト
python -m pytest -q
node --test tests/speech.test.mjs tests/highlight.test.mjs tests/repeat.test.mjs
python tools/e2e_browser.py

# 5) アプリを起動して、Google Chrome で開く
python -m voice_teaching.web --port 8765    # http://127.0.0.1:8765/
```

### 家のPCの `.env`（APIキー）の作り方
1. Anthropic のコンソール（https://console.anthropic.com/）で API キーを作るか、会社のPCと同じキーを使う（キーは自分で管理する。チャットや GitHub に貼らない）
2. voice-teaching のフォルダの直下に `.env` という名前のファイルを作り、次の2行を書いて保存する
   ```
   ANTHROPIC_API_KEY=（キー）
   ANTHROPIC_MODEL=claude-sonnet-5-5
   ```
3. `git status` で `.env` が出てこない（.gitignore で除外されている）ことを確かめる
4. 確認：`python -m voice_teaching.claude_explain --job samples/dummy/DEMO_BUTTON_REPEAT.JBI --say "このロボット、何をしている？" --env-file .env`（`--call` を付けなければ、送る内容を表示するだけで料金はかからない）

### 作業が途中で止まっていたときの取り出し方
`wip/backup-<名前>` は、コミット前の作業フォルダの写し。続きをするときは、そのブランチを取り出して差分を見る：
```powershell
git fetch origin
git diff origin/feat/claude-talk origin/wip/backup-talk --stat
```
（中身は未レビュー・テスト未確認のことがある。そのまま使わず、シクロに確かめてもらう）

## 10. 家でシクロに最初に渡すプロンプト（そのまま貼る）
```
シクロ、家のPCで Voice Teaching の開発を再開します。
まず docs/frame-prep ブランチの docs/HANDOFF_20261103_EVENING.md を読んで、
1) 各ブランチ（fix/checker026, fix/checker030-should, feat/repeat-count, feat/demo-3d, feat/claude-explain, feat/claude-talk, feat/ui-refresh, docs/frame-prep, wip/backup-*）の GitHub の先頭と、この文書の表を照らし合わせる
2) wip/backup-* に、ブランチのコミットより新しい作業が残っていないか確かめる（残っていれば、テストを通してから正式なコミットにする）
3) 環境（.venv・.env の有無（中身は見せない）・Chromium）を確かめ、各ブランチのテストを流す
4) 11章の「次にやること」の1から進める
を、安全の決まり（CLAUDE.md・docs/CURRENT_DECISIONS.md）を守ってお願いします。main と feat/mvp には勝手にマージしないでください。
```

## 11. 次にやること（優先順）
1. 作業中の4つ（feat/claude-talk・feat/demo-3d・feat/repeat-count の P1-A・fix/checker030-should）を仕上げて、内部レビュー（Safety・QA）
2. クロちゃんに独立レビューを依頼：fix/checker026 の 7e6f4e8 以降＋fix/checker030-should、feat/repeat-count の最新、feat/claude-talk（E1〜E7）
3. 本物の Claude で、台本 Scene 3 の会話（3-1〜3-3）を通す（読み取りのまま）。応答時間を測る
4. 独立レビューの合格と唐川さんの承認のあと、docs/INTEGRATION_PLAN.md の順で統合
5. 本物の Google Chrome・唐川さんの声で通しのリハーサル（180秒）

## 12. 唐川さんの判断が要ること
- 台本 Scene 5：「じゃあ、上に10ミリ」と言う／「候補が3つ…どれですか？」のままでよいか／止める文を短くするか（安全修正のブランチの変更）
- 台本 3-3：統合の前（説明の欄＋指示の欄）で撮るか、統合のあとで撮るか
- 場所の言葉と位置番号が一緒の「〜ます」「〜動かします」（「C00005の置くところを3mm下げます」）は、位置を確かめるボタンだけで候補にしてよいか（2択も通すか）
- 2回→3回の範囲の確認で［この範囲を繰り返す］を目立たせてよいか（前の決め：ボタンは同じ重さ）。区間の長さの上限（自動で探すときは10点）を、範囲を言ったときにも当てるか
- 上下の向きの設定がジョブの中身に関係なく効く形（K4 の残るリスク）、相対ジョブでないジョブには並びを求めない扱い、「3回から3回にして」に［合計3回］の1択で聞く扱い
- 設定があるときに `--robot` をどう扱うか（CHECKER_030 S30-1。fix/checker030-should では実装していない）：A 今のまま（表示で気づく）／B 設定があるときは `--robot` を必須、付けなければ上下は未確認（起動はする）＝**推奨**／C 既定値をなくす
