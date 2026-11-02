# 書き出しの設計（E：変更履歴とUndo／F：承認済みの変更だけをUSB用に出力／G：バイト単位の差分検証）

> **状態：設計の案（2026-11-02、クロ作成）。コードはまだ書いていない。**
> 本人の指示により、この設計に Safety レビューを入れてから、受入テストを先に書いて実装する。
> 基準にしたもの：CLAUDE.md、仕様 v2.1（4・6・7・11・12章）、CURRENT_DECISIONS.md、docs/JBI_FORMAT_NOTES.md、docs/REAL_MACHINE_CHECK.md、
> voice_teaching/jbi.py（レビュー中の写し。次の変更が入る予定のものとして読む：PL=0 は通す／速度の変更は `SPEED_CHANGE_ENABLED=False` で全面禁止／
> 同じ位置への変更は元のジョブを基準に軸ごとの累積で50mm（仮）まで／JUMP・CALL・RET・ラベルがあれば位置の変更を止める／知らない命令は problems で止める）。
> 仕様と決定事項は変えない。変える必要がありそうな点は、各章の「本人に決めてもらうこと」に書いた。

## 0. 全体で共通のこと

### 0-1. 流れ（1承認＝1行＝1書き出し）
```
ジョブを読む（元のバイト列を保持）
  → 引き継ぎを調べる（正規化ハッシュ → 基準と枠）……E
  → Claude の提案 → 検査（jbi.py の止め ＋ 枠 ＋ 基準からの累積）→ 変更案
  → 大きな確認表示 → 承認ボタン → 承認（承認トークン）……F
  → 書き出し：検査のやり直し → 期待するバイト列を元から作り直す → 差分検証 → 新しいファイルとして作る
              → 読み戻してバイト単位で照合 → 変更記録を残す……F・G
  → 「書き出しました」を表示（照合と記録が終わったときだけ）
  → 人がUSBでペンダントに読み込み、ペンダントで選んでスタート（アプリは転送も起動もしない）
```
- **1回の承認で変わるのは1行（位置の数値1つ、または速度の数値1つ）と `//NAME` の行だけ**。1回の承認で1つのファイルを書き出す。
  承認済みの変更を書き出さずに積み重ねることはしない（差分が「承認した1行」にならなくなるため）。
- 次の変更は、**書き出して読み戻したバイト列**を「今のジョブ」として始める。

### 0-2. 守ること（3章すべてに効く）
- Claude はジョブの文字列を書かない。Claude が触れるのは「どの位置・どの軸・何mm」という提案だけ。行の文字列はプログラムが作る。
- 承認はボタンだけ。音声・文字の「承認します」は承認にならない。承認していないジョブは書き出さない。
- アプリは転送しない・ロボットを起動しない（この3章の範囲では、Ethernet・FTP の処理は一切持たない）。
- 元のジョブは変えない・消さない・上書きしない。書き出しは新しい名前の新しいファイルとしてだけ作る。
- 分からないもの（形式・文字コード・改行・名前・記録の不整合）は全部止める。止めたときは理由を出し、何も書かない。
- 失敗したときに成功と表示しない。
- 画面と文章に、安全や距離を断定する言葉（CLAUDE.md「安全の線引き」に挙げた言葉）を使わない。
- **1回50mm、累積50mm（どちらも仮の値）は、このアプリが変更を受け付ける量の上限であって、安全の保証ではない。**
  枠の範囲も同じ。検査を通ったことは、実機の周りの物との距離や、人の安全を保証しない。動かす前の確認（仕様6章「撮影前の確認手順」）は人が行う。

### 0-3. 置き場所（git に入れない）
| もの | 置き場所 | 理由 |
|---|---|---|
| 変更記録・承認・書き出しの記録 | `records/`（.gitignore 済み） | 実機のジョブの行や数値を含むため |
| 書き出したジョブ | 利用者が選ぶフォルダ（USBのドライブ）。既定は `output/`（.gitignore 済み） | 実機のジョブはどのリポジトリにも入れない |
| 枠の設定（実機用） | リポジトリの外、または `records/frames/` | 実機のジョブの基準の値を含むため |

- 書き出し先がリポジトリの中で `output/` 以外（特に `samples/dummy/`。ここは .gitignore の例外で、JBI がコミットされ得る）のときは止める。

### 0-4. 新しく作るモジュールの案
| モジュール | 中身 | 章 |
|---|---|---|
| `voice_teaching/history.py` | 基準・引き継ぎ・累積・変更記録・Undo | E |
| `voice_teaching/approval.py` | 承認トークン・承認の記録 | F |
| `voice_teaching/export.py` | 書き出し（**JBI をファイルに書く唯一の場所**） | F |
| `voice_teaching/byte_diff.py` | バイト単位の差分検証 | G |
| `tests/test_history.py`・`tests/test_export.py`・`tests/test_byte_diff.py` | 受入テスト（実装より先に書く） | E・F・G |

---

## E. ジョブの変更履歴と Undo

### E-1. 目的
- 「どの元のジョブから、誰が・いつ・何を・なぜ・どの枠で変えたか」を残す（製品の中核③、仕様11章テスト23）。
- 繰り返し直しても、**基準（元のジョブ）からの累積**で軸ごとに検査できるようにする（仕様6章、テスト8）。
- 書き出したジョブを読み込み直しても、基準と枠を引き継ぐ。ペンダントなどで中身が変わったジョブは引き継がない（仕様6章、テスト9）。
- 「やめる」「戻す」を、元のジョブや過去のファイルを消さずに行う。

### E-2. 守ること（安全の線引き）
- **基準**は「専門家が枠を保存したときの元のジョブ」（仕様6章）。基準は書き換えない。
- **累積は実際の値から計算する**：「今の値＋今回の量 − 基準の値」を、読み直したジョブの数値から軸ごとに出す。記録の量を足し合わせた値は照合にだけ使い、
  両者が合わなければ止める（丸めのずれや記録の欠けを見逃さないため）。
- 累積の検査は2つとも通す必要がある：
  1. 枠（専門家が決めた、基準からの軸ごとの下限・上限と、1回の変更量）
  2. プログラムの上限（jbi.py：1回50mm（仮）、同じ位置の軸ごとの累積50mm（仮））
  どちらも**安全の保証ではない**。
- 引き継ぎが見つからない、2つ以上見つかる、記録が壊れている、軸が設定されていない → **位置の変更をさせない**（専門家が設定し直す）。
- 変更記録は**追記だけ**。消さない・書き換えない。Undo も「取り消した」という新しい記録を足す。
- 記録の「なぜ」に入れる Claude の文は、検査の判定には使わない（説明として残すだけ）。

### E-3. 基準・積み重ね・引き継ぎの考え方

**基準（BaseSnapshot）**：専門家が枠を保存したとき、元のジョブの正規化ハッシュと、元のバイト列の SHA-256、変えてよい位置の基準の値（文字列のまま）を枠に入れて保存する。

**積み重ね**：変更は木の形になる（同じジョブから別々の変更を書き出すこともあり得る）。各変更記録は「変更前の正規化ハッシュ」と「変更後の正規化ハッシュ」を持つ。
```
基準 H0 ──(+10mm Y, 承認・書き出し)──> H1 ──(+2mm Y)──> H2
                                          └─(Undo：H1→H0 の値に戻す新しい変更)──> H0' (= H0 と同じ中身)
```
- 累積は木の道筋ではなく、**今のジョブの値と基準の値の差**で決める。だから道筋が分岐しても、戻しても、累積は正しく出る。

**引き継ぎ（仕様6章：正規化ハッシュ → 基準・枠・変更記録）**：
読み込んだジョブの正規化ハッシュ H を、次の順で探す。
1. H がある枠の基準のハッシュと一致 → その枠（変更なしの状態）
2. H が「照合まで終わった書き出し」の変更後ハッシュと一致 → その記録の基準と枠
3. どれとも一致しない → 引き継がない（位置の変更をさせない。理由：「このジョブは、記録にある元のジョブやアプリが書き出したジョブと中身が違います。専門家が枠を設定し直してください」）
- 1・2で、**違う基準が2つ以上**見つかったら止める（あいまいなため）。
- 照合が終わっていない書き出し（途中で失敗したもの）の変更後ハッシュでは引き継がない。
- 正規化ハッシュは今の jbi.py の `normalized_hash()`（`//NAME` と `///DATE` の行を除き、改行を除いて UTF-8 で連結した SHA-256）を使う。
  記録には**計算方法の版**（例 `"nh1"`）を一緒に残し、版が違えば引き継がない（計算方法を変えたときに、別物が偶然一致したことにしないため）。
- 枠は「基準のハッシュ」と「枠の中身のハッシュ」を持つ。同じ基準で枠が保存し直されたときは、新しい枠で検査する。変更記録には、そのとき使った枠のハッシュと値を残す。

### E-4. Undo の意味（2種類）
| 名前 | いつ | 何をするか | 何をしないか |
|---|---|---|---|
| **候補を捨てる** | 承認の前（変更案が出ている間）、または承認の後・書き出しの前 | 変更案（と、あれば承認）を無効にする。ジョブもファイルも変わらない。記録には「捨てた」とだけ残す（ジョブの行は残さない） | 書き出し・記録の書き換え |
| **直前の承認済み変更を取り消す** | 書き出した後 | 今のジョブを作った変更記録 R を探し、R の対象の行を **R の変更前の値に戻す変更案** を作る。この案も、検査・大きな確認表示・**ボタン承認**・書き出し（新しい名前）・照合を通常の変更と同じに通す | 過去に書き出したファイルを消す・上書きする／元のジョブを書き換える／記録を消す |

「直前の承認済み変更を取り消す」で止めるもの：
- 今のジョブを作った記録が見つからない、または2つ以上ある
- 対象の行が R の変更後の行とバイト単位で一致しない（どこかで変わっている）
- 戻す変更が今の枠や jbi.py の止め（1回の量、累積、PL・CR、JUMP 等）に通らない（枠が後から厳しくなった場合など。そのときは専門家に相談）
- R が速度の変更で、`SPEED_CHANGE_ENABLED=False` のとき
- 取り消しの取り消しは、普通の変更として扱う（特別扱いしない）

### E-5. データの形（案）
```python
NORMALIZED_HASH_VERSION = "nh1"

@dataclass(frozen=True)
class BaseSnapshot:
    normalized_hash: str          # 基準のジョブの正規化ハッシュ（引き継ぎの鍵）
    raw_sha256: str               # 基準のジョブのバイト列の SHA-256
    job_name: str                 # 表示と記録用（鍵ではない）
    base_tokens: tuple[tuple[str, str, str], ...]  # (位置, 軸, 元の数値の文字列) 例 ("C00004", "Y", "190.000")
    hash_version: str = NORMALIZED_HASH_VERSION

@dataclass(frozen=True)
class AxisLimit:                  # 枠の1軸分（基準からの絶対範囲と1回の変更量。mm）
    lower_mm: float
    upper_mm: float
    step_max_mm: float
    reason_memo: str              # 専門家の理由のメモ（断定の言葉は使わない）

@dataclass(frozen=True)
class Frame:
    frame_hash: str               # 枠の中身（正規化した JSON）のハッシュ
    base: BaseSnapshot
    allowed: dict[str, dict[str, AxisLimit]]  # 位置 → 軸 → 範囲（軸が無ければ変更させない）
    saved_by: str
    saved_at: str                 # ISO 8601（タイムゾーン付き）

@dataclass(frozen=True)
class Lineage:                    # 読み込んだジョブの引き継ぎ
    frame: Frame
    current_normalized_hash: str
    produced_by: str | None       # 今のジョブを作った変更記録の ID（基準そのものなら None）

@dataclass(frozen=True)
class CumulativeCheck:            # 数字はすべてプログラムが計算する
    position: str
    axis: str
    base_value: float
    current_value: float
    proposed_value: float
    cumulative_after_mm: float    # proposed_value - base_value
    remaining_to_upper_mm: float  # 「あと何mm」の空欄に入れる数（プログラムが計算）
    remaining_to_lower_mm: float
    ok: bool
    reason: str | None

@dataclass(frozen=True)
class ChangeRecord:               # 変更記録（追記だけ。records/changes.jsonl に1行1件）
    record_id: str                # UUID
    event: str                    # "exported" | "export_failed" | "discarded" | "approval_revoked"
    lineage_base_hash: str
    before_normalized_hash: str
    after_normalized_hash: str | None
    kind: str                     # "shift" | "speed" | "revert"
    target: str                   # "C00004 Y" など
    meaning_name: str | None      # 専門家が確定した意味の名前（「置く位置」）
    line_index: int
    before_line: str
    after_line: str
    before_value: float
    after_value: float
    cumulative_after_mm: float | None
    who: str                      # 承認した人（E-8 の決めごと待ち）
    when: str                     # 承認の日時（ISO 8601）
    utterance: str                # 利用者の言葉（聞き取った文字。なぜ）
    explanation: str              # 確認表示の文（プログラムが差分から作った文）と Claude の説明
    frame_hash: str
    frame_limits: dict            # そのとき使った枠の値と理由のメモ（どの枠）
    approval_token: str
    source_job_name: str
    source_raw_sha256: str
    output_job_name: str | None
    output_path: str | None
    output_raw_sha256: str | None
    reverts_record_id: str | None # Undo のとき、取り消した記録
    app_version: str              # git のコミットなど
    hash_version: str

class History:
    def __init__(self, records_dir: Path): ...
    def find_lineage(self, job: Job) -> Lineage: ...                 # 見つからない・あいまい → JbiError
    def check_cumulative(self, lineage: Lineage, proposal: ChangeProposal) -> CumulativeCheck: ...
    def plan_revert_last(self, lineage: Lineage, job: Job) -> ChangeProposal: ...
    def append(self, record: ChangeRecord) -> None: ...              # 追記だけ。書けなければ例外
    def list_for(self, lineage: Lineage) -> list[ChangeRecord]: ...  # 画面C用
```
- 記録の書き方：1行1件の JSON（`records/changes.jsonl`）。書いたら `flush`・`fsync` する。読み込みで壊れた行があれば、その系統では位置の変更をさせない。
- jbi.py の累積50mm（仮）の止めは、`BaseSnapshot.base_tokens` から基準の値を渡して使う想定（jbi.py の新しい引数の形は、修正中のブランチに合わせる）。

### E-6. 受入テストの案（`tests/test_history.py`。先に書く）
| # | テスト名（案） | 確かめること | 仕様11章 |
|---|---|---|---|
| E1 | `test_cumulative_is_from_base_not_last_step` | 基準から +10、+10、+10 と書き出したあと、+25 が「累積45」として計算され、枠の上限を超えれば止まる | 8 |
| E2 | `test_cumulative_uses_actual_values_after_rounding` | 丸めで実際の量が違うときも、累積は読み直した値の差で出る。記録の和と食い違えば止まる | 8 |
| E3 | `test_cumulative_is_per_axis` | Y の累積と Z の累積は別に数える | 8 |
| E4 | `test_program_cap_50mm_cumulative_is_separate_from_frame` | 枠が広くても、同じ位置の軸ごとの累積が50mm（仮）を超えると止まる。理由の文に「安全の保証ではない」趣旨の断りがある | 8 |
| E5 | `test_reload_exported_job_inherits_base_and_frame` | 書き出したファイルを読み直すと、同じ基準・枠が見つかる | 9 |
| E6 | `test_name_or_date_only_change_keeps_inheritance` | `//NAME`・`///DATE` だけ違うジョブは引き継ぎが切れない | 9 |
| E7 | `test_other_change_breaks_inheritance` | 位置・命令・コメント・`///ATTR` が1文字でも違えば引き継がず、位置の変更が止まる | 9 |
| E8 | `test_ambiguous_lineage_is_rejected` | 違う基準が2つ見つかれば止まる | 9 |
| E9 | `test_unverified_export_is_not_inherited` | 照合に失敗した書き出しの変更後ハッシュでは引き継がない | 9・21 |
| E10 | `test_frame_without_axis_blocks_shift` | 軸が設定されていない枠では位置の変更が止まる | 7 |
| E11 | `test_discard_candidate_changes_nothing` | 候補を捨てても、ジョブ・ファイル・変更記録（"discarded" 以外）は変わらない | 11 |
| E12 | `test_revert_last_makes_new_proposal_needing_button` | 取り消しは変更案として出るだけで、ボタン承認と書き出しを通るまで何も変わらない | 11・12 |
| E13 | `test_revert_does_not_delete_or_overwrite_files` | 取り消しの書き出しは新しい名前で、過去のファイルと元のジョブはバイト単位で同じまま | 21 |
| E14 | `test_revert_rejected_when_line_differs` | 対象の行が記録の変更後の行と違えば、取り消しは止まる | ― |
| E15 | `test_revert_of_speed_rejected_while_speed_disabled` | `SPEED_CHANGE_ENABLED=False` の間、速度の取り消し案も作らない | ― |
| E16 | `test_record_has_who_when_what_why_frame` | 書き出しのたびに、誰が・いつ・何を（前後の行と値）・なぜ（言葉と説明）・どの枠（ハッシュと値）が残る | 23 |
| E17 | `test_records_are_append_only` | 既存の記録の行は書き換わらない。取り消しも新しい行として足される | 23 |
| E18 | `test_corrupted_record_blocks_changes` | 記録に読めない行があれば、その系統では位置の変更をさせない | ― |
| E19 | `test_hash_version_mismatch_breaks_inheritance` | 計算方法の版が違う記録では引き継がない | 9 |
| E20 | `test_records_dir_is_gitignored` | `records/` が .gitignore に入っている | ― |

### E-7. 未確認事項
- 実機でジョブを読み戻したとき、どの行が変わるか（`///DATE`・`///ATTR`・改行・末尾など）。変わる行によっては、USB で読み込み → 保存し直したジョブの引き継ぎが切れる（仕様6章【未確認：本人】11/3夜）。
- 正規化ハッシュの対象：仕様6章は「命令の並び・位置データ・ツール番号・形態だけで計算」。今の `normalized_hash()` は **`//NAME`・`///DATE` 以外のすべての行**（コメント・`///ATTR`・`///NPOS` を含む）で計算していて、仕様より厳しい（ペンダントでコメントを直しただけでも引き継ぎが切れる）。
- 書き出したジョブの名前の付け方と、ペンダント側で名前を変えた場合に引き継ぎが切れないか（`//NAME` は除いているので切れない設計。ファイル名との関係は F-7）。

### E-8. 本人に決めてもらうこと
1. **「誰が」の取り方**：アプリにはログインが無い。案：起動時に操作する人の名前を入れてもらい（本人確認ではなく自己申告）、記録に残す。
2. 正規化ハッシュの対象を、今のまま（`//NAME`・`///DATE` 以外のすべて。厳しい）にするか、仕様6章どおり（命令・位置・ツール番号・形態だけ）に狭めるか。クロの案：今のままの厳しい方。
3. 「候補を捨てる」を記録に残すか（案：「捨てた」とだけ残し、ジョブの行は残さない）。
4. 変更記録（実機のジョブの行と数値を含む）を、仕様5-3b の申し送り文のために Claude に送ってよいか（デモ用ジョブは送ってよいと本人申告 13:52。会社の他のジョブは送らない、でよいか）。
5. 取り消しは「直前の1件」だけでよいか（任意の過去の変更に戻すのは、普通の変更で行う）。

---

## F. 承認済みの変更だけを USB 用に出力する仕組み

### F-1. 目的
- 人がボタンで承認した変更案と、**まったく同じ中身**のジョブだけを、新しい名前の新しいファイルとして書き出す（仕様4章 画面B 6・7、11章テスト12・21）。
- 書き出しの後に読み戻して照合し、照合と記録が終わったときだけ「書き出しました」と出す。
- USB に入れて、人がペンダントで読み込む。アプリは転送もロボットの起動もしない。

### F-2. 守ること（安全の線引き。Safety レビューの条件をすべて入れる）
1. **承認済みの変更案だけを受け付ける**。書き出しの関数は `ApprovedChange` だけを引数に取り、`Job`・`ChangeProposal`・`bytes` は受け付けない。
2. **承認の後でデータが変わったら承認し直す**。書き出しの直前に承認トークンを計算し直し、承認したときの値と1文字でも違えば止める。対象：元のファイルのバイト列（ディスクから読み直す）、枠のファイル、変更案の中身、新しい名前、書き出し先。
3. **元のジョブのハッシュを確かめる**：読み直した元のバイト列の SHA-256 と正規化ハッシュの両方が、承認したときの値と一致すること。正規化ハッシュは引き継ぎ（E）の今のジョブとも一致すること。
4. **書き出す直前に新しいバイト列を読み直し、元との差が「承認した1行（＋`//NAME` の行）」だけであることをバイト単位で確かめる**（G の `verify_byte_diff`）。
5. **新しい名前は元の名前と違う**（大文字・小文字を区別せずに比べる）。**既存のファイルは上書きしない**：排他作成（Python の `open(path, "xb")`）で新しいファイルとしてだけ作る。同じ名前（大文字・小文字の違いを含む）のファイルが書き出し先にあれば止める。
6. **元の文字コード・改行を保つ**。書いた後に読み戻し、書くつもりのバイト列とバイト単位で照合する。
7. **互換の関数や `render_bytes` から、承認を通らずに書き出せないようにする**：
   - JBI をファイルに書く処理は `export.py` の1か所だけにする（他のモジュールに `write_bytes`・`open(..., "wb"/"xb"/"ab")` を置かない。テストでソースを調べる）。
   - 書き出す中身は `ChangeProposal.new_job`（`lines` は後から書き換えられる list）を**使わない**。承認したときに固めた値（元のバイト列のハッシュ、行番号、変更前・変更後の行のバイト列、新しい名前）から、**元のバイト列を土台に作り直す**。
   - `shift_position`・`set_speed`・`render_bytes` は `Job`・`bytes` を返すだけで、書き出しの関数には渡せない（型で断る）。
8. **自動では転送もロボットの起動もしない**。`export.py` は `socket`・`ftplib`・`subprocess` などを読み込まない（テストで確かめる）。
9. **承認はボタンだけ**。承認の関数は画面のボタンの処理（127.0.0.1 の HTTP の POST）からだけ呼ぶ。Claude の道具には承認・書き出しを入れない。音声・文字で「承認」「OK」と言っても承認にならない。
10. **承認トークンは1回だけ使える**。書き出しが成功したら使用済みにする。失敗したら、そのトークンは無効にして**承認し直し**にする（失敗の原因が分からないまま同じ承認で再挑戦しない）。
11. 速度の変更は `SPEED_CHANGE_ENABLED=False` の間、承認も書き出しもしない（jbi.py の止めに加えて、書き出しの側でも断る）。
12. **失敗したとき成功と表示しない**。元のジョブは残す。
13. 名前の長さの上限は、分かったら定数 `JOB_NAME_MAX_LEN` に入れる（今は【未確認】）。

### F-3. 承認トークン
承認した変更案の中身を、決まった並びの JSON にして SHA-256 を取ったもの。
```
token = "vt-approve-v1:" + sha256( canonical_json({
    "source_raw_sha256":        元のファイルのバイト列の SHA-256,
    "source_normalized_hash":   元のジョブの正規化ハッシュ,
    "hash_version":             "nh1",
    "source_encoding":          "ascii" | "utf-8" | "cp932",
    "source_job_name":          元の名前,
    "lineage_base_hash":        基準の正規化ハッシュ,
    "frame_hash":               枠の中身のハッシュ,
    "kind":                     "shift" | "revert"（速度は今は無効）,
    "target":                   "C00004 Y",
    "line_index":               行番号,
    "before_line_hex":          変更前の行（改行を含むバイト列）の16進,
    "after_line_hex":           変更後の行（改行を含むバイト列）の16進,
    "before_value_text":        "190.000",
    "after_value_text":         "200.000",
    "name_line_index":          //NAME の行番号,
    "new_job_name":             新しい名前,
    "expected_new_raw_sha256":  元のバイト列から作り直した、書き出す予定のバイト列の SHA-256,
    "expected_new_normalized_hash": その正規化ハッシュ,
    "date_policy":              "keep"（G-6 の本人判断待ち）,
    "destination_dir":          書き出し先のフォルダ（絶対パス）,
}))
```
- `canonical_json`：`json.dumps(…, sort_keys=True, ensure_ascii=True, separators=(",", ":"))`。浮動小数は使わず、数値は**ファイルの文字列のまま**入れる。
- 確認表示の画面には、トークンの先頭（例 8文字）を小さく出し、ボタンの POST にトークンを入れて送る。サーバーは今の変更案からトークンを計算し直し、一致したときだけ承認を記録する。
- 「承認の後でデータが変わったら承認し直す」は、書き出しの直前に同じ計算をやり直し、承認のトークンと一致しなければ止めることで行う。

### F-4. 書き出し先と新しい名前
- 書き出し先：利用者が設定で選んだフォルダ（USBのドライブ）。既定は `output/`。
  - フォルダが無い、フォルダでない → 止める（勝手に作らない。`output/` だけは作ってよい）。
  - リポジトリの中で `output/` 以外 → 止める（`samples/dummy/` は特に止める）。
- 新しい名前：
  - 使える文字は今の `rename()` と同じ `[A-Za-z0-9_-]`（実機の規則は【未確認】）。
  - 元の名前と違う（大文字・小文字を区別せずに比べる）。
  - 自動で付ける案：`元の名前 + "_VT" + 2桁の通し番号`（書き出し先と変更記録に無い最初の番号）。付け方は本人判断。
  - 長さの上限 `JOB_NAME_MAX_LEN` は【未確認】。分かるまでは、上限を超えたかを判定できないことを確認表示に出す（勝手な値で切り詰めない）。
- ファイル名 = 新しい名前 + `.JBI`。ファイル名と `//NAME` の名前を同じにする。

### F-5. 書き出しの手順（`export_approved` の中）
1. 承認が有効か（使用済み・取り消し済み・失敗済みでない）。速度の変更でないか（今は無効）。
2. 元のファイルをディスクから読み直す → SHA-256・正規化ハッシュ・文字コードが承認時と一致するか。
3. 枠のファイルを読み直す → ハッシュが承認時と一致するか。引き継ぎ（E）を探し直し、今のジョブと一致するか。
4. **検査をやり直す**：読み直した元のジョブに、同じ位置・軸・量で jbi.py の変更案を作り直し（累積の検査も）、変更後の行が承認した行とバイト単位で同じか。
5. **元のバイト列を土台に、新しいバイト列を作り直す**（`build_new_bytes`：承認した1行と `//NAME` の行だけを差し替える。`new_job` は使わない）。
6. 承認トークンを計算し直し、承認のトークンと一致するか（ここで `expected_new_raw_sha256` も照合される）。
7. **差分検証**（G の `verify_byte_diff(元, 新, 承認)`）。
8. 書き出し先に、同じ名前（大文字・小文字の違いを含む）のファイルが無いか。
9. 変更記録に「書き出しを始めた」を追記（記録が書けなければ止める。ファイルはまだ作らない）。
10. `open(path, "xb")` で新しいファイルとして作り、書いて `flush`・`fsync`・閉じる。
11. **読み戻し**：同じパスをバイト列で読み、書くつもりのバイト列と完全に一致するか。`parse_bytes` で読み直し、`problems` が無く、文字コードが元と同じか。もう一度 `verify_byte_diff(元, 読み戻し, 承認)`。
12. 元のファイルを読み直し、書き出しの前とバイト単位で同じか（元が残っていること）。
13. 変更記録に「書き出した（照合済み）」を追記。トークンを使用済みにする。
14. ここまですべて通ったときだけ `ExportReceipt(ok=True)` を返し、画面に「書き出しました」を出す。

**途中で失敗したとき**
- 1〜9 で失敗：ファイルは作らない。理由を出す。承認は無効にする（承認し直し）。記録に「失敗」を残す。
- 10〜13 で失敗：自分が `xb` で作ったファイルだけを消す（消せなければ、そのファイルのパスを大きく出し「このファイルは使わないでください」と出す）。承認は無効。記録に「失敗」を残す。**「書き出しました」は出さない。**
- 元のファイルには一度も書き込まない（読むだけ）。

画面の文の例（断定の言葉を使わない）：
- 成功：「`DEMO_PLACE_VT01.JBI` を書き出しました。読み戻して、承認した1行とジョブ名の行だけが変わっていることを確かめました。元のジョブ `DEMO_PLACE` はそのまま残っています。動かす前に、低速・ステップで確かめてください。」
- 失敗：「書き出せませんでした（理由：…）。ジョブは変わっていません。もう一度、変更案を確かめて承認してください。」

### F-6. データの形（案）
```python
SPEED_CHANGE_ENABLED = False      # jbi.py と同じ値を使う（2か所で別々に定義しない）
JOB_NAME_MAX_LEN: int | None = None   # 【未確認】分かったら入れる

@dataclass(frozen=True)
class ApprovalSnapshot:           # 承認したときに固めた中身（bytes と tuple だけ。list を持たない）
    source_path: str
    source_raw_sha256: str
    source_normalized_hash: str
    source_encoding: str
    source_job_name: str
    lineage_base_hash: str
    frame_hash: str
    kind: str
    target: str
    position: str | None
    axis: str | None
    requested_mm: float | None
    line_index: int
    before_line: bytes            # 改行を含む
    after_line: bytes             # 改行を含む
    before_value_text: str
    after_value_text: str
    name_line_index: int
    new_job_name: str
    expected_new_raw_sha256: str
    expected_new_normalized_hash: str
    date_policy: str              # "keep"
    destination_dir: str

@dataclass(frozen=True)
class ApprovedChange:
    snapshot: ApprovalSnapshot
    token: str
    approved_by: str
    approved_at: str
    via: str                      # 必ず "button"（それ以外の値では作れない）

class ApprovalBook:               # サーバーの中だけに持つ。承認の状態（有効・使用済み・無効）
    def prepare(self, proposal: ChangeProposal, source_bytes: bytes, lineage: Lineage,
                new_job_name: str, destination_dir: Path) -> tuple[ApprovalSnapshot, str]: ...
        # 確認表示を出すときに呼ぶ。トークンを返す（まだ承認ではない）
    def approve_from_button(self, pending_id: str, shown_token: str, operator: str,
                            session_nonce: str) -> ApprovedChange: ...
        # ボタンの POST の処理からだけ呼ぶ。トークンを計算し直して一致しなければ JbiError
    def revoke(self, token: str, reason: str) -> None: ...   # 候補を捨てる・失敗したとき
    def consume(self, token: str) -> None: ...               # 書き出しが成功したとき

@dataclass(frozen=True)
class ExportReceipt:
    ok: bool
    output_path: str | None
    output_raw_sha256: str | None
    message: str                  # 画面に出す文（断定の言葉を使わない）
    reason_code: str | None       # 失敗の理由の種類

def build_new_bytes(source: bytes, snap: ApprovalSnapshot) -> bytes: ...
def export_approved(approved: ApprovedChange, book: ApprovalBook, history: History) -> ExportReceipt: ...
```
- `ApprovedChange` は `ApprovalBook.approve_from_button` だけが作る。`ExportReceipt(ok=True)` は `export_approved` の最後でだけ作る。
- 書き出しの関数は `isinstance(approved, ApprovedChange)` でなければ断る（`Job`・`ChangeProposal`・`bytes` を渡したら止まる）。さらに `book` に有効な承認として登録されていなければ断る（`ApprovedChange` を手で作っても通らない）。

### F-7. 受入テストの案（`tests/test_export.py`。先に書く）
| # | テスト名（案） | 確かめること | 仕様11章 |
|---|---|---|---|
| F1 | `test_unapproved_proposal_cannot_be_exported` | `ChangeProposal`・`Job`・`bytes`・`render_bytes()` の結果を渡すと断られ、ファイルが作られない | 12 |
| F2 | `test_hand_made_approved_change_is_rejected` | `ApprovalBook` に登録の無い `ApprovedChange` は断られる | 12 |
| F3 | `test_compat_functions_cannot_reach_file_output` | `shift_position`・`set_speed` の結果から書き出す道が無い。`export.py` 以外のモジュールに JBI のファイル書き込みが無い（ソースを調べる） | 11・12 |
| F4 | `test_mutating_new_job_lines_after_approval_has_no_effect` | 承認の後に `proposal.new_job.lines` を書き換えても、書き出されるのは承認した中身（または止まる） | 12 |
| F5 | `test_source_changed_after_approval_requires_reapproval` | 承認の後で元のファイルが1バイト変わると止まり、承認し直しになる | 12 |
| F6 | `test_frame_changed_after_approval_requires_reapproval` | 承認の後で枠のファイルが変わると止まる | 12 |
| F7 | `test_source_normalized_hash_must_match_lineage` | 元の正規化ハッシュが引き継ぎと違えば止まる | 9 |
| F8 | `test_guards_are_rerun_before_export` | 承認の後で jbi.py の止めに通らなくなった場合（例：上限の定数を下げる）、書き出さない | 6 |
| F9 | `test_new_name_must_differ_from_original` | 同じ名前・大文字小文字だけ違う名前は止まる | ― |
| F10 | `test_never_overwrites_existing_file` | 書き出し先に同じ名前（大文字小文字の違いを含む）があれば止まり、既存のファイルはバイト単位で同じまま | 21 |
| F11 | `test_original_file_is_unchanged_after_export` | 書き出しの後、元のファイルはバイト単位で同じ | 21 |
| F12 | `test_readback_mismatch_is_not_success` | 書いた後の読み戻しが違う場合（書き込みを差し替えるテスト用の仕掛けで再現）、成功と出ず、作ったファイルは消される（または使わない旨が出る） | 21 |
| F13 | `test_write_error_is_not_success` | 書き込みの途中の例外（USB が抜けた想定）で、成功と出ない。承認は無効になる | 21 |
| F14 | `test_token_is_single_use` | 同じ承認で2回書き出せない | 12 |
| F15 | `test_failed_export_requires_reapproval` | 失敗の後、同じトークンでは再挑戦できない | 21 |
| F16 | `test_voice_or_text_cannot_approve` | 「承認します」「OK」の発話・文字では承認が作られない。Claude の道具の一覧に承認・書き出しが無い | 12 |
| F17 | `test_speed_change_not_exported_while_disabled` | `SPEED_CHANGE_ENABLED=False` の間、速度の変更は承認も書き出しもされない | ― |
| F18 | `test_export_does_not_transfer_or_start_robot` | `export.py` が `socket`・`ftplib`・`subprocess` などを読み込まない。書き出し先以外にファイルを作らない | ― |
| F19 | `test_destination_inside_repo_is_rejected` | 書き出し先が `samples/dummy/` など、リポジトリの中の `output/` 以外なら止まる | ― |
| F20 | `test_success_message_has_no_assertive_words` | 成功・失敗の文に、断定の言葉（CLAUDE.md の一覧）が無い | 18 |
| F21 | `test_record_written_only_after_verified_export` | 「書き出した（照合済み）」の記録は照合の後にだけ残る。失敗は「失敗」として残る | 21・23 |
| F22 | `test_name_length_limit_applied_when_known` | `JOB_NAME_MAX_LEN` を入れたら、それを超える名前は止まる（値は確認後） | ― |
| F23 | `test_end_to_end_dummy_shift_export` | ダミーで「C00004 Y +10」→ 承認ボタン → 書き出し → 読み戻し照合 → 記録、がすべて通る | 2・12・23 |

### F-8. 未確認事項
- YRC1000 が USB からジョブを読み込むときのフォルダの決まり、ファイル名と `//NAME` が違うときの扱い、同じ名前のジョブがコントローラにあるときの動き（仕様15章 8）。
- ジョブ名に使える文字（小文字を使えるか）と長さの上限。
- USB の形式（FAT32 など）。排他作成（`xb`）は FAT32 でも効く想定だが、実機の PC で確かめる。
- 読み戻しは OS のキャッシュから返ることがあり、USB の中身そのものを読んだとは限らない。本当の照合は、ペンダントで読み込んだ後の確認（仕様11章テスト24・REAL_MACHINE_CHECK.md 4章）で行う。
- アプリが書き出したジョブをペンダントが受け付けるか（仕様12章 11/3夜④）。

### F-9. 本人に決めてもらうこと
1. **新しい名前の付け方**（案：`元の名前_VT01` のように通し番号）と、名前を利用者が手で入れられるようにするか。
2. **承認と書き出しを1つのボタンにするか、2つに分けるか**（案：2つに分ける。承認の後、書き出しの前に「やめる」ができる）。
3. 承認の有効期限を設けるか（案：設けない。代わりに書き出しの直前にすべてを計算し直す）。
4. 照合に失敗したとき、作ったファイルを**消す**か、**名前を変えて残す**（例 `.JBI.NG`）か（案：消す。消せなければパスを大きく出す）。
5. 書き出し先を、毎回選ぶか、設定で決めておくか。
6. 「誰が」承認したかの取り方（E-8 の1と同じ）。

---

## G. 書き出し前後のバイト単位の差分検証

### G-1. 目的
- 書き出すバイト列が「元のバイト列のうち、承認した1行と `//NAME` の行だけを変えたもの」であることを、**行の単位とバイトの単位の両方**で確かめる。
- 書き出しの前（作り直したバイト列）と後（読み戻したバイト列）の2回、同じ関数で確かめる（F-5 の 7・11）。

### G-2. 守ること（安全の線引き）
- 比べるのは**バイト列**。文字列に直してから比べて「同じ」とはしない（文字コードや改行の違いを見逃さないため）。
- 許す差は、下の定義に**書いたものだけ**。それ以外の差は、どんなに小さくても（空白1つ、改行1つ、末尾の改行の有無）落とす。
- 期待する値は、`ApprovalSnapshot`（承認したときに固めた値）から取る。`ChangeProposal.new_job` は使わない。
- 落ちたら何も書かない（書いた後なら F-5 の失敗の扱い）。理由は種類（コード）と行番号で返す。行の中身は画面と記録に出してよいが、Claude には送らない。

### G-3. 関数の入力と出力（案）
```python
@dataclass(frozen=True)
class DiffViolation:
    code: str          # 下の表の種類
    line_no: int | None  # 1から数えた行番号
    detail: str        # 利用者に見せる文（断定の言葉を使わない）

@dataclass(frozen=True)
class DiffReport:
    ok: bool
    changed_lines: tuple[int, ...]       # 実際に違った行（0から）
    violations: tuple[DiffViolation, ...]

def split_lines_bytes(data: bytes) -> list[bytes]:
    """b"\\n" だけで分け、各行に改行（\\r\\n または \\n、最後の行は無いこともある）を含めたまま返す。"""

def verify_byte_diff(original: bytes, new: bytes, approved: ApprovedChange) -> DiffReport: ...
```

### G-4. 許す差の定義
**行の単位**
1. `split_lines_bytes(original)` と `split_lines_bytes(new)` の行の数が同じ。
2. 違ってよい行は、`approved.snapshot.line_index`（承認した行）と `name_line_index`（`//NAME` の行）の**2つだけ**。この2つは別の行であること。
3. それ以外の行は、改行を含めて**バイト単位で完全に同じ**。
4. （`///DATE` を変える方針になったときだけ）`///DATE` の行も違ってよい。形は `///DATE YYYY/MM/DD HH:MM` に限る（G-6）。

**承認した行（バイトの単位）**
5. 元の行 == `snapshot.before_line`、新しい行 == `snapshot.after_line`（どちらも改行を含めてバイト単位で一致）。
6. 2つの行の改行（`\r\n` か `\n`）が同じ。
7. 違う部分は**数値1つの中だけ**：
   - 位置：`Cnnnnn=` の後ろをカンマで分け、`snapshot.axis` の欄（X=1つ目、Y=2つ目、Z=3つ目）だけが違う。他の欄・カンマの数・`Cnnnnn=` の部分はバイト単位で同じ。
   - 速度（今は無効）：`V=` の数値だけが違う。
8. 変えた欄は `^[+-]?\d+(\.\d+)?$` の形で、**小数点以下の桁数が元と同じ**。元の欄 == `before_value_text`、新しい欄 == `after_value_text`。
9. 変えた欄の数値の差が、承認した量（丸めた後の実際の量）と一致する（文字列の数値を `Decimal` で引き算して比べる。浮動小数を使わない）。

**`//NAME` の行**
10. 元の行 == `b"//NAME " + 元の名前 + 改行`、新しい行 == `b"//NAME " + 新しい名前 + 同じ改行`。後ろの空白など、この形でない名前の行は**止める**（分からない形）。
11. 新しい名前は `[A-Za-z0-9_-]` だけで、元の名前と違う（大文字・小文字を区別せずに比べる）。

**全体**
12. 文字コード：`parse_bytes(new)` が元と同じ文字コードで読め、書き戻しで `new` と完全に一致する。`problems` が無い。
13. 改行：各行の改行の種類と、最後の行に改行があるかどうかが、元と同じ（混ざった改行もそのまま）。BOM の有無も同じ（先頭の行のバイト一致で確かめられる）。
14. 読み直した意味の照合：変えた位置の変えた軸だけが `after_value_text` の値になり、他の位置・他の軸・命令の並び・ツール番号・形態・ユーザ座標は元と同じ。
15. `sha256(new) == snapshot.expected_new_raw_sha256`、`normalized_hash(new) == snapshot.expected_new_normalized_hash`。
16. `normalized_hash(original) == snapshot.source_normalized_hash`、`sha256(original) == snapshot.source_raw_sha256`。

**落ちる種類（`code`）の例**：`LINE_COUNT`・`UNEXPECTED_LINE`・`TARGET_LINE_MISMATCH`・`OTHER_FIELD_CHANGED`・`DECIMALS_CHANGED`・`DELTA_MISMATCH`・`NAME_LINE_FORM`・`NAME_SAME`・`LINE_ENDING`・`FINAL_NEWLINE`・`ENCODING`・`PROBLEMS`・`SEMANTIC_MISMATCH`・`HASH_MISMATCH`・`SAME_INDEX`。

### G-5. 改行・文字コード
- 改行は**行ごとに**元のものを保つ（`\r\n` と `\n` が混ざっていても、そのまま）。今の jbi.py は `\n` を伴わない `\r` を `problems` で止めるので、それは読み込みの時点で止まる。
- 文字コードは jbi.py の `parse_bytes` と同じ（ascii → utf-8 → cp932 の順に試し、書き戻して元と一致するときだけ扱う）。書き出しで変える部分（数値と名前）は ASCII だけなので、どの文字コードでもバイト列は同じ形になる。名前に ASCII 以外を使わない（G-4 の11）。
- 差し替えはバイト列の上で行う（`build_new_bytes`）。元の行のバイト列を文字列に直してから書き直すことはしない。

### G-6. `//NAME` と `///DATE` の扱い
- `//NAME`：新しい名前に変える（必ず変わる）。正規化ハッシュでは除かれる。
- `///DATE`：**クロの案は「変えない」**（`date_policy="keep"`）。差分が「承認した1行＋`//NAME`」だけになり、検証が単純になる。正規化ハッシュでは除かれるので、変えても変えなくても引き継ぎには影響しない。
  変える場合（`date_policy="export_time"`）は、G-4 の4を許し、形が `///DATE YYYY/MM/DD HH:MM` の行だけを書き出しの時刻に変える。この行が無い・形が違うときは止める。**どちらにするかは本人判断**。

### G-7. 検証に落ちたときの扱い
- 書き出しの前（F-5 の7）：ファイルを作らない。理由（種類と行番号）を画面に出す。承認は無効にする（承認し直し）。記録に「失敗」と種類を残す。
- 書き出しの後（F-5 の11）：自分が作ったファイルを消す（消せなければパスと「使わないでください」を出す）。承認は無効。記録に「失敗」を残す。
- どちらも「書き出しました」は出さない。元のジョブは変わらない（読むだけ）。
- 検証の失敗は、プログラムの不具合か、承認の後の変化の印。Claude に言い直させて量を変えた案を出し直すことはしない（同じ発話の中での出し直しは、もともと禁止）。

### G-8. 受入テストの案（`tests/test_byte_diff.py`。先に書く）
| # | テスト名（案） | 確かめること |
|---|---|---|
| G1 | `test_exact_expected_bytes_pass` | 承認した1行と `//NAME` だけが違うバイト列は通る（LF のダミー・CRLF にしたダミー・cp932 のコメント入りの3種） |
| G2 | `test_unchanged_roundtrip_equals_original` | 何も変えない読込→書出しが元と完全に一致（仕様テスト1。書き出しの土台の確認） |
| G3 | `test_any_other_line_change_fails` | 他の行を1バイト変えると落ちる（位置の行・命令の行・コメント・`///ATTR`・`///DATE`（keep のとき）） |
| G4 | `test_other_field_in_target_line_fails` | 承認した行の別の軸・姿勢（Rx・Ry・Rz）が違えば落ちる |
| G5 | `test_decimal_places_change_fails` | `200.000` が `200.00` や `200` になれば落ちる |
| G6 | `test_delta_mismatch_fails` | 変えた欄の差が承認した量と違えば落ちる（`Decimal` で比べる） |
| G7 | `test_line_ending_change_fails` | 1行でも `\r\n`⇔`\n` が変われば落ちる。最後の行の改行の有無が変われば落ちる |
| G8 | `test_line_count_change_fails` | 行が増える・減ると落ちる（末尾に空行を足す、を含む） |
| G9 | `test_encoding_change_fails` | 同じ中身を別の文字コードにすると落ちる。BOM を足すと落ちる |
| G10 | `test_name_line_must_have_exact_form` | `//NAME` の後ろに空白がある、名前が同じ、名前に ASCII 以外がある → 落ちる |
| G11 | `test_approved_line_and_name_line_must_differ` | 承認した行番号と `//NAME` の行番号が同じなら落ちる |
| G12 | `test_hashes_must_match_snapshot` | `expected_new_raw_sha256`・正規化ハッシュ・元のハッシュが違えば落ちる |
| G13 | `test_new_job_lines_are_not_used` | `ChangeProposal.new_job.lines` を書き換えても、検証の期待値は変わらない |
| G14 | `test_date_policy_keep_rejects_date_change` | `keep` のとき `///DATE` の変化で落ちる。`export_time` のときは決まった形の変化だけ通る（本人判断の後に有効にする） |
| G15 | `test_violation_messages_have_no_assertive_words` | 落ちた理由の文に断定の言葉が無い |

### G-9. 未確認事項
- 実機のジョブの改行（CRLF か）と文字コード（Shift_JIS か）、最後の行に改行があるか（REAL_MACHINE_CHECK.md チェック表 8）。
- 実機のジョブで `//NAME` の行の形（後ろの空白、名前の長さ、使える文字）。
- `///DATE` を変えないジョブを、ペンダントが問題なく読み込むか（日付で何かを判定しているか）。
- 数値の書き方：実機の位置の値が常に同じ小数点以下の桁数か、`+` 記号や先頭の0が付くことがあるか（付く場合、今の `_format_like` は元の書き方を保たない。そのときは止める側に倒す必要がある）。

### G-10. 本人に決めてもらうこと
1. **`///DATE` を書き出しで変えるか**（クロの案：変えない）。
2. 数値の書き方が元と違う形になる場合（`+` や先頭の0など）は止める、でよいか（クロの案：止める）。

---

## まとめ：Safety レビューで特に見てほしい点
1. **書き出しの中身を `new_job` から作らず、元のバイト列から作り直す**（F-5 の5、G）。承認したときに固めた `ApprovalSnapshot` が本当に変更できないか（`bytes`・`str`・`tuple` だけで、`list` を持たない）。
2. **承認トークンに入れる項目**（F-3）に抜けがないか。特に、書き出し先・枠・`date_policy`・ハッシュの計算方法の版。
3. **「書き出しを JBI のファイルに書くのは `export.py` だけ」をテストで守る方法**（F3：ソースを調べる）で十分か。`render_bytes` を残すことの危うさ。
4. **累積を実際の値の差で出す**（E-2）と、記録の和との食い違いで止める設計。道筋が分岐した場合（同じジョブから別々に書き出す）でも累積が正しく出るか。
5. **引き継ぎが見つからない・あいまい・記録が壊れている・照合が終わっていない書き出し**で、すべて変更が止まるか（E-3）。
6. **Undo（取り消し）を「新しい変更案」にして、ボタン承認と書き出しを通す**設計（E-4）。取り消しが枠や止めに通らない場合の扱い。
7. **失敗したときの順番**（F-5）：記録を先に書く → ファイル → 読み戻し → 記録。どこで止まっても「書き出しました」が出ないか。作ったファイルを消すことの是非。
8. 読み戻しが OS のキャッシュから返る限界（F-8）を、画面の文でどう伝えるか。
9. 50mm・累積50mm・枠の範囲を、画面と記録で「受け付ける量の上限であって、安全の保証ではない」と書くこと（0-2・E-2）。

## まとめ：本人に決めてもらうこと（一覧）
| # | こと | クロの案 | 章 |
|---|---|---|---|
| 1 | 「誰が」の取り方（ログインが無い） | 起動時に名前を入れてもらう（自己申告） | E-8・F-9 |
| 2 | 正規化ハッシュの対象（仕様6章より今の実装が厳しい） | 今のまま（`//NAME`・`///DATE` 以外すべて） | E-8 |
| 3 | 「候補を捨てる」を記録に残すか | 「捨てた」とだけ残す | E-8 |
| 4 | 変更記録を Claude に送る範囲 | デモ用ジョブだけ | E-8 |
| 5 | 取り消しは直前の1件だけか | 直前の1件だけ | E-8 |
| 6 | 新しい名前の付け方・手入力の可否 | `元の名前_VT01` の通し番号 | F-9 |
| 7 | 承認と書き出しのボタンを分けるか | 分ける | F-9 |
| 8 | 承認の有効期限 | 設けない（直前に計算し直す） | F-9 |
| 9 | 照合に失敗したファイルを消すか残すか | 消す | F-9 |
| 10 | 書き出し先の決め方 | 設定で決めておく（毎回確認表示に出す） | F-9 |
| 11 | `///DATE` を変えるか | 変えない | G-10 |
| 12 | 数値の書き方が変わる場合は止めるか | 止める | G-10 |
| 13 | （実機で確認）ジョブ名の長さ・使える文字、USB のフォルダの決まり、同じ名前の扱い、改行・文字コード、読み戻しで変わる行 | ― | E-7・F-8・G-9 |
