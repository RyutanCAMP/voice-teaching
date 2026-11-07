"""保存のボタンが、保留・取り消し・元に戻す・新しい候補のあとに残って押せるか（偽の Claude・偽の保存の窓・API 0回）。
使い方：python -I ui_hold_save.py <worktree> <出力フォルダ>
流れ：承認して保存（窓は自動で開かない）→ 次のどれか → ［保存先を選んで保存］が見えるか・押すと保存されるか
  hold：「どこが変わったの？」（保留）／cancel：保留 → ［取り消す］／undo：［元に戻す］／new：「Zプラス方向に3ミリ動かして」（新しい候補）
期待（クロークの案）：承認が消えた（取り消し・元に戻す・新しい候補）あとは、前の SIM を「保存」で書けない。保留中は書けないか、少なくとも「保留中」と分かる
"""
from __future__ import annotations
import json, sys, threading
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
RES = []
def vis(pg, s): return pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()
def z4(arr):
    if not arr: return None
    t = bytes(arr).decode("ascii", "replace")
    l = [x for x in t.splitlines() if x.startswith("C00004=")]
    return l[0].split(",")[2] if l else None

with sync_playwright() as p:
    br = p.chromium.launch()
    for case in ["hold", "cancel", "undo", "new"]:
        pg = br.new_page(viewport={"width": 1920, "height": 1080})
        pg.add_init_script(E.FAKE_RECOGNITION); pg.add_init_script(PICKER)
        pg.goto(URL); pg.set_input_files("#file-input", RJ); pg.wait_for_selector("#job-area:not([hidden])")
        pg.locator("#position-chips button", has_text="C00004").first.click(); pg.wait_for_timeout(200)
        E.fill_text(pg, "Zプラス方向に5ミリ動かして"); pg.click("#text-send")
        E.until(pg, lambda: vis(pg, "#quick-approve-button"), 10000); pg.wait_for_timeout(400)
        pg.fill("#quick-approver", "QA"); pg.click("#quick-approve-button")
        E.until(pg, lambda: vis(pg, ".save-as-pick"), 10000); pg.wait_for_timeout(500)
        if case in ("hold", "cancel"):
            E.fill_text(pg, "どこが変わったの？"); pg.click("#text-send"); pg.wait_for_timeout(2000)
            if case == "cancel":
                b = pg.locator("button", has_text="取り消す").first
                if b.count() and b.is_visible(): b.click(); pg.wait_for_timeout(2000)
        elif case == "undo":
            b = pg.locator("#undo-button")
            if b.count() and b.is_visible(): b.click(); pg.wait_for_timeout(2000)
        elif case == "new":
            E.fill_text(pg, "Zプラス方向に3ミリ動かして"); pg.click("#text-send"); pg.wait_for_timeout(2500)
        st = pg.evaluate("fetch('/api/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id: (window.state||{}).sessionId})}).then(r=>r.ok?r.json():null).catch(()=>null)")
        head = pg.inner_text("#next-action") if pg.locator("#next-action").count() else ""
        shown = vis(pg, ".save-as-pick"); dl = vis(pg, ".save-as-download"); res_vis = vis(pg, "#export-result")
        # 11/7 22時（828b40d）：保留中は保存のボタンを押せない（disabled）仕様。押せるかを記録し、押せないときも
        # JS で click() を送って（人は押せない）保存されないことを確かめる。期待は緩めない：保存された中身は承認して出力したものだけ
        dis = pg.evaluate("[...document.querySelectorAll('#save-as-area button')].map(b => b.disabled)")
        note = pg.inner_text("#save-held-note") if vis(pg, "#save-held-note") else ""
        saved = None; downloads = []
        pg.on("download", lambda d: downloads.append(d.suggested_filename))
        if shown or dl:
            pg.evaluate("for (const b of document.querySelectorAll('#save-as-area button')) b.click()")
            pg.wait_for_timeout(1000)
            saved = z4(pg.evaluate("window.__saved"))
        cand = pg.inner_text(".cand-pop") if vis(pg, ".cand-pop") else ""
        pg.screenshot(path=str(OUT / f"H_{case}.png"))
        r = {"case": case, "head": head, "export_result_visible": res_vis, "save_pick_visible": shown, "download_visible": dl,
             "saved_z_of_C00004": saved, "buttons_disabled": dis, "held_note": note, "downloads": downloads,
             "picker_calls": pg.evaluate("window.__pickerCalls"), "cand_head": " ".join(cand.split())[:160]}
        RES.append(r); print(json.dumps(r, ensure_ascii=False), flush=True)
        pg.close()
    br.close()
(OUT / "ui_hold_save.json").write_text(json.dumps(RES, ensure_ascii=False, indent=1), encoding="utf-8")
