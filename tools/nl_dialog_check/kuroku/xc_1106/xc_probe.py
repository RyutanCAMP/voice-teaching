"""シクロの依頼（docs/REQUEST_KUROKU_NL_CROSSCHECK_20261106.md）の照合用（クローク・11/6 夜）。モックだけ・API 0回。
使い方：python -I xc_probe.py <worktree> <SHA の名前> <出力 json>
- B：依頼1 のバグの表（F-2・Q-3・q3 の 12件の形・R1/R2・ask の保留・R8・撮影の D・R10）
- G：依頼2 の「だめ・ノー・大丈夫？」を3つの組×3つの場面（候補なし・未承認・承認済み）
- C：依頼3 の右・左（C02・C05・C06）
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
NAME = sys.argv[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa: E402
from voice_teaching import sim  # noqa: E402

D = ROOT / "samples" / "dummy"
CP = (D / "DEMO_C_PLACE.JBI").read_bytes()
RJ = (D / "DEMO_RJ_XYZ.JBI").read_bytes()
BR = (D / "DEMO_BUTTON_REPEAT.JBI").read_bytes()
OUT = []


def new(d):
    sim.DEFAULT_OUT_DIR = Path(d) / "out"
    w, fake = T.flow(Path(d), *[T.answer("この位置へ動く動作です。", (21, 22, 23)) for _ in range(60)])
    return w, fake


def st(w, sid):
    s = w.state(sid)["state"]
    c = s.get("candidate") or {}
    return {"cand": (c.get("target"), c.get("delta")) if c else None, "approval": bool(s.get("approval")), "hold": bool(s.get("hold")),
            "can_approve": bool(s.get("can_approve")), "can_export": bool(s.get("can_export")), "gen": w.candidate_gen_of(sid),
            "range": bool(s.get("repeat_range")), "voided": (s.get("voided") or {}).get("why") if s.get("voided") else None}


def msg(r):
    h, a = (r.get("hear") or {}), (r.get("ask") or {})
    p = [a.get("reply"), a.get("error"), h.get("message"), r.get("message") if isinstance(r.get("message"), str) else None,
         r.get("error") if isinstance(r.get("error"), str) else None]
    return " ".join(x for x in p if x)[:260]


def choices(r):
    h = r.get("hear") or {}
    return [c.get("label") for c in (h.get("choices") or r.get("choices") or [])]


def press(w, sid, r, label):
    h = r.get("hear") or {}
    for c in (h.get("choices") or r.get("choices") or []):
        if c.get("label") == label:
            return w.hear(sid, c["text"], "text")  # 画面のボタンは /api/hear（app.js answerChoice）
    return {"error": f"ボタン「{label}」が無い"}


def rec(cid, **kw):
    OUT.append({"id": cid, **kw})
    print(cid, json.dumps(kw, ensure_ascii=False)[:600], flush=True)


def run(cid, fn):
    with tempfile.TemporaryDirectory() as d:
        try:
            fn(d)
        except Exception as ex:  # noqa: BLE001
            rec(cid, error=repr(ex)[:200], tb=traceback.format_exc()[-500:])


def pos_setup(d, approved, job=RJ, pos="C00004", make="Zプラス方向に5ミリ"):
    w, f = new(d); sid = w.load(job)["session_id"]; w.select(sid, pos); w.talk(sid, make, "voice")
    g = w.candidate_gen_of(sid)
    if approved:
        w.approve(sid, "QA", candidate_gen=g)
    return w, sid, g, f


def old_ok(w, sid, g):
    """古い世代で承認・出力できるか（できたら危ない）。承認済みの古い世代で出力も試す。"""
    e = w.export(sid, candidate_gen=g).get("ok")
    a = w.approve(sid, "QA", candidate_gen=g).get("ok")
    return {"old_export": bool(e), "old_reapprove": bool(a)}


# ---- B：依頼1 ----
def b_f2(d, text, approved=True, exported=False):
    w, sid, g, _ = pos_setup(d, approved)
    if exported:
        w.export(sid, candidate_gen=g)
    r = w.talk(sid, text, "voice"); s = st(w, sid)
    return w, sid, g, r, s


for i, text in enumerate(["3ミリにして", "3ミリで", "量は3ミリ", "2ミリ減らして", "Zプラス方向に3ミリ", "Zマイナス方向に5ミリ",
                          "C00004をZプラス方向に3ミリ", "5ミリで合ってる？"]):
    def f(d, text=text):
        w, sid, g, r, s = b_f2(d, text)
        rec(f"B-F2-{text}", state=s, gen_changed=s["gen"] != g, msg=msg(r), **old_ok(w, sid, g))
    run(f"B-F2-{text}", f)


def b_f2_exported(d):
    w, sid, g, r, s = b_f2(d, "Zプラス方向に10ミリ", exported=True)
    rec("B-F2-出力済み→Zプラス方向に10ミリ", state=s, gen_changed=s["gen"] != g, msg=msg(r), **old_ok(w, sid, g))


run("B-F2-exported", b_f2_exported)


def br_setup(d, approved):
    w, f = new(d); sid = w.load(BR)["session_id"]
    w.talk(sid, "C00001からC00003の作業を2回から3回にして", "voice")
    rr = w.state(sid)["state"].get("repeat_range")
    w.repeat_choose(sid, "yes", rr["turn"])
    g = w.candidate_gen_of(sid)
    if approved:
        w.approve(sid, "QA", candidate_gen=g)
    return w, sid, g


for approved in (False, True):
    for text in ("4回にして", "やっぱり4回にして", "1回にして", "じゃあ5回"):
        def f(d, text=text, approved=approved):
            w, sid, g = br_setup(d, approved)
            r = w.talk(sid, text, "voice"); s = st(w, sid)
            rec(f"B-Q3-{'承認済' if approved else '未承認'}-{text}", state=s, gen_changed=s["gen"] != g, msg=msg(r), **old_ok(w, sid, g))
        run("q3", f)

for approved in (False, True):
    for text in ("もうちょっと上", "もう少し上", "もうちょっと", "もう少し右"):
        def f(d, text=text, approved=approved):
            w, sid, g, _ = pos_setup(d, approved)
            r = w.talk(sid, text, "voice"); s = st(w, sid)
            rec(f"B-R1R2-{'承認済' if approved else '未承認'}-{text}", state=s, gen_changed=s["gen"] != g, msg=msg(r), **old_ok(w, sid, g))
        run("r12", f)

# ask の保留（質問の欄）
for approved in (False, True):
    for job, text in ((BR, "じゃあ3回にして"), (RJ, "うーん"), (RJ, "C00004を3ミリ下げて"), (RJ, "この動きは何をしている？")):
        def f(d, job=job, text=text, approved=approved):
            if job is BR:
                w, sid, g = br_setup(d, approved)
            else:
                w, sid, g, _ = pos_setup(d, approved)
            r = w.ask(sid, text)
            s = st(w, sid)
            rec(f"B-ASK-{'承認済' if approved else '未承認'}-{text}", state=s, gen_changed=s["gen"] != g, msg=msg(r), **old_ok(w, sid, g))
        run("ask", f)


def b_r8(d):
    w, _ = new(d); sid = w.load(RJ)["session_id"]; w.select(sid, "C00004")
    r = w.talk(sid, "Zプラス10ミリ、いや5ミリ", "voice"); s = st(w, sid)
    ch = choices(r)
    r2 = press(w, sid, r, ch[0]) if ch else {}
    rec("B-R8", state=s, choices=ch, msg=msg(r), after_press=st(w, sid), msg2=msg(r2))


run("r8", b_r8)


def b_film_d(d):  # 「上に5ミリ」（上下が未確認）→ 声の「はい」
    w, _ = new(d); sid = w.load(RJ)["session_id"]; w.select(sid, "C00004")
    r = w.talk(sid, "上に5ミリ", "voice"); s1 = st(w, sid)
    r2 = w.talk(sid, "はい", "voice"); s2 = st(w, sid)
    rec("B-撮影D", s1=s1, msg1=msg(r), choices1=choices(r), s2=s2, msg2=msg(r2))


run("filmD", b_film_d)


def b_r10(d):  # 「もう少し右に寄せて」→ 確認 →「5ミリ」→［合っている］
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1 = w.talk(sid, "もう少し右に寄せて", "voice")
    r2 = w.talk(sid, "5ミリ", "voice")
    r3 = press(w, sid, r2, "合っている")
    s = st(w, sid)
    rec("B-R10", msg1=msg(r1), msg2=msg(r2), choices2=choices(r2), msg3=msg(r3), state=s, dead_end="使えません" in msg(r3))


run("r10", b_r10)

# ---- G：依頼2 ----
GROUPS = {
    "①否定": ["だめ", "ダメ", "ノー", "No", "いいえ", "違う", "やめて", "出さないで", "きゃんせる", "あかん", "それじゃない", "いや"],
    "②質問": ["大丈夫？", "これ大丈夫？", "合ってる？", "5ミリで合ってる？", "本当に？", "ほんとに？", "高すぎない？", "え？", "なんで？"],
    "③どちらとも": ["うーん", "ちょっと待って", "まだ", "えーと", "どうしよう"],
}
for grp, words in GROUPS.items():
    for w_ in words:
        for scene in ("none", "unapproved", "approved"):
            def f(d, w_=w_, scene=scene, grp=grp):
                if scene == "none":
                    w, f2 = new(d); sid = w.load(RJ)["session_id"]; w.select(sid, "C00004"); g = None
                else:
                    w, sid, g, f2 = pos_setup(d, scene == "approved")
                n = len(f2.requests)
                r = w.talk(sid, w_, "voice"); s = st(w, sid)
                extra = old_ok(w, sid, g) if g else {}
                rec(f"G-{grp}-{scene}-{w_}", grp=grp, scene=scene, word=w_, state=s, gen_changed=(g is not None and s["gen"] != g),
                    via=r.get("via"), claude=len(f2.requests) - n, msg=msg(r), **extra)
            run("g", f)


# ---- C：依頼3 ----
def c_confirm(w, sid, text):
    r = w.talk(sid, text, "voice")
    ch = choices(r)
    return r, ch


def c02(d):
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, ch1 = c_confirm(w, sid, "もう少し右に寄せて")
    r2 = press(w, sid, r1, "合っている") if "合っている" in ch1 else {}
    r3 = w.talk(sid, "5ミリ", "voice")
    rec("C02", msg1=msg(r1), ch1=ch1, msg2=msg(r2), msg3=msg(r3), ch3=choices(r3), state=st(w, sid),
        facing=w.state(sid)["state"].get("facing"))


def c_same(d):  # 確認のあと、同じ位置で「右に3ミリ」：覚えるか
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, ch1 = c_confirm(w, sid, "右に5ミリ")
    r2 = press(w, sid, r1, "合っている")
    s2 = st(w, sid)
    w.undo(sid)
    r3, ch3 = c_confirm(w, sid, "右に3ミリ")
    rec("C-同じ位置", msg2=msg(r2), state2=s2, msg3=msg(r3), ch3=ch3, asked_again="合っている" in ch3, state3=st(w, sid))


def c05(d):
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, _ = c_confirm(w, sid, "右に5ミリ")
    r2 = press(w, sid, r1, "合っている"); s2 = st(w, sid)
    w.undo(sid); w.select(sid, "C00004")
    r3, ch3 = c_confirm(w, sid, "右に3ミリ")
    rec("C05", msg2=msg(r2), state2=s2, msg3=msg(r3), ch3=ch3, asked_again="合っている" in ch3, state3=st(w, sid))


def c06(d):
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, _ = c_confirm(w, sid, "右に5ミリ")
    r2 = press(w, sid, r1, "合っている"); s2 = st(w, sid)
    sid2 = w.load(CP, previous=sid)["session_id"]; w.select(sid2, "C00003")
    r3, ch3 = c_confirm(w, sid2, "右に3ミリ")
    old = w.talk(sid, "右に3ミリ", "voice")
    rec("C06", msg2=msg(r2), state2=s2, msg3=msg(r3), ch3=ch3, asked_again="合っている" in ch3, state3=st(w, sid2), old_session=msg(old))


def c_wrong(d):  # ［違う］を押したあと
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, _ = c_confirm(w, sid, "右に5ミリ")
    r2 = press(w, sid, r1, "違う")
    r3, ch3 = c_confirm(w, sid, "右に5ミリ")
    rec("C-違う", msg2=msg(r2), state2=st(w, sid), msg3=msg(r3), ch3=ch3)


def c_selpending(d):  # 確認の途中で別の位置を選び、［合っている］を押す（古いボタン）
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, _ = c_confirm(w, sid, "右に5ミリ")
    w.select(sid, "C00004")
    r2 = press(w, sid, r1, "合っている")
    rec("C-確認中に位置を変えて古いボタン", msg2=msg(r2), state=st(w, sid))


def c_reloadpending(d):  # 確認の途中で JOB を読み直し、新しい画面に古いボタンの文を送る
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, _ = c_confirm(w, sid, "右に5ミリ")
    sid2 = w.load(CP, previous=sid)["session_id"]; w.select(sid2, "C00003")
    r2 = press(w, sid2, r1, "合っている")
    rec("C-読み直して古いボタン", msg2=msg(r2), state=st(w, sid2))


def c_left(d):  # 右を確かめたあと「左に3ミリ」
    w, _ = new(d); sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
    r1, _ = c_confirm(w, sid, "右に5ミリ")
    press(w, sid, r1, "合っている"); w.undo(sid)
    r3, ch3 = c_confirm(w, sid, "左に3ミリ")
    rec("C-右の確認のあとで左", msg3=msg(r3), ch3=ch3, state=st(w, sid))


for cid, fn in (("C02", c02), ("C-同じ位置", c_same), ("C05", c05), ("C06", c06), ("C-違う", c_wrong),
                ("C-確認中に位置", c_selpending), ("C-確認中に読み直し", c_reloadpending), ("C-左", c_left)):
    run(cid, fn)

Path(sys.argv[3]).write_text(json.dumps({"sha": NAME, "api": 0, "res": OUT}, ensure_ascii=False, indent=1), encoding="utf-8")
print("done", len(OUT))
