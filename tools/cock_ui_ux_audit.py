"""Repeatable UI-only Chrome audit. Uses existing synthetic JOBs and mock clients.

No .env, real microphone, paid API, shared server, or robot connection is used.
Run: python tools/cock_ui_ux_audit.py --out docs/ui-ux-1106/before
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import demo_mock
import e2e_browser as existing
from playwright.sync_api import sync_playwright
from voice_teaching import claude_explain as cx, sim
from voice_teaching.claude_interpreter import MockInterpreter
from voice_teaching.web import server

SIZES = [(1920, 1080), (1440, 900), (1280, 720)]

class AuditClient(demo_mock.ScriptClient):
    """Reuse the existing short answer and long-answer fixture; no network."""
    def create(self, **kwargs):
        response = super().create(**kwargs)
        questions = [t.get("question", "") for m in kwargs.get("messages", []) for t in demo_mock._texts(m)]
        if any("詳しく" in q for q in questions) and response.content[0].input.get("intent") == "explain":
            response.content[0].input["reply"] += existing.LONG_TAIL
        return response
MEASURE = """() => {
 const rect = e => { const r=e.getBoundingClientRect(), s=getComputedStyle(e);
   return {x:r.x,y:r.y,width:r.width,height:r.height,fontSize:parseFloat(s.fontSize),
     lineHeight:s.lineHeight,overflowY:s.overflowY,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight}; };
 const selectors=['.top','.side','#side-scroll','#fig-3d','.cand-pop','#candidate-panel',
   '#candidate-view .cand-change','#text-input','#text-send','#mic-button','#kbd-button',
   '#next-action','#reply-message','#open-confirm','#export-button','#approval-status',
   '#approve-button','#confirm-overlay .confirm-body','#play-button','#reset-front'];
 const boxes={};
 for (const sel of selectors) { const e=document.querySelector(sel);
   if(e && e.checkVisibility()) boxes[sel]=rect(e); }
 const small=[...document.querySelectorAll('button')].filter(e=>e.checkVisibility() && !e.matches('.tip,.link'))
   .filter(e=>e.getBoundingClientRect().height<43.5).map(e=>({id:e.id,text:e.textContent.trim(),...rect(e)}));
 const unread=[...document.querySelectorAll('.bubble .said')].filter(e=>e.checkVisibility())
   .map(e=>({fontSize:parseFloat(getComputedStyle(e).fontSize),text:e.textContent.length}));
 return {viewport:[innerWidth,innerHeight],document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
   boxes,smallButtons:small,bubbleText:unread};
}"""


def run(out: Path, headed: bool = False) -> int:
    out.mkdir(parents=True, exist_ok=True)
    data = {"base_sha": "60f3d2469fe125da3913e950b74f9974d95055f5",
            "tested_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "api_calls": 0, "mode": "mock + fake SpeechRecognition; Chrome", "checks": [], "screens": [], "errors": []}
    def check(ok, name):
        data["checks"].append({"pass": bool(ok), "name": name})
        print(("PASS " if ok else "FAIL ") + name, flush=True)
    def capture(pg, size, name):
        pg.wait_for_timeout(450)
        path = out / f"{size[0]}x{size[1]}_{name}.png"
        pg.screenshot(path=str(path), animations="disabled")
        m = pg.evaluate(MEASURE)
        data["screens"].append({"name": name, "size": size, "path": path.name, "metrics": m})
        check(m["document"][0] <= size[0], f"{size} {name}: no horizontal page overflow")
    def send(pg, text):
        existing.fill_text(pg, text)
        pg.click("#text-send")
        existing.until(pg, lambda: pg.is_enabled("#text-send"))
    def page_for(browser, size, url):
        ctx=browser.new_context(viewport={"width": size[0], "height": size[1]}, reduced_motion="reduce")
        ctx.add_init_script(existing.FAKE_RECOGNITION)
        # Browser traffic is limited to the audit's local HTTP server.
        ctx.route("**/*", lambda route: route.continue_() if route.request.url.startswith("http://127.0.0.1:") else route.abort())
        pg=ctx.new_page()
        pg.on("pageerror", lambda e:data["errors"].append(str(e)))
        pg.goto(url)
        return ctx,pg
    with tempfile.TemporaryDirectory(prefix="cock-ux-") as tmp:
        old_out=sim.DEFAULT_OUT_DIR
        sim.DEFAULT_OUT_DIR=Path(tmp)/"sim"
        cx.PRICES[demo_mock.MOCK_MODEL]=cx.Price(0,0,0,0,0)
        ex=cx.Explainer("mock-no-network", demo_mock.MOCK_MODEL, client=AuditClient(),
                        usage_log=cx.UsageLog(Path(tmp)/"usage.jsonl"))
        srv=server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None, explainer=ex, channel="dev")
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        url=f"http://127.0.0.1:{srv.server_address[1]}/"
        try:
            with sync_playwright() as p:
                b=p.chromium.launch(channel="chrome",headless=not headed)
                data["browser_version"]=b.version
                for size in SIZES:
                    # Each viewport gets a fresh output folder: SIM intentionally refuses overwriting.
                    sim.DEFAULT_OUT_DIR=Path(tmp)/f"sim-{size[0]}"
                    ctx,pg=page_for(b,size,url)
                    capture(pg,size,"initial")
                    pg.click("#sample-button")
                    pg.wait_for_selector("#job-area:not([hidden])")
                    capture(pg,size,"loaded")
                    check(pg.locator("#kbd-button").bounding_box()["height"]>=44, f"{size}: keyboard touch target >=44px")
                    pg.locator("#position-chips button",has_text="C00003").click()
                    pg.click("#mic-button")
                    pg.wait_for_selector("#voice-consent:not([hidden])")
                    capture(pg,size,"voice_consent")
                    pg.click("#consent-yes")
                    pg.wait_for_selector("#voice-stop:enabled")
                    capture(pg,size,"listening_double")
                    pg.click("#voice-cancel")
                    pg.locator('.tip[data-tip="mic"]').hover()
                    pg.wait_for_timeout(250)
                    try:
                        pg.click("#kbd-button", timeout=2000)
                        check(True,f"{size}: keyboard entry reachable with mic tooltip open")
                    except Exception:
                        check(False,f"{size}: keyboard entry reachable with mic tooltip open")
                        capture(pg,size,"tooltip_blocked")
                    pg.keyboard.press("Escape")
                    pg.locator('.tip[data-tip="mic"]').click()
                    pg.click("#tip-pop .tip-close")
                    check(pg.is_hidden("#tip-pop"),f"{size}: tooltip close button remains usable")
                    send(pg,"Zプラス方向に30mm")
                    capture(pg,size,"rejected")
                    check(not pg.is_enabled("#open-confirm"),f"{size}: rejected move cannot be confirmed")
                    send(pg,"Zプラス方向に5mm")
                    pg.wait_for_selector("#open-confirm:enabled")
                    if pg.is_enabled("#play-stop"):
                        pg.click("#play-stop")
                    capture(pg,size,"candidate")
                    box=pg.locator("#fig-3d").bounding_box()
                    check(box["height"]>=300,f"{size}: 3D height >= 300px")
                    pg.click("#open-confirm")
                    pg.wait_for_selector("#confirm-overlay:not([hidden])")
                    capture(pg,size,"confirm")
                    pg.click("#approve-button")
                    check(pg.is_visible("#confirm-error") and pg.is_visible("#confirm-overlay") and pg.is_hidden("#approval-status"),
                          f"{size}: empty name does not approve; recovery message visible")
                    pg.fill("#approver-name","UI QA")
                    pg.click("#approve-button")
                    pg.wait_for_selector("#approval-status:not([hidden])")
                    capture(pg,size,"approved")
                    pg.click("#export-button")
                    pg.wait_for_selector("#export-result:not([hidden])")
                    check("出力しました" in pg.inner_text("#export-result"),f"{size}: synthetic SIM export succeeds")
                    capture(pg,size,"exported")
                    send(pg,"今の提案は取り消して")
                    capture(pg,size,"hold")
                    check(not pg.is_enabled("#export-button"),f"{size}: held/cancelled candidate cannot export")
                    ctx.close()

                    ctx,pg=page_for(b,size,url)
                    pg.set_input_files("#file-input",str(ROOT/"samples/dummy/DEMO_BUTTON_REPEAT.JBI"))
                    pg.wait_for_selector("#job-area:not([hidden])")
                    send(pg,"このロボット、何してる？")
                    pg.wait_for_selector("#ask-turns .bubble.claude:not(.thinking)")
                    capture(pg,size,"conversation")
                    send(pg,"詳しく説明して")
                    capture(pg,size,"long_conversation")
                    for _ in range(3):
                        send(pg,"どんな動き？")
                    capture(pg,size,"conversation_history")
                    send(pg,"じゃあ3回にして")
                    capture(pg,size,"range_question")
                    check(pg.is_visible("#reply-message"),f"{size}: range confirmation is displayed")
                    if pg.locator(".range-go").count():
                        pg.locator(".range-go").first.click()
                        pg.wait_for_selector("#open-confirm:enabled")
                        if pg.is_enabled("#play-stop"):
                            pg.click("#play-stop")
                        capture(pg,size,"repeat_candidate")
                        check(pg.is_visible("#play-compare"),f"{size}: before/after playback available")
                    ctx.close()
                check(not data["errors"],"no browser JavaScript errors")
                b.close()
        except Exception as err:
            data["execution_error"] = f"{type(err).__name__}: {err}"
            print(data["execution_error"],flush=True)
        finally:
            srv.shutdown();srv.server_close();sim.DEFAULT_OUT_DIR=old_out
    data["pass"]=sum(c["pass"] for c in data["checks"])
    data["fail"]=sum(not c["pass"] for c in data["checks"])
    (out/"audit.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:data.get(k) for k in ["pass","fail","execution_error","browser_version"]}),flush=True)
    return int(bool(data["fail"] or data.get("execution_error")))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--headed",action="store_true")
    args=parser.parse_args()
    raise SystemExit(run(args.out,args.headed))
