import sys, json, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
CP = (ROOT / "samples/dummy/DEMO_C_PLACE.JBI").read_bytes()
EXP = [T.answer("この位置へ動く動作です。", (21,22,23,24,25,26)) for _ in range(4)]
def choices(r):
    for k in ("hear", "ask", None):
        x = r.get(k) if k else r
        if isinstance(x, dict) and x.get("choices"):
            return x["choices"]
    return []
def run(name, steps):
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d) / "out"
        w, f = T.flow(Path(d), *EXP)
        sid = w.load(CP)["session_id"]; w.select(sid, "C00003")
        btn = None; out = []
        for k, v in steps:
            if k == "talk": r = w.talk(sid, v)
            elif k == "hear": r = w.hear(sid, v, "text")
            elif k == "ask": r = w.ask(sid, v)
            elif k == "press": r = w.hear(sid, btn, "text")
            elif k == "press_talk": r = w.talk(sid, btn)
            if btn is None:
                for c in choices(r):
                    t = c.get("text") if isinstance(c, dict) else (c[1] if isinstance(c, (list, tuple)) else c)
                    if t and "向きの確かめ：合っている" in t: btn = t
            st = w.state(sid)["state"]; cd = st.get("candidate")
            msg = (r.get("message") or (r.get("hear") or {}).get("message") or (r.get("ask") or {}).get("reply") or "")
            out.append(f"{k}:{v or ''} -> cand={cd and cd.get('summary') or (cd and cd.get('target'))} appr={st.get('can_approve')} | {msg[:90]}")
        print("==", name, "(button found)" if btn else "(NO BUTTON)"); print("\n".join("   " + o for o in out))
run("F1 基本：右に10mm→押す", [("talk","右に10mm"),("press",None)])
run("F2 talk の新しい発話のあと押す", [("talk","右に10mm"),("talk","Zプラス"),("press",None)])
run("F3 /api/hear に新しい発話（Zプラス）のあと押す", [("talk","右に10mm"),("hear","Zプラス"),("press",None)])
run("F4 /api/hear に「3回にして」のあと押す", [("talk","右に10mm"),("hear","3回にして"),("press",None)])
run("F5 /api/ask に質問のあと押す", [("talk","右に10mm"),("ask","この位置は何？"),("press",None)])
run("F6 /api/hear に別の指示（Yマイナス10mm）→候補→元に戻すなし→押す", [("talk","右に10mm"),("hear","Zプラス5ミリ"),("press",None)])
run("F7 ボタンの文を talk で送る", [("talk","右に10mm"),("press_talk",None)])
