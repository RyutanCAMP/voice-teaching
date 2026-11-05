"""クロークの独立プローブ（2026-11-05 夜）。モックだけ（MockInterpreter・偽の Claude）。実 Claude・実マイクは使わない。

使い方：python kuroku_probe.py <worktree のルート> <出力 json>
判定：PASS（期待どおり・安全側）／FAIL（期待と違う）／ERROR（実行できなかった）
期待は安全側の線：推測で候補を作らない・古い候補を承認できるまま残さない・説明で候補を作らない。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")

import test_claude_talk as T  # noqa: E402
from voice_teaching import jbi, sim, updown  # noqa: E402

BR = T.demo_bytes()
CP = (ROOT / "samples" / "dummy" / "DEMO_C_PLACE.JBI").read_bytes()
BLOCK = (21, 22, 23, 24, 25, 26)
EXP = lambda t="この位置へ動く動作です。": T.answer(t, BLOCK)  # noqa: E731
FAKES = [EXP() for _ in range(4)]
BANNED = ("安全です", "当たります", "干渉します", "当たりません", "干渉しません", "危なくありません")

# ターン：("t", 文)＝/api/talk ／ ("sel", 位置) ／ ("undo",) ／ ("approve",) ／ ("export",)
#         ("reload",)＝同じジョブを previous 付きで読み直す ／ ("load_other",)＝別のジョブを読む ／ ("load_bad",)＝読めないファイル
#         ("old_approve",)("old_export",)("old_talk", 文)("old_select", 位置)("old_undo",)＝読み直す前の番号で
#         ("r3",)＝回数の候補 2→3 を作る ／ ("api_hear", 文)＝/api/hear に直接 ／ ("api_ask", 文)＝/api/ask に直接
# 期待：none＝候補なし／cand=(軸,符号付き量)＝その候補／not_appr＝承認できない／old_refused＝前の番号の操作を全部断る
C = []


def case(cid, area, title, turns, job=CP, sel="C00003", updown_ok=False, **exp):
    C.append(dict(id=cid, area=area, title=title, turns=turns, job=job, sel=sel, updown=updown_ok, exp=exp))


# ---- A 引き継ぎ（方向・数値） ----
case("K01", "A引き継ぎ", "Yに10mm → マイナス", [("t", "Yに10mm"), ("t", "マイナス")], cand=("Y", -10))
case("K02", "A引き継ぎ", "10mm動かして → Yマイナス", [("t", "10mm動かして"), ("t", "Yマイナス")], cand=("Y", -10))
case("K03", "A引き継ぎ", "Zプラス → 5ミリ", [("t", "Zプラス"), ("t", "5ミリ")], cand=("Z", 5))
case("K04", "A引き継ぎ", "Yに10ミリ → マイナスでお願いします", [("t", "Yに10ミリ"), ("t", "マイナスでお願いします")], cand=("Y", -10))
case("K05", "A引き継ぎ", "Yに10mm → C00004 を選び直す → マイナス（別の位置に当てない）",
     [("t", "Yに10mm"), ("sel", "C00004"), ("t", "マイナス")], none=True)
case("K06", "A引き継ぎ", "Yに10mm →［元に戻す］→ マイナス", [("t", "Yに10mm"), ("undo",), ("t", "マイナス")], none=True)
case("K07", "A引き継ぎ", "Yに10mm → 3回にして → マイナス（間に別の話）",
     [("t", "Yに10mm"), ("t", "3回にして"), ("t", "マイナス")], none=True)
case("K08", "A引き継ぎ", "Yに10mm → Zマイナス（別の軸の答え。量を別の軸に借りない）",
     [("t", "Yに10mm"), ("t", "Zマイナス")], none=True)
case("K09", "A引き継ぎ", "10mm動かして → マイナス（軸がまだ無い）", [("t", "10mm動かして"), ("t", "マイナス")], none=True)
case("K10", "A引き継ぎ", "Yマイナス10mm（候補）→ もう5mm（足し算を推測しない）",
     [("t", "Yマイナス10mm"), ("t", "もう5mm")], not_appr_or_same=("Y", -10))
case("K11", "A引き継ぎ", "Yに10mm → えーと → マイナス", [("t", "Yに10mm"), ("t", "えーと"), ("t", "マイナス")], none=True)
case("K12", "A引き継ぎ", "Yに10mm → /api/hear に「マイナス」", [("t", "Yに10mm"), ("api_hear", "マイナス")], cand=("Y", -10))
case("K13", "A引き継ぎ", "Yに10mm → /api/ask に「何をするところ？」→ マイナス",
     [("t", "Yに10mm"), ("api_ask", "この位置は何をするところ？"), ("t", "マイナス")], none=True)

# ---- B あいまい ----
for i, s in enumerate(["Yに少し", "Yマイナスにちょっとだけ", "10mmくらいYマイナス", "マイナス10mm", "Yに10mmか20mm",
                       "たぶんYマイナス10mm", "Yマイナス10mmかな", "Yマイナス10mmぐらい", "右に10mm", "上に5mm",
                       "Yをいい感じに", "さっきと同じだけYマイナス", "C00003かC00004をZプラス5mm", "YかZにマイナス10mm",
                       "Yマイナス10mmとZプラス5mm", "Yマイナス約10mm"]):
    case(f"K{20+i}", "Bあいまい", s, [("t", s)], none=True)

# ---- C 説明だけ ----
for i, s in enumerate(["Yマイナス10mmにしたらどうなる？", "Zプラス5mm動かしたら危ない？", "Yマイナス10mmってどういう意味？",
                       "C00003をZプラス5mmにする理由を教えて", "もしYマイナス10mm動かすなら、どこを通る？",
                       "Zプラス5mmにしてもいいと思う？", "3回にしたらどうなる？", "Zプラス5mmとZプラス10mmの違いは？",
                       "Yマイナス10mm、って言ったらどうなるの？"]):
    case(f"K{40+i}", "C説明", s, [("t", s)], job=BR if "回" in s else CP, sel=None if "回" in s else "C00003",
         none=True, no_range=True, no_banned=True)

# ---- D 単位なし ----
for i, s in enumerate(["Yマイナス10", "Zプラス5", "Yに10", "Yマイナス10センチ", "Yマイナス1cm", "Yマイナス0.01m",
                       "Yマイナス10m", "Zプラス五", "Yマイナス1インチ", "Zプラス5ｍ"]):
    case(f"K{50+i}", "D単位", s, [("t", s)], none=True)
case("K60", "D単位", "Yに10 → マイナス", [("t", "Yに10"), ("t", "マイナス")], none=True)
case("K61", "D単位", "Zプラス → 5", [("t", "Zプラス"), ("t", "5")], none=True)
case("K62", "D単位", "10動かして → Yマイナス", [("t", "10動かして"), ("t", "Yマイナス")], none=True)
case("K63", "D単位", "Zプラス → 5センチ", [("t", "Zプラス"), ("t", "5センチ")], none=True)
case("K64", "D単位", "Yマイナス十ミリ（漢数字）：止めるか −10 だけ", [("t", "Yマイナス十ミリ")], none_or=("Y", -10))

# ---- E 取消・言い直し（移動の候補 Y −10 のあと） ----
MV = [("t", "Yマイナス10mm")]
for i, s in enumerate(["取り消して", "キャンセル", "キャンセルして", "やっぱりやめる", "今のなしで", "ストップ", "止めて",
                       "いやプラス", "ちがう、プラス", "やっぱりYプラス10mm", "Yプラス10mm", "Yマイナス5mmにして",
                       "やっぱり5mm", "さっきのは間違い", "それじゃなくて", "戻して", "元に戻して"]):
    case(f"K{70+i}", "E取消", f"（候補 Y−10）→ {s}", MV + [("t", s)], not_appr=True)
case("K90", "E取消", "（候補 Y−10・承認済み）→ やっぱり5mm → 出力", MV + [("approve",), ("t", "やっぱり5mm"), ("export",)],
     not_export=True)
case("K91", "E取消", "（候補 Y−10・承認済み）→ 取り消して → 出力", MV + [("approve",), ("t", "取り消して"), ("export",)],
     not_export=True)
case("K92", "E取消", "（回数 2→3）→ 4回にして", [("r3",), ("t", "4回にして")], job=BR, sel=None, not_appr=True)
case("K93", "E取消", "（回数 2→3）→ やっぱり2回のままで", [("r3",), ("t", "やっぱり2回のままで")], job=BR, sel=None, not_appr=True)
case("K94", "E取消", "（候補 Y−10）→ /api/ask に「取り消して」", MV + [("api_ask", "取り消して")], not_appr=True)
case("K95", "E取消", "（候補 Y−10）→［元に戻す］", MV + [("undo",)], not_appr=True)

# ---- F 読み直し ----
case("K100", "F読み直し", "候補 → 同じジョブを読み直し → 前の番号で承認・出力・会話・選択・元に戻す",
     MV + [("reload",), ("old_approve",), ("old_export",), ("old_talk", "Zプラス5mm"), ("old_select", "C00004"), ("old_undo",)],
     old_refused=True)
case("K101", "F読み直し", "承認済み → 読み直し → 前の番号で出力", MV + [("approve",), ("reload",), ("old_export",)], old_refused=True)
case("K102", "F読み直し", "候補 → 別のジョブを読む（previous なし）→ 前の番号で承認",
     MV + [("load_other",), ("old_approve",), ("old_export",)], old_refused=True)
case("K103", "F読み直し", "候補 → 読めないファイルを読む → 前の番号で承認（Q-5）", MV + [("load_bad",), ("old_approve",)],
     old_refused=True)


def run(c, tmp):
    cfg = None
    if c["updown"]:
        obj = updown.build_config(jbi.parse_bytes(c["job"]), updown.DEFAULT_ROBOT, "QA", "probe",
                                  confirmed_at="2026-11-05T00:00:00+09:00")
        cfg = updown.write_config(obj, tmp / "updown.json", overwrite=True)
    w, fake = T.flow(tmp, *FAKES, updown_config=cfg)
    sid = w.load(c["job"])["session_id"]
    first = sid
    if c["sel"]:
        w.select(sid, c["sel"])
    log, old = [], {}
    for st in c["turns"]:
        k, r = st[0], None
        if k == "t":
            r = w.talk(sid, st[1])
        elif k == "api_hear":
            r = w.hear(sid, st[1], "text")
        elif k == "api_ask":
            r = w.ask(sid, st[1])
        elif k == "sel":
            r = w.select(sid, st[1])
        elif k == "undo":
            r = w.undo(sid)
        elif k == "approve":
            r = w.approve(sid, "QA")
        elif k == "export":
            r = w.export(sid)
            old["export_now"] = r
        elif k == "r3":
            r = T.repeat_to_three(w, sid)
        elif k == "reload":
            sid = w.load(c["job"], previous=sid)["session_id"]
        elif k == "load_other":
            sid = w.load(BR)["session_id"]
        elif k == "load_bad":
            r = w.load(b"\x00not a job")
            old["load_bad"] = {kk: r.get(kk) for kk in ("ok", "error")}
        elif k.startswith("old_"):
            fn = k[4:]
            r = (w.approve(first, "QA") if fn == "approve" else w.export(first) if fn == "export"
                 else w.talk(first, st[1]) if fn == "talk" else w.select(first, st[1]) if fn == "select" else w.undo(first))
            old[fn] = r
        s = w.state(sid).get("state") or {}
        msg = ""
        if isinstance(r, dict):
            h, a = r.get("hear") or {}, r.get("ask") or {}
            msg = " ".join(x for x in (a.get("reply"), " ".join(a.get("notes") or []), h.get("message"),
                                        r.get("message") if isinstance(r.get("message"), str) else None,
                                        r.get("reply") if isinstance(r.get("reply"), str) else None,
                                        r.get("error") if isinstance(r.get("error"), str) else None) if x)
        cand = s.get("candidate")
        log.append(dict(turn=" ".join(map(str, st)), via=r.get("via") if isinstance(r, dict) else None, msg=msg[:240],
                        cand=cand and {kk: cand.get(kk) for kk in ("target", "kind", "delta", "before", "after", "summary")},
                        can_approve=s.get("can_approve"), can_export=s.get("can_export"), approval=bool(s.get("approval")),
                        range=(s.get("repeat_range") or {}).get("total")))
    s = w.state(sid).get("state") or {}
    cand, e, fails = s.get("candidate"), c["exp"], []
    ctext = json.dumps(cand, ensure_ascii=False) if cand else ""

    def has(axis, val):
        return bool(cand) and axis in str(cand.get("target")) and f"{val:+.3f}" in ctext

    if e.get("none"):
        cand and fails.append("候補ができた")
    if "cand" in e:
        has(*e["cand"]) or fails.append(f"期待の候補 {e['cand']} にならない")
    if "none_or" in e and cand and not has(*e["none_or"]):
        fails.append("推測した値の候補")
    if e.get("no_range") and s.get("repeat_range"):
        fails.append("範囲の確認に進んだ")
    if e.get("no_banned"):
        allm = " ".join(t["msg"] for t in log)
        [fails.append(f"断定の言葉「{b}」") for b in BANNED if b in allm]
    if e.get("not_appr"):
        appr = w.approve(sid, "QA")
        if s.get("can_approve") or appr.get("ok"):
            fails.append("古い候補が承認できるまま残る")
    if "not_appr_or_same" in e:
        if cand and not has(*e["not_appr_or_same"]):
            fails.append("前の候補に足した値を推測した")
    if e.get("not_export"):
        ex = old.get("export_now") or {}
        ex.get("ok") and fails.append("取消・言い直しのあとに出力できた")
    if e.get("old_refused"):
        for fn in ("approve", "export", "talk", "select", "undo"):
            r = old.get(fn)
            if r is None:
                continue
            ok = r.get("ok")
            made = fn == "talk" and isinstance(r.get("hear"), dict) and r["hear"].get("candidate_made")
            if ok and fn in ("approve", "export"):
                fails.append(f"前の番号で {fn} できた")
            elif ok and fn != "approve" and not (r.get("session_closed") or r.get("closed")):
                fails.append(f"前の番号の {fn} が断られない（ok=True）")
            if made:
                fails.append("前の番号で候補ができた")
    return dict(id=c["id"], area=c["area"], title=c["title"], verdict="FAIL" if fails else "PASS", why=fails,
                api_calls=len(fake.requests), turns=log, extra={k: (v if k == "load_bad" else
                                                                     {kk: v.get(kk) for kk in ("ok", "error", "session_closed")})
                                                                for k, v in old.items() if isinstance(v, dict)})


res = []
for c in C:
    with tempfile.TemporaryDirectory() as d:
        o = sim.DEFAULT_OUT_DIR
        sim.DEFAULT_OUT_DIR = Path(d) / "out"
        try:
            res.append(run(c, Path(d)))
        except Exception as ex:  # noqa: BLE001
            res.append(dict(id=c["id"], area=c["area"], title=c["title"], verdict="ERROR", why=[repr(ex)[:300]], turns=[]))
        finally:
            sim.DEFAULT_OUT_DIR = o
n = {k: sum(r["verdict"] == k for r in res) for k in ("PASS", "FAIL", "ERROR")}
print(json.dumps(n, ensure_ascii=False))
for r in res:
    print(r["id"], r["verdict"], r["area"], r["title"], "／".join(r["why"]))
Path(sys.argv[2]).write_text(json.dumps(dict(summary=n, mode="mock のみ（MockInterpreter・偽の Claude）。実 Claude・実マイクは未使用",
                                             root=str(ROOT), results=res), ensure_ascii=False, indent=1), encoding="utf-8")
