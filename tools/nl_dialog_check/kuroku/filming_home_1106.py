"""自宅の画面録画のシナリオ確認（11/6 夜・クローク）。撮影版を読むだけの別フォルダ・サーバーを起動しない・実 Claude。
承認・出力は一時フォルダの中だけ（シミュレーション用）。実機への転送・起動はしない。キーは表示・保存しない。
使い方：python filming_home_1106.py <worktree> <.env> <JOB のフォルダ> <出力 json> [--rep 3] [--only ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("root"); ap.add_argument("envfile"); ap.add_argument("jobdir"); ap.add_argument("out")
ap.add_argument("--rep", type=int, default=3); ap.add_argument("--only", default="")
A = ap.parse_args()
ROOT = Path(A.root).resolve()
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
from voice_teaching import claude_explain, claude_interpreter, sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

claude_interpreter.load_dotenv(A.envfile)
CALLS = []
import anthropic.resources.messages as _m  # noqa: E402
_orig = _m.Messages.create


def _t(self, *a, **kw):
    r = None
    try:
        r = _orig(self, *a, **kw); return r
    finally:
        u = getattr(r, "usage", None)
        CALLS.append((getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0, r is None))


_m.Messages.create = _t
JD = Path(A.jobdir)
JOBS = {"R2": (JD / "bak/VT_TEST_XYZ_R2.JBI").read_bytes(), "R2N": (JD / "C番号を分けた版(OK)/VT_TEST_XYZ_R2.JBI").read_bytes(),
        "XYZ": (JD / "VT_TEST_XYZ.JBI").read_bytes(), "BR": (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes(),
        "RJ": (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes()}


def msg_of(r):
    h, a = (r.get("hear") or {}), (r.get("ask") or {})
    p = [a.get("reply"), a.get("error"), " ".join(a.get("notes") or []), h.get("message"),
         r.get("message") if isinstance(r.get("message"), str) else None, r.get("error") if isinstance(r.get("error"), str) else None]
    return " ".join(x for x in p if x)


def snap(w, sid):
    st = w.state(sid)["state"]
    c = st.get("candidate") or {}
    return {"cand": (c.get("target"), c.get("delta")) if c else None, "approval": st.get("approval") is not None,
            "hold": st.get("hold"), "can_approve": st.get("can_approve"), "can_export": st.get("can_export"),
            "range": bool(st.get("repeat_range")), "gen": w.candidate_gen_of(sid)}


def run(job, steps, tmp):
    sim.DEFAULT_OUT_DIR = tmp / "out"
    w = WebFlow(interpreter=claude_interpreter.from_env(), explainer=claude_explain.Explainer.from_env(usage_path=tmp / "u.jsonl"))
    sid = w.load(JOBS[job])["session_id"]; log = []
    for s in steps:
        n = len(CALLS)
        if s.startswith("@sel "):
            r = w.select(sid, s[5:])
        elif s == "@approve":
            r = w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
        elif s == "@export":
            r = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
        elif s == "@range_yes":
            rr = w.state(sid)["state"].get("repeat_range")
            r = w.repeat_choose(sid, "yes", rr["turn"]) if rr else {"error": "範囲の確認が無い"}
        elif s == "@undo":
            r = w.undo(sid) if hasattr(w, "undo") else {"error": "undo なし"}
        elif s.startswith("@load "):
            sid = w.load(JOBS[s[6:]])["session_id"]; r = {"message": "読み込み " + s[6:]}
        elif s == "@reload":
            sid = w.load(JOBS[job])["session_id"]; r = {"message": "読み込み直し"}
        else:
            r = w.talk(sid, s, "voice")
        m = msg_of(r)
        log.append({"do": s, "ok": r.get("ok"), "via": r.get("via"), "msg": m[:500], "chars": len(m), "api": len(CALLS) - n,
                    "file": r.get("file_name"), **snap(w, sid)})
    return log


SC = {
    # 1つの画面で 1〜5 を続ける（合成ジョブ：出力まで）
    "BR_all_C2": ("BR", ["@sel C00002", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "@approve", "@export",
                         "2回から3回にして", "@range_yes", "@approve", "@export"]),
    "BR_all_C1": ("BR", ["@sel C00001", "Zプラス方向に5ミリ動かして"]),
    "RJ_pos": ("RJ", ["@sel C00004", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "@approve", "@export"]),
    # 回数の言い方（合成ジョブ）
    "BR_23": ("BR", ["2回から3回にして", "@range_yes", "@approve", "@export"]),
    "BR_this23": ("BR", ["この動きを2回から3回にして", "@range_yes"]),
    "BR_full": ("BR", ["C00001からC00003の作業を2回から3回にして", "@range_yes", "@approve", "@export"]),
    # 実機で作った R2 で続ける（出力はできない）
    "R2_all": ("R2", ["@sel C00004", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "@approve",
                      "C00001からC00005を3回繰り返して", "@range_yes", "@approve"]),
    "R2_23": ("R2", ["2回から3回にして"]),
    # 実機で読み込めた新しい R2（2回目は C00006〜C00010）と新しい XYZ
    "R2N_23": ("R2N", ["2回から3回にして"]),
    "R2N_c15": ("R2N", ["C00001からC00005を3回繰り返して", "@range_yes"]),
    "R2N_c110": ("R2N", ["C00001からC00010の作業を2回から3回にして"]),
    "R2N_pos": ("R2N", ["@sel C00004", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "@approve"]),
    "XYZ_pos": ("XYZ", ["@sel C00004", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "@approve", "@export"]),
    # 残る状態：承認のあと別の指示、読み込み直し
    "RJ_after_export": ("RJ", ["@sel C00004", "Zプラス方向に5ミリ動かして", "@approve", "@export", "Zプラス方向に3ミリ動かして",
                               "@load BR", "2回から3回にして", "@range_yes", "@approve", "@export"]),
    "RJ_undo_then": ("RJ", ["@sel C00004", "Zプラス方向に5ミリ動かして", "@approve", "取り消して", "Zプラス方向に5ミリ動かして"]),
    "BR_leftover": ("BR", ["@sel C00002", "Zプラス方向に5ミリ動かして", "@approve", "2回から3回にして", "@reload"]),
}
REPS = {"BR_all_C1": 1, "BR_this23": 2, "R2_23": 1, "BR_leftover": 1, "R2N_23": 2, "R2N_c15": 2, "R2N_c110": 2, "R2N_pos": 2, "XYZ_pos": 2}
only = {x for x in A.only.split(",") if x}
res = []
for name, (job, steps) in SC.items():
    if only and name not in only:
        continue
    for rep in range(REPS.get(name, A.rep)):
        with tempfile.TemporaryDirectory() as d:
            try:
                log = run(job, steps, Path(d))
            except Exception as e:  # noqa: BLE001
                log = [{"error": repr(e)[:300]}]
        res.append({"case": name, "rep": rep, "log": log})
        print("==", name, rep, flush=True)
        for x in log:
            print("  ", json.dumps(x, ensure_ascii=False)[:520], flush=True)
usd = sum(i * 2.0 + o * 10.0 for i, o, _ in CALLS) / 1e6
print(f"API {len(CALLS)} 回・失敗 {sum(1 for *_, f in CALLS if f)}・推定 {usd:.3f} ドル")
Path(A.out).write_text(json.dumps({"sha": "60f3d24", "calls": len(CALLS), "usd": round(usd, 3), "res": res}, ensure_ascii=False, indent=1), encoding="utf-8")
