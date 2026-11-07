"""「繰り返し」の言い方の検査（クローク・11/7 昼。docs/FINAL_RC_REPEAT_RANGE_GUIDANCE_20261107.md 5章）。
使い方：python -I rep_guide.py <worktree> <出力 json> [--real <.env>]
見ること：
- 違う範囲への無断の置き換え 0（言った範囲と違う範囲で、範囲の確かめ・候補が出る）
- あいまいな回数の勝手な確定 0（「2回繰り返したい」で 2→3 の候補）
- 未承認の出力 0
- 範囲の案内が出るか（「変更できる範囲」「C00001〜C00003」の文、または範囲の確かめのボタン）
- JOB の読み直し・取り消しのあと、古い範囲の確かめが残らない
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("out"); ap.add_argument("--real", default="")
A = ap.parse_args()
ROOT = Path(A.root).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
from voice_teaching import claude_explain, claude_interpreter, sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

CALLS = []
if A.real:
    claude_interpreter.load_dotenv(A.real)
    import anthropic.resources.messages as _m  # noqa: E402
    _orig = _m.Messages.create

    def _t(self, *a, **kw):
        r = None
        try:
            r = _orig(self, *a, **kw); return r
        finally:
            u = getattr(r, "usage", None)
            CALLS.append(((getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
                          + (getattr(u, "cache_read_input_tokens", 0) or 0) * 0.1, getattr(u, "output_tokens", 0) or 0))
    _m.Messages.create = _t
else:
    import test_claude_talk as T  # noqa: E402

D = ROOT / "samples/dummy"
JOBS = {"BR": (D / "DEMO_BUTTON_REPEAT.JBI").read_bytes(), "RJ": (D / "DEMO_RJ_XYZ.JBI").read_bytes()}


def flow(d):
    sim.DEFAULT_OUT_DIR = Path(d) / "o"
    if A.real:
        return WebFlow(interpreter=claude_interpreter.from_env(),
                       explainer=claude_explain.Explainer.from_env(usage_path=Path(d) / "u.jsonl"))
    w, _ = T.flow(Path(d), *[T.answer("同じ動きを2回くり返しています。", (21, 22, 23, 24, 25, 26)) for _ in range(20)])
    return w


# 期待：kind = "guide"（範囲の案内・候補なし）／"ask"（聞き返し・候補なし）／"range_ok"（言った範囲どおりの範囲の確かめ）／"none"（対応なし）
CASES = [
    ("R01", "BR", ["C1C4を2回繰り返したい"], "guide", "C00001〜C00004 と言った。2→3 に読み替えない・C00001〜C00003 に黙って置き換えない"),
    ("R02", "BR", ["C00001からC00004を2回から3回にして"], "guide", "違う範囲。黙って C00001〜C00003 にしない"),
    ("R03", "BR", ["繰り返しを増やして"], "guide", "範囲も回数も言わない"),
    ("R04", "BR", ["もう1回繰り返して"], "guide", "回数の言い方の揺れ"),
    ("R05", "BR", ["2回繰り返したい"], "ask", "あいまい：今2回なのか、2回にしたいのか。2→3 にしない"),
    ("R06", "BR", ["3回にして"], "guide", "範囲を言わない 3回"),
    ("R07", "BR", ["反復を3回にしたい"], "guide", "「反復」"),
    ("R08", "BR", ["回数を変えたい"], "guide", "回数だけ"),
    ("R09", "BR", ["2回から2回にして"], "none", "変わらない回数"),
    ("R10", "BR", ["3回から4回にして"], "none", "対応外の回数"),
    ("R11", "RJ", ["2回から3回にして"], "none", "繰り返しの無い JOB"),
    ("R12", "BR", ["C00001からC00003の作業を2回から3回にして"], "range_ok", "今までの言い方（壊れていないこと）"),
    ("R13", "BR", ["2回から3回にして"], "range_ok", "撮影の言い方"),
    ("R14", "BR", ["2回から3回にして", "@range_no"], "none", "範囲の確かめで［違う］：候補なし"),
    ("R15", "BR", ["2回から3回にして", "@reload", "@range_yes_old"], "none", "読み直したあと、古い範囲のボタンを押す"),
    ("R16", "BR", ["2回から3回にして", "取り消して", "@range_yes_old"], "none", "取り消したあと、古い範囲のボタン"),
    ("R17", "BR", ["2回から3回にして", "@range_yes", "@approve", "@export"], "exported", "2→3 の出力（壊れていないこと）"),
    ("R18", "BR", ["C2からC3を3回にして"], "guide", "範囲の一部"),
]


def snap(w, sid):
    st = w.state(sid)["state"]
    rr = st.get("repeat_range") or {}
    c = st.get("candidate") or {}
    return {"range": {k: rr.get(k) for k in ("first", "last", "count", "target", "turn") if k in rr} or (bool(rr) or None),
            "cand": (c.get("target"), c.get("delta")) if c else None, "can_approve": st.get("can_approve"),
            "can_export": st.get("can_export"), "approval": bool(st.get("approval"))}


def msg(r):
    h, a = (r.get("hear") or {}), (r.get("ask") or {})
    return " ".join(x for x in [a.get("reply"), a.get("error"), h.get("message"),
                                r.get("message") if isinstance(r.get("message"), str) else None,
                                r.get("error") if isinstance(r.get("error"), str) else None] if x)


RES = []
for cid, job, steps, want, note in CASES:
    with tempfile.TemporaryDirectory() as d:
        w = flow(d)
        sid = w.load(JOBS[job])["session_id"]
        log, old_rr, file = [], None, None
        for s in steps:
            if s == "@range_yes":
                rr = w.state(sid)["state"].get("repeat_range")
                r = w.repeat_choose(sid, "yes", rr["turn"]) if rr else {"error": "範囲の確かめが無い"}
            elif s == "@range_no":
                rr = w.state(sid)["state"].get("repeat_range")
                r = w.repeat_choose(sid, "no", rr["turn"]) if rr else {"error": "範囲の確かめが無い"}
            elif s == "@range_yes_old":
                r = w.repeat_choose(sid, "yes", old_rr["turn"]) if old_rr else {"error": "古い範囲の確かめが無い"}
            elif s == "@reload":
                sid_old = sid
                sid = w.load(JOBS[job], previous=sid)["session_id"]
                r = {"message": "読み直し"}
            elif s == "@approve":
                r = w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
            elif s == "@export":
                r = w.export(sid, candidate_gen=w.candidate_gen_of(sid)); file = r.get("file_name")
            else:
                r = w.talk(sid, s, "voice")
            rr = w.state(sid)["state"].get("repeat_range")
            if rr:
                old_rr = rr
            log.append({"do": s, "msg": msg(r)[:400], **snap(w, sid)})
        last = log[-1]
        text = " ".join(x["msg"] for x in log)
        said_c4 = "C00004" in " ".join(steps).replace("C4", "C00004")
        rng = last["range"] if isinstance(last["range"], dict) else {}
        shown_range = re.findall(r"C0000[0-9]〜C0000[0-9]", text)
        substituted = said_c4 and (bool(last["range"]) or last["cand"] is not None) and "C00004" not in text
        ambiguous_fixed = cid == "R05" and last["cand"] is not None
        unapproved_export = file is not None and not last["approval"]
        guide = bool(re.search(r"変更できる範囲|範囲は|C00001〜C00003", text))
        fixed_phrase = "のように言ってください" in text
        if want == "guide":
            ok = guide and last["cand"] is None and not fixed_phrase and not substituted
        elif want == "ask":
            ok = last["cand"] is None and not ambiguous_fixed
        elif want == "range_ok":
            ok = bool(last["range"]) and last["cand"] is None
        elif want == "exported":
            ok = file is not None and last["approval"]
        else:
            ok = last["cand"] is None and not last["can_export"]
        RES.append({"id": cid, "job": job, "steps": steps, "want": want, "note": note, "ok": ok,
                    "danger": {"substituted": bool(substituted), "ambiguous_fixed": ambiguous_fixed, "unapproved_export": unapproved_export},
                    "guide_shown": guide, "fixed_phrase_demanded": fixed_phrase, "ranges_in_text": sorted(set(shown_range)), "log": log})
        print(("ok " if ok else "NG ") + cid, steps[0][:30], "| 期待", want, "| 範囲", last["range"], "| 候補", last["cand"],
              "| 案内", guide, "| 定型文", fixed_phrase, "| 危", {k: v for k, v in RES[-1]["danger"].items() if v}, "|", log[0]["msg"][:120], flush=True)
usd = sum(i * 2.0 + o * 10.0 for i, o in CALLS) / 1e6
print("API", len(CALLS), f"推定 {usd:.3f} ドル")
Path(A.out).write_text(json.dumps({"root": ROOT.name, "real": bool(A.real), "calls": len(CALLS), "usd": round(usd, 3), "res": RES},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
