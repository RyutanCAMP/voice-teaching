"""クロークの品質検証（11/6 夜・60f3d24 向け）。モックだけ（偽の Claude・API 0回）。サーバーを起動しない。
使い方：python -I qa_mock.py <worktree> <出力 json>
- N：言い方・単位・語順・あいまい・無関係（DEMO_RJ_XYZ C00004、Z=180.000）
- S：上限・累積・承認前後・位置・JOB の切り替え
- J：読み込み・差分・出力の中身・回数・同名のファイル
期待と違うものを NG として出す（安全の判定は、危ない候補ができたかどうか）。
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T  # noqa: E402
from voice_teaching import sim  # noqa: E402

D = ROOT / "samples" / "dummy"
RJ = (D / "DEMO_RJ_XYZ.JBI").read_bytes()
BR = (D / "DEMO_BUTTON_REPEAT.JBI").read_bytes()
FAKE = lambda: [T.answer("この位置へ動く動作です。", (24, 25, 26, 27)) for _ in range(60)]  # noqa: E731
OUT = []


def new(tmp):
    sim.DEFAULT_OUT_DIR = Path(tmp) / "out"
    w, fake = T.flow(Path(tmp), *FAKE())
    return w, fake


def cand(w, sid):
    st = w.state(sid)["state"]
    c = st.get("candidate")
    return (c.get("target"), c.get("delta")) if c else None


def st_of(w, sid):
    st = w.state(sid)["state"]
    return {k: st.get(k) for k in ("can_approve", "can_export", "hold")} | {"approval": bool(st.get("approval")),
                                                                            "cand": cand(w, sid), "gen": w.candidate_gen_of(sid)}


def msg(r):
    h, a = (r.get("hear") or {}), (r.get("ask") or {})
    p = [a.get("reply"), a.get("error"), h.get("message"), r.get("message") if isinstance(r.get("message"), str) else None,
         r.get("error") if isinstance(r.get("error"), str) else None]
    return " ".join(x for x in p if x)[:300]


def rec(cid, ok, what, **kw):
    OUT.append({"id": cid, "ok": ok, "what": what, **kw})
    print(("ok " if ok else "NG ") + cid, what, json.dumps(kw, ensure_ascii=False)[:400], flush=True)


# ---- N：言い方。期待＝(軸の対象, 量) か None（候補を作らない）----
N = [
    ("N01", "Zプラス方向に5ミリ動かして", "+5.000"), ("N02", "5ミリZプラス方向に動かして", "+5.000"),
    ("N03", "Zを5ミリプラスに", "+5.000"), ("N04", "プラス方向にZを5ミリ", "+5.000"),
    ("N05", "Zプラス方向に0.5センチ", "+5.000"), ("N06", "Zプラス方向に0.5cm", "+5.000"),
    ("N07", "Zプラス方向に1cm", "+10.000"), ("N08", "Zプラス方向に3cm", None), ("N09", "Zプラス方向に2.5センチ", None),
    ("N10", "Zプラス方向に20ミリ", "+20.000"), ("N11", "Zプラス方向に20.1ミリ", None), ("N12", "Zプラス方向に21ミリ", None),
    ("N13", "Zプラス方向にマイナス5ミリ", None), ("N14", "Zプラス方向に-5ミリ", None), ("N15", "Zプラス5インチ", None),
    ("N16", "Zプラス方向に5", None), ("N17", "Zプラス方向に5メートル", None), ("N18", "Zプラス方向に0ミリ", None),
    ("N19", "Zプラス方向に五ミリ", "+5.000"), ("N20", "Zプラス方向に５ミリ", "+5.000"), ("N21", "Ｚプラス５ｍｍ", "+5.000"),
    ("N22", "Zプラス方向に5ミリと3ミリ", None), ("N23", "XとYを5ミリプラス", None),
    ("N24", "Zプラス5ミリ、それとYプラス3ミリ", None), ("N25", "C00004とC00003をZプラス5ミリ", None),
    ("N26", "Zプラス方向に十ミリ", "+10.000"), ("N27", "Zプラス方向に二十五ミリ", None), ("N28", "Zプラス方向に0.05m", None),
    ("N29", "Zマイナス方向に5ミリ", "-5.000"), ("N30", "Zを5ミリ下げて", "-5.000"), ("N31", "Z+5mm", "+5.000"),
    ("N32", "Z-5mm", "-5.000"), ("N33", "Zプラス方向に5ミリくらい", None), ("N34", "Zプラス方向に少し", None),
    ("N35", "もうちょっと上", None), ("N36", "今日の天気は？", None), ("N37", "ありがとう", None),
    ("N38", "Zプラス方向に5ミリ動かして" + "あ" * 600, None), ("N39", "Zプラス方向に1e1ミリ", None),
    ("N40", "Zプラス方向に5.0000001ミリ", None), ("N41", "Zプラス方向に19.9999ミリ", None), ("N42", "Zプラス方向に5ミリ🙂", "+5.000"),
    ("N43", "Zプラス方向に5ミリ動かさないで", None), ("N44", "Zプラス方向に5ミリ動かしたらどうなる？", None),
    ("N45", "Zプラス方向に50ミリの半分", None), ("N46", "Zプラス方向に5ミリを3回", None), ("N47", "Rxプラス5度", None),
    ("N48", "速度を半分に", None), ("N49", "ゼットプラス方向に5ミリ", "+5.000"), ("N50", "zぷらす5みり", "+5.000"),
]
for cid, text, want in N:
    with tempfile.TemporaryDirectory() as d:
        try:
            w, fake = new(d)
            sid = w.load(RJ)["session_id"]
            w.select(sid, "C00004")
            r = w.talk(sid, text, "voice")
            c = cand(w, sid)
            got = c[1] if c else None
            tgt = c[0] if c else None
            # 危ない：期待に無い候補ができた（量が違う・あるはずのない候補）。期待の候補が無いのは使い勝手（聞き返し）
            danger = c is not None and (want is None or got != want or tgt != "C00004 Z")
            rec(cid, not danger and got == want, text[:40], want=want, got=c, danger=danger, api=len(fake.requests), msg=msg(r))
        except Exception as ex:  # noqa: BLE001
            rec(cid, False, text[:40], error=repr(ex)[:200], tb=traceback.format_exc()[-400:])


def scen(cid, what, fn):
    with tempfile.TemporaryDirectory() as d:
        try:
            ok, info = fn(d)
            rec(cid, ok, what, **info)
        except Exception as ex:  # noqa: BLE001
            rec(cid, False, what, error=repr(ex)[:200], tb=traceback.format_exc()[-500:])


def appr(w, sid):
    return w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))


def expo(w, sid):
    return w.export(sid, candidate_gen=w.candidate_gen_of(sid))


def ld(w, data, prev=None):
    r = w.load(data, previous=prev) if prev else w.load(data)
    return r["session_id"]


# ---- S：上限・累積・状態 ----
def s01(d):  # 未承認 +15 のあとに +10：置きかえか、合計か。合計なら 25 で断るべき
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004")
    w.talk(sid, "Zプラス方向に15ミリ", "voice"); a = cand(w, sid)
    r = w.talk(sid, "Zプラス方向に10ミリ", "voice"); b = cand(w, sid)
    after = (w.state(sid)["state"].get("candidate") or {}).get("after")
    return (b is None or b[1] in ("+10.000",)), {"first": a, "second": b, "after": after, "msg": msg(r)}


def s02(d):  # 「さらに10ミリ」（+15 のあと）：合計 25 は断るべき
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004")
    w.talk(sid, "Zプラス方向に15ミリ", "voice")
    r = w.talk(sid, "さらに10ミリ", "voice"); b = cand(w, sid)
    return (b is None or b[1] == "+15.000" or b[1] == "+10.000"), {"second": b, "msg": msg(r)}


def s03(d):  # +15 出力 → 同じ画面で +10：古い候補が残るか（既知の注意）・25 にならないか
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004")
    w.talk(sid, "Zプラス方向に15ミリ", "voice"); appr(w, sid); e1 = expo(w, sid)
    r = w.talk(sid, "Zプラス方向に10ミリ", "voice"); s = st_of(w, sid)
    e2 = expo(w, sid)
    return (not e2.get("ok")) and not s["can_export"], {"export1": e1.get("ok"), "after_state": s, "export2": e2.get("ok"), "msg": msg(r)}


def s04(d):  # 出力した _SIM の中身を読み込んで、もう一度 +15（累積 30）：上限は1回ごと（仕様の確認）
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004")
    w.talk(sid, "Zプラス方向に15ミリ", "voice"); appr(w, sid); e = expo(w, sid)
    p = Path(d) / "out" / e.get("file_name", "x")
    if not p.exists():
        return False, {"why": "出力ファイルが無い", "e": e}
    r = w.load(p.read_bytes())
    return True, {"load_sim_ok": r.get("ok", "session_id" in r), "msg": (r.get("error") or r.get("message") or "")[:200],
                  "note": "SIM 出力を読み込めるか（読み込めるなら累積の上限は効かない＝仕様の確認）"}


def s05(d):  # 候補（C00004）のあとに C00003 を選ぶ：候補が消える。C00003 で +5 が C00003 に付く
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    r = w.select(sid, "C00003"); c1 = cand(w, sid)
    w.talk(sid, "Zプラス方向に5ミリ", "voice"); c2 = cand(w, sid)
    return c1 is None and c2 == ("C00003 Z", "+5.000"), {"after_select": c1, "new": c2, "sel_msg": msg(r)}


def s06(d):  # 「C00003をZプラス5ミリ」（C00004 選択中）：文の位置が優先されるか
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004")
    r = w.talk(sid, "C00003をZプラス方向に5ミリ", "voice"); c = cand(w, sid)
    sel = w.state(sid)["state"].get("selected")
    return c in (None, ("C00003 Z", "+5.000")), {"cand": c, "selected": sel, "msg": msg(r)}


def s07(d):  # 承認済み → 別の JOB（previous）→ 前の sid で出力
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice"); appr(w, sid)
    g = w.candidate_gen_of(sid)
    sid2 = ld(w, BR, prev=sid)
    e = w.export(sid, candidate_gen=g)
    return not e.get("ok"), {"old_export": e.get("ok"), "msg": msg(e), "new_state": st_of(w, sid2)}


def s08(d):  # 承認済み → 「速度を半分に」（別の種類の指示）
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice"); appr(w, sid)
    g = w.candidate_gen_of(sid)
    r = w.talk(sid, "速度を半分にして", "voice"); s = st_of(w, sid)
    e = w.export(sid, candidate_gen=g)
    return not e.get("ok"), {"state": s, "old_export": e.get("ok"), "msg": msg(r)}


def s09(d):  # 承認済み → 承認ボタンをもう一度（二重承認）・出力を2回
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    a1 = appr(w, sid); a2 = appr(w, sid); e1 = expo(w, sid); e2 = expo(w, sid)
    return e1.get("ok") and not e2.get("ok"), {"a1": a1.get("ok"), "a2": a2.get("ok"), "a2msg": msg(a2), "e1": e1.get("ok"),
                                               "e2": e2.get("ok"), "e2msg": msg(e2)}


def s10(d):  # 承認者の名前が空・空白・長い
    out = {}
    for name in ("", "   ", "A" * 300, "<script>"):
        w, _ = new(d + name[:1].strip()) if False else new(d)
        sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
        r = w.approve(sid, name, candidate_gen=w.candidate_gen_of(sid))
        out[repr(name[:10])] = (r.get("ok"), msg(r)[:80])
    bad = out[repr("")][0] or out[repr("   ")][0]
    return not bad, {"res": out}


def s11(d):  # 世代番号なし・文字列・負の数で承認／出力
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    res = {}
    for g in (None, "1", -1, 999, True, 1.0):
        res[repr(g)] = w.approve(sid, "QA", candidate_gen=g).get("ok")
    good = w.candidate_gen_of(sid)
    return not any(v for k, v in res.items() if k != repr(good)), {"good": good, "res": res}


def s12(d):  # 位置を選ばずに「C00004をZプラス5ミリ」
    w, _ = new(d); sid = ld(w, RJ)
    r = w.talk(sid, "C00004をZプラス方向に5ミリ動かして", "voice")
    return cand(w, sid) == ("C00004 Z", "+5.000"), {"cand": cand(w, sid), "msg": msg(r)}


def s13(d):  # 存在しない位置・MOVJ の位置・C00000（MOVJ）
    w, _ = new(d); sid = ld(w, RJ); res = {}
    for p in ("C00099", "C00000", "C00006", "C00005", "c00004", "C4", "Ｃ００００４"):
        r = w.select(sid, p)
        w.talk(sid, "Zプラス方向に5ミリ", "voice")
        st = w.state(sid)["state"]
        res[p] = {"sel_ok": r.get("ok"), "cand": cand(w, sid), "can_approve": st.get("can_approve"), "msg": msg(r)[:80]}
        w.undo(sid)
    bad = [p for p, v in res.items() if v["can_approve"] and p not in ("C00004", "c00004", "Ｃ００００４")]
    return not bad, {"res": res, "bad": bad}


def s14(d):  # 取り消し → 「はい」（何も残らない）→ 承認ボタン
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    g = w.candidate_gen_of(sid); w.talk(sid, "取り消して", "voice"); w.talk(sid, "はい", "voice")
    a = w.approve(sid, "QA", candidate_gen=g); a2 = appr(w, sid)
    return not a.get("ok") and not a2.get("ok"), {"old": a.get("ok"), "now": a2.get("ok"), "state": st_of(w, sid)}


def s15(d):  # 元に戻す を候補なしで・2回
    w, _ = new(d); sid = ld(w, RJ); r1 = w.undo(sid); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
    r2 = w.undo(sid); r3 = w.undo(sid)
    return cand(w, sid) is None, {"r1": msg(r1), "r2": msg(r2), "r3": msg(r3)}


def s16(d):  # 回数の候補（承認前）→ 位置の指示
    w, _ = new(d); sid = ld(w, BR); w.talk(sid, "C00001からC00003の作業を2回から3回にして", "voice")
    rr = w.state(sid)["state"].get("repeat_range")
    if rr:
        w.repeat_choose(sid, "yes", rr["turn"])
    c1 = cand(w, sid)
    r = w.talk(sid, "C00002をZプラス方向に5ミリ", "voice"); c2 = cand(w, sid)
    return c2 in (c1, None), {"repeat": c1, "after": c2, "msg": msg(r)}


for cid, what, fn in [
    ("S01", "未承認 +15 → +10（置きかえ・合計 25 にしない）", s01), ("S02", "+15 → さらに10ミリ（合計 25 を断る）", s02),
    ("S03", "+15 出力 → +10（古い候補のまま出力できない）", s03), ("S04", "出力した SIM を読み込む（累積の仕様確認）", s04),
    ("S05", "候補のあとに別の位置 → その位置で +5", s05), ("S06", "C00004 選択中に C00003 を言う", s06),
    ("S07", "承認済み → 別 JOB → 前の画面で出力", s07), ("S08", "承認済み → 速度の指示 → 古い世代で出力", s08),
    ("S09", "二重承認・出力2回", s09), ("S10", "承認者の名前が空・空白", s10), ("S11", "世代番号が変な値", s11),
    ("S12", "位置を選ばずに位置番号つきの文", s12), ("S13", "無い位置・MOVJ・書き方の違う番号", s13),
    ("S14", "取り消し → はい → 承認", s14), ("S15", "元に戻すを候補なし・2回", s15), ("S16", "回数の候補 → 位置の指示", s16),
]:
    scen(cid, what, fn)


# ---- J：JOB ----
def j01(d):  # 全部の合成ジョブを読む：落ちない
    w, _ = new(d); res = {}
    for p in sorted(D.glob("*.JBI")):
        try:
            r = w.load(p.read_bytes())
            res[p.name] = ("ok" if r.get("session_id") else "refused", (r.get("error") or "")[:70])
        except Exception as ex:  # noqa: BLE001
            res[p.name] = ("CRASH", repr(ex)[:100])
    return not any(v[0] == "CRASH" for v in res.values()), {"res": res}


def j02(d):  # 壊れた入力
    w, _ = new(d); res = {}
    cases = {"empty": b"", "space": b"   ", "binary": bytes(range(256)) * 4, "utf16": "/JOB\r\n//NAME X\r\n".encode("utf-16"),
             "huge": RJ * 2000, "noend": RJ.replace(b"//END", b""), "trunc": RJ[: len(RJ) // 2],
             "dupname": RJ.replace(b"C00005=", b"C00004="), "nanpos": RJ.replace(b"C00004=680.000", b"C00004=nan"),
             "infpos": RJ.replace(b"C00004=680.000", b"C00004=1e309"), "lf": RJ.replace(b"\r\n", b"\n"),
             "bom": b"\xef\xbb\xbf" + RJ, "pulse": RJ.replace(b"POSTYPE ROBOT", b"POSTYPE PULSE"),
             "pl1": RJ.replace(b"MOVL C00004 V=60.0", b"MOVL C00004 V=60.0 PL=1"),
             "vvar": RJ.replace(b"MOVL C00004 V=60.0", b"MOVL C00004 V=I000"), "tool1": RJ.replace(b"///TOOL 0", b"///TOOL 1"),
             "user": RJ.replace(b"///RECTAN", b"///USER 1\r\n///RECTAN")}
    for k, data in cases.items():
        try:
            r = w.load(data)
            sid = r.get("session_id")
            info = ("ok" if sid else "refused", (r.get("error") or "")[:60])
            if sid and k not in ("lf", "bom", "huge"):
                w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice")
                st = w.state(sid)["state"]
                info += ("can_approve=%s" % st.get("can_approve"),)
            res[k] = info
        except Exception as ex:  # noqa: BLE001
            res[k] = ("CRASH", repr(ex)[:120])
    danger = [k for k in ("nanpos", "infpos", "pulse", "pl1", "vvar", "dupname", "tool1", "user", "trunc", "noend")
              if k in res and len(res[k]) > 2 and res[k][2] == "can_approve=True"]
    return not danger and not any(v[0] == "CRASH" for v in res.values()), {"res": res, "danger": danger}


def j03(d):  # 出力の中身：C00004 の Z だけが変わる・名前は _SIM・元のファイルは変わらない
    h0 = hashlib.sha256((D / "DEMO_RJ_XYZ.JBI").read_bytes()).hexdigest()
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice"); appr(w, sid)
    e = expo(w, sid); p = Path(d) / "out" / e["file_name"]
    a = RJ.decode("ascii").splitlines(); b = p.read_bytes().decode("ascii", "replace").splitlines()
    diff = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    h1 = hashlib.sha256((D / "DEMO_RJ_XYZ.JBI").read_bytes()).hexdigest()
    want = {"//NAME DEMO_RJ_XYZ_SIM", "C00004=680.000,240.000,185.000,-179.5000,1.2500,25.0000"}
    got = {y for _, _, y in diff}
    return got == want and len(a) == len(b) and h0 == h1, {"diff": diff, "len": (len(a), len(b)), "orig_same": h0 == h1}


def j04(d):  # 回数 2→3：出力の中身（命令の数・位置の行）
    w, _ = new(d); sid = ld(w, BR); w.talk(sid, "C00001からC00003の作業を2回から3回にして", "voice")
    rr = w.state(sid)["state"].get("repeat_range"); w.repeat_choose(sid, "yes", rr["turn"]); c = cand(w, sid)
    appr(w, sid); e = expo(w, sid); p = Path(d) / "out" / e["file_name"]
    a = BR.decode("ascii").splitlines(); b = p.read_bytes().decode("ascii", "replace").splitlines()
    mv = lambda L: [x for x in L if x.startswith("MOV")]  # noqa: E731
    npos = [x for x in b if x.startswith("///NPOS")]
    return len(mv(b)) == len(mv(a)) + 3, {"cand": c, "mov_before": mv(a), "mov_after": mv(b), "npos": npos,
                                          "name": [x for x in b if x.startswith("//NAME")]}


def j05(d):  # 同名のファイル：2つ目の JOB（同じ名前）は断る・断ったあとの状態
    w, _ = new(d); sid = ld(w, RJ); w.select(sid, "C00004"); w.talk(sid, "Zプラス方向に5ミリ", "voice"); appr(w, sid); expo(w, sid)
    sid2 = ld(w, RJ, prev=sid); w.select(sid2, "C00004"); w.talk(sid2, "Zプラス方向に3ミリ", "voice"); appr(w, sid2)
    e = expo(w, sid2); s = st_of(w, sid2)
    p = Path(d) / "out" / "DEMO_RJ_XYZ_SIM.JBI.txt"
    still5 = "185.000" in p.read_text("ascii")
    return (not e.get("ok")) and still5, {"export2": e.get("ok"), "msg": msg(e), "state_after_refuse": s, "file_still_old": still5,
                                          "note": "同じ JOB の2つ目の出力は、ファイルを動かさない限りできない（使い勝手）"}


for cid, what, fn in [("J01", "合成ジョブを全部読む", j01), ("J02", "壊れた・分からない JOB", j02), ("J03", "位置の出力の中身", j03),
                      ("J04", "回数 2→3 の出力の中身", j04), ("J05", "同名の出力ファイル", j05)]:
    scen(cid, what, fn)

ng = [x["id"] for x in OUT if not x["ok"]]
print("NG", len(ng), "/", len(OUT), ng)
Path(sys.argv[2]).write_text(json.dumps({"sha": "60f3d24", "api": 0, "res": OUT}, ensure_ascii=False, indent=1), encoding="utf-8")
