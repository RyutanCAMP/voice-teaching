"""クロークの UI Safety プローブ（11/6 朝）。モック（MockInterpreter・台本の Claude）・一時フォルダの出力・ポート 0。
使い方：python ui_probe.py <worktree> <出力フォルダ>
各場面で、サーバーの状態（/api/state 相当：WebFlow の state）と画面の表示（緑の ✓・出力ボタン・承認へのボタン・上の帯の記録）を比べる。
"""
from __future__ import annotations
import json, sys, threading
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
sys.stdout.reconfigure(encoding="utf-8")
import e2e_browser as E  # noqa
from playwright.sync_api import sync_playwright  # noqa
from voice_teaching import sim  # noqa
from voice_teaching.claude_interpreter import MockInterpreter  # noqa
from voice_teaching.web import server  # noqa

sim.DEFAULT_OUT_DIR = OUT / "sim_out"
srv = server.make_server(port=0, interpreter=MockInterpreter(), updown_config=None)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
JOB = str(ROOT / "samples/dummy/DEMO_C_PLACE.JBI")
RES = []


def snap(pg, name):
    vis = lambda s: pg.locator(s).count() > 0 and pg.is_visible(s)  # noqa
    d = dict(
        green_check_visible=vis("#approval-status") and "✓" in (pg.text_content("#approval-status") or ""),
        approval_status=(pg.text_content("#approval-status") or "").strip() if vis("#approval-status") else "",
        approval_states_visible=vis("#approval-states"),
        export_enabled=pg.is_enabled("#export-button") and vis("#export-button"),
        open_confirm_enabled=pg.is_enabled("#open-confirm") and vis("#open-confirm"),
        cand_pop_visible=vis("#cand-pop"),
        cand_text=(pg.inner_text("#candidate-view") if vis("#candidate-view") else "")[:300],
        status_line_visible=vis("#status-line"),
        status_line=(pg.text_content("#status-line") or "").strip()[:200],
        next_action=(pg.inner_text("#next-action") if vis("#next-action") else "")[:160],
        reply=(pg.inner_text("#reply-message") if vis("#reply-message") else "")[:300],
        mode_banner=(pg.inner_text("#mode-banner") if vis("#mode-banner") else ""),
        figure_short_visible=vis("#figure-short"),
        sim_chip_visible=vis(".sim-chip"),
        export_result=(pg.inner_text("#export-result") if vis("#export-result") else "")[:200],
    )
    pg.screenshot(path=str(OUT / f"{name}.png"))
    return d


def start(pg):
    pg.goto(URL + "?opening=0")
    pg.set_input_files("#file-input", JOB)
    pg.wait_for_selector("#job-area:not([hidden])")
    pg.locator("#position-chips button", has_text="C00005").first.click()


def say(pg, text, wait=600):
    E.fill_text(pg, text)
    pg.click("#text-send")
    pg.wait_for_timeout(wait)


def make_and_approve(pg):
    say(pg, "Zプラス方向に5ミリ")
    E.until(pg, lambda: pg.is_enabled("#open-confirm"), 10000)
    pg.click("#open-confirm")
    pg.fill("#approver-name", "クローク確認")
    pg.click("#approve-button")
    E.until(pg, lambda: pg.is_visible("#approval-status"), 10000)
    pg.wait_for_timeout(300)


def record(cid, title, before, after, why):
    RES.append(dict(id=cid, title=title, verdict="FAIL" if why else "PASS", why=why, before=before, after=after))
    print(cid, "FAIL" if why else "PASS", title, "／".join(why))


def scen_after_approval(cid, title, action, expect):
    try:
        _scen(cid, title, action, expect)
    except Exception as ex:  # noqa
        RES.append(dict(id=cid, title=title, verdict="未確認", why=[repr(ex)[:200]]))
        print(cid, "未確認", title, repr(ex)[:120])


def _scen(cid, title, action, expect):
    """承認済み → action → 画面を見る。expect：'void'（候補なし）・'hold'（保留）・'revoked'（承認だけ取り消し・候補あり）・'keep'"""
    pg = BR.new_page(viewport={"width": 1920, "height": 1080})
    pg.add_init_script(E.FAKE_RECOGNITION)
    start(pg); make_and_approve(pg)
    b = snap(pg, f"{cid}_a_approved")
    action(pg)
    pg.wait_for_timeout(800)
    a = snap(pg, f"{cid}_b_after")
    why = []
    if not b["green_check_visible"] or not b["export_enabled"]:
        why.append("前提：承認のあとに ✓ と出力ボタンが出ない")
    if expect != "keep":
        if a["green_check_visible"]:
            why.append("承認が無効になったのに、緑の ✓ が残る")
        if a["export_enabled"]:
            why.append("承認が無効になったのに、出力ボタンを押せる")
        if a["approval_states_visible"]:
            why.append("承認のあとの3つの状態が残る")
    if expect == "void" and a["open_confirm_enabled"]:
        why.append("候補を取り消したのに［確認して承認へ］を押せる")
    if expect == "hold":
        if a["open_confirm_enabled"]:
            why.append("保留中に［確認して承認へ］を押せる")
        if not a["status_line_visible"] or "保留" not in a["status_line"]:
            why.append("保留の記録が上の帯に見えない")
    if expect == "revoked" and not ("承認 まだ" in a["status_line"] or "取り消" in a["reply"]):
        why.append("承認を取り消したことが画面の文で分からない")
    record(cid, title, b, a, why)
    pg.close()


with sync_playwright() as p:
    BR = p.chromium.launch()
    # U01：30mm の拒否の理由
    pg = BR.new_page(viewport={"width": 1920, "height": 1080}); pg.add_init_script(E.FAKE_RECOGNITION); start(pg)
    say(pg, "Zプラス方向に30ミリ", 1200)
    s = snap(pg, "U01_30mm")
    vis_text = pg.inner_text("body")
    why = []
    if s["cand_pop_visible"] and s["open_confirm_enabled"]:
        why.append("30mm で承認へ進める")
    if not any(k in vis_text for k in ("上限", "20mm", "20 mm", "超え")):
        why.append("拒否の理由（上限）が画面の文に無い")
    record("U01", "Zプラス方向に30ミリ：拒否の理由が見える・承認へ進めない", {}, s, why)
    # U02：5mm の候補の前後の座標・移動量
    say(pg, "Zプラス方向に5ミリ", 1200)
    s = snap(pg, "U02_5mm")
    t = pg.inner_text("#cand-pop") if pg.is_visible("#cand-pop") else ""
    why = []
    if "200.000" not in t or "205.000" not in t:
        why.append("ポップアップに変更前後の座標（200.000 → 205.000）が無い")
    if not any(k in t for k in ("+5.000", "+5", "5mm", "5 mm", "5.000")):
        why.append("ポップアップに移動量が無い")
    if "C00005" not in t:
        why.append("ポップアップに対象の位置が無い")
    s["cand_pop_text"] = t[:600]
    record("U02", "Zプラス方向に5ミリ：候補に対象・変更前後・移動量が見える", {}, s, why)
    # U03：シミュレーションの表示
    why = []
    if "SIM" not in s["mode_banner"]:
        why.append("SIM の印が見えない")
    title = pg.get_attribute("#mode-banner", "title") or ""
    if "実機への出力・転送・ロボットの起動はしません" not in title:
        why.append("SIM の説明に実機をしない旨が無い")
    if not s["figure_short_visible"]:
        why.append("図の注意の短い1行が見えない")
    btn = pg.inner_text("#export-button")
    if "実機に入れない" not in btn:
        why.append("出力ボタンの文に「実機に入れない」が無い")
    banned = [w for w in ("安全です", "当たりません", "干渉しません", "問題ありません", "実機に送", "転送しました", "ロボットを動か") if w in pg.inner_text("body")]
    if banned:
        why.append(f"断定・誤認の言葉：{banned}")
    record("U03", "シミュレーションと実機を取り違えない表示（SIM・図の注意・出力ボタンの文・断定の言葉なし）", {}, dict(mode_banner=s["mode_banner"], title=title, export_button=btn), why)
    pg.close()

    scen_after_approval("U10", "承認済み → 取り消して", lambda pg: say(pg, "取り消して"), "void")
    scen_after_approval("U11", "承認済み → やっぱり3ミリ（言い直し）", lambda pg: say(pg, "やっぱり3ミリ"), "void")
    scen_after_approval("U12", "承認済み → いや、Zプラス3ミリ（読点あり）", lambda pg: say(pg, "いや、Zプラス3ミリ"), "void")
    scen_after_approval("U13", "承認済み → いやZプラス3ミリ（F-1：読点なし）", lambda pg: say(pg, "いやZプラス3ミリ"), "revoked")
    scen_after_approval("U14", "承認済み → 3ミリにして（F-2：印なし）", lambda pg: say(pg, "3ミリにして"), "revoked")
    scen_after_approval("U15", "承認済み → ちょっと待って（保留）", lambda pg: say(pg, "ちょっと待って"), "hold")
    scen_after_approval("U16", "承認済み → 違くない？（保留）", lambda pg: say(pg, "違くない？"), "hold")
    scen_after_approval("U17", "承認済み → ［元に戻す］", lambda pg: pg.click("#undo-button"), "void")
    def pick_other(pg):
        if not pg.locator("#position-chips button", has_text="C00004").first.is_visible():
            pg.click("#voice-position"); pg.wait_for_timeout(300)
        pg.locator("#position-chips button", has_text="C00004").first.click(timeout=5000)
    scen_after_approval("U18", "承認済み → 別の位置 C00004 を選ぶ", pick_other, "void")

    def reload_job(pg):
        pg.set_input_files("#file-input", JOB)
        pg.wait_for_timeout(800)
    scen_after_approval("U19", "承認済み → 同じ JOB を読み直す", reload_job, "void")

    def reload_page(pg):
        pg.reload(); pg.wait_for_timeout(800)
    scen_after_approval("U20", "承認済み → ブラウザーの再読み込み", reload_page, "void")
    scen_after_approval("U21", "承認済み → はい（相づち・承認を残してよい）", lambda pg: say(pg, "はい"), "keep")

    # U22：出力したあとに言い直し → 出力済みの表示と食い違わないか
    pg = BR.new_page(viewport={"width": 1920, "height": 1080}); pg.add_init_script(E.FAKE_RECOGNITION); start(pg); make_and_approve(pg)
    pg.click("#export-button"); pg.wait_for_timeout(800)
    b = snap(pg, "U22_a_exported")
    say(pg, "やっぱり3ミリ", 900)
    a = snap(pg, "U22_b_after")
    why = []
    if a["green_check_visible"]:
        why.append("出力後に言い直したのに、緑の ✓ が残る")
    if a["export_enabled"]:
        why.append("出力後に言い直したのに、出力ボタンを押せる")
    record("U22", "出力したあと → やっぱり3ミリ：✓・出力ボタンが残らない（出力したファイルは消えない。表示は記録）", b, a, why)
    pg.close()

    # U23 の前に出力先を空にする（前の場面 U22 の同じ名前のファイルで、出力が断られないように）
    for f in list((OUT / "sim_out").rglob("*")):
        if f.is_file():
            f.unlink()
    # U23：F-1 の画面：取り消したあと、ポップアップの候補はどれか・もう一度承認すると何が出力されるか
    pg = BR.new_page(viewport={"width": 1920, "height": 1080}); pg.add_init_script(E.FAKE_RECOGNITION); start(pg); make_and_approve(pg)
    say(pg, "いやZプラス3ミリ", 900)
    a = snap(pg, "U23_a_after_iya")
    why = []
    done = False
    if a["open_confirm_enabled"]:
        pg.click("#open-confirm"); pg.wait_for_timeout(300)
        conf = pg.inner_text("#confirm-overlay")[:600]
        pg.screenshot(path=str(OUT / "U23_b_confirm.png"))
        pg.fill("#approver-name", "クローク確認"); pg.click("#approve-button"); pg.wait_for_timeout(600)
        if pg.is_enabled("#export-button"):
            pg.click("#export-button"); pg.wait_for_timeout(800)
            r = pg.inner_text("#export-result") if pg.is_visible("#export-result") else ""
            files = list((OUT / "sim_out").rglob("*.txt"))
            body = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
            done = True
            a["confirm_text"] = conf
            a["export_result_after"] = r[:200]
            pg.screenshot(path=str(OUT / "U23_c_exported.png"))
            a["export_file_has_205"] = "205.000" in body
            a["export_files"] = [f.name for f in files]
            if "205.000" in conf and "205.000" in body:
                why.append("F-1：言い直し（Z+3）のあと、画面の確かめ表示は古い 200.000 → 205.000 を出し、承認と出力のボタンで古い 205.000 の合成ジョブが出力された")
            elif "205.000" in conf:
                why.append("F-1：言い直し（Z+3）のあと、画面で古い 205.000 の候補をもう一度承認できた（出力は別の理由で断られた：" + r[:80] + "）")
    if not done:
        a["note"] = "もう一度承認・出力できなかった"
    record("U23", "F-1 の画面での再現：いやZプラス3ミリ →［確認して承認へ］→ 承認 → 出力", {}, a, why)
    pg.close()
    BR.close()

srv.shutdown()
n = {k: sum(r["verdict"] == k for r in RES) for k in ("PASS", "FAIL", "未確認")}
print(json.dumps(n, ensure_ascii=False))
(OUT / "ui_probe.json").write_text(json.dumps(dict(summary=n, mode="モック（MockInterpreter）・Playwright Chromium 1920×1080", results=RES),
                                              ensure_ascii=False, indent=1), encoding="utf-8")
