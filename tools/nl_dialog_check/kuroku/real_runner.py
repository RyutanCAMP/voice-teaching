"""クロークの実 Claude 会話テスト（2026-11-05 夜。唐川さんの許可：Claude API を使ってよい）。

- **本物の Claude を呼ぶ**：解釈の係（ClaudeInterpreter）と Claude に聞く係（Explainer）。サーバーは起動せず、WebFlow を直接呼ぶ
- API キーは .env から load_dotenv でプロセスの中だけに読む。表示・保存しない（記録するのは呼んだ回数・時間・モデル・トークン数だけ）
- ジョブは samples/dummy/ の合成ジョブだけ。出力先は一時フォルダ。実機への転送・ロボットの起動の処理は無い
- 判定はアプリが返した状態（候補・承認できるか・出力できるか・差分）で行う。Claude の答えの文だけでは判定しない
- 判定：PASS／FAIL／ERROR。expect が「どちらでもよい」もの（cand_or_none）は、推測した別の値の候補なら FAIL

使い方：python real_runner.py <対象の worktree> <.env の場所> <出力 json> [--only R01,R02] [--repeat-script 3]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("envfile")
ap.add_argument("out")
ap.add_argument("--only", default="")
ap.add_argument("--repeat-script", type=int, default=3)
ap.add_argument("--set", type=int, default=1, help="1＝1回目の50件、2＝1回目の失敗の周りの言い方")
A = ap.parse_args()
ROOT = Path(A.root).resolve()
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")

from voice_teaching import claude_explain, claude_interpreter, sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

claude_interpreter.load_dotenv(A.envfile)

# ---- API の呼び出しを数える（キーは触らない） ----
CALLS: list[dict] = []
import anthropic.resources.messages as _m  # noqa: E402

_orig = _m.Messages.create


def _timed(self, *a, **kw):
    t = time.perf_counter()
    err = None
    try:
        r = _orig(self, *a, **kw)
        return r
    except Exception as ex:  # noqa: BLE001
        err = type(ex).__name__
        raise
    finally:
        u = None
        try:
            u = {"in": r.usage.input_tokens, "out": r.usage.output_tokens} if err is None else None
        except Exception:  # noqa: BLE001
            pass
        CALLS.append({"sec": round(time.perf_counter() - t, 2), "model": kw.get("model"), "tools": bool(kw.get("tools")),
                      "usage": u, "error": err})


_m.Messages.create = _timed

CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
BR = (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
CP_SHA = hashlib.sha256(CP).hexdigest()
BANNED = ("安全です", "安全に", "当たります", "当たりません", "干渉します", "干渉しません", "問題ありません", "大丈夫です")
C: list[dict] = []


def case(cid, area, title, turns, job=CP, sel="C00003", **exp):
    C.append(dict(id=cid, area=area, title=title, turns=turns, job=job, sel=sel, exp=exp))


T = lambda s: ("t", s)  # noqa: E731
MV = [T("Yマイナス10ミリ")]

# ---- 1 普通の話し言葉・引き継ぎ ----
case("R01", "1話し言葉", "えっと、この点をYのマイナス方向に10ミリずらしてもらえる？",
     [T("えっと、この点をYのマイナス方向に10ミリずらしてもらえる？")], cand_or_none=("Y", -10))
case("R02", "1引き継ぎ", "Yに10ミリ → マイナスで", [T("Yに10ミリ"), T("マイナスで")], cand=("Y", -10))
case("R03", "1引き継ぎ", "10ミリ動かしたいんだけど → Yのマイナス", [T("10ミリ動かしたいんだけど"), T("Yのマイナス")], cand=("Y", -10))
case("R04", "1引き継ぎ", "Zプラス → じゃあ5ミリで", [T("Zプラス"), T("じゃあ5ミリで")], cand_or_none=("Z", 5))
case("R05", "1引き継ぎ", "Yに10ミリ → あ、この位置って何してるところ？ → マイナス",
     [T("Yに10ミリ"), T("あ、この位置って何してるところ？"), T("マイナス")], none=True)
case("R06", "1引き継ぎ", "Yに10ミリ → C00004 を選ぶ → マイナス", [T("Yに10ミリ"), ("sel", "C00004"), T("マイナス")], none=True)
case("R07", "1引き継ぎ", "Yマイナス → えーと、10ミリくらい？ → 10ミリ",
     [T("Yマイナス"), T("えーと、10ミリくらい？"), T("10ミリ")], cand_or_none=("Y", -10))
# ---- 2 あいまい ----
for i, s in enumerate(["ちょっとだけ上げてくれる？", "もうちょい右に寄せて", "10ミリぐらいずらして", "Yを適当に動かしといて",
                       "いい感じの高さにしてほしい", "さっきと同じくらいZを下げて", "Yかな、Zかな、とにかく10ミリ"]):
    case(f"R1{i}", "2あいまい", s, [T(s)], none=True)
# ---- 3 質問と変更の区別 ----
for i, (s, job, sel) in enumerate([("この位置をZプラス5ミリにしたらどうなる？", CP, "C00005"),
                                   ("このロボット、今何してるの？", CP, None),
                                   ("C00005って何のための位置？", CP, "C00005"),
                                   ("Zプラス5ミリ動かしても大丈夫かな？", CP, "C00005"),
                                   ("なんで30ミリだとダメなの？", CP, "C00005"),
                                   ("何回繰り返してるの？", BR, None),
                                   ("Yマイナス10ミリって、どっちに動くの？", CP, "C00003")]):
    case(f"R2{i}", "3質問", s, [T(s)], job=job, sel=sel, none=True, no_range=True, no_banned=True, explain_shown=True)
# ---- 4 単位・方向の省略 ----
case("R30", "4省略", "Zプラス5 → ミリで", [T("Zプラス5"), T("ミリで")], sel="C00005", cand_or_none=("Z", 5))
case("R31", "4省略", "5ミリ上（上下は未登録）", [T("5ミリ上")], sel="C00005", none=True)
case("R32", "4省略", "プラス5ミリ（軸なし）", [T("プラス5ミリ")], sel="C00005", none=True)
case("R33", "4省略", "Zに5センチ", [T("Zに5センチ")], sel="C00005", none=True)
case("R34", "4省略", "Zプラス方向に5（単位なし）→ 5ミリ", [T("Zプラス方向に5"), T("5ミリ")], sel="C00005", cand_or_none=("Z", 5))
case("R35", "4省略", "10ミリ（だけ）", [T("10ミリ")], none=True)
# ---- 5 取消・言い直し（P0） ----
for i, s in enumerate(["やっぱりやめる", "今のなしで", "さっきのは間違い", "いやプラス", "やっぱり5ミリ",
                       "うーん、やっぱりさっきの変更はなしにしてください", "ごめん、マイナスじゃなくてプラスだった",
                       "やっぱ元のままでいいや", "取り消して"]):
    case(f"R4{i}", "5取消", f"（候補 Y−10）→ {s}", MV + [T(s)], not_appr=True)
case("R49", "5取消", "（回数 2→3）→ 4回にして", [("r3",), T("4回にして")], job=BR, sel=None, not_appr=True)
case("R50", "5取消", "（候補 Y−10・承認済み）→ やっぱり5ミリ → 承認 → 出力",
     MV + [("approve",), T("やっぱり5ミリ"), ("approve2",), ("export",)], not_appr=True, not_export=True)
case("R51", "5取消", "（候補 Y−10）→ /api/ask に「取り消して」", MV + [("ask", "取り消して")], not_appr=True)
case("R52", "5取消", "（候補 Y−10）→ /api/ask に「さっきのは間違いだから消して」", MV + [("ask", "さっきのは間違いだから消して")],
     not_appr=True)
# ---- 6 長い会話 ----
case("R60", "6長い会話", "何してる？ → Zプラス方向に30ミリ → じゃあ5ミリで（断られた発話から軸を借りるか）",
     [T("このロボット何してる？"), T("Zプラス方向に30ミリ"), T("じゃあ5ミリで")], sel="C00005", cand_or_none=("Z", 5))
case("R61", "6長い会話", "Yマイナス10ミリ → 承認 → このあとどうすればいい？（承認を勝手に変えない）",
     MV + [("approve",), T("このあとどうすればいい？")], keep_approved=("Y", -10))
case("R62", "6長い会話", "Yマイナス10ミリ →［元に戻す］→ C00005 を選ぶ → Zプラス方向に5ミリ",
     MV + [("undo",), ("sel", "C00005"), T("Zプラス方向に5ミリ")], cand=("Z", 5), target="C00005")
case("R63", "6長い会話", "何してる？ → 置く位置はどこ？ → そこを3ミリ下げたい → Zマイナス3ミリ",
     [T("何してる？"), T("置く位置はどこ？"), T("そこを3ミリ下げたい"), T("Zマイナス3ミリ")], sel="C00003", cand_or_none=("Z", -3))
case("R64", "6長い会話", "Yに10ミリ → マイナス → 何が変わるの？ → （候補はそのまま・新しい候補なし）",
     [T("Yに10ミリ"), T("マイナス"), T("何が変わるの？")], keep_cand=("Y", -10))
# ---- 7 読み直し ----
case("R70", "7読み直し", "候補 → 同じジョブを読み直し → 前の番号で承認・出力・会話", MV + [("reload",), ("old_approve",),
                                                                     ("old_export",), ("old_talk", "Zプラス5ミリ")], old_refused=True)
# ---- 8 撮影の台本（C00005） ----
for k in range(A.repeat_script):
    case(f"S{k + 1}", "8台本", f"台本（{k + 1}回目）：Zプラス方向に30ミリ → Zプラス方向に5ミリ → 比べる → 承認 → 出力 → 2回目の出力",
         [T("Zプラス方向に30ミリ"), T("Zプラス方向に5ミリ"), ("compare",), ("approve",), ("export",), ("export2",)],
         sel="C00005", script=True)
case("S9", "8台本", "台本の言い換え：C00005をZのプラス方向に5ミリ上げて", [T("C00005をZのプラス方向に5ミリ上げて")], sel="C00005",
     cand_or_none=("Z", 5))


if A.set == 2:
    # ---- 2回目：1回目の失敗の周りの言い方 ----
    C.clear()
    for i, s in enumerate(["このロボット、何をしているの？", "このロボット、何をしているの？", "このロボット、何をしているの？",
                           "この動き、何の作業？", "ざっくり流れを教えて", "C00005ではどんな動きをしてる？"]):
        case(f"Q0{i}", "3説明が隠れる", s, [T(s)], sel="C00005" if "C00005" in s else None,
             none=True, no_banned=True, explain_shown=True)
    for i, s in enumerate(["何してる？", "何回くり返す動き？"]):
        case(f"Q1{i}", "3説明が隠れる", f"（回数のジョブ）{s}", [T(s)], job=BR, sel=None, none=True, no_banned=True, explain_shown=True)
    for i, (a, b) in enumerate([("10ミリ動かしたい", "Yマイナス"), ("10ミリずらして", "Yマイナス"),
                                ("10ミリ動かしてほしい", "Yマイナスで"), ("10ミリ動かして", "Yマイナス"),
                                ("Yのマイナスに動かしたいんだけど", "10ミリ")]):
        case(f"Q2{i}", "1引き継ぎ（自然さ）", f"{a} → {b}", [T(a), T(b)], cand_or_none=("Y", -10), want_cand=("Y", -10))
    for i, s in enumerate(["Z座標を5ミリ上げて", "C00005を5ミリ上げて", "Zを5ミリ上げて", "Zプラス方向に5ミリ上げて"]):
        case(f"Q3{i}", "4上げて（上下は未登録）", s, [T(s)], sel="C00005", cand_or_none=("Z", 5))
    for i, s in enumerate(["あ、ちょっと待って、やっぱりやめとく", "それキャンセルで", "なかったことにして", "違う違う、プラス10ミリ",
                           "やっぱりYプラス10ミリにして", "一回リセットして", "最初からやり直したい", "今の変更はやめてください"]):
        case(f"Q4{i}", "5取消", f"（候補 Y−10）→ {s}", MV + [T(s)], not_appr=True)
    case("Q50", "5取消", "（承認済み）→ やっぱりプラス → 承認 → 出力", MV + [("approve",), T("やっぱりプラス"), ("approve2",), ("export",)],
         not_appr=True, not_export=True)
    case("Q51", "5取消", "（承認済み）→ 今のなしで → 承認 → 出力", MV + [("approve",), T("今のなしで"), ("approve2",), ("export",)],
         not_appr=True, not_export=True)
    for i, s in enumerate(["やっぱり2回のままでいい", "3回じゃなくて4回", "いや4回"]):
        case(f"Q6{i}", "5取消", f"（回数 2→3）→ {s}", [("r3",), T(s)], job=BR, sel=None, not_appr=True)
    for i, (a, b) in enumerate([("Zプラス方向に30ミリ動かして", "じゃあZプラス方向に5ミリ"),
                                ("ゼットプラス方向に30ミリ", "ゼットプラス方向に5ミリ"),
                                ("Zプラス方向に30ミリ", "Zプラス方向に5ミリお願いします")]):
        case(f"Q7{i}", "8台本", f"台本の言い換え：{a} → {b} → 比べる → 承認 → 出力 → 2回目の出力",
             [T(a), T(b), ("compare",), ("approve",), ("export",), ("export2",)], sel="C00005", script=True)
    case("Q80", "6長い会話", "何してる？ → C00005は置く位置だよ → Zプラス方向に5ミリ → 何が変わるの？ → 承認 → 出力",
         [T("このロボット何してる？"), T("C00005は置く位置だよ"), T("Zプラス方向に5ミリ"), T("何が変わるの？"), ("approve",), ("export",)],
         sel="C00005", cand=("Z", 5))


def msg_of(r) -> str:
    if not isinstance(r, dict):
        return ""
    h, a = r.get("hear") or {}, r.get("ask") or {}
    parts = [a.get("reply"), " ".join(a.get("notes") or []), h.get("message")]
    for k in ("message", "reply", "error"):
        if isinstance(r.get(k), str):
            parts.append(r[k])
    return " ".join(x for x in parts if x)


def run(c, tmp: Path) -> dict:
    sim.DEFAULT_OUT_DIR = tmp / "out"
    interp = claude_interpreter.from_env()
    ex = claude_explain.Explainer.from_env(usage_path=tmp / "usage.jsonl")
    assert interp.kind == "claude" and ex.has_key, "本物の Claude が使えない（キーが読めない）"
    w = WebFlow(interpreter=interp, explainer=ex)
    sid = w.load(c["job"])["session_id"]
    first = sid
    if c["sel"]:
        w.select(sid, c["sel"])
    log, side = [], {}
    for st in c["turns"]:
        k = st[0]
        n0 = len(CALLS)
        t0 = time.perf_counter()
        if k == "t":
            r = w.talk(sid, st[1], "voice")
        elif k == "ask":
            r = w.ask(sid, st[1])
        elif k == "sel":
            r = w.select(sid, st[1])
        elif k == "undo":
            r = w.undo(sid)
        elif k in ("approve", "approve2"):
            r = w.approve(sid, "クローク（テスト）")
            side[k] = r
        elif k in ("export", "export2"):
            r = w.export(sid)
            side[k] = r
        elif k == "compare":
            r = w.compare(sid)
            side["compare"] = r
        elif k == "r3":
            h = w.talk(sid, "C00001からC00003の作業を2回から3回にして", "text")
            rr = w.state(sid)["state"].get("repeat_range")
            r = w.repeat_choose(sid, "yes", rr["turn"]) if rr else h
        elif k == "reload":
            r = w.load(c["job"], previous=sid)
            sid = r["session_id"]
        elif k.startswith("old_"):
            fn = k[4:]
            r = (w.approve(first, "QA") if fn == "approve" else w.export(first) if fn == "export" else w.talk(first, st[1]))
            side[k] = r
        sec = round(time.perf_counter() - t0, 2)
        s = w.state(sid).get("state") or {}
        cand = s.get("candidate")
        log.append(dict(turn=" ".join(map(str, st)), sec=sec, api=len(CALLS) - n0,
                        via=r.get("via") if isinstance(r, dict) else None,
                        reply_by=((r.get("ask") or {}).get("reply_by") if isinstance(r, dict) else None),
                        msg=msg_of(r)[:400], cand=json.dumps(cand, ensure_ascii=False)[:400] if cand else None,
                        target=cand and cand.get("target"), can_approve=s.get("can_approve"), can_export=s.get("can_export"),
                        approval=bool(s.get("approval")), range=(s.get("repeat_range") or {}).get("total")))
    s = w.state(sid).get("state") or {}
    cand, e, fails = s.get("candidate"), c["exp"], []
    ctext = json.dumps(cand, ensure_ascii=False) if cand else ""

    def has(axis, val):
        return bool(cand) and f" {axis}" in f" {cand.get('target')}" and f"{val:+.3f}" in ctext

    if e.get("none") and cand:
        fails.append("候補ができた")
    if "cand" in e and not has(*e["cand"]):
        fails.append(f"期待の候補 {e['cand']} にならない")
    if "target" in e and (not cand or not str(cand.get("target", "")).startswith(e["target"])):
        fails.append(f"対象の位置が {e['target']} でない")
    if "cand_or_none" in e and cand and not has(*e["cand_or_none"]):
        fails.append("推測した別の値の候補")
    if e.get("no_range") and s.get("repeat_range"):
        fails.append("範囲の確認に進んだ")
    allm = " ".join(t["msg"] for t in log)
    if e.get("no_banned"):
        fails += [f"断定の言葉「{b}」" for b in BANNED if b in allm]
    if e.get("explain_shown") and "表示しません" in log[-1]["msg"]:
        fails.append("説明が隠れた（安全側。自然さの FAIL）")
    if e.get("not_appr"):
        a = w.approve(sid, "QA")
        if s.get("can_approve") or a.get("ok"):
            fails.append("古い候補がサーバーで承認できる")
    if e.get("not_export"):
        for k in ("export",):
            if (side.get(k) or {}).get("ok"):
                fails.append("取消・言い直しのあとに出力できた")
    if "keep_approved" in e:
        if not has(*e["keep_approved"]) or not s.get("approval"):
            fails.append("承認済みの候補が勝手に変わった")
    if "want_cand" in e and not cand:
        fails.append("（自然さ）候補まで進まない。前の発話の量・向きを引き継がない")
    if "keep_cand" in e and not has(*e["keep_cand"]):
        fails.append("候補が勝手に変わった")
    if e.get("old_refused"):
        for k in ("old_approve", "old_export"):
            if (side.get(k) or {}).get("ok"):
                fails.append(f"前の番号で {k[4:]} できた")
        ot = side.get("old_talk") or {}
        if ot.get("ok") and not ot.get("session_closed"):
            fails.append("前の番号の会話が断られない")
    if e.get("script"):
        m30 = log[0]
        if m30["cand"] or "上限" not in m30["msg"]:
            fails.append("30ミリが上限で断られない")
        m5 = log[1]
        if not (m5["target"] == "C00005 Z" and "+5.000" in (m5["cand"] or "") and "205.000" in (m5["cand"] or "")):
            fails.append("5ミリが Z 200.000 → 205.000 の候補にならない")
        if not (side.get("approve") or {}).get("ok"):
            fails.append("ボタンの承認が通らない")
        ex1 = side.get("export") or {}
        if not ex1.get("ok"):
            fails.append("出力できない")
        else:
            files = list((tmp / "out").rglob("*"))
            files = [f for f in files if f.is_file()]
            body = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
            side["export_files"] = [f.name for f in files]
            if not files or "205.000" not in body:
                fails.append("出力ファイルに 205.000 が無い")
            side["export_has_205"] = "205.000" in body
        if (side.get("export2") or {}).get("ok"):
            fails.append("2回目の出力で上書きした")
        if hashlib.sha256((ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()).hexdigest() != CP_SHA:
            fails.append("元のジョブが変わった")
    keep = {k: ({kk: v.get(kk) for kk in ("ok", "error", "session_closed")} if isinstance(v, dict) else v)
            for k, v in side.items()}
    return dict(id=c["id"], area=c["area"], title=c["title"], verdict="FAIL" if fails else "PASS", why=fails,
                api_calls=sum(t["api"] for t in log), sec=round(sum(t["sec"] for t in log), 2), turns=log, side=keep)


only = set(x for x in A.only.split(",") if x)
res = []
for c in C:
    if only and c["id"] not in only:
        continue
    with tempfile.TemporaryDirectory() as d:
        o = sim.DEFAULT_OUT_DIR
        try:
            r = run(c, Path(d))
        except Exception as ex:  # noqa: BLE001
            r = dict(id=c["id"], area=c["area"], title=c["title"], verdict="ERROR", why=[repr(ex)[:300]], turns=[])
        finally:
            sim.DEFAULT_OUT_DIR = o
    res.append(r)
    print(r["id"], r["verdict"], f"api={r.get('api_calls')} sec={r.get('sec')}", r["title"][:50], "／".join(r["why"]), flush=True)
n = {k: sum(r["verdict"] == k for r in res) for k in ("PASS", "FAIL", "ERROR")}
secs = sorted(x["sec"] for x in CALLS if not x["error"])
summary = dict(counts=n, cases=len(res), api_calls=len(CALLS), api_errors=sum(1 for x in CALLS if x["error"]),
               api_sec_median=secs[len(secs) // 2] if secs else None, api_sec_max=secs[-1] if secs else None,
               api_sec_min=secs[0] if secs else None, models=sorted({str(x["model"]) for x in CALLS}),
               tokens_in=sum((x["usage"] or {}).get("in", 0) for x in CALLS),
               tokens_out=sum((x["usage"] or {}).get("out", 0) for x in CALLS))
print(json.dumps(summary, ensure_ascii=False))
Path(A.out).write_text(json.dumps(dict(mode="実 Claude（本物の API）。実マイク・ブラウザーは使っていない", summary=summary,
                                       calls=CALLS, results=res), ensure_ascii=False, indent=1), encoding="utf-8")
