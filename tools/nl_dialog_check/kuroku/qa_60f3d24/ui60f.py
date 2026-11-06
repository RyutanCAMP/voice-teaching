"""クロークの画面の品質検証（11/6 夜・60f3d24 向け）。モック（偽の Claude・偽の音声認識）。API 0回。
自分のフォルダで、空いているポート（port=0）にテスト用サーバーを立てる。8896 には触らない。
使い方：python -I ui60f.py <worktree> <出力フォルダ>
- V：撮影の流れ（DEMO_RJ_XYZ C00004 → 30mm → 5mm → 承認 → 出力 → DEMO_BUTTON_REPEAT 2→3 → 承認 → 出力）を画面の大きさごとに
- A：承認のアイコン（data-appr）が状態と合うか
- M：音声認識の失敗・聞き取った文が自動で送られないこと
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
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
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
RJ = str(ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI")
BRJ = str(ROOT / "samples/dummy/DEMO_BUTTON_REPEAT.JBI")
RES = []


def clear_out():
    d = OUT / "sim_out"
    if d.exists():
        for p in d.iterdir():
            p.unlink()


def rec(cid, ok, what, **kw):
    RES.append({"id": cid, "verdict": "PASS" if ok is True else ("未確認" if ok is None else "FAIL"), "what": what, **kw})
    print(cid, RES[-1]["verdict"], what, json.dumps(kw, ensure_ascii=False)[:500], flush=True)


def vis(pg, s):
    return pg.locator(s).count() > 0 and pg.is_visible(s)


def icon(pg):
    return pg.get_attribute("#approval-icon", "data-appr")


def reachable(pg, sel, loc=None):
    """見えていて、スクロールで画面に入り、真ん中が他の物で隠れていないか。"""
    loc = loc or pg.locator(sel).first
    if not loc.count() or not loc.is_visible():
        return "hidden"
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    if not box:
        return "nobox"
    vw = pg.viewport_size
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    if not (0 <= cx <= vw["width"] and 0 <= cy <= vw["height"]):
        return f"outside({int(cx)},{int(cy)})"
    top = loc.evaluate("(t, [x,y]) => { const e = document.elementFromPoint(x,y);"
                       " return e && (t === e || t.contains(e)) ? 'ok' : (e ? (e.id || e.className || e.tagName) : 'none'); }",
                       [cx, cy])
    return "ok" if top == "ok" else f"covered_by:{str(top)[:40]}"


def hscroll(pg):
    return pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")


def load(pg, path):
    pg.set_input_files("#file-input", path)
    pg.wait_for_selector("#job-area:not([hidden])")
    pg.wait_for_timeout(300)


def chip(pg, name):
    pg.locator("#position-chips button", has_text=name).first.click()
    pg.wait_for_timeout(200)


def say(pg, text, wait=700):
    E.fill_text(pg, text)
    pg.click("#text-send")
    E.until(pg, lambda: pg.is_enabled("#text-send"), 10000)
    pg.wait_for_timeout(wait)


def reply(pg):
    return (pg.inner_text("#reply-message") if vis(pg, "#reply-message") else "")[:300]


def approve(pg):
    E.until(pg, lambda: pg.is_enabled("#open-confirm"), 10000)
    pg.click("#open-confirm")
    pg.wait_for_selector("#confirm-overlay:not([hidden])")
    conf = pg.inner_text("#confirm-overlay")[:600]
    r = reachable(pg, "#approve-button")
    pg.fill("#approver-name", "クローク確認")
    pg.click("#approve-button")
    E.until(pg, lambda: vis(pg, "#approval-status"), 10000)
    pg.wait_for_timeout(300)
    return conf, r


def export(pg):
    r = reachable(pg, "#export-button")
    pg.click("#export-button")
    E.until(pg, lambda: vis(pg, "#export-result"), 10000)
    pg.wait_for_timeout(300)
    return pg.inner_text("#export-result")[:200], r


def new_page(BR, w, h):
    pg = BR.new_page(viewport={"width": w, "height": h})
    pg.add_init_script(E.FAKE_RECOGNITION)
    pg.goto(URL + "?opening=0")
    return pg


def flow_v(BR, w, h):
    cid = f"V_{w}x{h}"
    clear_out()
    pg = new_page(BR, w, h); log = {}
    try:
        load(pg, RJ); log["icon_loaded"] = icon(pg); chip(pg, "C00004")
        say(pg, "Zプラス方向に30ミリ動かして"); log["r30"] = reply(pg)[:120]; log["icon_30"] = icon(pg)
        log["open_confirm_after_30"] = pg.is_enabled("#open-confirm") and vis(pg, "#open-confirm")
        say(pg, "Zプラス方向に5ミリ動かして"); log["r5"] = reply(pg)[:160]; log["icon_cand"] = icon(pg)
        log["cand_text"] = (pg.inner_text("#candidate-view") if vis(pg, "#candidate-view") else "")[:200]
        log["open_confirm_reach"] = reachable(pg, "#open-confirm")
        pg.screenshot(path=str(OUT / f"{cid}_1_cand.png"))
        conf, log["approve_reach"] = approve(pg); log["confirm_has_185"] = "185.000" in conf and "180.000" in conf
        log["icon_approved"] = icon(pg)
        log["export_res"], log["export_reach"] = export(pg)
        pg.screenshot(path=str(OUT / f"{cid}_2_exported.png"))
        log["hscroll"] = hscroll(pg)
        load(pg, BRJ); log["icon_reload"] = icon(pg)
        log["cand_after_reload"] = vis(pg, "#cand-pop")
        say(pg, "C00001からC00003の作業を2回から3回にして"); log["r23"] = reply(pg)[:160]
        btn = pg.locator("button", has_text="この範囲を繰り返す").first
        log["range_btn_reach"] = reachable(pg, None, btn)
        btn.click(); pg.wait_for_timeout(500)
        log["cand23"] = (pg.inner_text("#candidate-view") if vis(pg, "#candidate-view") else "")[:200]
        conf, _ = approve(pg); log["icon_approved2"] = icon(pg)
        log["export2"], _ = export(pg)
        pg.screenshot(path=str(OUT / f"{cid}_3_repeat_exported.png"))
        f = OUT / "sim_out"
        log["files"] = sorted(p.name for p in f.iterdir()) if f.exists() else []
        why = []
        if log["icon_loaded"] != "pending": why.append("読み込み後のアイコンが pending でない")
        if log["open_confirm_after_30"]: why.append("30mm のあとに［確認して承認へ］が押せる")
        if log["icon_approved"] != "ok" or log["icon_approved2"] != "ok": why.append("承認後のアイコンが ok でない")
        if log["icon_reload"] not in ("pending",): why.append("読み直し後のアイコンが pending でない")
        for k in ("open_confirm_reach", "approve_reach", "export_reach", "range_btn_reach"):
            if log[k] != "ok": why.append(f"{k}={log[k]}")
        if log["hscroll"] > 2: why.append(f"横にはみ出す {log['hscroll']}px")
        if not log["confirm_has_185"]: why.append("確認表示に 180.000→185.000 が無い")
        if len(log["files"]) != 2: why.append("出力ファイルが2つでない")
        rec(cid, not why, "撮影の流れ", why=why, log=log)
    except Exception as ex:  # noqa: BLE001
        pg.screenshot(path=str(OUT / f"{cid}_err.png"))
        rec(cid, None, "撮影の流れ（途中で止まった）", error=repr(ex)[:200], log=log)
    pg.close()


def a_case(BR, cid, what, action, want_icon, want_green=False):
    clear_out()
    pg = new_page(BR, 1920, 1080)
    try:
        load(pg, RJ); chip(pg, "C00004"); say(pg, "Zプラス方向に5ミリ"); approve(pg)
        action(pg); pg.wait_for_timeout(600)
        st = (pg.text_content("#approval-status") or "") if vis(pg, "#approval-status") else ""
        got = dict(icon=icon(pg), label=pg.get_attribute("#approval-icon", "aria-label"), green="✓" in st,
                   export_enabled=vis(pg, "#export-button") and pg.is_enabled("#export-button"),
                   open_confirm=vis(pg, "#open-confirm") and pg.is_enabled("#open-confirm"), reply=reply(pg)[:200],
                   cand=(pg.inner_text("#candidate-view") if vis(pg, "#candidate-view") else "")[:120])
        pg.screenshot(path=str(OUT / f"{cid}.png"))
        why = []
        if got["icon"] != want_icon: why.append(f"アイコン {got['icon']}（期待 {want_icon}）")
        if got["green"] != want_green: why.append(f"緑の✓ {got['green']}（期待 {want_green}）")
        if want_icon != "ok" and got["export_enabled"]: why.append("出力ボタンが押せる")
        rec(cid, not why, what, why=why, got=got)
    except Exception as ex:  # noqa: BLE001
        rec(cid, None, what, error=repr(ex)[:200])
    pg.close()


def m_case(BR, cid, what, fn):
    pg = new_page(BR, 1920, 1080)
    try:
        load(pg, RJ); chip(pg, "C00004")
        ok, info = fn(pg)
        pg.screenshot(path=str(OUT / f"{cid}.png"))
        rec(cid, ok, what, **info)
    except Exception as ex:  # noqa: BLE001
        rec(cid, None, what, error=repr(ex)[:200])
    pg.close()


def mic(pg, text=None, fail=None):
    pg.evaluate("([t, f]) => { if (t !== null) window.__fakeText = t; window.__failNext = f; }", [text, fail])
    pg.click("#mic-button"); pg.wait_for_timeout(150)
    if pg.is_visible("#consent-yes"):
        pg.click("#consent-yes"); pg.wait_for_timeout(150)
    if not fail:
        pg.click("#voice-stop")
    pg.wait_for_timeout(400)


def m01(pg):  # 聞き取った文は入力欄に入るだけ（送らない）
    mic(pg, "Zプラス方向に5ミリ動かして")
    v = pg.input_value("#text-input"); c = vis(pg, "#cand-pop")
    return v == "Zプラス方向に5ミリ動かして" and not c, {"input": v, "cand_shown": c}


def m02(pg):  # no-speech / network / not-allowed：文と、文字の欄
    out = {}
    for f in ("no-speech", "network", "not-allowed", "audio-capture", "aborted"):
        mic(pg, None, f)
        out[f] = ((pg.inner_text("#voice-error") if vis(pg, "#voice-error") else "")[:100], vis(pg, "#text-input"),
                  pg.is_enabled("#mic-button"))
    bad = [k for k, v in out.items() if not v[0] or not v[1]]
    return not bad, {"res": out, "bad": bad}


def m03(pg):  # 候補のあいだはマイクを押せない・文字は入れられる
    say(pg, "Zプラス方向に5ミリ")
    m = pg.is_enabled("#mic-button"); t = pg.is_enabled("#text-input")
    return (not m) and t, {"mic_enabled": m, "text_enabled": t}


def m04(pg):  # 「Z方向に5mm」（プラスが落ちた）：送る前のヒント
    mic(pg, "Z方向に5mm動かして")
    h = vis(pg, "#voice-hint")
    say(pg, "Z方向に5mm動かして"); r = reply(pg)
    return h and not vis(pg, "#cand-pop"), {"hint": h, "hint_text": pg.inner_text("#voice-hint")[:100] if h else "", "reply": r[:120]}


def m05(pg):  # 話している間に位置を変えると、聞き取った文を使わない
    pg.evaluate("() => { window.__fakeText = 'Zプラス方向に5ミリ'; window.__failNext = null; }")
    pg.click("#mic-button"); pg.wait_for_timeout(100)
    if pg.is_visible("#consent-yes"):
        pg.click("#consent-yes"); pg.wait_for_timeout(100)
    en = pg.locator("#position-chips button", has_text="C00003").first.is_enabled()
    return None, {"chip_enabled_while_recording": en, "note": "録音中に位置のボタンが押せるか（押せないなら仕様どおり）"}


def m06(pg):  # 空の送信・空白だけ・長すぎ
    out = {}
    for t in ("", "   ", "あ" * 600):
        E.fill_text(pg, t); en = pg.is_enabled("#text-send")
        if en:
            pg.click("#text-send"); pg.wait_for_timeout(600)
        out[repr(t[:5])] = (en, reply(pg)[:100], (pg.inner_text("#voice-error") if vis(pg, "#voice-error") else "")[:80])
    return True, {"res": out}


with sync_playwright() as p:
    BR = p.chromium.launch()
    for w, h in ((1920, 1080), (1366, 768), (1280, 720), (1536, 864), (2560, 1440), (1024, 768), (390, 844)):
        flow_v(BR, w, h)
    a_case(BR, "A01", "承認済み", lambda pg: None, "ok", True)
    a_case(BR, "A02", "承認済み→ちょっと待って", lambda pg: say(pg, "ちょっと待って"), "warn")
    a_case(BR, "A03", "承認済み→取り消して", lambda pg: say(pg, "取り消して"), "warn")
    a_case(BR, "A04", "承認済み→Zプラス方向に3ミリ（F-2：承認だけ取り消し）", lambda pg: say(pg, "Zプラス方向に3ミリ"), "pending")
    a_case(BR, "A05", "承認済み→いやZプラス3ミリ（F-1）", lambda pg: say(pg, "いやZプラス3ミリ"), "warn")
    a_case(BR, "A06", "承認済み→元に戻す", lambda pg: pg.click("#undo-button"), "pending")
    a_case(BR, "A07", "承認済み→ページの再読み込み", lambda pg: pg.reload(), "none")
    a_case(BR, "A08", "承認済み→別の JOB", lambda pg: load(pg, BRJ), "pending")
    a_case(BR, "A09", "承認済み→出力→Zプラス方向に3ミリ", lambda pg: (export(pg), say(pg, "Zプラス方向に3ミリ")), "pending")
    a_case(BR, "A10", "承認済み→はい", lambda pg: say(pg, "はい"), "ok", True)
    a_case(BR, "A11", "承認済み→違くない？", lambda pg: say(pg, "違くない？"), "warn")
    for cid, what, fn in (("M01", "聞き取った文は送らない", m01), ("M02", "認識の失敗の文", m02), ("M03", "候補の間のマイク", m03),
                          ("M04", "プラスが落ちたときのヒント", m04), ("M05", "録音中の位置の変更", m05), ("M06", "空・長すぎの送信", m06)):
        m_case(BR, cid, what, fn)
    BR.close()
srv.shutdown()
(OUT / "ui60f.json").write_text(json.dumps({"sha": "60f3d24", "api": 0, "res": RES}, ensure_ascii=False, indent=1), encoding="utf-8")
print("FAIL", [r["id"] for r in RES if r["verdict"] == "FAIL"], "未確認", [r["id"] for r in RES if r["verdict"] == "未確認"])
