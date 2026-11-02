# 書き出しの設計（E：変更履歴とUndo／F：承認済みの変更だけをUSB用に出力／G：バイト単位の差分検証）

> **状態：設計の案 第2版（2026-11-02、クロ作成）。コードはまだ書いていない。**
> 第1版への Safety レビュー（CONDITIONAL PASS）の P1 4件と P2 の一部を入れた。本人の方針「必要以上に設計を複雑化しない」に合わせ、
> **1章「最小版」を実装の基準**とし、2〜4章（E・F・G）は最小版の補足、5章は「後回し・将来」の一覧にした。
> 基準にしたもの：CLAUDE.md、仕様 v2.1（4・6・7・11・12章）、CURRENT_DECISIONS.md、docs/JBI_FORMAT_NOTES.md、docs/REAL_MACHINE_CHECK.md、
> voice_teaching/jbi.py（レビュー中の写し。修正予定：PL=0 は通す／`SPEED_CHANGE_ENABLED=False` で速度の変更は全面禁止／
> 同じ位置は元のジョブを基準に軸ごとの累積で50mm（仮）まで／JUMP・CALL・RET・ラベルがあれば位置の変更を止める／知らない命令は problems で止める）、
> voice_teaching/sim.py（ブランチ feat/sim-core）。仕様と決定事項は変えない。変える必要がありそうな点は6章「本人に決めてもらうこと」に書いた。

**どの章にも共通の線引き**
- Claude はジョブの文字列を書かない。行の文字列はプログラムが作る。承認はボタンだけ。承認していないジョブは書き出さない。
- アプリは転送もロボットの起動もしない。元のジョブは変えない・消さない・上書きしない。
- 分からないもの（形式・文字コード・改行・名前・記録や枠の不整合）は全部止め、理由を出し、何も書かない。失敗したときに成功と表示しない。
- 画面と文章に、安全や距離を断定する言葉（CLAUDE.md「安全の線引き」に挙げた言葉）を使わない。
- **1回50mm・累積50mm（どちらも仮）と枠の範囲は、このアプリが変更を受け付ける量の上限であって、安全の保証ではない。** 動かす前の確認（仕様6章）は人が行う。
- **前提：このPCの手元のファイル（records/・枠・元のジョブ）は、悪意で書き換えられていないものとして扱う。** ハッシュの照合は、うっかりの変化や食い違いを見つけるためのもので、改ざんを防ぐ仕組みではない。

---

## 1. 最小版（実装の基準。11/3〜11/4夜の実機確認まで）

### 1-1. 流れ（1承認＝1行＝1書き出し）
```
元のジョブを読む → 引き継ぎを探す（規則1・2）→ 検査（jbi.py の止め＋枠＋基準の写しとの差による累積）→ 変更案
 → 確認表示 → 承認ボタン（承認帳に snapshot を保存・乱数の承認ID）
 → export_approved(承認ID)：承認帳の確認 → 元の読み直しとハッシュ照合 → 枠の読み直しと検証 → 検査のやり直し
   → 元のバイト列から作り直し → トークン再計算 → 差分検証 → 新しい名前 → .partial に排他作成 → 読み戻し照合
   → 記録 → 名前を .JBI に変える → 再読み戻し → 記録 → 「書き出しました」
```
- 1回の承認で変わるのは**1行（位置の数値1つ）と `//NAME` の行だけ**。承認済みの変更を書き出さずに積み重ねない。次の変更は、書き出して読み戻したバイト列から始める。
- 速度の変更は `SPEED_CHANGE_ENABLED=False` の間、承認も書き出しもしない（書き出しの側でも断る）。

### 1-2. 基準の写しと枠（P1-1・P1-2）
**基準の写し**
- 枠を登録するとき、基準のジョブのバイト列の写しを `records/bases/<SHA-256>.JBI` に置く（`export.py` が排他作成。同じ名前があれば中身が同じことだけ確かめ、上書きしない）。
- **枠を読むたびに**、写しから `raw_sha256`・`normalized_hash`・基準の値（`base_tokens`）を計算し直し、枠の中の値と照合する。合わなければ止める。**枠に手で書いた値は信用しない。**
- 累積（枠の検査、jbi.py の累積50mm（仮）の両方）の基準の値は、**この写しから取る**。
- **枠の登録を断る**：そのジョブの正規化ハッシュが、変更記録のどれかの「変更後ハッシュ」と一致するとき（アプリが書き出したジョブを基準にし直して、累積を0に戻すことを防ぐ）。

**枠の置き場所と形**
- 枠は `records/frames/` の1か所だけ（最小版では専門家が手で書いた JSON を置き、アプリは読むだけ）。
- **枠の検証**（1つでも外れたら、その枠を使わない）：
  - 数値は有限で、bool でない。`lower_mm ≤ 0 ≤ upper_mm`、`0 < step_max_mm`
  - 位置が基準のジョブにある。軸は `X`・`Y`・`Z` だけ
  - 知らないキー、JSON の重複キー（`object_pairs_hook` で検出）は断る
  - 基準の写しとの照合（上）が合う
- 同じ基準（正規化ハッシュ）を持つ枠が2つ以上あれば止める。

### 1-3. 引き継ぎ（仕様6章）と累積
読み込んだジョブの正規化ハッシュ H で探す（ハッシュの計算方法の版 `nh1` も一致すること）。
- **規則1**：H が、ある枠の基準のハッシュと一致 → その枠
- **規則2**：H が、`exported`（最後まで照合が済んだ書き出し）の記録の変更後ハッシュと一致 → その記録の基準の枠
- 規則1・2の両方に一致する場合（取り消して元と同じ中身に戻った等）は、**同じ基準を指すときだけ**使う。違う基準を指せば止める。
- どれにも一致しない・あいまい・**記録に壊れた行が1つでもある** → 位置の変更をさせない（専門家が設定し直す）。
- 累積＝「変更後の値 − 基準の写しの値」を、読み直したジョブの数値から軸ごとに計算する。記録の和は使わない。
- 枠（基準からの下限・上限、1回の変更量）と、jbi.py の上限（1回50mm・累積50mm、仮）の**両方**を通す必要がある。どちらも安全の保証ではない。

### 1-4. モードの分け方（P1-3）
- 書き出しの関数は **`export_approved` の1つだけ**。モードは `"real"`（実機用）と `"sim"`（開発・シミュレーション用）。**モードで検査を緩めない**（止め・枠・累積・差分検証・承認はすべて同じ）。
- モードが違うのは次だけ：

| | real | sim |
|---|---|---|
| 受け付ける元のジョブ | 何でも（検査を通るもの） | **合成ジョブの許可リスト**（`samples/dummy/SYNTHETIC_SHA256.txt` の SHA-256 に一致するバイト列）だけ |
| 書き出し先 | **既定を持たない**。利用者が選ぶ。`realpath` で解決した先がリポジトリの中なら止める | `output/sim/` だけ（`realpath` で確かめる） |
| 名前 | 1-6 の規則 | 1-6 の規則に `_SIM` を付ける |

- モードは承認トークンと変更記録に入れる。引き継ぎは同じモードの記録の中だけで探す。
- **sim.py との関係（案）**：`export_sim` は `export_approved(mode="sim")` に置き換え、sim.py は候補を作る側（`simulate_shift` とプレビュー）だけにする。
  - sim.py は今、実機用の検査で止まった案（`blocked_reason` あり）も、合成ジョブなら出力できる。**「モードで検査を緩めない」に合わせ、止まった案は表示だけにし、承認・書き出しはしない。**
  - あわせて、合成ジョブかどうかの判定はファイルとの比較から SHA-256 の許可リストに、書き出す中身は `proposal.new_bytes` から元のバイト列での作り直し（1-5）に揃える。
  - この変更は feat/sim-core の作業に影響するので、6章で本人とシクロに確かめる。

### 1-5. 承認帳・トークン・書き出しの手順（P2-1・P2-2・P2-3・P2-5）
**承認帳（`ApprovalBook`。メモリだけ）**
- 承認ボタンの POST で、サーバーが `ApprovalSnapshot` を作って承認帳に保存し、**乱数の承認ID**（`secrets.token_urlsafe`）を割り当てる。
- `export_approved` は承認IDだけを受け取り、**承認帳に保存した snapshot だけを使う**（引数の snapshot・`ChangeProposal.new_job`・`Job`・`bytes` は使わない、受け付けない）。
- 承認IDは1回だけ使える。成功したら使用済み、失敗したら無効（承認し直し）。アプリを再起動すると承認はすべて消える。
- **トークン**＝`ApprovalSnapshot` の全項目（元の raw/正規化ハッシュ・文字コード・名前、基準と枠のハッシュ、モード、対象・行番号、変更前後の行のバイト列、変更前後の数値の文字列、`//NAME` の行番号、新しい名前、書き出す予定のバイト列の SHA-256、書き出し先）＋**確認表示の文**を、決まった並びの JSON にした SHA-256。書き出しの直前に計算し直し、1文字でも違えば止める（＝承認し直し）。

**承認の POST の守り（CSRF 対策）**
- POST だけを受け付ける。サーバー起動時に作る推測できない値をページに埋め、POST に入っていなければ断る。`Host` が `127.0.0.1:ポート`・`localhost:ポート`、`Origin` が同じでなければ断る。
- 限界：同じPCで動く別のプログラムは防げない（前提の「手元のファイルを信用する」と同じ扱い）。防ぐのは、他のサイトのページからの承認の送りつけ。
- 音声・文字の「承認します」は承認にならない。Claude の道具に承認・書き出しを入れない。

**書き出しの手順（`export_approved`）**
1. 承認帳に有効な承認IDがあるか。モードの条件（1-4）、速度でないことを確かめる。
2. **同時書き出しの排他**：プロセスの中のロックに加え、`records/export.lock` を排他作成する（あれば止めて「別の書き出しが途中です」。古いロックは人が確かめて消す）。
3. 元のファイルを読み直し、raw SHA-256・正規化ハッシュ・文字コードが snapshot と一致するか。
4. 枠と基準の写しを読み直して検証（1-2）し、引き継ぎ（1-3）が snapshot と同じ基準を指すか。
5. **検査をやり直す**：同じ位置・軸・量で jbi.py の変更案と累積の検査を作り直し、変更後の行が snapshot とバイト単位で同じか。
6. **元のバイト列から作り直す**（承認した1行と `//NAME` の行だけを、バイト列の上で差し替える）。
7. トークンを計算し直して一致するか。
8. **差分検証**（4章の `verify_byte_diff`）。
9. 書き出し先に同じ名前（大文字・小文字の違いを含む）の `.JBI` と `.JBI.partial` が無いか。
10. 記録に `export_started` を追記。
11. `NAME.JBI.partial` を排他作成（`"xb"`）→ 書く → `flush`・`fsync` → 閉じる → 読み戻してバイト一致と差分検証。
12. 記録に `export_written` を追記。
13. `.partial` を `NAME.JBI` に名前を変える（**上書きしない方法で**：Windows の `os.rename` は相手があれば失敗する。`os.replace` は使わない）。
14. `NAME.JBI` を読み直してバイト一致。元のファイルが書き出しの前とバイト単位で同じか。
15. 記録に `exported` を追記し、承認IDを使用済みにし、ロックを外す。ここまで通ったときだけ「書き出しました」。

**失敗したとき**：ファイルを作る前（1〜10）なら何も作らない。作った後（11〜14）なら、自分が作った `.partial`／`.JBI` だけを消す（消せなければパスを大きく出し「このファイルは使わないでください」）。どちらも `export_failed` を記録し、承認を無効にし、成功と出さない。`.partial` の名前ではペンダントが読み込まない想定（【未確認】）なので、途中で落ちても読み込める `.JBI` は、照合の済んだ中身でしか残らない。`export_written` があって `exported` が無い記録は、起動時に一覧で知らせる（引き継ぎには使わない）。

**画面の文の例**
- 成功：「`DEMO_PLACE_VT01.JBI` を書き出しました。このPCで読み戻して、承認した1行とジョブ名の行だけが変わっていることを照合しました。USBの中身そのものを確かめたものではありません。ペンダントで読み込んだ後に、変わった行を確かめてください。元のジョブ `DEMO_PLACE` はそのまま残っています。動かす前に、低速・ステップで確かめてください。」
- 失敗：「書き出せませんでした（理由：…）。ジョブは変わっていません。もう一度、変更案を確かめて承認してください。」

### 1-6. 新しい名前と書き出し先
- 新しい名前は `[A-Za-z0-9_-]` だけ、元の名前と違う（大文字・小文字を区別せずに比べる）。案：`元の名前_VT01`（書き出し先と記録に無い最初の番号）。ファイル名＝新しい名前＋`.JBI`＝`//NAME` の名前。
- 長さの上限 `JOB_NAME_MAX_LEN` は【未確認】。分かったら入れる（それまで勝手な値で切り詰めない）。
- 既存のファイルは上書きしない（1-5 の9・11・13）。

### 1-7. 書き込みを許可リストで限る（P1-4）
- **主な守りは型と承認帳**（`export_approved` は承認IDしか受け付けず、中身は承認帳の snapshot と元のバイト列から作る）。下の2つは補助。
- **許可リスト**：ファイルに書いてよいのは次だけ。
  | モジュール | 書いてよいもの |
  |---|---|
  | `export.py` | `.JBI`・`.JBI.partial`（書き出し先）、`records/bases/*.JBI`、`records/export.lock` |
  | `history.py` | `records/*.jsonl`（追記だけ） |
  | `inspect_job.py` | HTML（`output/` など） |
- **ソースのテスト**：上以外のモジュールに、ファイルを書く書き方が無いことを調べる。対象：`open(…, "w"/"x"/"a"/"+")`・モードが変数の `open`、`write_bytes`・`write_text`、`os.open`・`os.write`、`io.open`、`shutil.copy*`・`shutil.move`、`os.replace`・`os.rename`、`tempfile`。
- **実行時の守り**：アプリの起動時（とテストの `conftest.py`）に `sys.addaudithook` を入れ、`open`（書き込みのモード・フラグ）と `os.rename` の監査イベントで、パスが `.jbi`／`.jbi.partial`（大文字・小文字を問わない）のものは、`export.py` が書き込みの区間で立てる印（`contextvars`）が無ければ例外で断る。限界：C の拡張や別のプロセスからの書き込みは捕まえられない。

### 1-8. 変更記録（最小）
- `records/changes.jsonl` に1行1件、追記だけ（`flush`・`fsync`）。イベント：`approved`・`export_started`・`export_written`・`exported`・`export_failed`・`discarded`。
- 中身：モード、操作した人（自己申告）、日時、対象と意味の名前、変更前後の行と数値、累積と残り、利用者の言葉、確認表示の文と Claude の説明、枠のハッシュと値、承認ID、元と書き出したファイルの名前・パス・ハッシュ、計算方法の版、アプリの版。

### 1-9. 最小版の受入テスト（先に書く。40件）
2〜4章の表の番号。★は Safety レビューの P1 で足したもの。

| 章 | テスト |
|---|---|
| E | E1〜E10、E18、E19、★E21〜E25 |
| F | F1〜F3、F5、F9〜F15、F20、F23、★F24〜F29 |
| G | G1、G3、G7、G8 |

---

## 2. E：ジョブの変更履歴と Undo（補足）

**目的**：誰が・いつ・何を・なぜ・どの枠で変えたかを残す（仕様11章テスト23）。基準からの累積で軸ごとに検査する（テスト8）。書き出したジョブを読み直しても基準と枠を引き継ぎ、中身が変わったジョブは引き継がない（テスト9）。

**守ること**：1-2・1-3・1-8 のとおり。記録は追記だけで、消さない・書き換えない。記録の「なぜ」に入れる Claude の文は判定に使わない。

**Undo**
- **候補を捨てる**（最小版）：承認前、または承認後・書き出し前に、変更案と承認を無効にする。ジョブもファイルも変わらない。記録には `discarded` とだけ残す。**ボタンだけ**で行う。
- **直前の承認済み変更を取り消す**（後回し）：書き出した後に、値を戻す新しい変更案を作り、通常と同じ検査・ボタン承認・新しい名前での書き出しを通す。過去のファイルと記録は消さない。

**データの形（案）**
```python
NORMALIZED_HASH_VERSION = "nh1"

@dataclass(frozen=True)
class BaseSnapshot:              # 基準の写しから毎回計算し直す（枠の手書きの値は照合にだけ使う）
    raw_sha256: str
    normalized_hash: str
    job_name: str
    base_tokens: tuple[tuple[str, str, str], ...]   # (位置, 軸, 元の数値の文字列)
    hash_version: str = NORMALIZED_HASH_VERSION

@dataclass(frozen=True)
class AxisLimit:
    lower_mm: float              # ≤ 0
    upper_mm: float              # ≥ 0
    step_max_mm: float           # > 0
    reason_memo: str

@dataclass(frozen=True)
class Frame:
    frame_hash: str
    base: BaseSnapshot
    allowed: dict[str, dict[str, AxisLimit]]   # 位置 → 軸（X/Y/Z）→ 範囲
    saved_by: str
    saved_at: str

def load_frames(frames_dir: Path, bases_dir: Path, history: "History") -> list[Frame]: ...  # 1-2 の検証。1つでも外れたら JbiError

class History:
    def __init__(self, records_dir: Path, mode: str): ...
    def find_lineage(self, job: Job, frames: list[Frame]) -> Frame: ...      # 規則1・2。見つからない・あいまい・壊れた行 → JbiError
    def check_cumulative(self, frame: Frame, proposal: ChangeProposal) -> "CumulativeCheck": ...
    def append(self, event: dict) -> None: ...                                # 追記だけ
```

**受入テストの案（`tests/test_history.py`）**
| # | テスト名（案） | 確かめること |
|---|---|---|
| E1 | `test_cumulative_is_from_base_not_last_step` | 基準から +10・+10・+10 と書き出した後の +25 は「累積55」として計算され、枠の上限を超えれば止まる |
| E2 | `test_cumulative_uses_actual_values_after_rounding` | 丸めがあっても、累積は読み直した値と基準の写しの差で出る |
| E3 | `test_cumulative_is_per_axis` | Y と Z の累積は別に数える |
| E4 | `test_program_cap_50mm_cumulative_is_separate_from_frame` | 枠が広くても、累積50mm（仮）を超えると止まる。理由の文に「安全の保証ではない」趣旨の断りがある |
| E5 | `test_reload_exported_job_inherits_base_and_frame` | 書き出したファイルを読み直すと、同じ基準・枠が見つかる |
| E6 | `test_name_or_date_only_change_keeps_inheritance` | `//NAME`・`///DATE` だけ違うジョブは引き継ぎが切れない |
| E7 | `test_other_change_breaks_inheritance` | 他の行が1文字でも違えば引き継がず、位置の変更が止まる |
| E8 | `test_ambiguous_lineage_is_rejected` | 違う基準が2つ見つかる（規則1・2が別の基準を指す場合を含む）と止まる |
| E9 | `test_unverified_export_is_not_inherited` | `exported` の無い書き出し（`export_written` まで等）では引き継がない |
| E10 | `test_frame_without_axis_blocks_shift` | 軸が設定されていない枠では位置の変更が止まる |
| E18 | `test_corrupted_record_blocks_all_changes` | 記録に読めない行が1つでもあれば、すべての位置の変更が止まる |
| E19 | `test_hash_version_mismatch_breaks_inheritance` | 計算方法の版が違う記録では引き継がない |
| ★E21 | `test_frame_on_exported_job_is_rejected` | 書き出したジョブ（記録の変更後ハッシュと一致）を基準にした枠は使われない（累積が0に戻らない） |
| ★E22 | `test_frame_values_recomputed_from_base_copy` | 枠の `base_tokens`・ハッシュが基準の写しから計算した値と違えば、その枠は使われない。写しが無い・壊れていても同じ |
| ★E23 | `test_program_cap_uses_base_copy` | jbi.py の累積50mm（仮）の基準の値は、枠の手書きの値ではなく写しから取られる |
| ★E24 | `test_frame_validation_rejects_bad_values` | 有限でない・bool・`lower_mm > 0`・`upper_mm < 0`・`step_max_mm ≤ 0`・基準に無い位置・X/Y/Z 以外の軸・知らないキー・重複キーは、どれも断られる |
| ★E25 | `test_two_frames_for_same_base_are_rejected` | 同じ基準の枠が2つあると止まる |

**未確認事項**：実機で読み戻したときに変わる行（`///DATE`・`///ATTR`・改行など。11/3夜）。正規化ハッシュの対象（仕様6章は「命令の並び・位置データ・ツール番号・形態だけ」、今の実装は `//NAME`・`///DATE` 以外のすべての行で、より厳しい）。

---

## 3. F：承認済みの変更だけを USB 用に出力する仕組み（補足）

**目的**：ボタンで承認した変更案とまったく同じ中身のジョブだけを、新しい名前の新しいファイルとして書き出し、照合と記録が終わったときだけ「書き出しました」と出す（仕様4章 画面B、11章テスト12・21）。USB に入れてペンダントで読み込むのは人。

**守ること**：1-4〜1-7 のとおり。

**データの形（案）**
```python
SPEED_CHANGE_ENABLED = False          # jbi.py の値を使う（別々に定義しない）
JOB_NAME_MAX_LEN: int | None = None   # 【未確認】

@dataclass(frozen=True)
class ApprovalSnapshot:               # bytes・str・int・tuple だけ（list を持たない）
    mode: str                         # "real" | "sim"
    source_path: str
    source_raw_sha256: str
    source_normalized_hash: str
    source_encoding: str
    source_job_name: str
    lineage_base_hash: str
    frame_hash: str
    kind: str                         # "shift"
    position: str
    axis: str
    requested_mm: str                 # 文字列で持つ（浮動小数を token に入れない）
    line_index: int
    before_line: bytes                # 改行を含む
    after_line: bytes
    before_value_text: str
    after_value_text: str
    name_line_index: int
    new_job_name: str
    expected_new_raw_sha256: str
    destination_dir: str              # realpath
    confirmation_text: str            # 確認表示の文

class ApprovalBook:                   # メモリだけ
    def approve_from_button(self, pending_id: str, shown_token: str, operator: str,
                            csrf_value: str, origin: str, host: str) -> str: ...   # 承認IDを返す
    def discard(self, approval_id: str) -> None: ...

@dataclass(frozen=True)
class ExportReceipt:
    ok: bool
    output_path: str | None
    message: str
    reason_code: str | None

def export_approved(approval_id: str, book: ApprovalBook, history: History) -> ExportReceipt: ...
```

**受入テストの案（`tests/test_export.py`）**
| # | テスト名（案） | 確かめること |
|---|---|---|
| F1 | `test_unapproved_proposal_cannot_be_exported` | `ChangeProposal`・`Job`・`bytes`・`render_bytes()` の結果・知らない承認IDでは書き出されない |
| F2 | `test_snapshot_from_caller_is_not_trusted` | 呼ぶ側が作った snapshot や `ApprovedChange` を渡しても使われない（承認帳の snapshot だけ） |
| F3 | `test_compat_functions_cannot_reach_file_output` | `shift_position`・`set_speed` の結果から書き出す道が無い。`new_job.lines` を承認の後に書き換えても、書き出される中身は変わらない（または止まる） |
| F5 | `test_source_changed_after_approval_requires_reapproval` | 承認の後に元のファイルや枠が1バイト変わると止まる |
| F9 | `test_new_name_must_differ_from_original` | 同じ名前・大文字小文字だけ違う名前は止まる |
| F10 | `test_never_overwrites_existing_file` | 同じ名前の `.JBI`・`.JBI.partial` があれば止まり、既存のファイルは変わらない |
| F11 | `test_original_file_is_unchanged_after_export` | 書き出しの後、元のファイルはバイト単位で同じ |
| F12 | `test_readback_mismatch_is_not_success` | 読み戻しが違えば成功と出ず、作ったファイルは消される（または使わない旨が出る） |
| F13 | `test_write_error_or_crash_leaves_no_loadable_jbi` | 書き込み・名前変更の途中の失敗で成功と出ず、照合の済んでいない `.JBI` が残らない |
| F14 | `test_approval_id_is_single_use` | 同じ承認IDで2回書き出せない |
| F15 | `test_failed_export_requires_reapproval` | 失敗の後、同じ承認IDでは再挑戦できない |
| F20 | `test_messages_have_no_assertive_words` | 成功・失敗の文に断定の言葉が無い。成功の文に「USBの中身そのものを確かめたものではありません」がある |
| F23 | `test_end_to_end_dummy_shift_export` | ダミーで「C00004 Y +10」→ 承認ボタン → 書き出し → 読み戻し照合 → 記録、がすべて通る |
| ★F24 | `test_write_allowlist_in_source` | 許可リスト以外のモジュールに、1-7 に挙げた書き方が無い |
| ★F25 | `test_runtime_hook_blocks_jbi_write_outside_export` | `export.py` の書き込みの区間の外で `.JBI`・`.jbi.partial` に書く（`open`・`write_bytes`・`shutil.copy`・`os.rename`）と例外になる |
| ★F26 | `test_sim_mode_accepts_only_synthetic_allowlist` | sim では許可リストに無いバイト列は書き出されない。許可リストは `samples/dummy/` のファイルと一致する。sim でも検査は緩まない（実機用の検査で止まった案は承認できない） |
| ★F27 | `test_real_mode_has_no_default_destination_and_rejects_repo` | real では書き出し先が無ければ止まり、`realpath` がリポジトリの中（`samples/dummy/`・`output/` を含む）なら止まる。モードがトークンと記録に入る |
| ★F28 | `test_approve_post_requires_csrf_and_local_origin` | GET、推測できない値の無い POST、`Origin`・`Host` が違う POST は断られる。発話・文字の「承認します」では承認されない |
| ★F29 | `test_concurrent_export_is_rejected` | 書き出しの途中に別の書き出しを始めると止まる |

**未確認事項**：YRC1000 が USB から読み込むときのフォルダの決まり、ファイル名と `//NAME` が違うときの扱い、同じ名前のジョブがあるときの動き、ジョブ名に使える文字と長さ、`.JBI.partial` という名前をペンダントが無視するか、USB の形式（FAT32 などで排他作成と名前変更が期待どおり動くか）。

---

## 4. G：書き出し前後のバイト単位の差分検証（補足）

**目的**：書き出すバイト列が「元のバイト列のうち、承認した1行と `//NAME` の行だけを変えたもの」であることを、行とバイトの両方で確かめる。書き出しの前（1-5 の8）と `.partial` の読み戻し（11）で同じ関数を使う。

**守ること**：比べるのはバイト列。期待する値は承認帳の snapshot から取り、`new_job` は使わない。許す差は下に書いたものだけ。落ちたら何も書かない（書いた後なら 1-5 の失敗の扱い）。

**関数（案）**
```python
@dataclass(frozen=True)
class DiffReport:
    ok: bool
    changed_lines: tuple[int, ...]
    violations: tuple[tuple[str, int | None, str], ...]   # (種類, 行番号, 利用者に見せる文)

def split_lines_bytes(data: bytes) -> list[bytes]: ...    # b"\n" だけで分け、改行を含めたまま
def verify_byte_diff(original: bytes, new: bytes, snap: ApprovalSnapshot) -> DiffReport: ...
```

**許す差**
1. 行の数が同じ。違ってよいのは `snap.line_index` と `snap.name_line_index` の2行だけ（2つは別の行）。他の行は改行を含めてバイト単位で同じ。
2. 承認した行：元の行＝`before_line`、新しい行＝`after_line`。改行の種類が同じ。違うのは対象の軸の欄（`Cnnnnn=` の後ろをカンマで分けた X=1つ目・Y=2つ目・Z=3つ目）だけ。
3. 変えた欄は小数点以下の桁数が元と同じ。**符号や先頭の0の書き方が元と違えば止める**（例：元が `+190.000` や `0190.000` の形なら止める）。
4. 変えた欄の差（`Decimal` で引き算）が承認した実際の量と一致し、`requested_mm` との差が最後の桁の半分以内。
5. `//NAME` の行：元＝`b"//NAME " + 元の名前 + 改行`、新＝`b"//NAME " + 新しい名前 + 同じ改行`。この形でなければ止める。
6. 全体：文字コード（`parse_bytes` が元と同じ文字コードで読め、書き戻しが一致）、行ごとの改行、最後の行の改行の有無、BOM が元と同じ。`problems` が無い。変えた位置の変えた軸以外の値・命令・ツール番号・形態は元と同じ。`sha256(new) == expected_new_raw_sha256`。
7. `///DATE` は変えない（変えるかは本人判断。5章）。

**受入テストの案（`tests/test_byte_diff.py`）**
| # | テスト名（案） | 確かめること |
|---|---|---|
| G1 | `test_exact_expected_bytes_pass` | 承認した1行と `//NAME` だけが違うバイト列は通る（LF・CRLF・cp932 のコメント入りの3種） |
| G3 | `test_any_other_line_change_fails` | 他の行を1バイト変えると落ちる（`///DATE` を含む） |
| G7 | `test_line_ending_change_fails` | 1行でも `\r\n`⇔`\n` が変わる、最後の改行の有無が変わると落ちる |
| G8 | `test_line_count_change_fails` | 行が増える・減ると落ちる |

（後で足す候補：別の欄・桁数・符号の変化、量の食い違い、文字コード・BOM、`//NAME` の形、ハッシュの不一致）

**未確認事項**：実機のジョブの改行と文字コード、最後の行の改行、`//NAME` の行の形、数値の書き方（`+` や先頭の0が付くか）。

---

## 5. 後回し・将来（詳しく設計しない）
- 書き出した後の取り消し（値を戻す新しい変更案。ボタン承認と新しい名前での書き出しを通す）
- 記録の和と実際の累積の照合
- `///DATE` の書き換え（`date_policy`）
- ジョブ名の長さの上限の適用（`JOB_NAME_MAX_LEN`。値が分かってから）
- 通し番号の凝った付け方、名前の手入力
- 記録のつなぎのハッシュ（前の行のハッシュを次の行に入れて、書き換えに気づけるようにする）
- 画面C：変更記録の一覧
- USB の中身をもう一度照合するボタン（仕様11章テスト24の前段）
- 記録のイベントに `discarded` 以外の取り消し理由を細かく残す
- 確認表示に出すもの（書き出す数値の文字列、丸め後の量、累積と残り、ファイル名と書き出し先、「上限であって安全の保証ではない」）の画面設計
- G のテストの残り（G2・G4〜G6・G9〜G15 相当）、E11〜E17・E20、F4・F6〜F8・F16〜F19・F21・F22 相当
- Ethernet の転送（仕様12章 P2。この設計の範囲外）

---

## 6. 本人に決めてもらうこと
| # | こと | クロの案 |
|---|---|---|
| 1 | **sim.py の扱い**：`export_sim` を `export_approved(mode="sim")` に置き換え、**実機用の検査で止まった案（`blocked_reason` あり）は表示だけにして書き出さない**。feat/sim-core と feat/sim-ui の作業に影響する（シクロにも確認） | 置き換える。止まった案は書き出さない |
| 2 | 「誰が」の取り方（ログインが無い） | 起動時に名前を入れる「操作した人（自己申告）」 |
| 3 | 正規化ハッシュの対象（今の実装は仕様6章より厳しい） | 今のまま（`//NAME`・`///DATE` 以外すべて） |
| 4 | 新しい名前の付け方 | `元の名前_VT01`（sim は `_SIM` も付ける） |
| 5 | 承認と書き出しのボタンを分けるか | 分ける（承認の後、書き出しの前に「やめる」ができる） |
| 6 | 照合に失敗したファイルを消すか残すか | 消す。消せなければパスを大きく出す |
| 7 | `///DATE` を書き出しで変えるか | 変えない |
| 8 | 数値の書き方（符号・先頭の0）が元と違う形になる場合 | 止める |
| 9 | 枠の置き場所 `records/frames/`（実機用の枠は git に入れない）と、最小版では枠を手で書く運用でよいか | よい |
| 10 | 変更記録（実機のジョブの行と数値を含む）を Claude に送る範囲 | デモ用ジョブだけ |
| 11 | （実機で確認）ジョブ名の長さと使える文字、USB のフォルダの決まり、同じ名前の扱い、`.JBI.partial` をペンダントが無視するか、改行・文字コード、読み戻しで変わる行 | ― |
