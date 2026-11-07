"""UX の最終点検（11/7 21時・シクロ）：初めて使う人の流れを、偽の Claude・合成 JOB で通して、画面を撮り、隠れを測る。

  python tools/ux_audit/walkthrough.py --out <フォルダ>

- 本物の Claude は呼ばない（MockInterpreter と tools/demo_mock.py の台本）。実機・ファイル転送はしない。保存の窓は偽物
- 各段階で：画面を撮る・大事な要素が「画面の中にあり、ほかの物の下に隠れていないか」（中心の elementFromPoint）・
  3D の点が候補の窓の下に隠れていないか、を measure.json に書く
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playwright.sync_api import sync_playwright  # noqa: E402

import demo_mock as dm  # noqa: E402
from voice_teaching import claude_explain as cx  # noqa: E402
from voice_teaching import sim  # noqa: E402
from voice_teaching.claude_interpreter import MockInterpreter  # noqa: E402
from voice_teaching.web import server  # noqa: E402

FAKE_PICKER = (ROOT / "tools" / "check_approve_save.py").read_text(encoding="utf-8").split('FAKE_PICKER = """')[1].split('"""')[0]

MEASURE = """(sels) => {
  const out = {};
  for (const s of sels) {
    const e = document.querySelector(s);
    if (!e) { out[s] = 'なし'; continue; }
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(e).visibility === 'hidden') { out[s] = '出ていない'; continue; }
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) { out[s] = '画面の外'; continue; }
    const cut = r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth;
    const x = Math.min(Math.max((r.left + r.right) / 2, 1), innerWidth - 1), y = Math.min(Math.max((r.top + r.bottom) / 2, 1), innerHeight - 1);
    const top = document.elementFromPoint(x, y);
    const covered = top && !e.contains(top) && !top.contains(e);
    out[s] = (covered ? '隠れている（' + (top.id || top.className || top.tagName) + '）' : cut ? '一部が画面の外' : 'OK')
      + ` ${Math.round(r.left)},${Math.round(r.top)}-${Math.round(r.right)},${Math.round(r.bottom)}`;
  }
  const pop = document.querySelector('.cand-pop');
  const pr = pop ? pop.getBoundingClientRect() : null;
  const pts = [...document.querySelectorAll('#fig-3d g.pt3 > text, #fig-3d text.moved-label')];
  out['3D の点の名前（候補の窓の下）'] = !pr || !pr.width ? '候補の窓なし' : pts.filter((t) => {
    const r = t.getBoundingClientRect(); const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
    return x >= pr.left && x <= pr.right && y >= pr.top && y <= pr.bottom; }).map((t) => t.textContent.trim()).join(' / ') || 'なし';
  out['見出し'] = (document.querySelector('#next-action') || {}).innerText || '';
  return out;
}"""

KEY = ["#next-action", "#file-input", "#position-chips", "#text-input", "#text-send", "#fig-3d", "#reply-message",
       "#candidate-panel", "#quick-approve-button", "#quick-approver", "#open-confirm", "#approval-status", "#export-result",
       "#undo-button", "#range-yes", "#approve-button", "#mic-button"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="1920x1080,1440x900,1280x720")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vt-ux-"))
    sim.DEFAULT_OUT_DIR = tmp / "sim"
    server.AUTOSAVE_DEFAULT = True
    cx.PRICES[dm.MOCK_MODEL] = cx.Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0)
    ex = cx.Explainer("mock-no-network", dm.MOCK_MODEL, client=dm.ScriptClient(), usage_log=cx.UsageLog(tmp / "usage.jsonl"))
    srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None, explainer=ex)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    report: dict[str, dict] = {}

    def shot(pg, w, name):
        pg.wait_for_timeout(700)
        key = f"{w}_{name}"
        pg.screenshot(path=str(out / f"{key}.png"))
        report[key] = pg.evaluate(MEASURE, KEY)
        print(key, report[key].get("見出し"), "|", report[key].get("3D の点の名前（候補の窓の下）"))

    def say(pg, text, wait="() => true"):
        if not pg.is_visible("#text-input") and pg.is_visible("#kbd-button"):
            pg.click("#kbd-button")
        pg.fill("#text-input", text)
        pg.click("#text-send")
        pg.wait_for_function(wait, timeout=20000)

    def new(b, w, h, mode="ok"):
        ctx = b.new_context(viewport={"width": w, "height": h})
        pg = ctx.new_page()
        pg.add_init_script(FAKE_PICKER.replace("MODE", mode))
        pg.goto(url)
        pg.wait_for_timeout(700)
        return ctx, pg

    def load(pg, job):
        pg.set_input_files("#file-input", str(ROOT / "samples" / "dummy" / job))
        pg.wait_for_selector("#job-area:not([hidden])")

    cand = "() => !document.querySelector('#quick-approve').hidden"
    saved = "() => /保存しました|まだ保存していません|保存に失敗/.test(document.querySelector('#export-result').innerText)"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for size in args.sizes.split(","):
                w, h = (int(v) for v in size.split("x"))
                # A：位置の変更（動画の主な流れ）
                ctx, pg = new(b, w, h)
                shot(pg, w, "A01_start")
                load(pg, "DEMO_RJ_XYZ.JBI")
                shot(pg, w, "A02_job_loaded")
                pg.locator("#position-chips .chip", has_text="C00004").first.click()
                shot(pg, w, "A03_position_selected")
                say(pg, "もう少し上に寄せたいな")
                shot(pg, w, "A04_vague")
                say(pg, "Zプラス方向に3センチ動かして")
                shot(pg, w, "A05_over_limit")
                say(pg, "Zプラス方向に5ミリ動かして", cand)
                shot(pg, w, "A06_candidate")
                pg.click("#open-confirm")
                pg.wait_for_selector("#confirm-overlay:not([hidden])")
                shot(pg, w, "A07_detail_overlay")
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(300)
                if pg.is_visible("#confirm-overlay"):
                    pg.locator("#confirm-overlay button", has_text="閉じる").first.click()
                pg.fill("#quick-approver", "唐川")
                pg.click("#quick-approve-button")
                pg.wait_for_function(saved, timeout=15000)
                shot(pg, w, "A08_saved")
                say(pg, "C00005も上に5ミリ")
                shot(pg, w, "A09_next_after_save")
                ctx.close()
                # B：保存の窓を閉じた・失敗（1920 だけで十分な見え方の違いだが、3つの大きさで撮る）
                for mode in ("abort", "fail"):
                    ctx, pg = new(b, w, h, mode)
                    load(pg, "DEMO_RJ_XYZ.JBI")
                    pg.locator("#position-chips .chip", has_text="C00004").first.click()
                    say(pg, "Zプラス方向に5ミリ動かして", cand)
                    pg.fill("#quick-approver", "唐川")
                    pg.click("#quick-approve-button")
                    pg.wait_for_function(saved, timeout=15000)
                    shot(pg, w, f"B_{mode}")
                    ctx.close()
                # C：回数の変更（範囲の案内 → 2→3回 → 承認して保存）
                ctx, pg = new(b, w, h)
                load(pg, "DEMO_BUTTON_REPEAT.JBI")
                say(pg, "このロボット、何をしている？", "() => document.querySelector('#ask-turns .bubble.claude:not(.thinking)')")
                shot(pg, w, "C01_question")
                say(pg, "ボタンを押してるんだよ", "() => document.querySelector('#ask-turns .talk-choice')")
                shot(pg, w, "C02_teach_choice")
                pg.locator("#ask-turns .talk-choice", has_text="この動きです").click()
                pg.wait_for_selector("#ask-turns .bubble.taught")
                say(pg, "じゃあ、3回にして", "() => document.querySelector('#range-yes')")
                shot(pg, w, "C03_range_confirm")
                pg.click("#range-yes")
                pg.wait_for_function(cand, timeout=15000)
                shot(pg, w, "C04_repeat_candidate")
                pg.fill("#quick-approver", "唐川")
                pg.click("#quick-approve-button")
                pg.wait_for_function(saved, timeout=15000)
                shot(pg, w, "C05_repeat_saved")
                ctx.close()
            b.close()
    finally:
        srv.shutdown()
        srv.server_close()
    (out / "measure.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
