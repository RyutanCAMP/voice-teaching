"""閉じた画面（別のタブで新しい JOB を読んだ）で、前の画面の保存のボタンが保存しないか（偽の Claude・偽の保存の窓・API 0回）。
使い方：python -I ui_closed_save.py <worktree> <出力フォルダ>
流れ：タブ1 で承認して保存（窓は自動で開かない）→ タブ2 で JOB を読む → タブ1 で何か送る（サーバーが「閉じた」と返す）
     → タブ1 の保存のボタンが押せるか（disabled）・JS で click() を送っても保存・ダウンロードされないか
期待（XC-28・828b40d の仕様）：閉じた画面では保存のボタンを押せない。JS で押しても保存しない
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
sys.stdout.reconfigure(encoding="utf-8")
import e2e_browser as E  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web import server  # noqa: E402

sim.DEFAULT_OUT_DIR = OUT / "sim_out"
srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/?opening=0"
RJ = str(ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI")
PICKER = """
window.__saved = null; window.__pickerCalls = 0;
window.showSaveFilePicker = async (opts) => { window.__pickerCalls += 1; let buf = null;
  return { name: opts.suggestedName,
    async createWritable() { return { async write(b) { buf = new Uint8Array(b); }, async close() { window.__saved = Array.from(buf); } }; },
    async getFile() { return new Blob([buf || new Uint8Array()]); } }; };
"""


def vis(pg, s):
    return pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
    ctx.add_init_script(E.FAKE_RECOGNITION)
    ctx.add_init_script(PICKER)
    a = ctx.new_page()
    a.goto(URL); a.set_input_files("#file-input", RJ); a.wait_for_selector("#job-area:not([hidden])")
    a.locator("#position-chips button", has_text="C00004").first.click(); a.wait_for_timeout(200)
    E.fill_text(a, "Zプラス方向に5ミリ動かして"); a.click("#text-send")
    E.until(a, lambda: vis(a, "#quick-approve-button"), 10000); a.wait_for_timeout(400)
    a.fill("#quick-approver", "QA"); a.click("#quick-approve-button")
    E.until(a, lambda: vis(a, ".save-as-pick"), 10000); a.wait_for_timeout(500)
    before = a.evaluate("[...document.querySelectorAll('#save-as-area button')].map(b => b.disabled)")
    b = ctx.new_page()
    b.goto(URL); b.set_input_files("#file-input", RJ); b.wait_for_selector("#job-area:not([hidden])"); b.wait_for_timeout(800)
    a.bring_to_front()
    E.fill_text(a, "ありがとう"); a.click("#text-send"); a.wait_for_timeout(2000)
    closed = a.evaluate("!!(window.state && window.state.closed)") if a.evaluate("typeof window.state") != "undefined" else None
    reply = a.inner_text("#reply-message") if vis(a, "#reply-message") else ""
    dis = a.evaluate("[...document.querySelectorAll('#save-as-area button')].map(b => b.disabled)")
    shown = vis(a, ".save-as-pick") or vis(a, ".save-as-download")
    note = a.inner_text("#save-held-note") if vis(a, "#save-held-note") else ""
    downloads = []
    a.on("download", lambda d: downloads.append(d.suggested_filename))
    a.evaluate("for (const x of document.querySelectorAll('#save-as-area button')) x.click()")
    a.wait_for_timeout(1000)
    saved = a.evaluate("window.__saved")
    calls = a.evaluate("window.__pickerCalls")
    a.screenshot(path=str(OUT / "closed_tab1.png"))
    res = {"before_disabled": before, "closed_flag": closed, "reply": " ".join(reply.split())[:160], "buttons_visible": shown,
           "buttons_disabled": dis, "held_note": note, "picker_calls": calls, "saved": bool(saved), "downloads": downloads}
    ok = not saved and not downloads and calls == 0
    res["verdict"] = "PASS" if ok else "FAIL"
    print(json.dumps(res, ensure_ascii=False), flush=True)
    (OUT / "ui_closed_save.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    br.close()
