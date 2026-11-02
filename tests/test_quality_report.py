"""品質レポート（tools/quality_report.py）の受入テスト。実装より先に書いた。

すべて一時フォルダの中で行い、リポジトリ本体のファイルは変えない。
禁止語や秘密らしい文字列は、このファイル自体が検出されないように、下のリストや連結で作る。
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "quality_report.py"

FORBIDDEN = ["安全です", "当たります", "干渉します"]
FAKE_KEY = "sk-" + "ant-" + "api03-" + "Zx9" * 12
FAKE_VALUE = "abcd" + "1234" * 5


def load_tool():
    spec = importlib.util.spec_from_file_location("quality_report", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quality_report"] = mod  # dataclass が自分のモジュールを引けるように
    spec.loader.exec_module(mod)
    return mod


qr = load_tool()


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git が無い")


# --- 断定の言葉 ---

def test_forbidden_word_found_with_file_and_line(tmp_path):
    write(tmp_path, "voice_teaching/screen.py", "a = 1\nmsg = 'この位置は" + FORBIDDEN[0] + "'\n")
    write(tmp_path, "docs/note.md", "# メモ\n\n腕が" + FORBIDDEN[2] + "。\n")
    write(tmp_path, "samples/dummy/readme.txt", "問題なし\n")
    hits = qr.check_forbidden_words(tmp_path)
    found = {(h.path, h.line, h.word) for h in hits}
    assert ("voice_teaching/screen.py", 2, FORBIDDEN[0]) in found
    assert ("docs/note.md", 3, FORBIDDEN[2]) in found
    assert len(hits) == 2


def test_forbidden_word_outside_targets_is_not_checked(tmp_path):
    # CLAUDE.md のような約束ごとの文書は対象外（voice_teaching/・docs/・samples/・tests/ だけを見る）
    write(tmp_path, "CLAUDE.md", "「" + FORBIDDEN[0] + "」は使わない\n")
    assert qr.check_forbidden_words(tmp_path) == []


def test_forbidden_word_list_in_tests_is_excluded(tmp_path):
    # テストの中の禁止語リスト（2語以上を引用符で並べた行）は除外する
    line = "    for word in [" + ", ".join('"' + w + '"' for w in FORBIDDEN) + "]:\n"
    write(tmp_path, "tests/test_screen.py", "def test_x():\n" + line + "        pass\n")
    assert qr.check_forbidden_words(tmp_path) == []


def test_single_forbidden_word_in_tests_is_still_found(tmp_path):
    # テストの中でも、リストでない1語の使用は見つける
    write(tmp_path, "tests/test_screen.py", "MSG = '腕は" + FORBIDDEN[1] + "'\n")
    hits = qr.check_forbidden_words(tmp_path)
    assert [(h.path, h.line) for h in hits] == [("tests/test_screen.py", 1)]


def test_forbidden_word_list_outside_tests_is_not_excluded(tmp_path):
    line = "WORDS = [" + ", ".join('"' + w + '"' for w in FORBIDDEN) + "]\n"
    write(tmp_path, "voice_teaching/words.py", line)
    assert len(qr.check_forbidden_words(tmp_path)) == 3


# --- 秘密らしい文字列 ---

def test_secret_is_found_but_value_is_never_shown(tmp_path):
    write(tmp_path, "voice_teaching/conf.py", "KEY = '" + FAKE_KEY + "'\n")
    write(tmp_path, "docs/setup.md", "設定\napi_key=" + FAKE_VALUE + "\n")
    hits = qr.check_secrets(tmp_path, files=["voice_teaching/conf.py", "docs/setup.md"])
    found = {(h.path, h.line) for h in hits}
    assert found == {("voice_teaching/conf.py", 1), ("docs/setup.md", 2)}

    report = qr.render_report(qr.Report(root=tmp_path, pytest=None, forbidden=[], secrets=hits, jbi=[]))
    assert "voice_teaching/conf.py" in report
    assert FAKE_KEY not in report
    assert FAKE_KEY[:12] not in report
    assert FAKE_VALUE not in report
    for h in hits:
        assert FAKE_KEY not in repr(h)
        assert FAKE_VALUE not in repr(h)


def test_env_example_placeholder_is_not_a_secret(tmp_path):
    write(tmp_path, ".env.example", "ANTHROPIC_API_KEY=ここに自分のAPIキーを入れる\n")
    assert qr.check_secrets(tmp_path, files=[".env.example"]) == []


# --- 追跡している JBI ---

@needs_git
def test_tracked_jbi_outside_samples_dummy_is_found(tmp_path):
    git(tmp_path, "init", "-q")
    write(tmp_path, "samples/dummy/OK.JBI", "/JOB\n")
    write(tmp_path, "jobs/REAL.JBI", "/JOB\n")
    write(tmp_path, "samples/other/LOWER.jbi", "/JOB\n")
    write(tmp_path, "samples/dummy/sub/DEEP.JBI", "/JOB\n")
    git(tmp_path, "add", "-f", ".")
    bad = qr.check_tracked_jbi(tmp_path)
    assert sorted(bad) == ["jobs/REAL.JBI", "samples/dummy/sub/DEEP.JBI", "samples/other/LOWER.jbi"]


@needs_git
def test_untracked_jbi_is_not_reported(tmp_path):
    git(tmp_path, "init", "-q")
    write(tmp_path, "samples/dummy/OK.JBI", "/JOB\n")
    git(tmp_path, "add", "-f", ".")
    write(tmp_path, "private/REAL.JBI", "/JOB\n")  # 追跡していない
    assert qr.check_tracked_jbi(tmp_path) == []


# --- pytest の結果の読み取り ---

def test_parse_pytest_output():
    out = (
        "..F.x\n"
        "=========================== short test summary info ===========================\n"
        "FAILED tests/test_a.py::test_one - AssertionError: x\n"
        "FAILED tests/test_b.py::test_two[1]\n"
        "ERROR tests/test_c.py - ImportError\n"
        "2 failed, 3 passed, 1 xfailed, 1 error in 0.50s\n"
    )
    r = qr.parse_pytest_output(out, returncode=1)
    assert r.passed == 3
    assert r.failed == 2
    assert r.xfailed == 1
    assert r.errors == 1
    assert r.failed_tests == ["tests/test_a.py::test_one", "tests/test_b.py::test_two[1]", "tests/test_c.py"]
    assert not r.ok


def test_parse_pytest_output_all_passed():
    r = qr.parse_pytest_output("....\n4 passed in 0.10s\n", returncode=0)
    assert (r.passed, r.failed, r.xfailed, r.ok) == (4, 0, 0, True)


# --- 全体（終了コード・書き出し先） ---

@needs_git
def test_main_exit_code_and_out_file(tmp_path, capsys):
    git(tmp_path, "init", "-q")
    write(tmp_path, "samples/dummy/OK.JBI", "/JOB\n")
    write(tmp_path, "docs/a.md", "ふつうの文\n")
    git(tmp_path, "add", "-f", ".")
    assert qr.main(["--root", str(tmp_path), "--no-pytest"]) == 0
    assert "# 品質レポート" in capsys.readouterr().out
    assert not (tmp_path / "output").exists()  # --out が無ければファイルは書かない

    write(tmp_path, "docs/b.md", "腕が" + FORBIDDEN[1] + "\n")
    out = tmp_path / "output" / "r.md"
    assert qr.main(["--root", str(tmp_path), "--no-pytest", "--out", str(out)]) == 1
    text = out.read_text(encoding="utf-8")
    assert "docs/b.md" in text
