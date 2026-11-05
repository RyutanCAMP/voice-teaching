"""ケース集（corpus_1105.py）を本物の Claude で流し、分類ごとの指標を出す（クローク 2026-11-05 夜）。

- 解釈の係・Claude に聞く係とも本物の Claude。サーバーは起動せず WebFlow を直接呼ぶ。キーは .env からプロセスの中だけに読み、保存しない
- ジョブは samples/dummy/ だけ。出力先は一時フォルダ。承認・出力・実機への転送はしない（このケース集では呼ばない）
- 判定はアプリが返した状態（候補の軸・符号・量・位置）と、返事の文の種類で行う

指標（ケースごと）：
- understood：意図を正しく扱えた（cand：正しい候補／ask：聞くべきことを聞いた／stop：候補なし／explain：説明が見えた）
- needless_stop：候補にしてよい・説明してよいのに、「分かりませんでした」などで止めた（安全側だが不親切）
- good_ask：聞き返しが、足りないものを具体的に聞いている
- danger：期待と違う候補（軸・符号・量・位置）、または作ってはいけないときの候補。0件が条件

使い方：python real_corpus.py <worktree> <.env> <出力 json> [--only A01,B02]
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
ap.add_argument("--ledger", default="", help="累計の費用を書く台帳（json）。前の実行の累計に足す")
ap.add_argument("--stop-usd", type=float, default=90.0, help="台帳の累計がこの額を超えたら新しいケースを始めない")
A = ap.parse_args()
ROOT = Path(A.root).resolve()
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
sys.stdout.reconfigure(encoding="utf-8")

from voice_teaching import claude_explain, claude_interpreter, sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402
import corpus_1105  # noqa: E402

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
    "unit": r"単位",
    "position": r"位置を選|どの位置|位置.*決まっていません",
    "confirm": r"合っていますか|ですか？|どちら",
    "any": r".",
}
GENERIC = re.compile(r"が分かりませんでした|何をするか分かりませんでした")


def msg_of(r) -> str:
    if not isinstance(r, dict):
        return ""
    h, a = r.get("hear") or {}, r.get("ask") or {}
    parts = [a.get("reply"), " ".join(a.get("notes") or []), h.get("message")]
    parts += [r[k] for k in ("message", "error") if isinstance(r.get(k), str)]
    return " ".join(x for x in parts if x)


def run(c, tmp: Path) -> dict:
    sim.DEFAULT_OUT_DIR = tmp / "out"
    interp = claude_interpreter.from_env()
    ex = claude_explain.Explainer.from_env(usage_path=tmp / "usage.jsonl")
    assert interp.kind == "claude" and ex.has_key, "本物の Claude が使えない"
    w = WebFlow(interpreter=interp, explainer=ex)
    sid = w.load(JOBS[c["job"]])["session_id"]
    if c["sel"]:
        w.select(sid, c["sel"])
    log, r, pressed = [], {}, False
    n0, t0 = len(CALLS), time.perf_counter()
    for text in c["turns"]:
        r = w.talk(sid, text, "voice")
        log.append({"said": text, "via": r.get("via"), "reply_by": (r.get("ask") or {}).get("reply_by"), "msg": msg_of(r)[:300],
                    "labels": [x.get("label") for x in (r.get("hear") or {}).get("choices") or []]})
    btn = next((x["text"] for x in ((r.get("hear") or {}).get("choices") or []) if x.get("label") == "合っている"), None)
    if c["press"] and btn:
        r = w.hear(sid, btn, "text")
        pressed = True
        log.append({"said": "［合っている］", "via": None, "reply_by": None, "msg": msg_of(r)[:300], "labels": []})
    st = w.state(sid)["state"]
    cand = st.get("candidate")
    last = log[-1]["msg"] if log else ""
    labels = log[-1]["labels"] if log else []
    kind = c["exp"][0]
    got = None
    if cand:
        tgt = str(cand.get("target"))
        got = (tgt.split()[0], tgt.split()[-1], float(cand.get("delta") or 0))
    said_pos = re.findall(r"C[0-9]{5}", " ".join(c["turns"]))
    want_pos = said_pos[-1] if said_pos else (c["sel"] or "")
    if kind in ("cand", "cand_or_ask"):
        _, ax, v = c["exp"]
        ok_cand = got is not None and got[1] == ax and abs(got[2] - v) < 1e-9 and got[0] == want_pos
    else:
        ok_cand = False
    danger = bool(got) and not ok_cand
    asked = not cand and (bool(labels) or "？" in last or "ください" in last or "言って" in last)
    generic = bool(GENERIC.search(last))
    hidden = "表示しません" in last
    if kind == "cand":
        understood = ok_cand
        good_ask = False
        needless = not cand and not understood and (generic or not asked)
    elif kind == "cand_or_ask":
        good_ask = asked and not generic
        understood = ok_cand or good_ask
        needless = not cand and not good_ask
    elif kind == "ask":
        what = c["exp"][1]
        if what == "last":
            good_ask = asked and not generic and bool(re.search(r"最後|言い直", last))
        else:
            good_ask = asked and not generic and bool(re.search(ASK_RE[what], last + " ".join(labels)))
        understood = not cand and good_ask
        needless = not cand and not good_ask
    elif kind == "stop":
        understood, good_ask, needless = not cand, False, False
    else:  # explain
        shown = (log[-1]["reply_by"] == "claude" and not hidden) or (log[-1]["reply_by"] == "app" and not hidden and bool(last))
        understood, good_ask = not cand and shown, False
        needless = not cand and not shown
    return dict(id=c["id"], cat=c["cat"], said=" → ".join(c["turns"]), exp=list(c["exp"]), got=got, pressed=pressed,
                understood=understood, needless_stop=needless, good_ask=good_ask, danger=danger,
                turns=len(c["turns"]) + (1 if pressed else 0), api=len(CALLS) - n0,
                sec=round(time.perf_counter() - t0, 2), last=last[:240], log=log)


PRICE_IN, PRICE_OUT = 2.0, 10.0  # claude-sonnet-5-5（voice_teaching/claude_explain.PRICES。100万トークンあたりのドル）
LEDGER = Path(A.ledger) if A.ledger else None
base_usd = json.loads(LEDGER.read_text(encoding="utf-8")).get("usd", 0.0) if LEDGER and LEDGER.exists() else 0.0


def usd_now() -> float:
    return sum(((x["in"] or 0) * PRICE_IN + (x["out"] or 0) * PRICE_OUT) / 1e6 for x in CALLS)


only = {x for x in A.only.split(",") if x}
res = []
stopped = False
for c in corpus_1105.CASES:
    if only and c["id"] not in only:
        continue
    if any(x["in"] is None and not x["error"] for x in CALLS):
        print("使用量が読めない呼び出しがあったため止めます", flush=True)
        stopped = True
        break
    if base_usd + usd_now() >= A.stop_usd:
        print(f"累計 {base_usd + usd_now():.2f} ドルが上限 {A.stop_usd} に達したため止めます", flush=True)
        stopped = True
        break
    with tempfile.TemporaryDirectory() as d:
        try:
            r = run(c, Path(d))
        except Exception as e:  # noqa: BLE001
            r = dict(id=c["id"], cat=c["cat"], said=" → ".join(c["turns"]), error=repr(e)[:300], understood=False,
                     needless_stop=False, good_ask=False, danger=False, turns=0, api=0, sec=0)
    res.append(r)
    flag = "DANGER" if r["danger"] else ("OK" if r["understood"] else ("STOP" if r["needless_stop"] else "NG"))
    print(r["id"], flag, r["cat"], r["said"][:40], "|", (r.get("last") or r.get("error") or "")[:80], flush=True)

cats: dict[str, dict] = {}
for r in res:
    k = cats.setdefault(r["cat"], {"cases": 0, "understood": 0, "needless_stop": 0, "good_ask": 0, "ask_cases": 0,
                                   "danger": 0, "error": 0, "turns": 0})
    k["cases"] += 1
    k["understood"] += r["understood"]
    k["needless_stop"] += r["needless_stop"]
    k["danger"] += r["danger"]
    k["error"] += "error" in r
    k["turns"] += r["turns"]
    if r.get("exp") and r["exp"][0] in ("ask", "cand_or_ask"):
        k["ask_cases"] += 1
        k["good_ask"] += r["good_ask"]
secs = sorted(x["sec"] for x in CALLS if not x["error"])
total = {k: sum(v[k] for v in cats.values()) for k in ("cases", "understood", "needless_stop", "good_ask", "ask_cases", "danger",
                                                     "error", "turns")}
summary = dict(total=total, by_cat=cats, api_calls=len(CALLS), api_errors=sum(1 for x in CALLS if x["error"]),
               api_sec_median=secs[len(secs) // 2] if secs else None, api_sec_p90=secs[int(len(secs) * 0.9)] if secs else None,
               api_sec_max=secs[-1] if secs else None, models=sorted({str(x["model"]) for x in CALLS}),
               tokens_in=sum(x["in"] or 0 for x in CALLS), tokens_out=sum(x["out"] or 0 for x in CALLS),
               usd=round(usd_now(), 4), usd_cumulative=round(base_usd + usd_now(), 4), stopped_by_budget=stopped)
if LEDGER:
    LEDGER.write_text(json.dumps({"usd": summary["usd_cumulative"], "note": "推定（料金表×トークン数）。正しい額は Anthropic Console"},
                                 ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
Path(A.out).write_text(json.dumps(dict(mode="実 Claude（本物の API）。実マイク・ブラウザーは使っていない", root_sha=None,
                                       summary=summary, calls=CALLS, results=res), ensure_ascii=False, indent=1), encoding="utf-8")
