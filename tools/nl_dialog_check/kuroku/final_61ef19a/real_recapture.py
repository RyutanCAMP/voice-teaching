"""H02・H16・G04・G11 を本物の Claude で（61ef19a）。シクロの録音（recordings）には書き込まない。結果は json だけ。
使い方：python real_recapture.py <worktree> <.env> <出力 json> [回数]
"""
from __future__ import annotations
import json, sys, tempfile, time
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
from voice_teaching import claude_explain, claude_interpreter, sim  # noqa
from voice_teaching.web.flow import WebFlow  # noqa
claude_interpreter.load_dotenv(sys.argv[2])
import anthropic.resources.messages as _m  # noqa
CALLS = []
_o = _m.Messages.create


def _t(self, *a, **kw):
    t = time.perf_counter(); r = None; err = None
    try:
        r = _o(self, *a, **kw); return r
    except Exception as ex:  # noqa
        err = type(ex).__name__; raise
    finally:
        u = None
        try:
            u = {"in": r.usage.input_tokens, "out": r.usage.output_tokens}
        except Exception:  # noqa
            pass
        CALLS.append({"sec": round(time.perf_counter() - t, 2), "model": kw.get("model"), "usage": u, "error": err})


_m.Messages.create = _t
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
BR = (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
N = int(sys.argv[4]) if len(sys.argv) > 4 else 2


def msg(r):
    h, a = r.get("hear") or {}, r.get("ask") or {}
    return " / ".join(str(x) for x in (h.get("message"), a.get("reply"), " ".join(a.get("notes") or []),
                                       r.get("message") if isinstance(r.get("message"), str) else None) if x)


def new_flow(tmp):
    sim.DEFAULT_OUT_DIR = tmp / "out"
    i = claude_interpreter.from_env()
    e = claude_explain.Explainer.from_env(usage_path=tmp / "usage.jsonl")
    assert i.kind == "claude" and e.has_key
    return WebFlow(interpreter=i, explainer=e)


def repeat_setup(w, sid):
    w.talk(sid, "3回にして", "voice")
    rr = w.state(sid)["state"].get("repeat_range")
    if rr:
        w.repeat_choose(sid, "yes", rr["turn"])


def case_shift(text, expect_cand):
    def f(tmp):
        w = new_flow(tmp); sid = w.load(CP)["session_id"]; w.select(sid, "C00005")
        n0 = len(CALLS); r = w.talk(sid, text, "voice"); s = w.state(sid)["state"]; c = s.get("candidate")
        got = c and {k: c.get(k) for k in ("target", "delta", "before", "after")}
        if expect_cand:
            ok = bool(c) and c.get("target") == "C00005 Z" and c.get("delta") == "+10.000"
        else:
            ok = not c
        return ok, dict(reply=msg(r)[:300], cand=got, api=len(CALLS) - n0)
    return f


def case_h(text, approved):
    def f(tmp):
        w = new_flow(tmp); sid = w.load(BR)["session_id"]; repeat_setup(w, sid)
        s0 = w.state(sid)["state"]; g0 = w.candidate_gen_of(sid)
        if not s0.get("candidate"):
            return False, dict(why="3回の候補ができない")
        if approved:
            w.approve(sid, "クローク（テスト）", candidate_gen=g0)
        n0 = len(CALLS); r = w.talk(sid, text, "voice"); s = w.state(sid)["state"]; g = w.candidate_gen_of(sid)
        a = w.approve(sid, "QA", candidate_gen=g); e_old = w.export(sid, candidate_gen=g0); e_now = w.export(sid, candidate_gen=g)
        ok = not s.get("candidate") and not a.get("ok") and not e_old.get("ok") and not e_now.get("ok")
        return ok, dict(reply=msg(r)[:400], cand_after=bool(s.get("candidate")), g0=g0, g=g, approve=a.get("ok"),
                        export_old=e_old.get("ok"), export_now=e_now.get("ok"), api=len(CALLS) - n0,
                        status=str(s.get("status_line"))[:160])
    return f


CASES = [("G04", "Zプラスに十ミリ（契約：C00005 Z +10）", case_shift("Zプラスに十ミリ", True)),
         ("G11", "ゼットプラスに十ミリ（契約：clarify＝候補なし）", case_shift("ゼットプラスに十ミリ", False)),
         ("H16", "（3回の候補）変更は取り消して、何してるか教えて", case_h("変更は取り消して、何してるか教えて", False)),
         ("H16a", "（3回の候補・承認済み）変更は取り消して、何してるか教えて", case_h("変更は取り消して、何してるか教えて", True)),
         ("H02", "（3回の候補）さっきの3回じゃなくて2回", case_h("さっきの3回じゃなくて2回", False)),
         ("H02a", "（3回の候補・承認済み）さっきの3回じゃなくて2回", case_h("さっきの3回じゃなくて2回", True))]
res = []
for k in range(N):
    for cid, title, fn in CASES:
        with tempfile.TemporaryDirectory() as d:
            try:
                ok, info = fn(Path(d))
            except Exception as ex:  # noqa
                ok, info = None, dict(error=repr(ex)[:300])
        v = "PASS" if ok else "ERROR" if ok is None else "FAIL"
        res.append(dict(id=cid, run=k + 1, title=title, verdict=v, **info))
        print(cid, k + 1, v, title, "|", info.get("cand") or "", "|", str(info.get("reply", info.get("error", "")))[:160])
tin = sum((c["usage"] or {}).get("in", 0) for c in CALLS); tout = sum((c["usage"] or {}).get("out", 0) for c in CALLS)
summ = dict(calls=len(CALLS), errors=sum(bool(c["error"]) for c in CALLS), tokens_in=tin, tokens_out=tout,
            usd_est=round(tin * 2e-6 + tout * 10e-6, 4), models=sorted({str(c["model"]) for c in CALLS}))
print(json.dumps(summ, ensure_ascii=False))
Path(sys.argv[3]).write_text(json.dumps(dict(summary=summ, root=str(ROOT), results=res, calls=CALLS), ensure_ascii=False, indent=1),
                             encoding="utf-8")
