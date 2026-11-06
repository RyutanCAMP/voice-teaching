"""クロークの実 Claude 会話の品質確認（2026-11-06 午後・唐川さんの優先 7項目）。

- 本物の Claude（解釈の係・Claude に聞く係）。サーバーは起動せず WebFlow を直接呼ぶ。キーは .env からプロセスの中だけに読み、表示・保存しない
- ジョブは samples/dummy/ の合成ジョブだけ。出力先は一時フォルダ。承認・出力・実機への転送・ロボットの起動はしない
- 判定はアプリが返した状態（候補の位置・軸・符号・量、範囲の確認）と返事の文で行う
- 2ターン以上のケースは、1ターン目の候補（old）が最後まで残ったかも見る（old_kept：古い候補が残った＝安全側でない）

期待（exp）：
- ("cand", 軸, 量) / ("cand_or_ask", 軸, 量) / ("ask", 何を) / ("stop",) / ("explain",)：corpus_1105 と同じ
- ("stop_says", 正規表現)：候補・範囲を作らず、返事に正規表現が入っている（例：回数は「2回から3回」だけと説明する）
- ("repeat_ok",)：回数の範囲の確認（ボタン）か回数の候補になる

返事の文の指標（すべてのケースの最後の返事）：長さ（文字数）・専門用語の数・次にすることの案内があるか

使い方：python real_focus_1106.py <worktree> <.env> <出力 json> [--only F101,F201] [--repeat 1]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("envfile")
ap.add_argument("out")
ap.add_argument("--only", default="")
ap.add_argument("--repeat", type=int, default=1)
ap.add_argument("--stop-usd", type=float, default=5.0)
A = ap.parse_args()
ROOT = Path(A.root).resolve()
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")

from voice_teaching import claude_explain, claude_interpreter, sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

CASES: list[dict] = []


def c(cid, item, turns, exp, sel="C00003", job="CP"):
    CASES.append(dict(id=cid, item=item, turns=[turns] if isinstance(turns, str) else turns, exp=exp, sel=sel, job=job))


# 1 基本の指示
c("F101", "1 基本", "Zプラス方向に5ミリ", ("cand", "Z", 5), sel="C00005")
c("F102", "1 基本", "Zマイナス方向に2ミリ", ("cand", "Z", -2))
c("F103", "1 基本", "Yプラス方向に10ミリ", ("cand", "Y", 10))
c("F104", "1 基本", "Xマイナス1ミリ", ("cand", "X", -1))
c("F105", "1 基本", "Zプラス方向に5ミリ動かしてください", ("cand", "Z", 5), sel="C00005")
c("F106", "1 基本", "C00004をYマイナス方向に3ミリ", ("cand", "Y", -3))
# 2 言い直し（2ターン目。1ターン目の候補は古い候補）
c("F201", "2 言い直し", ["Zプラス方向に5ミリ", "もうちょっと"], ("ask", "any"), sel="C00005")
c("F202", "2 言い直し", ["Zプラス方向に5ミリ", "やっぱり3ミリ"], ("ask", "any"), sel="C00005")
c("F203", "2 言い直し", ["Zプラス方向に5ミリ", "いや違う"], ("ask", "any"), sel="C00005")
c("F204", "2 言い直し", ["Zプラス方向に5ミリ", "やっぱりZプラス3ミリ"], ("cand_or_ask", "Z", 3), sel="C00005")
c("F205", "2 言い直し", ["Zプラス方向に5ミリ", "いや、Zマイナス5ミリ"], ("cand_or_ask", "Z", -5), sel="C00005")
c("F206", "2 言い直し", ["Zプラス方向に5ミリ", "もうちょっと上"], ("ask", "any"), sel="C00005")
c("F207", "2 言い直し", ["Zプラス方向に5ミリ", "もう少し減らして"], ("ask", "any"), sel="C00005")
c("F208", "2 言い直し", "Zプラス10ミリ、いや5ミリ", ("ask", "last"))
c("F209", "2 言い直し", ["Zプラス方向に5ミリ", "Zプラス3ミリ"], ("cand_or_ask", "Z", 3), sel="C00005")
c("F210", "2 言い直し", ["Zプラス方向に5ミリ", "やっぱりやめた"], ("stop",), sel="C00005")
# 3 足りないときの聞き返し
c("F301", "3 聞き返し", "5ミリ動かして", ("ask", "axis"))
c("F302", "3 聞き返し", "Zに動かして", ("ask", "amount"))
c("F303", "3 聞き返し", "Zプラス", ("ask", "amount"))
c("F304", "3 聞き返し", "ちょっと動かして", ("ask", "any"))
c("F305", "3 聞き返し", "Yに3ミリ", ("ask", "axis"))
c("F306", "3 聞き返し", "動かして", ("ask", "any"))
c("F307", "3 聞き返し", "3", ("ask", "any"))
# 4 方向の言葉
c("F401", "4 方向", "上に5ミリ", ("cand_or_ask", "Z", 5), sel="C00005")
c("F402", "4 方向", "下に2ミリ", ("cand_or_ask", "Z", -2))
c("F403", "4 方向", "右に3ミリ", ("cand_or_ask", "Y", 3))
c("F404", "4 方向", "左に3ミリ", ("cand_or_ask", "Y", -3))
c("F405", "4 方向", "前に3ミリ", ("ask", "confirm"))
c("F406", "4 方向", "奥に3ミリ", ("ask", "confirm"))
c("F407", "4 方向", "手前に2ミリ", ("ask", "confirm"))
c("F408", "4 方向", "上にZマイナス3ミリ", ("ask", "any"))
c("F409", "4 方向", "Zプラス3ミリ下げて", ("ask", "any"))
c("F410", "4 方向", "斜め上に3ミリ", ("ask", "any"))
# 5 回数（このプロトタイプは 2回→3回 だけ）
RANGE = r"2回から3回|3回"
c("F501", "5 回数", "4回にして", ("stop_says", RANGE), sel=None, job="BR")
c("F502", "5 回数", "C00001からC00003の作業を2回から4回にして", ("stop_says", RANGE), sel=None, job="BR")
c("F503", "5 回数", "1回にして", ("stop_says", RANGE), sel=None, job="BR")
c("F504", "5 回数", "10回繰り返して", ("stop_says", RANGE), sel=None, job="BR")
c("F505", "5 回数", "C00001からC00003の作業を2回から3回にして", ("repeat_ok",), sel=None, job="BR")
c("F506", "5 回数", "もう1回増やして", ("stop_says", r"回"), sel=None, job="BR")
c("F507", "5 回数", "回数を増やして", ("stop_says", r"回"), sel=None, job="BR")
c("F508", "5 回数", "繰り返しを4回にしたい", ("stop_says", RANGE), sel=None, job="BR")
# 6・7 説明・次にすること
c("F601", "6-7 説明", "何をする動き？", ("explain",), sel=None)
c("F602", "6-7 説明", "次は何をすればいい？", ("explain",), sel=None)
c("F603", "6-7 説明", "どうやって使うの？", ("explain",), sel=None)
c("F604", "6-7 説明", "よく分からない", ("stop",), sel=None)
c("F605", "6-7 説明", "承認して", ("stop_says", r"ボタン"))
c("F606", "6-7 説明", ["Zプラス方向に5ミリ", "このあとどうすればいい？"], ("stop",), sel="C00005")

claude_interpreter.load_dotenv(A.envfile)
CALLS: list[dict] = []
import anthropic.resources.messages as _m  # noqa: E402

_orig = _m.Messages.create


def _timed(self, *a, **kw):
    t, err, r = time.perf_counter(), None, None
    try:
        r = _orig(self, *a, **kw)
        return r
    except Exception as ex:  # noqa: BLE001
        err = type(ex).__name__
        raise
    finally:
        CALLS.append({"sec": round(time.perf_counter() - t, 2), "model": kw.get("model"), "error": err,
                      "in": getattr(getattr(r, "usage", None), "input_tokens", None),
                      "out": getattr(getattr(r, "usage", None), "output_tokens", None)})


_m.Messages.create = _timed
JOBS = {"CP": (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes(),
        "BR": (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()}
ASK_RE = {
    "amount": r"何\s?mm|何ミリ|量",
    "axis": r"どの方向|どの軸|軸と向き|プラスですか、マイナスですか|向き",
    "confirm": r"合っていますか|ですか？|どちら",
    "any": r".",
}
GENERIC = re.compile(r"が分かりませんでした|何をするか分かりませんでした")
JARGON = re.compile(r"JBI|MOVL|MOVJ|PL[=>＝]|パルス|ツール座標|ベース座標|ユーザー座標|ロボット座標|TCP|教示点|命令|行番号|世代|変数|NOP|TIMER|DOUT|WAIT|インタープリタ|パラメータ")
NEXT = re.compile(r"ボタン|言ってください|言い直して|ください|ますか？|ですか？|例：|教えて")


def msg_of(r) -> str:
    if not isinstance(r, dict):
        return ""
    h, a = r.get("hear") or {}, r.get("ask") or {}
    parts = [a.get("reply"), " ".join(a.get("notes") or []), h.get("message")]
    parts += [r[k] for k in ("message", "error") if isinstance(r.get(k), str)]
    return " ".join(x for x in parts if x)


def cand_of(st):
    cand = st.get("candidate")
    if not cand:
        return None
    tgt = str(cand.get("target"))
    return (tgt.split()[0], tgt.split()[-1], float(cand.get("delta") or 0))


def run(c, tmp: Path) -> dict:
    sim.DEFAULT_OUT_DIR = tmp / "out"
    interp = claude_interpreter.from_env()
    ex = claude_explain.Explainer.from_env(usage_path=tmp / "usage.jsonl")
    assert interp.kind == "claude" and ex.has_key, "本物の Claude が使えない"
    w = WebFlow(interpreter=interp, explainer=ex)
    sid = w.load(JOBS[c["job"]])["session_id"]
    if c["sel"]:
        w.select(sid, c["sel"])
    log, r, old, old_gen = [], {}, None, None
    n0, t0 = len(CALLS), time.perf_counter()
    for i, text in enumerate(c["turns"]):
        r = w.talk(sid, text, "voice")
        log.append({"said": text, "via": r.get("via"), "reply_by": (r.get("ask") or {}).get("reply_by"), "msg": msg_of(r)[:400],
                    "labels": [x.get("label") for x in (r.get("hear") or {}).get("choices") or []]})
        if i == 0 and len(c["turns"]) > 1:
            old, old_gen = cand_of(w.state(sid)["state"]), w.candidate_gen_of(sid)
    st = w.state(sid)["state"]
    got = cand_of(st)
    gen = w.candidate_gen_of(sid)
    old_kept = old is not None and got is not None and gen == old_gen
    old_approvable = old_kept and bool(st.get("can_approve"))
    last = log[-1]["msg"] if log else ""
    labels = log[-1]["labels"] if log else []
    kind = c["exp"][0]
    said_pos = re.findall(r"C[0-9]{5}", " ".join(c["turns"]))
    want_pos = said_pos[-1] if said_pos else (c["sel"] or "")
    new_cand = got is not None and not old_kept
    if kind in ("cand", "cand_or_ask"):
        _, ax, v = c["exp"]
        ok_cand = new_cand and got[1] == ax and abs(got[2] - v) < 1e-9 and got[0] == want_pos
    else:
        ok_cand = False
    repeat_cand = bool(st.get("repeat_range")) or (got is not None and "回" in str((st.get("candidate") or {}).get("target")))
    danger = new_cand and not ok_cand and not (kind == "repeat_ok" and repeat_cand)
    asked = got is None and (bool(labels) or "？" in last or "ください" in last or "言って" in last)
    generic = bool(GENERIC.search(last))
    hidden = "表示しません" in last
    good_ask = False
    if kind == "cand":
        understood = ok_cand
    elif kind == "cand_or_ask":
        good_ask = asked and not generic
        understood = ok_cand or good_ask
    elif kind == "ask":
        what = c["exp"][1]
        pat = r"最後|言い直" if what == "last" else ASK_RE[what]
        good_ask = asked and not generic and bool(re.search(pat, last + " ".join(labels)))
        understood = got is None and not st.get("repeat_range") and good_ask
    elif kind == "stop":
        understood = got is None and not st.get("repeat_range")
    elif kind == "stop_says":
        understood = got is None and not st.get("repeat_range") and bool(re.search(c["exp"][1], last))
    elif kind == "repeat_ok":
        understood = repeat_cand
    else:  # explain
        shown = (log[-1]["reply_by"] == "claude" and not hidden) or (log[-1]["reply_by"] == "app" and not hidden and bool(last))
        understood = got is None and shown
    rr = st.get("repeat_range")
    return dict(id=c["id"], item=c["item"], said=" → ".join(c["turns"]), exp=list(c["exp"]), old=old, got=got,
                hold=st.get("hold"), can_approve=st.get("can_approve"), can_export=st.get("can_export"),
                repeat_range=bool(rr), old_kept=old_kept, old_approvable=old_approvable, understood=bool(understood), good_ask=good_ask, danger=danger, hidden=hidden,
                generic=generic, chars=len(last), jargon=JARGON.findall(last), next_hint=bool(NEXT.search(last)),
                api=len(CALLS) - n0, sec=round(time.perf_counter() - t0, 2), last=last[:400], log=log)


PRICE_IN, PRICE_OUT = 2.0, 10.0  # claude-sonnet-5-5（voice_teaching/claude_explain.PRICES。100万トークンあたりのドル）


def usd_now() -> float:
    return sum(((x["in"] or 0) * PRICE_IN + (x["out"] or 0) * PRICE_OUT) / 1e6 for x in CALLS)


only = {x for x in A.only.split(",") if x}
res = []
for rep in range(A.repeat):
    for c in CASES:
        if only and c["id"] not in only:
            continue
        if usd_now() >= A.stop_usd:
            print("上限に達したため止めます", flush=True)
            break
        with tempfile.TemporaryDirectory() as d:
            try:
                r = run(c, Path(d))
            except Exception as e:  # noqa: BLE001
                r = dict(id=c["id"], item=c["item"], said=" → ".join(c["turns"]), error=repr(e)[:300], understood=False,
                         danger=False, old_kept=False)
        r["rep"] = rep
        res.append(r)
        flag = "DANGER" if r["danger"] else ("OLD!" if r.get("old_approvable") else "OLD(hold)" if r.get("old_kept") else ("OK" if r["understood"] else "NG"))
        print(rep, r["id"], flag, r["said"][:36], "|", (r.get("last") or r.get("error") or "")[:90], flush=True)

items: dict[str, dict] = {}
for r in res:
    k = items.setdefault(r["item"], {"cases": 0, "understood": 0, "danger": 0, "old_kept": 0, "error": 0, "hidden": 0,
                                     "generic": 0, "next_hint": 0, "chars": [], "jargon": 0})
    k["cases"] += 1
    k["understood"] += r["understood"]
    k["danger"] += r["danger"]
    k["old_kept"] += r.get("old_kept", False)
    k["error"] += "error" in r
    k["hidden"] += r.get("hidden", False)
    k["generic"] += r.get("generic", False)
    k["next_hint"] += r.get("next_hint", False)
    k["jargon"] += bool(r.get("jargon"))
    k["chars"].append(r.get("chars", 0))
for k in items.values():
    s = sorted(k.pop("chars"))
    k["chars_median"], k["chars_max"] = (s[len(s) // 2], s[-1]) if s else (None, None)
summary = dict(by_item=items, cases=len(res), understood=sum(r["understood"] for r in res), danger=sum(r["danger"] for r in res),
               old_kept=sum(r.get("old_kept", False) for r in res),
               old_approvable=sum(r.get("old_approvable", False) for r in res), api_calls=len(CALLS),
               api_errors=sum(1 for x in CALLS if x["error"]), models=sorted({str(x["model"]) for x in CALLS}),
               usd=round(usd_now(), 4))
print(json.dumps(summary, ensure_ascii=False))
Path(A.out).write_text(json.dumps(dict(mode="実 Claude（本物の API）。実マイク・ブラウザーは使っていない", summary=summary,
                                       calls=CALLS, results=res), ensure_ascii=False, indent=1), encoding="utf-8")
