"""読むだけの確認用の道具（実機のジョブの形式を確かめる・2Dの図を見る）の受入テスト。実装より先に書いた。"""
from pathlib import Path

import pytest

from voice_teaching import inspect_job, jbi

DUMMY = Path(__file__).resolve().parent.parent / "samples" / "dummy" / "DEMO_PLACE.JBI"


def test_report_lists_positions_and_users():
    text = inspect_job.report(jbi.load(DUMMY))
    assert "DEMO_PLACE" in text
    assert "C00004=450.000,190.000,120.000" in text  # 位置はファイルの文字のまま出す
    # 位置ごとの形式・使っている行が出る
    assert "ROBOT" in text
    assert "共用" in text  # C00000 は2つのMOVLが使う
    assert "形式の検査" not in text and "検査:" not in text  # 読むだけの版は変更の判定を出さない


def test_report_shows_problems_and_still_lists_positions():
    data = DUMMY.read_bytes().replace(b"///GROUP1 RB1", b"///GROUP1 RB1,ST1")
    text = inspect_job.report(jbi.parse_bytes(data))
    assert "GROUP" in text
    assert "C00004" in text


def test_html_has_labels_and_disclaimer_and_no_assertive_words():
    html = inspect_job.html(jbi.load(DUMMY), source_name="DEMO_PLACE.JBI")
    for name in ["C00000", "C00004", "C00005"]:
        assert name in html
    assert "<svg" in html
    assert "当たらないとは限りません" in html
    for word in ["安全です", "当たります", "干渉します"]:
        assert word not in html


def test_html_handles_non_robot_positions():
    text = DUMMY.read_text(encoding="ascii").replace("///POSTYPE ROBOT\n", "///POSTYPE PULSE\n").replace("///RECTAN\n", "")
    html = inspect_job.html(jbi.parse(text), source_name="x.JBI")
    assert "ロボット座標でない" in html


def test_main_is_read_only_and_writes_html_outside_repo_tracking(tmp_path):
    src = tmp_path / "SAMPLE.JBI"
    src.write_bytes(DUMMY.read_bytes())
    out = tmp_path / "out"
    rc = inspect_job.main([str(src), "--out", str(out)])
    assert rc == 0
    assert src.read_bytes() == DUMMY.read_bytes()  # 元のジョブは変えない
    files = sorted(p.name for p in out.iterdir())
    assert files == ["SAMPLE.html"]  # JBIは書き出さない


def test_main_reports_unreadable_file(tmp_path, capsys):
    src = tmp_path / "BAD.JBI"
    src.write_bytes(b"/JOB\n\x81\xff\n")
    assert inspect_job.main([str(src), "--out", str(tmp_path / "out")]) == 1
    assert "読めません" in capsys.readouterr().out


def test_points_with_same_xy_share_one_readable_label():
    """真上の点・置く点など、上から見て重なる点は1つのラベルにまとめる（Safety P2-5）"""
    html = inspect_job.html(jbi.load(DUMMY), source_name="DEMO_PLACE.JBI")
    assert "C00000・C00001・C00002" in html


def test_three_views_are_drawn():
    html = inspect_job.html(jbi.load(DUMMY), source_name="DEMO_PLACE.JBI")
    for title in ["X・Y", "X・Z", "Y・Z"]:
        assert title in html


def test_line_with_loose_pl_is_drawn_dashed():
    """pl=3 のように緩い書き方の PL も「目安」（点線）にする"""
    text = DUMMY.read_text(encoding="ascii").replace("MOVL C00004 V=80.0", "MOVL C00004 V=80.0 pl=3")
    html = inspect_job.html(jbi.parse(text), source_name="x.JBI")
    assert '<line data-to="C00004" stroke-dasharray' in html
    assert '<line data-to="C00003" x1' in html  # PLの無いMOVLは実線


def test_main_does_not_print_position_lines_by_default(tmp_path, capsys):
    """実機の位置データを、AI補助のあるターミナルなどに流さないため、既定では位置の行を出さない（Safety P1-2）"""
    src = tmp_path / "SAMPLE.JBI"
    src.write_bytes(DUMMY.read_bytes())
    assert inspect_job.main([str(src), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "C00004=" not in out
    assert "SAMPLE.html" in out


def test_tool_is_read_only_by_construction():
    """読むだけの版：変更の検査・ジョブの書き出し・通信・プロセス起動につながる呼び出しが無い"""
    src = (Path(inspect_job.__file__)).read_text(encoding="utf-8")
    for word in ["plan_shift", "plan_speed", "shift_position", "set_speed", "rename(", "render_bytes",
                 "write_bytes", "socket", "urllib", "http", "subprocess", "os.system", "requests"]:
        assert word not in src, word
    assert src.count("write_text(") == 1  # HTML を書く1か所だけ


def test_move_to_variable_position_breaks_the_line_and_is_noted():
    """MOVL P000 のように位置がジョブの中に無い移動は描けないので、前後の点を直接つながず、注意を出す（Safety C2-5）"""
    text = DUMMY.read_text(encoding="ascii").replace("MOVL C00004 V=80.0\n", "MOVL P000 V=80.0\nMOVL C00004 V=80.0\n")
    html = inspect_job.html(jbi.parse(text), source_name="x.JBI")
    assert '<line data-to="C00004"' not in html  # C00003 から C00004 へ直接の線を引かない
    assert "描けない移動があります" in html


def test_wording_is_read_only_and_figure_is_marked_as_reference():
    html = inspect_job.html(jbi.load(DUMMY), source_name="DEMO_PLACE.JBI")
    text = inspect_job.report(jbi.load(DUMMY))
    for s in (html, text):
        assert "断る" not in s and "通る" not in s
    assert "参考表示" in html


@pytest.mark.parametrize("suffix", ["pl=3", "PL = 3", "PL=I001", "CR = 5"])
def test_unreadable_pl_or_cr_is_not_shown_as_absent(suffix):
    """読み取れない書き方の PL・CR を「なし」と出さない（QA 2回目 P2-2。チェック表の誤記録を防ぐ）"""
    text = DUMMY.read_text(encoding="ascii").replace("MOVL C00004 V=80.0", f"MOVL C00004 V=80.0 {suffix}")
    report = inspect_job.report(jbi.parse(text))
    line = [l for l in report.splitlines() if "速度:" in l][5]  # C00004 の行（6番目の移動命令）
    assert "読み取れない書き方" in line
