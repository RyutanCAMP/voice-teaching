# 合成JOB用の「上下の向き」の登録手順（家のPC・2026-11-03 夜。唐川さん承認）

目的：合成JOB（`samples/dummy/` の架空のデモ）で「この位置を3ミリ下げて」のような上下の言葉を使えるようにする。
**実機の座標系を確認したことにはしない。** 合成JOB専用のロボット名 `SIM-SYNTH` と、専用の設定ファイルで登録する。

## 0. 前提（守ること）
- 登録するのは唐川さん本人（コマンドの最後に `yes` と自分で入力する。シクロ・Claude・アプリの画面からは書けない）
- 設定は「誰が・何を根拠に確かめたか」の記録で、本人確認・物理的な安全の保証ではない
- ロボット名は **`SIM-SYNTH`**（実機の `HC20DT` とは別）。設定ファイルは **`records\updown_synthetic.json`**（`records/` は .gitignore 済み。GitHub に入らない）
- アプリを `--robot HC20DT`（既定）で起動したときは、この設定は使われない（上下は「未確認」のまま）

## 1. 合成JOBの座標系を確かめる（人が見る）
1. アプリを今まで通り起動し（`python -m voice_teaching.web --port 8765`）、Google Chrome で `DEMO_BUTTON_REPEAT.JBI` を読み込む
2. 3D 表示で確かめる
   - **Z+ の矢印が画面の上を向いている**
   - ボタンを押す位置 **C00002（Z=215.000）がいちばん低く**、待つ位置 C00000・C00004（Z=420.000）が高い
   - 「上で待つ → 下りて押す → 上へ戻る」が、Z の値の大小と合っている
3. 詳細表示で座標系を確かめる：`///POSTYPE ROBOT`・`///RECTAN`・`///TOOL 0`・`///USER` なし・FRAME の行なし
   （`DEMO_C_PLACE.JBI` も同じ座標系）
4. これは**合成JOBの座標の定義**として「Zプラス＝上」が成り立つことの確認。実機の設置・座標系は確かめていない

## 2. 登録する（唐川さんが PowerShell で）
```powershell
cd C:\Users\User\voice-teaching
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
python -m voice_teaching.updown register `
  --job samples\dummy\DEMO_BUTTON_REPEAT.JBI `
  --robot SIM-SYNTH `
  --by "唐川" `
  --evidence "合成JOB（架空）の座標の定義で確認：ROBOT 座標・直交（RECTAN）・ツール0。3D 表示で Z+ の矢印が上を向き、押す位置 C00002（Z=215）が最も低いことを見た。実機の座標系は確認していない" `
  --config records\updown_synthetic.json
```
- 表示される内容（向きの対応・確認した人・日時・根拠・対象のロボット SIM-SYNTH・座標系）を読み、正しければ `yes` と入力する
- 照合：`python -m voice_teaching.updown check --job samples\dummy\DEMO_C_PLACE.JBI --robot SIM-SYNTH --config records\updown_synthetic.json` → `状態：confirmed`

## 3. 合成JOBのデモでアプリを起動する
```powershell
python -m voice_teaching.web --port 8765 --robot SIM-SYNTH --updown-config records\updown_synthetic.json
```
- この起動のときだけ、合成JOBで「上・下・上げ・下げ」を Z± として読む
- 確かめる指示：`DEMO_C_PLACE.JBI` の C00005 を選び「この位置を3ミリ下げて」→ 候補 Z −3.000（承認はボタンで）。
  `DEMO_BUTTON_REPEAT.JBI` の C00001 は2つの命令が共用のため「変更できない」（参考の候補・理由が赤）

## 4. 残るリスク（正直に）
- `--robot SIM-SYNTH` で起動したまま、同じ座標系（ROBOT・RECTAN・ツール0）の実機のジョブを読み込むと、上下は「確認済み」と扱われる
  （設定はジョブの中身ではなく、ロボット名と座標系で照合する決まり：CHECKER_028 K4）。
  **SIM-SYNTH の起動では合成JOB（`samples/dummy/`）だけを使う**。実機のジョブは既定の起動（HC20DT・未確認）で
- 改善の案（未実装・判断待ち）：ロボット名が SIM-SYNTH のときは、合成JOBの印（`'SYNTHETIC DEMO JOB - NOT A REAL ROBOT JOB`）が無いジョブでは上下を未確認にする
