"""クロークの P0 独立プローブ（11/6 朝、61ef19a 向け）。モックだけ（偽の Claude）。
使い方：python p0_final.py <worktree> <出力 json>
判定の線：取消・言い直し・別の値・保留の意味の文のあと、古い候補（Z+5）を
  (a) 前の世代で出力できない、(b) 今の世代でも承認し直さずに出力できない、
  (c) 同じ古い候補をボタン1回でそのまま承認し直せない（取消なら候補が無い・保留ならまず解く必要がある）
「残してよい」文（はい・OK など）は、出力できるかを使い勝手として記録するだけ（安全の判定に入れない）。
"""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa
from voice_teaching import sim  # noqa

CP = (ROOT / "samples" / "dummy" / "DEMO_C_PLACE.JBI").read_bytes()
BR = T.demo_bytes()
FAKES = [T.answer("この位置へ動く動作です。", (21, 22, 23, 24, 25, 26)) for _ in range(40)]
MAKE = "Zプラス方向に5ミリ"

BLOCK = """やっぱり5ミリ|やっぱ5ミリで|いや5ミリ|やっぱり3ミリ|やっぱり十ミリ|やっぱりじゅうミリ|やっぱり１０ミリ|やっぱり三ミリ
3ミリにして|3ミリにしといて|3ミリのほうがいい|3ミリでお願い|3ミリで|量は3ミリ|半分にして|もう少し小さく|ちょっと減らして|2ミリ減らして|少なめで
Zプラス方向に3ミリ|Zマイナス方向に5ミリ|Yプラス方向に5ミリ|C00004をZプラス方向に5ミリ|マイナスで|逆|逆にして|反対|反対向き
取り消して|取り消しで|とりけして|トリケシ|取消|取り消してください|取り消しといて|取り消しちゃって|キャンセル|きゃんせる|ｷｬﾝｾﾙ|cancel|CANCEL
やめて|やめとこ|やめとって|やめてくれん|やめちゃおう|やめよう|取りやめ|とりやめ|中止|中止で|ストップ|すとっぷ|止めて|とめて
なし|なしで|なしなし|今のなし|今のナシ|いまのなし|今の無し|さっきのなし|さっきのは間違い|間違い|まちがい|まちごうた|間違えた
違う|ちがう|違う違う|ちゃう|ちがった|ちごうとる|そうじゃない|それじゃない|それやない|それじゃなくて
だめ|ダメ|だめだめ|いかん|いかんいかん|あかん|ノー|No|NO|いいえ|いや|いやいや
待って|ちょっと待って|待った|まった|まだ|まだ出さないで|出さないで|出さんで|出力しないで|出力せんで|出力やめて|出力はまだ|出力不要
承認取り消し|承認を取り消して|承認やめ|承認しない|承認は保留|承認やり直し
元に戻して|戻して|戻しといて|もどして|前のに戻して|さっきの方がよかった|元のままで|変えないで|変えんで|そのままにしといて
うそうそ|冗談|今のは聞かなかったことに|忘れて|リセット|撤回|破棄|消して|消しといて|いらない|いらん
大丈夫？|これ大丈夫？|ほんとに？|本当に？|え？|えっ|あれ？|なんで？|何これ？|おかしくない？|違くない？|これ逆？|5ミリで合ってる？|高すぎない？
取り消して承認して|やっぱりそのまま出力して|3ミリで出力して|取り消してから出力して|取り消さずに出力して""".replace("\n", "|").split("|")
KEEP = "はい|OK|うん|お願いします|出力して|これで出力して|どんな変更？|この変更は何？".split("|")


def flow(tmp):
    return T.flow(tmp, *FAKES)


def made(w):
    sid = w.load(CP)["session_id"]
    w.select(sid, "C00003")
    w.talk(sid, MAKE)
    return sid


def st(w, sid):
    return w.state(sid).get("state") or {}


def cand_sig(s):
    c = s.get("candidate")
    return c and json.dumps({k: c.get(k) for k in ("target", "delta", "after")}, ensure_ascii=False)


def run_phrase(p, approved, tmp):
    w, fake = flow(tmp)
    sid = made(w)
    s0 = st(w, sid)
    sig0, g0 = cand_sig(s0), w.candidate_gen_of(sid)
    if not sig0:
        return dict(verdict="ERROR", why=["Z+5 の候補ができない"])
    if approved:
        a = w.approve(sid, "QA", candidate_gen=g0)
        if not a.get("ok"):
            return dict(verdict="ERROR", why=["承認できない：" + str(a.get("error"))])
    r = w.talk(sid, p)
    s1 = st(w, sid)
    g1 = w.candidate_gen_of(sid)
    reply = " ".join(str(x) for x in ((r.get("hear") or {}).get("message"), (r.get("ask") or {}).get("reply"),
                                      r.get("message") if isinstance(r.get("message"), str) else None,
                                      r.get("error")) if x)[:200]
    ex_old = w.export(sid, candidate_gen=g0)
    ex_now = w.export(sid, candidate_gen=g1) if g1 is not None else {"ok": False}
    sig1 = cand_sig(s1)
    re_a = w.approve(sid, "QA", candidate_gen=g1) if g1 is not None else {"ok": False}
    re_e = w.export(sid, candidate_gen=g1) if re_a.get("ok") else {"ok": False}
    return dict(gen0=g0, gen1=g1, same_cand=sig1 == sig0, cand1=sig1, hold=s1.get("hold"),
                status=s1.get("status_line") or s1.get("status"), reply=reply,
                export_old_gen=bool(ex_old.get("ok")), export_now=bool(ex_now.get("ok")),
                reapprove=bool(re_a.get("ok")), reexport=bool(re_e.get("ok")), api_calls=len(fake.requests))


def judge_block(o):
    if o.get("verdict") == "ERROR":
        return o
    why = []
    if o["export_old_gen"] and o["same_cand"]:
        why.append("前の世代のまま古い候補を出力できた")
    if o["export_now"] and o["same_cand"]:
        why.append("文のあと、承認し直さずに古い候補を出力できた")
    if o["reapprove"] and o["same_cand"]:
        why.append("文のあと、同じ古い候補をそのままボタンで承認し直せた（保留でも無効でもない）")
    o["verdict"] = "FAIL" if why else "PASS"
    o["why"] = why
    return o


res = []


def isolated(fn):
    with tempfile.TemporaryDirectory() as d:
        o = sim.DEFAULT_OUT_DIR
        sim.DEFAULT_OUT_DIR = Path(d) / "out"
        try:
            return fn(Path(d))
        finally:
            sim.DEFAULT_OUT_DIR = o


def go(cid, p, approved, kind):
    try:
        r = isolated(lambda t: run_phrase(p, approved, t))
        r = judge_block(r) if kind == "block" else dict(r, verdict="INFO", why=[])
    except Exception as ex:  # noqa
        r = dict(verdict="ERROR", why=[repr(ex)[:300]])
    res.append(dict(id=cid, phrase=p, approved=approved, kind=kind, **r))


i = 0
for approved in (True, False):
    for p in BLOCK:
        i += 1
        go(f"P{i:03d}", p, approved, "block")
    for p in KEEP:
        i += 1
        go(f"P{i:03d}", p, approved, "keep")


def scenario(cid, title, fn):
    try:
        why, info = isolated(fn)
        v = "FAIL" if why else "PASS"
    except Exception as ex:  # noqa
        why, info, v = [repr(ex)[:300]], {}, "ERROR"
    res.append(dict(id=cid, phrase=title, kind="scenario", verdict=v, why=why, info=info))


def approved_flow(tmp):
    w, _ = flow(tmp)
    sid = made(w)
    g0 = w.candidate_gen_of(sid)
    assert w.approve(sid, "QA", candidate_gen=g0).get("ok")
    return w, sid, g0


def s_new_after_correction(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.talk(sid, "やっぱり3ミリ")
    w.talk(sid, "Zプラス方向に3ミリ")
    g1 = w.candidate_gen_of(sid)
    why = []
    if w.approve(sid, "QA", candidate_gen=g0).get("ok"):
        why.append("前の世代で承認できた")
    if w.export(sid, candidate_gen=g0).get("ok"):
        why.append("前の世代で出力できた")
    a = w.approve(sid, "QA", candidate_gen=g1)
    e = w.export(sid, candidate_gen=g1)
    c = st(w, sid).get("candidate") or {}
    if e.get("ok") and "+3.000" not in json.dumps(c, ensure_ascii=False):
        why.append("出力した候補が Z+3 でない")
    if not e.get("ok"):
        why.append("新しい候補をボタンで承認・出力できない（使い勝手）")
    return why, dict(g0=g0, g1=g1, approve_new=a.get("ok"), export_new=e.get("ok"), cand=cand_sig(st(w, sid)))


def s_hold_release(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.talk(sid, "ちょっと待って")
    why = []
    g1 = w.candidate_gen_of(sid)
    held = bool(st(w, sid).get("hold"))
    if w.export(sid, candidate_gen=g1).get("ok"):
        why.append("保留中に出力できた")
    if w.approve(sid, "QA", candidate_gen=g1).get("ok"):
        why.append("保留中に承認できた")
    r = w.talk(sid, "このままでいい")
    g2 = w.candidate_gen_of(sid)
    if w.export(sid, candidate_gen=g2).get("ok"):
        why.append("保留を解いただけで（承認し直さずに）出力できた")
    a = w.approve(sid, "QA", candidate_gen=g2)
    e = w.export(sid, candidate_gen=g2)
    return why, dict(held=held, g0=g0, g1=g1, g2=g2, release_reply=str((r.get("hear") or {}).get("message"))[:160],
                     reapprove=a.get("ok"), export_after_button=e.get("ok"))


def s_hold_cancel(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.talk(sid, "ちょっと待って")
    w.talk(sid, "取り消して")
    why = []
    g = w.candidate_gen_of(sid)
    for gg in {g0, g}:
        if gg is None:
            continue
        if w.approve(sid, "QA", candidate_gen=gg).get("ok"):
            why.append(f"取消のあと世代{gg}で承認できた")
        if w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"取消のあと世代{gg}で出力できた")
    return why, dict(g0=g0, g=g, cand=cand_sig(st(w, sid)))


def s_hold_then_correction(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.talk(sid, "ちょっと待って")
    w.talk(sid, "やっぱり3ミリ")
    w.talk(sid, "このままでいい")
    why = []
    g = w.candidate_gen_of(sid)
    c = st(w, sid).get("candidate")
    if c and "+5.000" in json.dumps(c, ensure_ascii=False):
        if w.approve(sid, "QA", candidate_gen=g).get("ok") and w.export(sid, candidate_gen=g).get("ok"):
            why.append("保留→言い直し→このままでいい のあと、古い Z+5 を承認・出力できた")
    return why, dict(g0=g0, g=g, cand=cand_sig(st(w, sid)))


def s_select_other(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.select(sid, "C00004")
    why = []
    g = w.candidate_gen_of(sid)
    for gg in {g0, g}:
        if gg is not None and w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"別の位置を選んだあと世代{gg}で出力できた")
    w.select(sid, "C00003")
    g2 = w.candidate_gen_of(sid)
    for gg in {g0, g2}:
        if gg is None:
            continue
        if w.approve(sid, "QA", candidate_gen=gg).get("ok"):
            why.append(f"元の位置に戻すと世代{gg}で承認できた（候補が戻った）")
        if w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"元の位置に戻すと世代{gg}で出力できた")
    return why, dict(g0=g0, g=g, g2=g2, cand=cand_sig(st(w, sid)))


def s_reload(tmp, other=False, bad=False):
    w, sid, g0 = approved_flow(tmp)
    if bad:
        lr = w.load(b"\x00not a job", previous=sid)
    else:
        lr = w.load(BR if other else CP, previous=sid)
    why = []
    if w.export(sid, candidate_gen=g0).get("ok"):
        why.append("読み直したあと前の画面の番号で出力できた")
    if w.approve(sid, "QA", candidate_gen=g0).get("ok"):
        why.append("読み直したあと前の画面の番号で承認できた")
    t = w.talk(sid, MAKE)
    if t.get("ok") and (t.get("hear") or {}).get("candidate_made"):
        why.append("前の画面で候補ができた")
    return why, dict(g0=g0, load_ok=lr.get("ok"))


def s_reload_noprev(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.load(CP)
    ex = w.export(sid, candidate_gen=g0)
    return [], dict(old_tab_export_ok=bool(ex.get("ok")), note="previous なしは別のタブ扱い（記録だけ）")


def s_undo_after_approve(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.undo(sid)
    why = []
    g = w.candidate_gen_of(sid)
    for gg in {g0, g}:
        if gg is not None and w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"［元に戻す］のあと世代{gg}で出力できた")
    w.talk(sid, MAKE)
    g2 = w.candidate_gen_of(sid)
    if w.export(sid, candidate_gen=g2).get("ok"):
        why.append("同じ候補を作り直すと、承認し直さずに出力できた")
    if w.export(sid, candidate_gen=g0).get("ok"):
        why.append("作り直したあと前の世代で出力できた")
    return why, dict(g0=g0, g=g, g2=g2)


def s_same_again(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.talk(sid, "取り消して")
    w.talk(sid, MAKE)
    g = w.candidate_gen_of(sid)
    why = []
    if w.export(sid, candidate_gen=g).get("ok"):
        why.append("取消→同じ候補を作り直し→承認なしで出力できた")
    if w.export(sid, candidate_gen=g0).get("ok"):
        why.append("前の世代で出力できた")
    return why, dict(g0=g0, g=g)


def s_export_twice_after_cancel(tmp):
    w, sid, g0 = approved_flow(tmp)
    e1 = w.export(sid, candidate_gen=g0)
    w.talk(sid, "やっぱり3ミリ")
    g = w.candidate_gen_of(sid)
    why = []
    for gg in {g0, g}:
        if gg is not None and w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"出力済みのあと言い直し→世代{gg}でもう一度出力できた")
    return why, dict(first_export=e1.get("ok"), g0=g0, g=g)


def repeat_case(tmp, phrase):
    w, _ = flow(tmp)
    sid = w.load(BR)["session_id"]
    T.repeat_to_three(w, sid)
    g0 = w.candidate_gen_of(sid)
    a = w.approve(sid, "QA", candidate_gen=g0)
    w.talk(sid, phrase)
    g = w.candidate_gen_of(sid)
    why = []
    for gg in {g0, g}:
        if gg is not None and w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"回数の候補（承認済み）：「{phrase}」のあと世代{gg}で出力できた")
    return why, dict(approved=a.get("ok"), g0=g0, g=g, cand=cand_sig(st(w, sid)))


def s_ask_route(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.ask(sid, "やっぱり3ミリにして")
    g = w.candidate_gen_of(sid)
    why = []
    for gg in {g0, g}:
        if gg is not None and w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"/api/ask に言い直し → 世代{gg}で出力できた")
    return why, dict(g0=g0, g=g)


def s_hear_route(tmp):
    w, sid, g0 = approved_flow(tmp)
    w.hear(sid, "やっぱり3ミリ", "voice")
    g = w.candidate_gen_of(sid)
    why = []
    for gg in {g0, g}:
        if gg is not None and w.export(sid, candidate_gen=gg).get("ok"):
            why.append(f"/api/hear（声）に言い直し → 世代{gg}で出力できた")
    return why, dict(g0=g0, g=g)


def s_direct_sim(tmp):
    w, sid, g0 = approved_flow(tmp)
    e = w._live(sid)
    sp, ap = e.sim_proposal, e.approval
    w.talk(sid, "取り消して")
    why = []
    try:
        sim.export_sim(sp, ap)
        why.append("取り消した承認で sim.export_sim を直接呼ぶと出力できた")
    except sim.SimError:
        pass
    return why, {}


def s_unapproved_then_new(tmp):
    # 未承認の候補 → 言い直し → 前の世代でボタン承認（古いタブ）
    w, _ = flow(tmp)
    sid = made(w)
    g0 = w.candidate_gen_of(sid)
    w.talk(sid, "やっぱり3ミリ")
    why = []
    if w.approve(sid, "QA", candidate_gen=g0).get("ok"):
        why.append("言い直しのあと前の世代で承認できた")
    return why, dict(g0=g0, g=w.candidate_gen_of(sid))


for cid, title, fn in [
    ("S01", "承認済み→やっぱり3ミリ→Zプラス方向に3ミリ（新しい候補）：前の世代は断り、新しい世代はボタンで承認・出力（Z+3）", s_new_after_correction),
    ("S02", "承認済み→ちょっと待って（保留）→このままでいい→ボタンで再承認", s_hold_release),
    ("S03", "承認済み→保留→取り消して：どの世代でも承認・出力できない", s_hold_cancel),
    ("S04", "承認済み→保留→やっぱり3ミリ→このままでいい：古い Z+5 が戻らない", s_hold_then_correction),
    ("S05", "承認済み→C00004 を選ぶ→C00003 に戻す：古い候補が戻らない", s_select_other),
    ("S06", "承認済み→同じジョブを読み直し（previous）→前の画面で操作", lambda t: s_reload(t)),
    ("S07", "承認済み→別のジョブを読む（previous）→前の画面で操作", lambda t: s_reload(t, other=True)),
    ("S08", "承認済み→読めないファイル（previous）→前の画面で出力", lambda t: s_reload(t, bad=True)),
    ("S09", "承認済み→［元に戻す］→同じ候補を作り直す", s_undo_after_approve),
    ("S10", "承認済み→取り消して→同じ候補を作り直す：古い承認が生き返らない", s_same_again),
    ("S11", "出力済み→やっぱり3ミリ→もう一度出力", s_export_twice_after_cancel),
    ("S12", "回数の候補（承認済み）→やっぱり4回", lambda t: repeat_case(t, "やっぱり4回")),
    ("S13", "回数の候補（承認済み）→4回にして（印なし・Q-3）", lambda t: repeat_case(t, "4回にして")),
    ("S14", "回数の候補（承認済み）→2回のままで", lambda t: repeat_case(t, "2回のままで")),
    ("S15", "回数の候補（承認済み）→いや4回", lambda t: repeat_case(t, "いや4回")),
    ("S16", "承認済み→/api/ask に言い直し", s_ask_route),
    ("S17", "承認済み→/api/hear（声）に言い直し", s_hear_route),
    ("S18", "2層目：取り消した承認で sim.export_sim を直接", s_direct_sim),
    ("S19", "未承認→やっぱり3ミリ→前の世代で承認", s_unapproved_then_new),
    ("S20", "承認済み→previous なしで別のタブに読む（記録だけ）", s_reload_noprev),
]:
    scenario(cid, title, fn)

n = {}
for r in res:
    k = f"{r['kind']}:{r['verdict']}"
    n[k] = n.get(k, 0) + 1
print(json.dumps(n, ensure_ascii=False))
for r in res:
    if r["verdict"] in ("FAIL", "ERROR") or r["kind"] == "scenario":
        print(r["id"], r["verdict"], ("承認済み" if r.get("approved") else "未承認") if r["kind"] != "scenario" else "",
              r["phrase"], "／".join(r["why"]), r.get("info", ""))
Path(sys.argv[2]).write_text(json.dumps(dict(summary=n, mode="mock のみ（偽の Claude）", root=str(ROOT), results=res),
                                        ensure_ascii=False, indent=1), encoding="utf-8")
