"""XC-21（候補の窓が会話に重なる）・XC-22（空の送信）を3つの大きさで（偽の Claude）。"""
import sys, threading
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]; sys.stdout.reconfigure(encoding="utf-8")
import e2e_browser as E
from playwright.sync_api import sync_playwright
from voice_teaching import sim
from voice_teaching.claude_interpreter import MockInterpreter
from voice_teaching.web import server
sim.DEFAULT_OUT_DIR = OUT / "o"
srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/?opening=0"
def box(pg, s):
    l = pg.locator(s)
    return l.first.bounding_box() if l.count() and l.first.is_visible() else None
def ov(a, b):
    if not a or not b: return 0
    x = max(0, min(a["x"]+a["width"], b["x"]+b["width"]) - max(a["x"], b["x"])); y = max(0, min(a["y"]+a["height"], b["y"]+b["height"]) - max(a["y"], b["y"]))
    return int(x*y)
with sync_playwright() as p:
    br = p.chromium.launch()
    for w, h in ((1920, 1080), (1440, 900), (1280, 720)):
        pg = br.new_page(viewport={"width": w, "height": h}); pg.add_init_script(E.FAKE_RECOGNITION); pg.goto(URL)
        pg.set_input_files("#file-input", str(ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI")); pg.wait_for_selector("#job-area:not([hidden])")
        pg.locator("#position-chips button", has_text="C00004").first.click(); pg.wait_for_timeout(200)
        E.fill_text(pg, ""); empty = pg.is_enabled("#text-send")
        E.fill_text(pg, "   "); space = pg.is_enabled("#text-send")
        E.fill_text(pg, "Zプラス方向に5ミリ動かして"); filled = pg.is_enabled("#text-send"); pg.click("#text-send")
        E.until(pg, lambda: pg.locator("#cand-pop").first.is_visible(), 10000); pg.wait_for_timeout(600)
        o = ov(box(pg, "#cand-pop"), box(pg, "#ask-turns"))
        last_reply_visible = pg.evaluate("""() => { const li = [...document.querySelectorAll('#ask-turns li')].pop(); if (!li) return null;
            const r = li.getBoundingClientRect(); const e = document.elementFromPoint(r.x + r.width/2, r.y + Math.min(20, r.height/2)); return !!(e && li.contains(e)); }""")
        pg.screenshot(path=str(OUT / f"{w}x{h}.png"))
        print(f"{w}x{h} 空で送れる={empty} 空白で送れる={space} 文字で送れる={filled} | 候補の窓と会話の重なり={o}px² 最後の返事が見える={last_reply_visible}")
        pg.close()
    br.close()
srv.shutdown()
