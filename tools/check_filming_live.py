"""Opt-in real Claude + Chrome UI QA. Uses synthetic JOBs, never copies .env.

python tools/check_filming_live.py --env-file PATH --call --out output/live-filming-ui
Real microphone audio is NOT tested. --fake-recognition tests the existing voice
UI with a transcript double and real Claude; it never represents audio accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from voice_teaching import claude_explain as cx, claude_interpreter as ci
from voice_teaching.web.server import make_server
from tools.e2e_browser import FAKE_RECOGNITION


def conversation_checks(cases):
    """Delivery check only; semantic accuracy still needs independent judgement."""
    checks = []
    for row in cases:
        if not row.get("api_call_ids"):
            continue
        answers = [h["ask"] for h in row.get("http", []) if h.get("ask")]
        if answers:
            a = answers[-1]
            checks.append(dict(name=row["id"]+": requested explanation delivered as Claude text",
                               passed=a.get("ok") is True and a.get("reply_by")=="claude",
                               detail=a.get("reply") or a.get("error")))
    return checks


class Recorder:
    def __init__(self, key, out):
        import anthropic
        self.messages = self
        self.out, self.calls, self.attempts = out, [], []
        self.case, self.inject = "setup", None
        def request(req):
            self.attempts.append(dict(case=self.case, method=req.method, path=req.url.path))
        def response(res):
            self.attempts[-1]["status_code"] = res.status_code
        self.http_client = anthropic.DefaultHttpxClient(timeout=ci.TIMEOUT_SECONDS,
                                                       event_hooks={"request": [request], "response": [response]})
        self.sdk = anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com",
                                      timeout=ci.TIMEOUT_SECONDS, max_retries=ci.MAX_RETRIES,
                                      http_client=self.http_client)

    def create(self, **kw):
        import anthropic
        if self.inject == "timeout":
            raise anthropic.APITimeoutError(request=self.http_client.build_request("POST", "https://api.anthropic.com/v1/messages"))
        if len(self.calls) >= 32:
            raise RuntimeError("QA API call cap reached")
        row = dict(id=len(self.calls)+1, case=self.case, model=kw.get("model"))
        self.calls.append(row)
        start = time.perf_counter()
        try:
            result = self.sdk.messages.create(**kw)
            row.update(ok=True, stop_reason=result.stop_reason,
                       usage=result.usage.model_dump(), response_model=result.model,
                       # Never save thinking/signature blocks or any HTTP headers.
                       answers=[dict(type=b.type, name=getattr(b, "name", None), input=getattr(b, "input", None),
                                     text=getattr(b, "text", None)) for b in result.content if b.type in ("tool_use", "text")])
            return result
        except Exception as ex:
            row.update(ok=False, error_type=type(ex).__name__, status_code=getattr(ex, "status_code", None))
            raise
        finally:
            row["seconds"] = round(time.perf_counter()-start, 4)
            self.save()

    def save(self):
        (self.out / "api_calls.json").write_text(json.dumps(dict(calls=self.calls, transport_attempts=self.attempts),
                                                          ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def run(args):
    import anthropic
    from playwright.sync_api import sync_playwright
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    cfg = {k: os.environ[k] for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL") if os.environ.get(k)}
    ci.load_dotenv(args.env_file, env=cfg)
    key, model = cfg.get("ANTHROPIC_API_KEY", ""), cfg.get("ANTHROPIC_MODEL") or cx.DEFAULT_MODEL
    if not ci.key_is_usable(key):
        raise SystemExit("Usable key unavailable; no API call made")
    if model != "claude-sonnet-5-5":
        raise SystemExit("Expected claude-sonnet-5-5; no model substitution")
    rec = Recorder(key, out)
    srv = make_server(port=0, interpreter=ci.ClaudeInterpreter(key, model, client=rec), updown_config=None,
                      explainer=cx.Explainer(key, model, client=rec, usage_log=cx.UsageLog(out / "app_usage.jsonl")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    cases, checks, errors = [], [], []
    active = {}

    def check(name, passed, detail=None):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))

    def snapshot(page):
        def txt(sel):
            return page.locator(sel).inner_text() if page.locator(sel).count() else ""
        return dict(next=txt("#next-action"), reply=txt("#reply-message"), conversation=txt("#ask-turns"),
                    candidate=txt("#candidate-view"), xyz=page.locator("#candidate-view .xyz td").all_text_contents(),
                    status=page.locator("#status-line").text_content(),
                    can_open_review=page.locator("#open-confirm").is_enabled(),
                    mic_visible=page.locator("#mic-button").is_visible())

    def observe_response(response):
        if response.request.method == "POST" and response.url.startswith(url):
            try:
                data = response.json()
                # Request/response bodies contain only this synthetic test JOB.
                # Session IDs and output paths are unnecessary for published evidence.
                active.setdefault("http", []).append(dict(path=response.url.split("/")[-1], status=response.status,
                    ask=data.get("ask"), hear=data.get("hear"), error=data.get("error"), ok=data.get("ok")))
            except Exception:
                pass

    def page_new(browser, fake=False):
        page = browser.new_page(viewport=dict(width=1920, height=1080), reduced_motion="no-preference")
        page.set_default_timeout(15000)
        if fake:
            page.add_init_script(FAKE_RECOGNITION)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", observe_response)
        page.goto(url)
        if page.locator("#opening").is_visible():
            page.screenshot(path=str(out / "01-opening.png"))
            page.locator("#opening").wait_for(state="hidden", timeout=12000)
        return page

    def load(page):
        page.set_input_files("#file-input", str(ROOT / "samples/dummy/DEMO_C_PLACE.JBI"))
        page.locator("#file-name", has_text="DEMO_C_PLACE.JBI").wait_for(state="visible")
        page.wait_for_function("() => !document.querySelector('#text-send').disabled")

    def send(page, cid, text, label="live_configuration", from_voice=False):
        nonlocal active
        rec.case = cid
        active = dict(id=cid, input=text, condition=label, api_start=len(rec.calls), http=[])
        cases.append(active)
        start = time.perf_counter()
        if not page.locator("#text-input").is_visible():
            page.locator("#kbd-button").click()
        page.locator("#text-input").fill(text)
        with page.expect_response("**/api/talk", timeout=90000) as pending:
            page.locator("#text-send").click()
            page.wait_for_timeout(150)
            active["waiting"] = dict(thinking=page.locator(".thinking").count()>0,
                                      send_disabled=page.locator("#text-send").is_disabled(),
                                      load_disabled=page.locator("#file-input").is_disabled(),
                                      heading=page.locator("#next-action").inner_text())
            if active["waiting"]["thinking"]:
                page.screenshot(path=str(out / (cid+"-waiting.png")))
        pending.value.finished()
        page.wait_for_timeout(150)
        active.update(seconds=round(time.perf_counter()-start, 4), api_call_ids=[x["id"] for x in rec.calls[active["api_start"]:]],
                      ui=snapshot(page), from_voice_transcript_double=from_voice)
        page.screenshot(path=str(out / (cid+"-result.png")))
        return active

    def group(name, operation):
        try:
            operation()
        except Exception as ex:
            # Playwright errors are from the test page, not SDK/raw HTTP errors.
            errors.append(name+": "+str(ex))
            check(name+" completed", False, str(ex))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=not args.headed)
            chrome = browser.version
            def filming():
                page = page_new(browser)
                page.screenshot(path=str(out / "02-start.png"))
                check("initial UI visible", page.locator("#sample-button").is_visible())
                load(page)
                page.screenshot(path=str(out / "03-loaded.png"))
                check("3D loaded", page.locator("#fig-3d svg").is_visible())
                check("mic displayed with real browser API", page.locator("#mic-button").is_visible() and page.locator("#mic-button").is_enabled())
                row = send(page, "F30", "C00005、Zプラス方向に30ミリ")
                check("30mm rejected without candidate", not row["ui"]["can_open_review"] and not row["ui"]["xyz"], row["ui"]["reply"])
                check("30mm stop reason visible", bool(row["ui"]["reply"]) and page.locator("#reply-message").is_visible())
                row = send(page, "F05", "C00005、Zプラス方向に5ミリ")
                check("5mm exact target/XYZ", row["ui"]["xyz"] == ["400.000", "150.000", "200.000", "400.000", "150.000", "205.000"], row["ui"]["xyz"])
                check("5mm candidate review reachable", row["ui"]["can_open_review"])
                if row["ui"]["can_open_review"]:
                    page.locator("#open-confirm").click()
                    page.locator("#confirm-overlay:not([hidden])").wait_for(state="visible")
                    page.screenshot(path=str(out / "04-human-review.png"))
                    check("review warnings visible", page.locator("#confirm-warnings").is_visible())
                    check("review exact changed Z", "205.000" in page.locator("#confirm-xyz").inner_text())
                    page.locator("#approver-name").fill("UI試験")
                    page.locator("#approve-button").click()
                    page.locator("#confirm-overlay").wait_for(state="hidden")
                    check("human approval reflected", page.locator("#approval-status").is_visible())
                    target = ROOT / "output/sim/DEMO_C_PLACE_SIM.JBI.txt"
                    if target.exists():
                        check("output scene not overwritten", False, "Existing simulation output; export not attempted")
                    else:
                        page.locator("#export-button").click()
                        page.locator("#export-result:not([hidden])").wait_for(state="visible")
                        check("synthetic simulation export created", target.is_file())
                        page.screenshot(path=str(out / "05-export.png"))
                        if target.is_file():
                            (out / "export-proof.json").write_text(json.dumps(dict(filename=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                                                                size=target.stat().st_size),indent=2)+"\n",encoding="utf-8")
                page.close()
            group("filming scenario", filming)

            def conversation():
                page = page_new(browser, fake=args.fake_recognition)
                load(page)
                if args.fake_recognition:
                    page.locator("#mic-button").click()
                    page.locator("#consent-yes").click()
                    page.locator("#voice-stop:not([disabled])").wait_for(state="visible")
                    page.evaluate("window.__fakeText='このロボット、何してる？'")
                    count = len(rec.calls)
                    page.locator("#voice-stop").click()
                    page.wait_for_function("() => document.querySelector('#text-input').value === 'このロボット、何してる？'")
                    check("recognition double fills input without API/auto-send", len(rec.calls)==count)
                prompts = ["このロボット、何してる？", "一言で説明して", "初めて見る人に、動きの流れをできるだけ詳しく説明して", "何回繰り返している？", "どこからどこまで動く？", "今の説明を短くまとめて"]
                for index, text in enumerate(prompts, 1):
                    row = send(page, f"C{index}", text, from_voice=(index==1 and args.fake_recognition))
                    last = page.locator("#ask-turns .bubble").last
                    check(f"C{index}: response text displayed", last.is_visible() and bool(last.inner_text().strip()))
                    if row["api_call_ids"]:
                        check(f"C{index}: waiting locks visible", row["waiting"]["send_disabled"] and row["waiting"]["load_disabled"])
                    # Compare the processed application answer to the actually rendered text.
                    asks = [x["ask"] for x in row["http"] if x.get("ask")]
                    if asks:
                        ask = asks[-1]
                        row["app_answer"] = {k:ask.get(k) for k in ("ok","status","reply","reply_by","error","model","hidden_reason")}
                        if ask.get("reply"):
                            check(f"C{index}: application reply preserved", ask["reply"] in page.locator("#ask-turns").inner_text())
                    check(f"C{index}: no horizontal page clipping", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                row = send(page, "C7-limit", "ありがとう")
                check("conversation limit shown without new API", not row["api_call_ids"] and bool(row["ui"]["conversation"]))
                area = page.locator("#side-scroll")
                row["scroll"] = area.evaluate("e => ({height:e.clientHeight,content:e.scrollHeight,top:e.scrollTop})")
                check("conversation scroll available", row["scroll"]["content"] > row["scroll"]["height"])
                area.hover()
                page.mouse.wheel(0,-800)
                page.screenshot(path=str(out / "06-conversation-history.png"))
                page.locator("#play-button").click()
                page.wait_for_timeout(500)
                check("3D plays alongside conversation", page.locator("#play-now").is_visible())
                page.locator("#play-stop").click()
                page.locator("#fig-3d").hover()
                page.mouse.wheel(0,-200)
                page.locator("#view-reset").wait_for(state="visible")
                page.locator("#view-reset").click()
                check("3D view controls alongside conversation", True)
                page.close()
            group("conversation", conversation)

            def ambiguous():
                page = page_new(browser)
                load(page)
                for cid, text in [("D1", "C00005を5ミリ動かして"),("D2", "右へ5ミリ"),("D3", "このロボットは何をしているの？")]:
                    row = send(page,cid,text)
                    check(cid+": no silent approval", not page.locator("#confirm-overlay").is_visible())
                    if cid != "D3":
                        check(cid+": no definite candidate for unknown direction", not row["ui"]["xyz"])
                        check(cid+": question visible", bool(row["ui"]["reply"] or row["ui"]["conversation"]))
                page.close()
            group("ambiguous input", ambiguous)

            def faults():
                page = page_new(browser)
                load(page)
                rec.inject = "timeout"
                try:
                    row = send(page,"E-timeout","このロボット、何してる？",label="SDK_TIMEOUT_INJECTED_NO_PROVIDER_CALL")
                    check("timeout error visible", "時間切れ" in row["ui"]["conversation"] or "ネットワーク" in row["ui"]["conversation"], row["ui"]["conversation"])
                finally:
                    rec.inject = None
                page.route("**/api/talk", lambda route: route.abort("connectionfailed"))
                if not page.locator("#text-input").is_visible():page.locator("#kbd-button").click()
                page.locator("#text-input").fill("何してる？")
                page.locator("#text-send").click()
                page.wait_for_timeout(800)
                check("browser connection error visible", "つながりません" in page.locator("#ask-turns").inner_text())
                page.screenshot(path=str(out / "07-network-error.png"))
                page.close()
            group("injected error UI", faults)
            browser.close()
    finally:
        srv.shutdown();srv.server_close();rec.sdk.close();rec.save()
        checks.extend(conversation_checks(cases))
        successful = [c for c in rec.calls if c.get("ok")]
        token_totals = {k:sum(c.get("usage",{}).get(k,0) or 0 for c in successful) for k in
                        ("input_tokens","output_tokens","cache_creation_input_tokens","cache_read_input_tokens")}
        # Official Sonnet 5.5 prices checked 2026-11-05. The application's older
        # cache-read estimate is left unchanged; do not change its budget guard.
        cost = (token_totals["input_tokens"]*2 + token_totals["output_tokens"]*10 +
                token_totals["cache_creation_input_tokens"]*2.5 + token_totals["cache_read_input_tokens"]*.1)/1e6
        result = dict(tested_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                      runtime_sha="a5e146413f27d2096603bb521a01a9227f96ca33",model=model,chrome=locals().get("chrome"),
                      cases=cases,checks=checks,errors=errors,provider_calls=len(rec.calls),provider_success=len(successful),
                      transport_attempts=len(rec.attempts),tokens=token_totals,estimated_cost_usd=round(cost,6),
                      median_api_seconds=statistics.median([c["seconds"] for c in successful]) if successful else None,
                      real_microphone="NOT_RUN: no human utterance captured",recognition_double=args.fake_recognition,
                      safety_final_verdict="NOT_EVALUATED; Issue 5/6 remain with implementation owner")
        (out / "results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(dict(provider_calls=len(rec.calls),provider_success=len(successful),passed=sum(c["passed"] for c in checks),
                              failed=sum(not c["passed"] for c in checks),errors=errors,cost=cost),ensure_ascii=True))
    return 0 if checks and all(c["passed"] for c in checks) and not errors else 1


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file",type=Path,required=True)
    parser.add_argument("--call",action="store_true")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--fake-recognition",action="store_true")
    parser.add_argument("--headed",action="store_true")
    args=parser.parse_args()
    if not args.call:raise SystemExit("Real API requires explicit --call")
    raise SystemExit(run(args))
