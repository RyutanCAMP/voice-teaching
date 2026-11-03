# 統合の計画（2026-11-03 夜。シクロ）

**本統合（変更エンジンとのつなぎ込み・安定ブランチへのマージ）は、安全修正の最新版がクロちゃんの独立レビューを通り、唐川さんが承認してから。** この文書は、その準備（順番・競合・確かめること）。

## 1. ブランチの関係
```
bb6f00f（feat/claude-dialog）
 └ fix/checker026 … c41ebb7（CHECKER_030 PASS）→ 7e6f4e8（唐川さんの決定：ATTR/FRAME の並び・ATTR なし・〜ます）→ eb80ec2（文書）
     ├ fix/checker030-should（eb80ec2 から）：CHECKER_030 の SHOULD（〜ます は2択・ロボット名と確認者の表示・承認後の案内）
     └ f783b2f（fix/checker026 の途中）
         ├ feat/repeat-count … f11279b（2回→3回）
         │   ├ feat/claude-explain 2c921e6（9104aa8 から＝2回→3回の最初の版の上）
         │   │   └ feat/claude-talk（会話の改善 E1〜E7）
         │   └ feat/demo-3d（f11279b から：再生の行番号・2回と3回の比較）
         └ feat/ui-refresh 2994ad7（テーマ・演出・音）
```

## 2. 競合（`git merge-tree` で確かめた。11/3 夜）
| 合わせる組 | 競合するファイル |
|---|---|
| fix/checker026 + feat/repeat-count | web/flow.py（2か所。試しに合わせた：`wip/integrate-trial` dd64183、pytest 4179 passed・e2e OK 256・NG 0） |
| fix/checker026 + feat/ui-refresh | static/style.css |
| fix/checker026 + feat/claude-explain | web/flow.py |
| feat/repeat-count + feat/ui-refresh | static/app.js・view3d.js |
| feat/repeat-count + feat/claude-explain | static/app.js（explain は repeat の古い版の上なので、新しい repeat と合わせると app.js がぶつかる） |
| feat/ui-refresh + feat/claude-explain | web/server.py・static/app.js・view3d.js |

## 3. 統合の順番（案）
1. **fix/checker026 ＋ fix/checker030-should** → クロちゃんの独立レビュー（7e6f4e8 以降の追加分）→ 唐川さんの承認 → 統合ブランチ `integrate/demo-mvp` の土台
2. **＋ feat/repeat-count**（変更エンジンの本体。`wip/integrate-trial` の解き方：hear の本体は `_hear_body` に回数の変更の分岐を移す、`_begin_instruction` で範囲の確認も捨てる）→ 回数の変更の候補と、承認の取り消しの文・実機 JOB の「確認のみ」・上下の照合の組み合わせのテストを足す → 内部レビュー → 独立レビュー
3. **＋ feat/demo-3d**（repeat の上なので、2 のあとが楽）
4. **＋ feat/claude-talk**（読み取り専用のまま合わせる。flow.py・app.js の競合）。**変更エンジンへのつなぎ込み（説明の欄の「3回にして」→ 範囲の確定の流れへ案内）は、この後に別のコミットで**、CHECKER_031 3章の1〜8を守って
5. **＋ feat/ui-refresh**（見た目は最後に。style.css・app.js・view3d.js の競合。テーマの色を、確認のみの帯・範囲の確認・会話の欄にも当てる）
6. 各段で：全テスト・e2e・クロのスクリプト（p0_split・frame_cases・b1_rereview）・内部レビュー。安定ブランチ（feat/mvp）へのマージは、最後に唐川さんの承認で

## 4. 合わせるときに必ず確かめること
- 変更候補を作る入口は Session の `_accept`（位置）と `confirm_repeat`（回数）だけ。Claude の change_request からは作らない
- 承認はボタンだけ。範囲の確定と承認は別の操作
- 上下の向きの照合・上限 20mm・MOVJ の隣の点・実機 JOB の出力禁止が、どの機能を合わせても緩まない
- 会話の記録と、今の動作データがそろっている（候補・承認・読み直しで区切る）
- 画面：安全の表示（赤い帯・確認のみの帯・承認ボタン・対象外の文）をテーマや演出で隠さない
