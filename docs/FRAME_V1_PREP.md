# FRAME v1.1 の実装準備（設計・テストの計画。実装はまだ）

書いた人：シクロ（会社の PC）。2026-11-03。ブランチ `docs/frame-prep`（`feat/voice-stable` 682d1ab から）。
正本の仕様：`RyutanCAMP/claude-hackathon-idea-lab` の `docs/FRAME_IMPL_SPEC_V1_20261102.md`（v1.1 確定版。このリポジトリには写さない）。
状態：**本実装・マージは保留**（唐川さんの指示。既存の安全ガードとの統合条件の確認待ち）。

## 1. 着手の条件と、今の状態
| 条件 | 状態（2026-11-03） |
|---|---|
| 安全ガード（R1・R6）が feat/mvp に入る | 済み（feat/mvp = f7eddc7、CHECKER_020 PASS） |
| D1・D2（方向の解釈）がクロちゃんの再レビューを通る | **待ち**（CHECKER_023） |
| 「バイオ」問題（知らない言葉）の対策 | 作業中（`fix/unknown-words`） |
| 土台のブランチ | 提案：`feat/voice-stable`（CHECKER_023 合格後）。FRAME は上・下の読み方（`utterance.UPDOWN_IS_Z`・`DIRECTION_NAMES`）を枠の directions に置き換えるため |
| デモ枠の review | 唐川さんが道具（`python -m voice_teaching.frame review`）で書く。シクロは書かない |
| 右・左 | 実機の確認（11/3 夜）まで未定。デモ枠に書かない |

## 2. 今のコードとの対応（どこを直すか）
| 仕様 | 今のコード | 直すこと |
|---|---|---|
| 1章 枠ファイルの読込・形式の検査 | 無い | 新しい `voice_teaching/frame.py`（`FrameError`、`load_frame(bytes, job)`、NaN・Infinity・bool を拒否、知らない項目は枠ごと拒否） |
| 1.1章 content_sha256・3つの状態 | 無い | `frame.py` に `content_sha256()`・`status`（確認済み／未確認／確認後に変更）。review を書く CLI |
| 2章 structure_hash | `jbi.Job.normalized_hash`（jbi.py:189） | 枠の位置の X・Y・Z を `*` にした hash を `frame.py` に。`hash` の CLI |
| 3章 判定（範囲・1回の上限） | `jbi.plan_shift`（jbi.py:201）が「1回 20mm」と**暫定の累積 20mm**（jbi.py:23・302-312）で止める | 枠の判定は plan_shift を**通ったあと**に重ねる（どちらかで止まれば止まる）。暫定の累積 20mm は、枠が無いときの止める側としてそのまま残す（緩めない）。枠の ±15 はそれより狭いので矛盾しない |
| 3章 X・Y の斜めの警告 | 無い | 候補の warnings に固定文を追加（Z には付けない） |
| 4章 承認・出力で blocked_reason を断る | R1 で済み（flow.approve・can_approve） | 枠なし・範囲外も blocked_reason に入れるだけで同じ止めが効く。export 側の二重の止めを sim.export_sim に追加 |
| 4章 承認後の枠の変更検出 | 承認後のジョブの変更検出はある | 承認の記録に frame_bytes_sha256・frame_id・content_sha256。`POST /api/frame` で必ず承認を消す |
| 4章 続けての変更・_is_synthetic の拡大 | `sim._is_synthetic`（sim.py:277）は samples と同じバイト列だけ | structure_hash 一致＋枠の範囲内に広げる（**出力の範囲が広がるので Safety レビュー必須**） |
| 4章 history.jsonl | 無い | `records/history.jsonl`（.gitignore 済み）に追記 |
| 5章 API・画面 | `flow.state` に direction_names（flow.py:293） | `state.frame` を追加。画面に「枠：…（シミュレーション専用）」、位置ごとの「今 +10.000 ／ 範囲 −15〜+15」 |
| 6章 上・下・右・左 | `utterance.UPDOWN_IS_Z`・`DIRECTION_NAMES`、claude_interpreter の固定の上→Z+ | 枠の directions から読む。枠が無ければ今どおり Z± |

## 3. 既存テストへの影響（見込み）
- 仕様 7章のとおり、**枠が無いジョブは承認・出力できなくなる**。今の「承認 → 出力」まで進むテスト（test_web_flow・test_session・test_sim・test_r1_r6_sim_output・test_dummy_patterns・tools/e2e_browser.py の承認と出力の部分）は、テスト用の枠を当てるか、期待を「比較だけ」に直す
- 直した件数と理由は PR に書く（期待を黙って変えない）
- DEMO_PLACE.JBI（C00004）にはデモ枠が無い → 画面の通し確認は DEMO_C_PLACE（C00005）に寄せる

## 4. 受入テストの計画（仕様 7章 → テストのファイル）
| 仕様 7章 | テストのファイル（案） |
|---|---|
| 1・2 デモ枠とテスト用の枠の表、流れ①〜④（承認・出力を挟む版／挟まない版） | `tests/test_frame_judge.py` |
| 2-2 専門家の確認（review の有無・一致・変更・空白だけの変更） | `tests/test_frame_review.py` |
| 2-3 API で当てた枠の承認後の変更検出 | `tests/test_frame_api.py` |
| 3 壊れた枠（各1件） | `tests/test_frame_load.py` |
| 4 照合（hash・_SIM・V= の変更・TOOL・範囲外） | `tests/test_frame_match.py` |
| 5〜8 枠なし・範囲外・ガードで止まった候補・承認後の枠ファイルの変更 | `tests/test_frame_api.py` |
| 9 斜めの警告 | `tests/test_frame_judge.py` |
| 10 続けての変更（10 → +5 → +6） | `tests/test_frame_flow.py` |
| 11 代わりの量を出さない／禁止語 | `tests/test_frame_judge.py`（文の検査） |
| 12 history.jsonl | `tests/test_frame_flow.py` |
| 13 右・左 | `tests/test_frame_directions.py` |

受入テストを先に書き、通るまで「できた」と言わない（CLAUDE.md）。

## 5. 実装の前に唐川さん（またはクロちゃん）に確かめること
1. 土台を `feat/voice-stable` にしてよいか（CHECKER_023 の合格後）
2. `_is_synthetic` の拡大（structure_hash 一致の _SIM も出力できる）は、出力できる範囲を広げる変更。安全の線引きとして認めるか
3. 暫定の累積 20mm（枠が無いとき）を、枠があるときも残してよいか（提案：残す。緩めない）
4. 枠が無いジョブで「承認できない」ことにより、今のデモ（DEMO_PLACE の C00004）が承認まで進めなくなる。デモは DEMO_C_PLACE に寄せてよいか
