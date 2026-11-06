"""未承認の候補があるときに、文字の欄（#text-input）・キーボードのボタン・マイクが見えるか（モック）。"""
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
srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/?opening=0"
with sync_playwright() as p:
    br = p.chromium.launch()
    for w, h in ((1920, 1080), (1440, 900), (1280, 720)):
        pg = br.new_page(viewport={"width": w, "height": h}); pg.add_init_script(E.FAKE_RECOGNITION); pg.goto(URL)
        pg.set_input_files("#file-input", str(ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI")); pg.wait_for_selector("#job-area:not([hidden])")
        pg.locator("#position-chips button", has_text="C00004").first.click(); pg.wait_for_timeout(300)
        E.fill_text(pg, "Zプラス方向に5ミリ"); pg.click("#text-send"); E.until(pg, lambda: pg.is_visible("#cand-pop"), 10000); pg.wait_for_timeout(800)
        v = {s: (pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()) for s in ("#text-input", "#kbd-button", "#mic-button", "#text-send", "#undo-button")}
        # 人と同じように：キーボードのボタンがあれば押してから入れる
        typed = None
        try:
            E.fill_text(pg, "だめ"); typed = pg.is_visible("#text-input")
        except Exception as ex:
            typed = f"ERR {type(ex).__name__}"
        pg.screenshot(path=str(OUT / f"{w}x{h}_cand_input.png"))
        print(f"{w}x{h}", v, "type:", typed)
        pg.close()
    br.close()
srv.shutdown()
