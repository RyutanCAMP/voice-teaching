"""撮影の台本の確認（11/6 夕方・クローク）。撮影版のコードを読むだけ・サーバーは起動しない・実 Claude。

- WebFlow を直接呼ぶ（画面の /api/talk と同じ入口 talk）。承認・出力は一時フォルダの中だけ（シミュレーション用。実機への転送・起動はしない）
- キーは .env からプロセスの中だけに読む。表示・保存しない
使い方：python filming_check_1106.py <worktree> <.env> <JOB のフォルダ> <出力 json> [--rep 3] [--only A,B]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
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
JOBS = {"XYZ": (JD / "VT_TEST_XYZ.JBI").read_bytes(), "R2": (JD / "VT_TEST_XYZ_R2.JBI").read_bytes(),
        "RJ": (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes()}


def msg_of(r):
    h, a = (r.get("hear") or {}), (r.get("ask") or {})
    p = [a.get("reply"), " ".join(a.get("notes") or []), h.get("message"), r.get("message") if isinstance(r.get("message"), str) else None]
    return " ".join(x for x in p if x)


def cand(st):
    c = st.get("candidate")
    return None if not c else {k: c.get(k) for k in ("target", "delta", "before", "after") if k in c} or str(c)


def flow(tmp):
    sim.DEFAULT_OUT_DIR = tmp / "out"
    i = claude_interpreter.from_env(); ex = claude_explain.Explainer.from_env(usage_path=tmp / "u.jsonl")
    assert i.kind == "claude" and ex.has_key
    return WebFlow(interpreter=i, explainer=ex)


def step(w, sid, said, log):
    n = len(CALLS); t = time.perf_counter()
    r = w.talk(sid, said, "voice")
    st = w.state(sid)["state"]
    log.append({"said": said, "via": r.get("via"), "status": (r.get("hear") or {}).get("status"), "msg": msg_of(r),
                "chars": len(msg_of(r)), "choices": [x.get("label") for x in (r.get("hear") or {}).get("choices") or []],
                "cand": cand(st), "repeat_range": st.get("repeat_range"), "hold": st.get("hold"),
                "can_approve": st.get("can_approve"), "api": len(CALLS) - n, "sec": round(time.perf_counter() - t, 1)})
    return r, st


def finish(w, sid, log, do_export=True):
    g = w.candidate_gen_of(sid)
    a = w.approve(sid, "QA", candidate_gen=g)
    log.append({"op": "approve", "ok": a.get("ok"), "msg": a.get("error") or a.get("message")})
    if do_export:
        x = w.export(sid, candidate_gen=g)
        log.append({"op": "export", "ok": x.get("ok"), "msg": x.get("error") or x.get("message") or x.get("file_name")})


def S_pos(job, first, second, pos="C00005"):
    def run(tmp):
        w = flow(tmp); sid = w.load(JOBS[job])["session_id"]; w.select(sid, pos); log = []
        if first:
            step(w, sid, first, log)
        _, st = step(w, sid, second, log)
        if st.get("candidate"):
            finish(w, sid, log)
        return log
    return run


def S_rep(said, press=True):
    def run(tmp):
        w = flow(tmp); sid = w.load(JOBS["R2"])["session_id"]; log = []
        _, st = step(w, sid, said, log)
        rr = st.get("repeat_range")
        if rr and press:
            r = w.repeat_choose(sid, "yes", rr["turn"])
            st = w.state(sid)["state"]
            log.append({"op": "range_yes", "msg": msg_of(r), "cand": cand(st)})
        if st.get("candidate"):
            finish(w, sid, log)
        return log
    return run


def S_recover(job, kind):
    def run(tmp):
        w = flow(tmp); sid = w.load(JOBS[job])["session_id"]; w.select(sid, "C00004"); log = []
        step(w, sid, "Zプラス方向に5ミリ動かして", log)
        if kind == "cancel":
            step(w, sid, "取り消して", log)
        elif kind == "undo":
            r = w.talk(sid, "元に戻して", "voice"); st = w.state(sid)["state"]
            log.append({"said": "元に戻して", "msg": msg_of(r), "cand": cand(st)})
        elif kind == "wait_after_approve":
            g = w.candidate_gen_of(sid); w.approve(sid, "QA", candidate_gen=g)
            step(w, sid, "ちょっと待って", log)
            step(w, sid, "このままでいい", log)
            finish(w, sid, log)
        return log
    return run


SC = {
    # 優先1：台本どおり（30→5）
    "P1_XYZ_script": S_pos("XYZ", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして"),
    "P1_RJ_script": S_pos("RJ", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして"),
    "P1_XYZ_C4": S_pos("XYZ", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "C00004"),
    "P1_RJ_C4": S_pos("RJ", "Zプラス方向に30ミリ動かして", "Zプラス方向に5ミリ動かして", "C00004"),
    # 優先3：別の言い方（いきなり 5mm）
    "W_z5": S_pos("XYZ", None, "Zプラス5ミリ", "C00004"),
    "W_up5": S_pos("XYZ", None, "上に5ミリ動かして", "C00004"),
    "W_c5": S_pos("XYZ", None, "C00004をZプラス方向に5ミリ動かして", "C00004"),
    "W_raise": S_pos("XYZ", None, "5ミリ上げて", "C00004"),
    # 優先2：回数（R2）
    "R_a": S_rep("C00001からC00005を3回繰り返して"),
    "R_b": S_rep("この動きを2回から3回にして"),
    "R_c": S_rep("繰り返しを3回にして"),
    "R_d": S_rep("C00001からC00005の作業を2回から3回にして"),
    # やり直し
    "X_cancel": S_recover("XYZ", "cancel"),
    "X_undo": S_recover("XYZ", "undo"),
    "X_wait": S_recover("RJ", "wait_after_approve"),
}
REPS = {"X_cancel": 1, "X_undo": 1, "X_wait": 1}
only = {x for x in A.only.split(",") if x}
res = []
for name, fn in SC.items():
    if only and name not in only:
        continue
    for rep in range(REPS.get(name, A.rep)):
        with tempfile.TemporaryDirectory() as d:
            try:
                log = fn(Path(d))
            except Exception as e:  # noqa: BLE001
                log = [{"error": repr(e)[:300]}]
        res.append({"case": name, "rep": rep, "log": log})
        print("==", name, rep, flush=True)
        for x in log:
            print("  ", json.dumps(x, ensure_ascii=False)[:600], flush=True)
usd = sum(i * 2.0 + o * 10.0 for i, o, _ in CALLS) / 1e6
print(f"API {len(CALLS)} 回・失敗 {sum(1 for *_, f in CALLS if f)}・推定 {usd:.3f} ドル")
Path(A.out).write_text(json.dumps({"sha": "60f3d24", "calls": len(CALLS), "usd": round(usd, 3), "res": res}, ensure_ascii=False, indent=1), encoding="utf-8")
