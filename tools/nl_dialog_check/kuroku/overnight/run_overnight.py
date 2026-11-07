"""クロークの夜間の検証（2026-11-07 夜〜11/8 朝）。決まった SHA を別の作業フォルダに出して、検査を順に流し、記録と要約を書く。
使い方（リポジトリのルートで。秘密の値は引数に書かない）：
  python -I tools/nl_dialog_check/kuroku/overnight/run_overnight.py --sha <固定の SHA> --work <作業用の空のフォルダ>
      [--env <.env のパス>] [--real-budget-usd 1.5] [--rounds 1] [--skip-slow]
- --env を付けないときは、偽の Claude だけ（API 0回）
- --env を付けたときだけ、本物の Claude の代表の場面を流す。この道具が数えた推定の料金が --real-budget-usd を超えそうなら、本物の Claude の検査を始めない
  - アプリの上限 VOICE_TEACHING_API_BUDGET_USD も同じ値にする
- 止める条件（見つけたら、その場で止めて STOP.md を書く）：
  1. 未承認の出力・古い承認での出力・承認と出力の中身の不一致・危ない候補（各検査の決まった印）
  2. 推定の料金が上限を超える
  3. 実機・外部との通信の疑い（この道具は 127.0.0.1 以外へつながない。アプリの出力先を作業フォルダの中にする）
  4. 同じ検査が時間切れ
- しないこと：8896・撮影版・ほかの人のブランチを触らない。実機の JOB を使わない。リリース・提出・承認の代わりをしない。OS の保存の窓は押さない（手での確かめ）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
HERE = Path(__file__).resolve().parent
K = HERE.parent  # tools/nl_dialog_check/kuroku
REPO = K.parents[2]
ap = argparse.ArgumentParser()
ap.add_argument("--sha", required=True)
ap.add_argument("--work", required=True)
ap.add_argument("--env", default="")
ap.add_argument("--real-budget-usd", type=float, default=1.5)
ap.add_argument("--rounds", type=int, default=1)
ap.add_argument("--skip-slow", action="store_true", help="pytest・e2e・画面の検査を飛ばす（道具の確かめ用）")
A = ap.parse_args()
WORK = Path(A.work).resolve(); WORK.mkdir(parents=True, exist_ok=True)
WT = WORK / f"wt-{A.sha[:7]}"
LOG = WORK / f"log-{A.sha[:7]}"; LOG.mkdir(exist_ok=True)
PY = sys.executable
NODE = os.environ.get("NODE", "node")
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "VOICE_TEACHING_API_BUDGET_USD": str(A.real_budget_usd)}
SUMMARY: list[dict] = []
SPENT = 0.0


def now() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def stop(why: str, detail: str = "") -> None:
    (LOG / "STOP.md").write_text(f"# 夜間の検証を止めました（{now()}）\n\n- SHA：{A.sha}\n- 理由：{why}\n\n{detail}\n", encoding="utf-8")
    write_summary(stopped=why)
    print("STOP:", why, flush=True)
    sys.exit(2)


def run(name: str, cmd: list[str], timeout: int, check=None, real: bool = False) -> str:
    """1つの検査を流す。check(out) は (ok, 危ない, 一言) を返す。危ないなら止める。"""
    global SPENT
    t0 = time.time()
    out_path = LOG / f"{len(SUMMARY) + 1:02d}_{name}.txt"
    try:
        p = subprocess.run(cmd, cwd=str(WORK), env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "") + "\n--- stderr ---\n" + (p.stderr or "")
        code = p.returncode
    except subprocess.TimeoutExpired as ex:
        out = f"時間切れ（{timeout} 秒）\n" + str(ex.stdout or "")[-4000:]
        code = -1
    out = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "***", out)
    out_path.write_text(out, encoding="utf-8")
    ok, danger, note = (code == 0, False, "") if check is None else check(out)
    usd = 0.0
    if real:
        m = re.findall(r"推定 ?([0-9.]+) ?ドル", out)
        usd = float(m[-1]) if m else 0.0
        SPENT += usd
    SUMMARY.append({"name": name, "ok": ok, "danger": danger, "note": note, "exit": code, "sec": round(time.time() - t0),
                    "usd": usd, "log": out_path.name, "at": now()})
    print(f"[{now()}] {'OK ' if ok else 'NG '}{name} {note} ({round(time.time() - t0)} 秒)", flush=True)
    write_summary()
    if code == -1:
        stop(f"{name} が時間切れ", f"記録：{out_path.name}")
    if danger:
        stop(f"{name} で危ないこと：{note}", f"記録：{out_path.name}")
    if SPENT > A.real_budget_usd:
        stop(f"推定の料金 {SPENT:.3f} ドルが上限 {A.real_budget_usd} ドルを超えた")
    return out


def write_summary(stopped: str | None = None) -> None:
    lines = [f"# クロークの夜間の検証の要約（{now()}）", "", f"- SHA：`{A.sha}`", f"- 本物の Claude：{'使う' if A.env else '使わない（偽の Claude だけ）'}",
             f"- 本物の Claude の推定の料金（この道具の計算）：{SPENT:.3f} ドル／上限 {A.real_budget_usd} ドル（請求額ではない）",
             f"- 止めた理由：{stopped}" if stopped else "- 止めた理由：なし（最後まで、または実行中）", "",
             "| # | 検査 | 合否 | 危ない | 一言 | 秒 | 推定 USD | 記録 |", "|---|---|---|---|---|---|---|---|"]
    for i, s in enumerate(SUMMARY, 1):
        lines.append(f"| {i} | {s['name']} | {'OK' if s['ok'] else 'NG'} | {'**あり**' if s['danger'] else 'なし'} | {s['note']} | {s['sec']} | {s['usd']:.3f} | {s['log']} |")
    lines += ["", "- 「OK」は決まった検査が通ったという意味だけ。実機の安全の認証ではない。クロークは同じ Claude なので、独立のレビューでもない",
              "- OS の保存の窓・実マイク・本当の2つのタブは、この道具では確かめない（手での確かめ）"]
    (LOG / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- 判定の小さな関数（各検査の出力の決まった行を読む） ----
def c_pytest(out):
    m = re.search(r"(\d+) passed", out); f = re.search(r"(\d+) failed", out)
    return (bool(m) and not f, False, f"{m.group(1) if m else '?'} passed" + (f" / {f.group(1)} failed" if f else ""))


def c_node(out):
    p = re.search(r"ℹ pass (\d+)", out); f = re.search(r"ℹ fail (\d+)", out)
    return (bool(p) and f and f.group(1) == "0", False, f"pass {p.group(1) if p else '?'} / fail {f.group(1) if f else '?'}")


def c_e2e(out):
    ok = out.count("\nOK "); ng = out.count("\nNG ")
    return ("すべて通りました" in out, False, f"OK {ok} / NG {ng}")


def c_iya(out):
    m = re.search(r"NG (\d+) / (\d+)", out)
    return (bool(m) and m.group(1) == "0", bool(m) and m.group(1) != "0", m.group(0) if m else "?")


def c_p0(out):
    a = len(re.findall(r"FAIL 承認済", out)); s = len(re.findall(r"^S\d+ (FAIL|ERR)", out, re.M))
    u = len(re.findall(r"FAIL 未承認", out))
    return (a == 0 and s == 0, a > 0 or s > 0, f"承認済みの FAIL {a}・場面の FAIL {s}・未承認の FAIL {u}（質問は D3 で許す）")


def c_sweep(out):
    m = re.search(r"(\d+) / (\d+) 承認が残って出力できる", out)
    return (bool(m) and m.group(1) == "0", bool(m) and m.group(1) != "0", m.group(0) if m else "?")


def c_match(out):
    ng = out.count("\nNG ") + out.startswith("NG ")
    ok = out.count("OK ")
    return (ng == 0 and ok >= 8, ng > 0, f"一致 {ok}・不一致 {ng}")


def c_race(out):
    bad = re.findall(r"R1 ok=(?!1 )|R2 export=True cand_after=False|export_after=True|old_export=True|R5 approve=\w+ hold=False export=True|crash=True", out)
    return (not bad, bool(bad), "安全側" if not bad else f"危ない行 {len(bad)}")


def c_adv(out):
    m = re.search(r"NG \[(.*?)\]", out)
    ng = [x.strip(" '") for x in (m.group(1).split(",") if m and m.group(1) else [])]
    danger = [x for x in ng if x not in ("U15",)]  # U15 は安全側の聞き返し（期待の側が古い）
    return (not danger, bool(danger), f"NG {ng}")


def c_apierr(out):
    return ("CRASH" not in out, "CRASH" in out, "落ちない" if "CRASH" not in out else "落ちた")


def c_rep(out):
    danger = re.findall(r"危 \{'(substituted|ambiguous_fixed|unapproved_export)'", out)
    ng = len(re.findall(r"^NG ", out, re.M))
    return (ng == 0 and not danger, bool(danger), f"NG {ng}・危ない {len(danger)}")


def c_ui(out):
    m = re.search(r"FAIL \[(.*?)\]", out)
    ng = [x.strip(" '") for x in (m.group(1).split(",") if m and m.group(1) else [])]
    return (not ng or ng == ["A05"], False, f"FAIL {ng}（A05 は Spec A の動きで正しい）")


def c_real(out):
    m = re.search(r"API (\d+) 回・失敗 (\d+)", out)
    return (bool(m) and m.group(2) == "0", False, m.group(0) if m else "?")


# ---- 準備：決まった SHA の作業フォルダ ----
print(f"[{now()}] 開始 SHA {A.sha}", flush=True)
if not WT.exists():
    subprocess.run(["git", "-C", str(REPO), "fetch", "-q", "origin"], check=False)
    r = subprocess.run(["git", "-C", str(REPO), "worktree", "add", "-q", "--detach", str(WT), A.sha], capture_output=True, text=True)
    if r.returncode != 0:
        stop("作業フォルダを作れない", r.stderr)
head = subprocess.run(["git", "-C", str(WT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
if not head.startswith(A.sha[:7]):
    stop("作業フォルダの SHA が違う", head)

FA, QA, XC, RC = K / "final_61ef19a", K / "qa_60f3d24", K / "xc_1106", K / "rc_1107"
for rnd in range(1, A.rounds + 1):
    if not A.skip_slow:
        run("node", [NODE, "--test", *[str(p) for p in sorted((WT / "tests").glob("*.test.mjs"))]], 600, c_node)
        run("pytest", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--ignore=tests/test_e2e_browser.py", str(WT / "tests")], 3600, c_pytest)
    run("F-1 の言い方（iya3）", [PY, "-I", str(FA / "iya3.py"), str(WT)], 900, c_iya)
    run("P0 の場面（p0_final）", [PY, "-I", str(FA / "p0_final.py"), str(WT), str(LOG / "p0_final.json")], 1800, c_p0)
    run("ためらい 123（xc_sweep）", [PY, "-I", str(XC / "xc_sweep.py"), str(WT)], 900, c_sweep)
    run("承認した内容と出力（xc_export_match）", [PY, "-I", str(XC / "xc_export_match.py"), str(WT)], 900, c_match)
    run("同時の操作（qa_race）", [PY, "-I", str(QA / "qa_race.py"), str(WT)], 1800, c_race)
    run("Claude の失敗（qa_apierr）", [PY, "-I", str(QA / "qa_apierr.py"), str(WT)], 900, c_apierr)
    run("わざと間違えた答え（rc_nlu_adv）", [PY, "-I", str(RC / "rc_nlu_adv.py"), str(WT), str(LOG / "nlu_adv.json"), A.sha[:7]], 900, c_adv)
    run("照合の場面（xc_probe）", [PY, "-I", str(XC / "xc_probe.py"), str(WT), A.sha[:7], str(LOG / "xc.json")], 1800)
    run("言い方・状態・JOB（qa_mock）", [PY, "-I", str(QA / "qa_mock.py"), str(WT), str(LOG / "qa_mock.json")], 1800)
    run("範囲の案内のボタン（rep_buttons）", [PY, "-I", str(RC / "rep_buttons.py"), str(WT)], 900)
    run("SIM の名前（sim_names）", [PY, "-I", str(RC / "sim_names.py"), str(WT)], 900)
    if not A.skip_slow:
        run("e2e（ブラウザー・偽の Claude）", [PY, str(WT / "tools" / "e2e_browser.py")], 3600, c_e2e)
        run("画面の回帰（ui60f）", [PY, "-I", str(QA / "ui60f.py"), str(WT), str(LOG / f"ui60f_r{rnd}")], 2400, c_ui)
        run("承認と保存のブラウザー（ui_approve_save）", [PY, "-I", str(RC / "ui_approve_save.py"), str(WT), str(LOG / f"ui_as_r{rnd}")], 2400, c_ui)
    if A.env and rnd == 1:
        # 本物の Claude は1周目だけ（代表の場面。約 0.2 ドル）
        run("本物の Claude：フローの場面（rc_real）", [PY, "-I", str(RC / "rc_real.py"), str(WT), A.env, str(LOG / "real.json")], 2400, c_real, real=True)
        run("本物の Claude：繰り返しの18場面（rep_guide）", [PY, "-I", str(RC / "rep_guide.py"), str(WT), str(LOG / "rep_real.json"), "--real", A.env], 2400, c_rep, real=True)
write_summary()
print(f"[{now()}] 終わり。要約：{LOG / 'SUMMARY.md'}", flush=True)
