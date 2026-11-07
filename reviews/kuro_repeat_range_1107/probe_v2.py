"""第2回：［承認して保存］・未承認／古い承認の出力禁止・.JBI の整合・繰り返しの範囲・否定／取消／二重操作（読むだけ・モック・プロセスの中）。
使い方：python -I <this> <repo> <結果の json>
"""
import base64
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repo))
from voice_teaching import claude_interpreter as ci  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.web.flow import WebFlow  # noqa: E402

OUT = Path(tempfile.mkdtemp()) / "sim"
sim.DEFAULT_OUT_DIR = OUT
REP_P = repo / "samples/dummy/DEMO_BUTTON_REPEAT.JBI"
PLACE_P = repo / "samples/dummy/DEMO_PLACE.JBI"
REP, PLACE = REP_P.read_bytes(), PLACE_P.read_bytes()
REP_SHA, PLACE_SHA = hashlib.sha256(REP).hexdigest(), hashlib.sha256(PLACE).hexdigest()
res = []


def rec(cat, name, ok, detail, severe=False):
    res.append({"cat": cat, "id": name, "pass": bool(ok), "severe_if_fail": severe, "detail": detail})
    print(("PASS " if ok else ("FAIL!! " if severe else "FAIL ")) + f"[{cat}] {name} :: {detail}")


def files():
    return sorted(OUT.glob("*")) if OUT.exists() else []


def new(data=REP):
    w = WebFlow(interpreter=ci.MockInterpreter(), updown_config=None)
    return w, w.load(data)["session_id"]


def gen(w, sid):
    return w.candidate_gen_of(sid)


def rr(r):
    return (r.get("state") or {}).get("repeat_range")


def cand(r):
    return (r.get("state") or {}).get("candidate")


def to_repeat_cand():
    w, sid = new()
    r = w.hear(sid, "3回にして")
    t = (rr(r) or {}).get("turn")
    r = w.repeat_choose(sid, "yes", t)
    assert cand(r), r.get("message")
    return w, sid


def to_shift_cand():
    w, sid = new(PLACE)
    w.select(sid, "C00003")
    r = w.hear(sid, "Zプラス方向に5mm")
    assert cand(r), r.get("message")
    return w, sid


# ---- A. 承認して保存（サーバーの側の順番と条件） ----
for kind, mk in [("回数", to_repeat_cand), ("位置", to_shift_cand)]:
    w, sid = mk()
    n0 = len(files())
    e = w.export(sid, candidate_gen=gen(w, sid))
    rec("A未承認", f"{kind}：承認の前の出力は断る", not e.get("ok") and len(files()) == n0, (e.get("error") or e.get("message") or "")[:80], True)
    a = w.approve(sid, "", candidate_gen=gen(w, sid))
    rec("A未承認", f"{kind}：名前なしの承認は断る", not a.get("ok"), (a.get("error") or "")[:60], True)
    a = w.approve(sid, "QA", candidate_gen=(gen(w, sid) or 0) + 1)
    rec("A古い", f"{kind}：違う世代での承認は断る", not a.get("ok"), (a.get("error") or "")[:60], True)
    a = w.approve(sid, "QA", candidate_gen=gen(w, sid))
    a2 = w.approve(sid, "QA", candidate_gen=gen(w, sid))
    rec("A二重", f"{kind}：承認を2回押しても状態が壊れない", a.get("ok") and (a2.get("ok") or True) and w.state(sid)["state"]["can_export"],
        f"1回目={a.get('ok')}・2回目={a2.get('ok')}（{(a2.get('error') or '')[:50]}）")
    e1 = w.export(sid, candidate_gen=gen(w, sid))
    e2 = w.export(sid, candidate_gen=gen(w, sid))
    rec("A二重", f"{kind}：同じ承認で出力は1回だけ（2回目は断る・ファイルは1つ）", e1.get("ok") and not e2.get("ok") and len(files()) == n0 + 1,
        f"1回目={e1.get('ok')}・2回目={e2.get('ok')}（{(e2.get('error') or '')[:60]}）・ファイル {len(files()) - n0}")
    # .JBI の整合
    if e1.get("ok"):
        p = Path(e1["path"])
        data = p.read_bytes()
        b64ok = base64.b64decode(e1["content_b64"]) == data and hashlib.sha256(data).hexdigest() == e1["sha256"]
        rec("C整合", f"{kind}：返す中身（content_b64・sha256）が書いたファイルと同じ", b64ok, p.name, True)
        jn = "DEMO_BUTTON_REPEAT" if kind == "回数" else "DEMO_PLACE"
        rec("C整合", f"{kind}：ファイル名が <ジョブ名>_SIM_YYMMDDHHMM.JBI", bool(re.fullmatch(jn + r"_SIM_\d{10}\.JBI", p.name)), p.name)
        txt = data.decode("ascii", "replace")
        rec("C整合", f"{kind}：中の //NAME が <ジョブ名>_SIM", f"//NAME {jn}_SIM" in txt, re.search(r"//NAME [^\r\n]*", txt).group(0))
        orig = (REP if kind == "回数" else PLACE).decode("ascii").splitlines()
        new_l = txt.splitlines()
        import difflib
        d = [x for x in difflib.unified_diff(orig, new_l, lineterm="", n=0) if x[:1] in "+-" and not x.startswith(("+++", "---"))]
        if kind == "回数":
            ok = sorted(d) == sorted(["-//NAME DEMO_BUTTON_REPEAT", "+//NAME DEMO_BUTTON_REPEAT_SIM",
                                      "+MOVL C00001 V=150.0", "+MOVL C00002 V=30.0", "+MOVL C00003 V=150.0"])
        else:
            ok = len(d) == 4 and any(x.startswith("+C00003=") for x in d)
        rec("C整合", f"{kind}：元との違いは決まった行だけ", ok, " | ".join(d)[:200], True)
        rec("C整合", f"{kind}：改行（CRLF）と文字（ASCII）が元と同じ", (b"\r\n" in data) == (b"\r\n" in (REP if kind == "回数" else PLACE)) and data.isascii(), "")
    # 承認のあとに元に戻す → 古い世代で出力できない
    g = gen(w, sid)
    w.undo(sid)
    e3 = w.export(sid, candidate_gen=g)
    rec("A古い", f"{kind}：元に戻したあと、古い承認で出力できない", not e3.get("ok"), (e3.get("error") or "")[:60], True)
rec("C整合", "元の JOB のファイルは変わらない", hashlib.sha256(REP_P.read_bytes()).hexdigest() == REP_SHA and hashlib.sha256(PLACE_P.read_bytes()).hexdigest() == PLACE_SHA, "", True)

# 合成ジョブでない JOB は出力しない（//NAME を変えた写し）
real_like = PLACE.replace(b"//NAME DEMO_PLACE", b"//NAME CELL_A01")
w, sid = new(real_like)
w.select(sid, "C00003")
r = w.hear(sid, "Zプラス方向に5mm")
if cand(r):
    a = w.approve(sid, "QA", candidate_gen=gen(w, sid))
    e = w.export(sid, candidate_gen=gen(w, sid))
    rec("A未承認", "合成ジョブでない JOB：出力しない", not e.get("ok") and not w.state(sid)["state"]["can_export"], f"承認={a.get('ok')}・出力={e.get('ok')}（{(e.get('error') or '')[:60]}）", True)
else:
    rec("A未承認", "合成ジョブでない JOB：候補まで進まない（出力もしない）", True, (r.get("message") or "")[:80])

# ---- B. 否定・取り消し・保留のあと、古い承認で出力できない ----
for word in ["違う", "取り消して", "やっぱりやめて", "止めて", "今のなし", "まだ出さないで", "承認しない", "うーん", "ちょっと待って", "忘れて"]:
    for kind, mk in [("回数", to_repeat_cand), ("位置", to_shift_cand)]:
        w, sid = mk()
        g = gen(w, sid)
        w.approve(sid, "QA", candidate_gen=g)
        r = w.talk(sid, word)
        st = w.state(sid)["state"]
        e = w.export(sid, candidate_gen=g)
        e_now = w.export(sid, candidate_gen=gen(w, sid)) if gen(w, sid) is not None else {"ok": False}
        rec("B否定", f"{kind}：承認のあと「{word}」→ 出力できない", not e.get("ok") and not e_now.get("ok") and not st["can_export"],
            f"承認={bool(st['approval'])}・保留={st.get('hold')}・返事「{(r.get('message') or '')[:70]}」", True)

# 承認の前に否定 → 承認できない or 候補が消える／保留
for word in ["違う", "取り消して", "今のなし"]:
    w, sid = to_repeat_cand()
    g = gen(w, sid)
    w.talk(sid, word)
    a = w.approve(sid, "QA", candidate_gen=g)
    st = w.state(sid)["state"]
    rec("B否定", f"承認の前に「{word}」→ 古い世代で承認できない", not a.get("ok"), f"{(a.get('error') or '')[:60]}・候補={'あり' if st['candidate'] else 'なし'}・保留={st.get('hold')}", True)

# 承認のあとに新しい変更の指示 → 古い承認で出力できない
for kind, mk, word in [("回数", to_repeat_cand, "4回にして"), ("回数", to_repeat_cand, "Zプラス方向に5mm"), ("位置", to_shift_cand, "Zプラス方向に10mm"), ("位置", to_shift_cand, "3回にして")]:
    w, sid = mk()
    g = gen(w, sid)
    w.approve(sid, "QA", candidate_gen=g)
    r = w.talk(sid, word)
    e = w.export(sid, candidate_gen=g)
    st = w.state(sid)["state"]
    rec("B新指示", f"{kind}：承認のあと「{word}」→ 古い承認で出力できない", not e.get("ok") and not st["can_export"], f"返事「{(r.get('message') or '')[:80]}」", True)

# JOB の読み直し → 前のセッションで出力できない
w, sid = to_repeat_cand()
g = gen(w, sid)
w.approve(sid, "QA", candidate_gen=g)
sid2 = w.load(REP, previous=sid)["session_id"]
e = w.export(sid, candidate_gen=g)
e2 = w.export(sid2, candidate_gen=g)
rec("B読み直し", "JOB の読み直しのあと、前の承認で出力できない", not e.get("ok") and not e2.get("ok"), f"古い sid={e.get('ok')}・新しい sid={e2.get('ok')}", True)

# ---- D. 繰り返しの範囲の案内（R1〜R8） ----
def guide(text, data=REP, via="talk"):
    w, sid = new(data)
    r = getattr(w, via)(sid, text)
    if via == "talk":  # talk は道ごとの答えを包む（hear・ask）。画面に出る答えを取り出す
        inner = r.get("hear") or r.get("ask") or {}
        r = {**inner, "state": inner.get("state") or w.state(sid)["state"]}
    return w, sid, r


cases = ["C1C4を2回繰り返したい", "C00001からC00004を2回繰り返したい", "C1からC4を3回にして", "C2からC3を3回にして", "C1とC4の動きを3回にして",
         "C00001を3回にして", "2回繰り返したい", "繰り返したい", "繰り返して", "もう1回", "回数を変えたい", "反復を増やして", "リピートして",
         "2回にして", "2回から2回にして", "3回から4回にして", "4回にして", "5回繰り返して", "3回くらいにして", "2.5回にして", "繰り返さないで",
         "3回にして", "C1からC3を3回にして"]
for via in ["talk", "hear"]:
    for t in cases:
        w, sid, r = guide(t, via=via)
        msg = r.get("message") or ""
        ch = [c.get("label") for c in (r.get("choices") or []) if isinstance(c, dict)]
        g = r.get("repeat_guide") or {}
        ranges = g.get("ranges")
        no_cand = not r.get("candidate_made") and not cand(r)
        rec("D範囲", f"[{via}]「{t}」：候補を作らない", no_cand, f"案内={ranges}・選択肢={ch}・範囲の確認={(rr(r) or {}).get('target')}・文「{msg[:110]}」", True)
        if ranges is not None:
            rec("D範囲", f"[{via}]「{t}」：案内の範囲は JOB の区間だけ（C00001〜C00003）", ranges in ([], [["C00001", "C00003"]]), str(ranges), True)
            if re.search(r"C0*4|C00004|C0*2から|C2から", t):
                rec("D範囲", f"[{via}]「{t}」：違いを説明する", "違" in msg, msg[:120])
            if re.search(r"[0-9]回", t) and not re.search(r"3回", t):
                rec("D範囲", f"[{via}]「{t}」：言った回数を 2→3 と決めつけない", "決めません" in msg or "どちら" in msg, msg[:120])
            if len(ch) > 3:
                rec("D範囲", f"[{via}]「{t}」：選択肢は対応範囲＋変更しないだけ", False, str(ch))

# 区間の無い JOB
for t in ["3回にして", "繰り返したい", "2回繰り返したい"]:
    w, sid, r = guide(t, PLACE, via="talk")
    msg = r.get("message") or ""
    rec("D範囲", f"[DEMO_PLACE]「{t}」：使えない範囲（C00001〜C00003 の例）を出さない", "C00001からC00003" not in msg and "C00001〜C00003" not in msg and not cand(r),
        f"案内={(r.get('repeat_guide') or {}).get('ranges')}・文「{msg[:140]}」", True)

# 案内カードの選択 → 範囲の確認（ボタン）→ 候補。選ぶだけでは候補・承認にならない
w, sid, r = guide("C1C4を2回繰り返したい", via="talk")
choices = r.get("choices") or []
pick = next((c for c in choices if isinstance(c, dict) and "3回" in c.get("label", "")), None)
if pick:
    r2 = w.hear(sid, pick["text"])
    rec("D範囲", "案内の［C00001〜C00003 を3回にする］→ 範囲の確認だけ（候補・承認なし）", not cand(r2) and rr(r2) and not r2["state"]["approval"],
        f"範囲の確認={(rr(r2) or {}).get('target')}")
    t = (rr(r2) or {}).get("turn")
    r3 = w.repeat_choose(sid, "yes", t)
    st = r3["state"]
    rec("D範囲", "範囲の確認のボタン → 候補は C00001〜C00003・承認なし・出力できない",
        st["candidate"] and "C00001" in json.dumps(st["candidate"], ensure_ascii=False) and not st["approval"] and not st["can_export"], str(st["candidate"].get("target") if st["candidate"] else None), True)
    r4 = w.repeat_choose(sid, "yes", t)
    rec("D二重", "範囲の確認のボタンを2回押しても候補は1つ（世代が増えない／2回目は使えない）", gen(w, sid) == st["candidate_gen"], f"2回目「{(r4.get('message') or '')[:70]}」")
    nochoice = next((c for c in choices if isinstance(c, dict) and "変更しない" in c.get("label", "")), None)
    if nochoice:
        w, sid, r = guide("C1C4を2回繰り返したい", via="talk")
        r5 = w.hear(sid, nochoice["text"])
        rec("D範囲", "［今回は変更しない］→ 候補・範囲の確認なし", not cand(r5) and not rr(r5), f"文「{(r5.get('message') or '')[:80]}」")
else:
    rec("D範囲", "案内カードに範囲を選ぶボタンがある", False, str(choices))

# 案内のあと JOB を読み直して、古いカードの文を送る → 新しい JOB でも範囲の確認止まり（候補にならない）
w, sid, r = guide("C1C4を2回繰り返したい", via="talk")
pick = next((c for c in (r.get("choices") or []) if isinstance(c, dict) and "3回" in c.get("label", "")), None)
sid2 = w.load(PLACE, previous=sid)["session_id"]
if pick:
    r6 = w.hear(sid2, pick["text"])
    rec("D古い", "案内のあと別の JOB を読んで古いカードを押す → 候補を作らない", not cand(r6), f"文「{(r6.get('message') or '')[:100]}」", True)
    r7 = w.hear(sid, pick["text"])
    rec("D古い", "読み直す前のセッションに古いカードを送る → 使えない", not r7.get("ok") or not cand(r7), f"ok={r7.get('ok')}")

# 範囲の確認を「はい」で決めない（R8）
for word in ["はい", "それで", "この範囲を繰り返す"]:
    w, sid = new()
    w.hear(sid, "3回にして")
    r = w.talk(sid, word)
    r = {**(r.get("hear") or r.get("ask") or r), "state": w.state(sid)["state"]}
    rec("D範囲", f"範囲の確認を声・文字の「{word}」で決めない", not cand(r), f"文「{(r.get('message') or '')[:80]}」", True)

# 範囲の確認のあと否定・取消・位置の選び直し → 古い turn で候補を作らない（R7）
for label, act in [("否定", lambda w, s: w.talk(s, "違う")), ("取り消し", lambda w, s: w.talk(s, "取り消して")),
                   ("選び直し", lambda w, s: w.select(s, "C00002")), ("元に戻す", lambda w, s: w.undo(s)),
                   ("別の範囲の発話", lambda w, s: w.talk(s, "C1からC4を3回にして"))]:
    w, sid = new()
    r = w.hear(sid, "3回にして")
    t = (rr(r) or {}).get("turn")
    act(w, sid)
    r2 = w.repeat_choose(sid, "yes", t)
    rec("D古い", f"範囲の確認のあと{label} → 古い確認で候補を作らない", not r2.get("candidate_made") and not cand(r2), f"文「{(r2.get('message') or '')[:70]}」", True)

sev = [r for r in res if not r["pass"] and r["severe_if_fail"]]
print(json.dumps({"pass": sum(r["pass"] for r in res), "total": len(res), "severe_fail": len(sev)}, ensure_ascii=False))
Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False, indent=1))
