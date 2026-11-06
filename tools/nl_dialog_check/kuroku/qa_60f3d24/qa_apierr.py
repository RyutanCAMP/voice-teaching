"""Claude の失敗（時間切れ・混雑・認証・形の違う答え・例外）で、候補・承認が変にならないか（モック・API 0回）。"""
import sys, tempfile
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import httpx2 as httpx, anthropic
import test_claude_talk as T
from voice_teaching import sim
from voice_teaching import claude_explain as cx
from voice_teaching.web.flow import WebFlow
from voice_teaching.claude_interpreter import MockInterpreter
RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes(); BR = (ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI").read_bytes()
req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
def resp(code): return httpx.Response(code, request=req)
ERRS = {"timeout": anthropic.APITimeoutError(request=req), "conn": anthropic.APIConnectionError(request=req),
        "429": anthropic.RateLimitError("rate", response=resp(429), body=None), "529": anthropic.InternalServerError("over", response=resp(529), body=None),
        "401": anthropic.AuthenticationError("auth", response=resp(401), body=None), "runtime": RuntimeError("boom"),
        "notool": SimpleNamespace(stop_reason="end_turn", usage=T.usage(), content=[SimpleNamespace(type="text", text="5ミリでいいです")]),
        "badjson": T.answer("", (), intent="explain", change={"axis": "Z", "mm": 50}),
        "numbers": T.answer("Z を 30mm 上げると 210mm になります", (27,)), "maxtok": SimpleNamespace(stop_reason="max_tokens", usage=T.usage(), content=[])}
class C:
    def __init__(s, x): s.x = x; s.messages = s
    def create(s, **kw):
        if isinstance(s.x, Exception): raise s.x
        return s.x
for name, x in ERRS.items():
    for job, steps in (("RJ", ["@sel C00004", "この位置は何？"]), ("BR", ["2回から3回にして"]), ("RJ", ["@sel C00004", "Zプラス方向に5ミリ", "@approve", "これ何？"])):
        with tempfile.TemporaryDirectory() as d:
            sim.DEFAULT_OUT_DIR = Path(d) / "o"
            ex = cx.Explainer(T.KEY, T.MODEL, client=C(x), usage_log=cx.UsageLog(Path(d) / "u.jsonl"))
            w = WebFlow(interpreter=MockInterpreter(), explainer=ex)
            sid = w.load(RJ if job == "RJ" else BR)["session_id"]; r = {}
            try:
                for s in steps:
                    if s.startswith("@sel"): w.select(sid, s[5:])
                    elif s == "@approve": w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid))
                    else: r = w.talk(sid, s, "voice")
                st = w.state(sid)["state"]; c = st.get("candidate")
                a = r.get("ask") or {}
                print(name, job, steps[-1], "| cand", (c or {}).get("delta"), "| appr", bool(st.get("approval")), "can_export", st.get("can_export"),
                      "| range", bool(st.get("repeat_range")), "|", (a.get("error") or a.get("reply") or (r.get("hear") or {}).get("message") or r.get("error") or "")[:90])
            except Exception as e:
                print(name, job, steps[-1], "CRASH", repr(e)[:150])
