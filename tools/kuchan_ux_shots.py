"""UI 精査用：本番の見せ方（filming チャンネル）で、モックの解釈・偽の音声認識を使い、主な操作の流れを撮る（クーちゃん 11/7）。

    python tools/kuchan_ux_shots.py --repo <撮るコードのフォルダ> --out <出力> [--sizes 1920x1080,1440x900,1280x720]

- API・実マイク・実機は使わない。出力は一時フォルダの SIM だけ（output/ に書かない）。
- アプリのコードは変えない。make_server を filming で起こすだけ（--mock は dev だけなので、撮影用にここで組み立てる）。
- 各場面で、3D の面積の割合・最小の文字の大きさ・開発用の文字の有無・会話と候補の重なりを測って metrics.json に残す。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--sizes", default="1920x1080,1440x900,1280x720")
ap.add_argument("--job", default="DEMO_RJ_XYZ.JBI")
ap.add_argument("--position", default="C00004")
A = ap.parse_args()
REPO = Path(A.repo).resolve()
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import demo_mock as dm  # noqa: E402
import e2e_browser as E  # noqa: E402
from voice_teaching import claude_explain as cx  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web import server  # noqa: E402

DEV_WORDS = ["TEST", "filming", "DEBUG", "SHA", "dev", "開発者", "モック"]

MEASURE = r"""
(devWords) => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const W = innerWidth, H = innerHeight;
  const rect = sel => { const el = document.querySelector(sel); if (!el || !vis(el)) return null;
    const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; };
  // 見えている文字の最小の大きさ（文字を直接持つ要素だけ）
  let minFont = 99, minFontText = '', smallCount = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const texts = [];
  while (walker.nextNode()) {
    const n = walker.currentNode; const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; if (!el || !vis(el)) continue;
    const r = el.getBoundingClientRect(); if (r.bottom < 0 || r.top > H || r.right < 0 || r.left > W) continue;
    // ダイアログの裏（背景）は数えない
    const dlg = document.querySelector('dialog[open]'); if (dlg && !dlg.contains(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    texts.push(t);
    if (fs < 12) smallCount++;
    if (fs < minFont) { minFont = fs; minFontText = t.slice(0, 30); }
  }
  const all = texts.join(' ');
  const dev = devWords.filter(w => new RegExp('(^|[^A-Za-z])' + w + '([^A-Za-z]|$)').test(all));
  const fig = rect('#fig-3d') || rect('canvas');
  const chars = all.replace(/\s/g, '').length;
  // 候補のポップアップの下に隠れた 3D の点（点の中心がポップアップの四角の中）
  const pop = rect('#cand-pop');
  let hiddenPts = [];
  if (pop) document.querySelectorAll('#fig-3d .pt3').forEach(g => {
    const r = g.getBoundingClientRect(); const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    if (cx >= pop.x && cx <= pop.x + pop.w && cy >= pop.y && cy <= pop.y + pop.h) hiddenPts.push(g.getAttribute('data-names') || g.textContent.trim().slice(0, 8) || '?');
  });
  return {pointsUnderPopup: hiddenPts, fig3d: fig, fig3dRatio: fig ? +(fig.w * fig.h / (W * H)).toFixed(3) : 0,
          minFontPx: minFont, minFontText, under12px: smallCount, visibleChars: chars, devWords: dev};
}
"""


def serve(tmp: Path):
    cx.PRICES[dm.MOCK_MODEL] = cx.Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0)
    sim.DEFAULT_OUT_DIR = tmp / "sim"
    ex = cx.Explainer("mock-no-network", dm.MOCK_MODEL, client=dm.ScriptClient(), usage_log=cx.UsageLog(tmp / "usage.jsonl"))
    srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None, explainer=ex, channel="filming")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def speak(pg, text):
    pg.evaluate("t => { window.__fakeText = t; }", text)
    pg.click("#mic-button")
    if pg.is_visible("#consent-yes"):
        pg.click("#consent-yes")
    E.until(pg, lambda: pg.is_enabled("#voice-stop"))
    pg.click("#voice-stop")
    E.until(pg, lambda: pg.input_value("#text-input") == text)
    pg.click("#text-send")
    E.until(pg, lambda: pg.is_enabled("#text-send") or not pg.is_visible("#text-send"), 40000)
    pg.wait_for_timeout(800)


def main() -> int:
    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vt-kuchan-"))
    srv, url = serve(tmp)
    from playwright.sync_api import sync_playwright
    metrics = {}
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for size in A.sizes.split(","):
                w, h = (int(v) for v in size.split("x"))
                ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ja-JP")
                pg = ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.add_init_script(E.FAKE_RECOGNITION)
                pg.add_init_script("try { localStorage.setItem('vt-voice-mode', 'browser'); } catch (_) {}")
                m = metrics.setdefault(size, {})

                def shot(name):
                    pg.screenshot(path=str(out / f"{size}_{name}.png"))
                    m[name] = pg.evaluate(MEASURE, DEV_WORDS)

                pg.goto(url)
                pg.wait_for_timeout(1500)
                shot("01_start")
                pg.set_input_files("#file-input", str(REPO / "samples/dummy" / A.job))
                pg.wait_for_selector("#job-area:not([hidden])")
                pg.wait_for_timeout(1000)
                shot("02_loaded")
                chip = pg.locator("#position-chips button", has_text=A.position)
                if chip.count():
                    chip.first.click()
                pg.wait_for_timeout(700)
                shot("03_selected")
                speak(pg, "Zプラス方向に30ミリ")
                shot("04_refused_30mm")
                speak(pg, "Zプラス方向に5ミリ")
                shot("05_candidate")
                if pg.is_visible("#open-confirm") and pg.is_enabled("#open-confirm"):
                    pg.click("#open-confirm")
                    pg.wait_for_timeout(800)
                shot("06_confirm")
                if pg.is_visible("#approver-name"):
                    pg.fill("#approver-name", "UI確認")
                    if pg.is_enabled("#approve-button"):
                        pg.click("#approve-button")
                        pg.wait_for_timeout(900)
                shot("07_approved")
                if pg.is_visible("#export-button") and pg.is_enabled("#export-button"):
                    pg.click("#export-button")
                    pg.wait_for_timeout(900)
                shot("08_exported")
                m["page_errors"] = errors
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print("shots:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
