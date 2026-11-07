"""回数の変更（2→3回）の見え方（クーちゃん 11/7 22時）：filming・偽の Claude・文字で入力・偽の保存の窓。アプリは変えない。
    python kuchan_review_repeat.py --repo <RC> --out <出力>"""
import argparse, json, sys, tempfile, threading
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--repo", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--sizes", default="1920x1080,1440x900,1280x720"); A = ap.parse_args()
REPO = Path(A.repo).resolve(); sys.path[:0] = [str(REPO), str(REPO / "tools")]
import demo_mock as dm
from voice_teaching import claude_explain as cx, sim
from voice_teaching.claude_interpreter import MockInterpreter
from voice_teaching.web import server
FAKE_PICKER = """window.__pickerMode='ok'; Object.defineProperty(navigator,'webdriver',{get:()=>false});
window.showSaveFilePicker = async (o) => { let d=new Uint8Array(); return {name:o.suggestedName,
 async createWritable(){return {async write(b){d=new Uint8Array(b);}, async close(){}};}, async getFile(){return new Blob([d]);}}; };"""
SEEN = """(sels) => Object.fromEntries(sels.map(s => { const e = document.querySelector(s);
 if (!e || e.offsetParent === null) return [s,'none']; const r = e.getBoundingClientRect(); if (!r.width) return [s,'none'];
 if (r.top < 0 || r.bottom > innerHeight+0.5 || r.left < 0 || r.right > innerWidth+0.5) return [s,'off-screen'];
 for (let p = e.parentElement; p; p = p.parentElement) { const cs = getComputedStyle(p);
  if (/(auto|scroll|hidden)/.test(cs.overflowY)) { const q = p.getBoundingClientRect(); if (r.top < q.top-1 || r.bottom > q.bottom+1) return [s,'cut']; } }
 const t = document.elementFromPoint(r.left + r.width/2, r.top + Math.min(r.height/2, 10));
 if (t && !e.contains(t) && !t.contains(e)) return [s,'covered:' + (t.id || t.className || t.tagName)]; return [s,'visible']; }))"""
# 3D の中の「×2 → ×3」の札（区間を通る回数）と、点がポップアップに隠れていないか
PTS = """() => { const pop = document.querySelector('#cand-pop'); if (!pop || getComputedStyle(pop).display === 'none' || !pop.getBoundingClientRect().width) return {pts:[], inset:'no-pop'};
 const p = pop.getBoundingClientRect(); const out = [];
 document.querySelectorAll('#fig-3d .pt3').forEach(g => { const r = g.getBoundingClientRect(); const cx = r.x + r.width/2, cy = r.y + r.height/2;
  if (cx >= p.x && cx <= p.right && cy >= p.y && cy <= p.bottom) out.push(g.getAttribute('data-names')); });
 let inset = 'not-found';
 for (const t of document.querySelectorAll('#fig-3d svg text')) { if (/区間を通る回数/.test(t.textContent)) { const r = t.getBoundingClientRect();
   inset = (r.right > p.x && r.left < p.right && r.bottom > p.y && r.top < p.bottom) ? 'under-popup' : 'visible'; break; } }
 return {pts: out, inset}; }"""
def serve(tmp):
    cx.PRICES[dm.MOCK_MODEL] = cx.Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0)
    sim.DEFAULT_OUT_DIR = tmp / "sim"
    ex = cx.Explainer("mock-no-network", dm.MOCK_MODEL, client=dm.ScriptClient(), usage_log=cx.UsageLog(tmp / "u.jsonl"))
    srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None, explainer=ex, channel="filming")
    threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv, f"http://127.0.0.1:{srv.server_address[1]}/"
def main():
    out = Path(A.out); out.mkdir(parents=True, exist_ok=True); srv, url = serve(Path(tempfile.mkdtemp()))
    from playwright.sync_api import sync_playwright
    res = {}
    with sync_playwright() as p:
        br = p.chromium.launch()
        for size in A.sizes.split(","):
            w, h = map(int, size.split("x")); m = res.setdefault(size, {}); pg = br.new_page(viewport={"width": w, "height": h})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.add_init_script(FAKE_PICKER)
            pg.goto(url); pg.wait_for_timeout(800)
            pg.set_input_files("#file-input", str(REPO / "samples/dummy/DEMO_BUTTON_REPEAT.JBI")); pg.wait_for_selector("#job-area:not([hidden])")
            pg.wait_for_timeout(600)
            if pg.is_visible("#kbd-button") and not pg.is_visible("#text-input"): pg.click("#kbd-button")
            pg.fill("#text-input", "C00001からC00003の作業を2回から3回にして"); pg.click("#text-send"); pg.wait_for_timeout(2500)
            pg.screenshot(path=str(out / f"{size}_r1_after_say.png"))
            m["reply"] = (pg.inner_text("#reply-message") if pg.is_visible("#reply-message") else "")[:200]
            if pg.locator("#range-yes").count() and pg.is_visible("#range-yes"):
                pg.screenshot(path=str(out / f"{size}_r2_range.png")); m["range_buttons"] = pg.evaluate(SEEN, ["#range-yes"])
                pg.click("#range-yes"); pg.wait_for_timeout(2000)
            ok = pg.locator("#quick-approve-button").count() and pg.is_visible("#quick-approve-button")
            m["candidate_reached"] = bool(ok)
            if ok:
                pg.wait_for_timeout(600); pg.screenshot(path=str(out / f"{size}_r3_candidate.png"))
                m["before"] = pg.evaluate(SEEN, ["#quick-approve-button", "#quick-approver", "#candidate-view .cand-warn", "#candidate-view .cand-big"])
                m["before_3d"] = pg.evaluate(PTS)
                pg.fill("#quick-approver", "UI確認"); pg.click("#quick-approve-button"); pg.wait_for_selector("#approval-status:not([hidden])", timeout=10000)
                pg.wait_for_timeout(1800); pg.screenshot(path=str(out / f"{size}_r4_saved.png"))
                m["after"] = pg.evaluate(SEEN, ["#approval-status", "#export-result", "#approval-states"]); m["after_3d"] = pg.evaluate(PTS)
                m["result"] = (pg.inner_text("#export-result") if pg.is_visible("#export-result") else "")[:200]
            m["errors"] = errs; pg.close()
        br.close()
    srv.shutdown(); (out / "review_repeat.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
main()
