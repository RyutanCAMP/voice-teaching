"""21時のあとの重点（唐川さんの指示 11/7 夜）の画面の確かめ。偽の Claude・偽の保存の窓・API 0回。シクロの道具とは別に書いた。
使い方：python -I ui_final_focus.py <worktree> <出力フォルダ>
R：回数 2→3（DEMO_BUTTON_REPEAT）の候補・承認して保存・そのあと話しかける、の各時点で、3D の区間の点（C00001〜C00003）・
   回数の札（.repeat-label）・右上の回数の窓（.repeat-inset）が、ほかの欄に隠れないか（3つの大きさ）
   隠れている＝図形の真ん中のいちばん上の要素が 3D の図（svg）の中でない、または画面の外
K：保存のあとに話しかけたとき（DEMO_RJ_XYZ）、変更の点（C00003〜C00005）が隠れず、操作のボタン（取り消す・元に戻す・
   保存のボタン・送る）の真ん中を押すとそのボタンに届く（elementFromPoint）か（3つの大きさ）
S：保存し直し：取りやめ → 保存先を選んで保存（成功）／失敗 → 保存し直し（成功）で、見出し・✓・保存した中身が合うか（1920）
"""
from __future__ import annotations

import hashlib
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
BR = str(ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI")
PICKER = """
window.__mode = window.__mode || 'ok'; window.__pickerCalls = 0; window.__saved = null;
window.showSaveFilePicker = async (opts) => {
  window.__pickerCalls += 1; const m = window.__mode;
  if (m === 'abort') { const e = new Error('cancel'); e.name = 'AbortError'; throw e; }
  let buf = null;
  return { name: opts.suggestedName,
    async createWritable() { return { async write(b) { if (m === 'writefail') throw new Error('disk full'); buf = new Uint8Array(b); },
                                      async close() { window.__saved = Array.from(buf); } }; },
    async getFile() { return new Blob([buf || new Uint8Array()]); } };
};
"""
NOWEBDRIVER = "Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false });"
SIZES = [(1920, 1080), (1440, 900), (1280, 720)]
RES = []

COVER_JS = """(want) => {
  const items = [];
  for (const g of document.querySelectorAll('g.pt3')) {
    const names = (g.dataset.names || '').split(' ');
    if (!names.some((n) => want.includes(n))) continue;
    items.push({ k: 'pt ' + names.join('/'), t: '', r: [...g.querySelectorAll('circle')].pop().getBoundingClientRect() });
  }
  for (const s of document.querySelectorAll('.repeat-label, .repeat-inset')) {
    items.push({ k: s.getAttribute('class'), t: s.textContent.slice(0, 40), r: s.getBoundingClientRect() });
  }
  return items.map((it) => {
    const cx = (it.r.left + it.r.right) / 2, cy = (it.r.top + it.r.bottom) / 2;
    const off = cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight;
    const top = off ? null : document.elementFromPoint(cx, cy);
    const onSvg = !!top && top.closest('svg') !== null;
    let cover = null;
    if (top && !onSvg) { const c = top.closest('[id], [class]'); cover = c ? (c.id || String(c.className).slice(0, 40)) : top.tagName; }
    return { k: it.k, t: it.t, ok: onSvg && !off, offscreen: off, cover };
  });
}"""

BTN_JS = """(sels) => sels.map(([name, sel]) => {
  const e = [...document.querySelectorAll(sel)].find((x) => x.offsetParent !== null && !x.closest('[hidden]'));
  if (!e) return { name, present: false };
  e.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  const r = e.getBoundingClientRect(); const cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
  const t = document.elementFromPoint(cx, cy);
  return { name, present: true, reach: !!t && (t === e || e.contains(t)),
           top: t ? (t.id || String(t.className).slice(0, 30) || t.tagName) : null, disabled: !!e.disabled };
})"""


def rec(cid, verdict, what, **kw):
    RES.append({"id": cid, "verdict": verdict, "what": what, **kw})
    print(cid, verdict, what, json.dumps(kw, ensure_ascii=False)[:700], flush=True)


def vis(pg, s):
    return pg.locator(s).count() > 0 and pg.locator(s).first.is_visible()


def load(br, w, h, job, init=PICKER):
    pg = br.new_page(viewport={"width": w, "height": h}, accept_downloads=True)
    pg.add_init_script(E.FAKE_RECOGNITION)
    pg.add_init_script(init)
    pg.goto(URL)
    pg.set_input_files("#file-input", job)
    pg.wait_for_selector("#job-area:not([hidden])")
    return pg


def say(pg, text, wait=2500):
    E.fill_text(pg, text)
    pg.click("#text-send")
    pg.wait_for_timeout(wait)


def approve_save(pg):
    pg.fill("#quick-approver", "QA")
    pg.click("#quick-approve-button")
    E.until(pg, lambda: vis(pg, "#export-result"), 10000)
    pg.wait_for_timeout(1200)


def to_rj_candidate(br, w, h, init=PICKER):
    pg = load(br, w, h, RJ, init)
    pg.locator("#position-chips button", has_text="C00004").first.click()
    pg.wait_for_timeout(200)
    say(pg, "Zプラス方向に5ミリ動かして", 600)
    E.until(pg, lambda: vis(pg, "#quick-approve-button"), 10000)
    pg.wait_for_timeout(400)
    return pg


with sync_playwright() as p:
    br = p.chromium.launch()
    # ---- R：回数 2→3 ----
    for w, h in SIZES:
        pg = load(br, w, h, BR)
        say(pg, "C00001からC00003の作業を2回から3回にして")
        E.until(pg, lambda: vis(pg, "#range-yes"), 10000)
        pg.click("#range-yes")
        E.until(pg, lambda: vis(pg, "#quick-approve-button"), 10000)
        pg.wait_for_timeout(600)
        stages = {}
        for i, stage in enumerate(["候補", "承認して保存", "保存のあと話す"]):
            if stage == "承認して保存":
                approve_save(pg)
            if stage == "保存のあと話す":
                say(pg, "どこが変わったの？")
            rows = pg.evaluate(COVER_JS, ["C00001", "C00002", "C00003"])
            pg.screenshot(path=str(OUT / f"R_{w}x{h}_{i}_{['cand', 'saved', 'talk'][i]}.png"))
            stages[stage] = {"bad": [(r["k"], r["t"], r["cover"], r["offscreen"]) for r in rows if not r["ok"]],
                             "label": [r["t"] for r in rows if "repeat-label" in r["k"]],
                             "inset": [r["t"] for r in rows if "repeat-inset" in r["k"]]}
        bad = {k: v["bad"] for k, v in stages.items() if v["bad"]}
        no_label = [k for k, v in stages.items() if not v["label"]]
        rec(f"R-{w}", "PASS" if not bad and not no_label else "FAIL", "回数 2→3：区間の点・回数の札・右上の窓が隠れない",
            bad=bad, no_label=no_label, label={k: v["label"] for k, v in stages.items()}, inset={k: v["inset"] for k, v in stages.items()})
        pg.close()
    # ---- K：保存のあとに話す（DEMO_RJ_XYZ） ----
    for w, h in SIZES:
        for text in ["どこが変わったの？", "ありがとう"]:
            pg = to_rj_candidate(br, w, h)
            approve_save(pg)
            say(pg, text)
            rows = pg.evaluate(COVER_JS, ["C00003", "C00004", "C00005"])
            btns = pg.evaluate(BTN_JS, [["取り消す", "button.choice"], ["元に戻す", "#undo-button"],
                                        ["保存先を選んで保存", ".save-as-pick"]])
            # ［送る］は入力が空のとき押せない決まり（style.css :placeholder-shown）。文字を入れてから測り、消す
            E.fill_text(pg, "テスト")
            btns += pg.evaluate(BTN_JS, [["送る（文字あり）", "#text-send"]])
            pg.fill("#text-input", "")
            pg.screenshot(path=str(OUT / f"K_{w}x{h}_{'q' if '？' in text else 'thanks'}.png"))
            miss = [b for b in btns if b.get("present") and not b.get("reach")]
            absent = [b["name"] for b in btns if not b.get("present")]
            bad = [(r["k"], r["cover"]) for r in rows if not r["ok"]]
            rec(f"K-{w}-{text}", "PASS" if not bad and not miss else "FAIL", "保存のあと話しても、変更の点が見えて、ボタンを押せる",
                hidden=bad, unreachable=miss, absent=absent, head=pg.inner_text("#next-action"))
            pg.close()
    # ---- S：保存し直し（1920・窓を自動で開く経路） ----
    for first in ["abort", "writefail"]:
        pg = to_rj_candidate(br, 1920, 1080, NOWEBDRIVER + f"window.__mode = {json.dumps(first)};" + PICKER)
        resp = {}

        def on_resp(r, resp=resp):
            if r.url.endswith("/api/export"):
                try:
                    resp["json"] = r.json()
                except Exception:  # noqa: BLE001
                    pass
        pg.on("response", on_resp)
        approve_save(pg)
        h1 = pg.inner_text("#next-action"); t1 = pg.inner_text("#export-result")
        pg.evaluate("window.__mode = 'ok'")
        ok_btn = vis(pg, ".save-as-pick")
        if ok_btn:
            pg.click(".save-as-pick")
            pg.wait_for_timeout(1000)
        h2 = pg.inner_text("#next-action"); t2 = pg.inner_text("#export-result")
        saved = pg.evaluate("window.__saved")
        sha_ok = bool(saved) and bool(resp.get("json")) and hashlib.sha256(bytes(saved)).hexdigest() == resp["json"].get("sha256")
        problems = []
        if "保存しました" in h1 or "✓" in t1:
            problems.append("1回目（保存していない）で 保存しました／✓")
        if not ok_btn:
            problems.append("保存し直しのボタンが無い")
        if h2 != "保存しました" or t2.count("✓") != 1:
            problems.append(f"保存し直しのあとの見出し・✓ が合わない（{h2}・✓{t2.count('✓')}）")
        if not sha_ok:
            problems.append("保存した中身がサーバーの SIM と違う")
        pg.screenshot(path=str(OUT / f"S_{first}_then_ok.png"))
        rec(f"S-{first}", "PASS" if not problems else "FAIL", "保存し直し（取りやめ／失敗 → 成功）", problems=problems,
            head1=h1, head2=h2, picker_calls=pg.evaluate("window.__pickerCalls"), sha_match=sha_ok)
        pg.close()
    br.close()
(OUT / "ui_final_focus.json").write_text(json.dumps(RES, ensure_ascii=False, indent=1), encoding="utf-8")
print("合計", len(RES), "FAIL", sum(r["verdict"] == "FAIL" for r in RES))
