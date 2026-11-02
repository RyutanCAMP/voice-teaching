"""品質レポート：テストの結果と、入れてはいけないものの点検を Markdown にまとめる。

使い方:
    python tools/quality_report.py                 # 標準出力に出す
    python tools/quality_report.py --out           # output/quality_report.md にも書く（output/ は git に入らない）
    python tools/quality_report.py --out FILE      # 指定したファイルにも書く

点検すること:
    1. python -m pytest -q の結果（通過・失敗・xfail の件数、失敗したテスト名）
    2. 断定の言葉（voice_teaching/・docs/・samples/・tests/ の中。テストの禁止語リストの行は除外）
    3. 秘密の情報らしい文字列（場所だけを出し、値は出さない）
    4. リポジトリで追跡している JBI が samples/dummy/ の中だけか

どれかに引っかかれば終了コード 1。標準ライブラリだけで書いている。
このレポートは点検の補助であり、ロボットの動作や安全を確かめるものではない。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path("output") / "quality_report.md"

FORBIDDEN_WORDS = ("安全です", "当たります", "干渉します")
FORBIDDEN_DIRS = ("voice_teaching", "docs", "samples", "tests")
TEST_DIR = "tests"
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "output"}

# 値そのものは保存も表示もしない。種類の名前だけを返す。
SECRET_PATTERNS = (
    ("Anthropic のAPIキーらしい文字列", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("APIキー・パスワードらしい代入",
     re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)"
                r"\s*[=:]\s*['\"]?[A-Za-z0-9_\-./+]{8,}")),
    ("AWS のアクセスキーらしい文字列", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub のトークンらしい文字列", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("秘密鍵", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


@dataclass(frozen=True)
class WordHit:
    path: str
    line: int
    word: str


@dataclass(frozen=True)
class SecretHit:
    path: str
    line: int
    kind: str  # 値は持たない


@dataclass
class PytestResult:
    returncode: int
    passed: int = 0
    failed: int = 0
    errors: int = 0
    xfailed: int = 0
    xpassed: int = 0
    skipped: int = 0
    failed_tests: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.failed == 0 and self.errors == 0


@dataclass
class Report:
    root: Path
    pytest: PytestResult | None
    forbidden: list[WordHit]
    secrets: list[SecretHit]
    jbi: list[str]

    @property
    def ok(self) -> bool:
        return ((self.pytest is None or self.pytest.ok)
                and not self.forbidden and not self.secrets and not self.jbi)


# --- 共通 ---

def read_text(path: Path) -> str | None:
    """文字として読めるファイルだけ読む。読めないもの（バイナリ等）は None。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    for enc in ("utf-8", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def walk_files(base: Path):
    if not base.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def git_files(root: Path, *extra: str) -> list[str] | None:
    """git ls-files の結果。git が使えなければ None。"""
    try:
        cp = subprocess.run(["git", "ls-files", "-z", *extra], cwd=root,
                            capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [p for p in cp.stdout.decode("utf-8", "replace").split("\0") if p]


# --- 1. pytest ---

_COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|xfailed|xpassed|skipped)\b")
_FAILED_RE = re.compile(r"^(FAILED|ERROR) (\S+)")


def parse_pytest_output(output: str, returncode: int) -> PytestResult:
    r = PytestResult(returncode=returncode)
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in reversed(lines):
        counts = _COUNT_RE.findall(ln)
        if counts or ln.startswith("no tests ran"):
            r.summary = ln.strip("= ")
            for n, kind in counts:
                n = int(n)
                if kind == "passed":
                    r.passed = n
                elif kind == "failed":
                    r.failed = n
                elif kind.startswith("error"):
                    r.errors = n
                elif kind == "xfailed":
                    r.xfailed = n
                elif kind == "xpassed":
                    r.xpassed = n
                elif kind == "skipped":
                    r.skipped = n
            break
    for ln in lines:
        m = _FAILED_RE.match(ln)
        if m and m.group(2) not in r.failed_tests:
            r.failed_tests.append(m.group(2))
    return r


def run_pytest(root: Path) -> PytestResult:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cp = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider"],
                        cwd=root, capture_output=True, env=env)
    out = cp.stdout.decode("utf-8", "replace") + "\n" + cp.stderr.decode("utf-8", "replace")
    return parse_pytest_output(out, cp.returncode)


# --- 2. 断定の言葉 ---

def _is_test_word_list(line: str) -> bool:
    """テストの中の禁止語リスト：禁止語を2つ以上、引用符で囲んで並べた行。"""
    quoted = {w for w in FORBIDDEN_WORDS
              if f'"{w}"' in line or f"'{w}'" in line}
    return len(quoted) >= 2


def check_forbidden_words(root: Path) -> list[WordHit]:
    root = Path(root)
    hits: list[WordHit] = []
    for d in FORBIDDEN_DIRS:
        for path in walk_files(root / d):
            text = read_text(path)
            if text is None:
                continue
            in_tests = d == TEST_DIR
            for no, line in enumerate(text.splitlines(), start=1):
                if in_tests and _is_test_word_list(line):
                    continue
                for w in FORBIDDEN_WORDS:
                    if w in line:
                        hits.append(WordHit(rel(root, path), no, w))
    return hits


# --- 3. 秘密らしい文字列 ---

def secret_scan_files(root: Path) -> list[str]:
    """追跡しているファイルと、まだ追跡していないが .gitignore で除外されていないファイル。"""
    files = git_files(root, "--cached", "--others", "--exclude-standard")
    if files is None:
        files = [rel(root, p) for p in walk_files(root)]
    return sorted(set(files))


def check_secrets(root: Path, files: list[str] | None = None) -> list[SecretHit]:
    root = Path(root)
    if files is None:
        files = secret_scan_files(root)
    hits: list[SecretHit] = []
    for f in files:
        text = read_text(root / f)
        if text is None:
            continue
        for no, line in enumerate(text.splitlines(), start=1):
            for kind, pat in SECRET_PATTERNS:
                if pat.search(line):
                    hits.append(SecretHit(Path(f).as_posix(), no, kind))
    return hits


# --- 4. 追跡している JBI ---

def check_tracked_jbi(root: Path) -> list[str]:
    """samples/dummy/ の直下以外で追跡している JBI。git が使えなければ点検できないことを返す。"""
    files = git_files(Path(root))
    if files is None:
        return ["（git ls-files を実行できず、点検できなかった）"]
    bad = []
    for f in files:
        if f.lower().endswith(".jbi"):
            parent = f.rsplit("/", 1)[0] if "/" in f else ""
            if parent != "samples/dummy":
                bad.append(f)
    return sorted(bad)


# --- まとめ ---

def build_report(root: Path, run_tests: bool = True) -> Report:
    root = Path(root).resolve()
    return Report(
        root=root,
        pytest=run_pytest(root) if run_tests else None,
        forbidden=check_forbidden_words(root),
        secrets=check_secrets(root),
        jbi=check_tracked_jbi(root),
    )


def _mark(ok: bool) -> str:
    return "問題なし" if ok else "要確認"


def render_report(r: Report) -> str:
    out = ["# 品質レポート", ""]
    out.append("このレポートは点検の補助です。ロボットの動作や安全を確かめるものではありません。")
    out.append("")
    out.append("| 点検 | 結果 |")
    out.append("|---|---|")
    out.append(f"| pytest | {'実行しなかった' if r.pytest is None else _mark(r.pytest.ok)} |")
    out.append(f"| 断定の言葉 | {_mark(not r.forbidden)}（{len(r.forbidden)}件） |")
    out.append(f"| 秘密らしい文字列 | {_mark(not r.secrets)}（{len(r.secrets)}件） |")
    out.append(f"| samples/dummy/ 以外の JBI | {_mark(not r.jbi)}（{len(r.jbi)}件） |")
    out.append("")

    out.append("## 1. テスト（python -m pytest -q）")
    if r.pytest is None:
        out.append("- 実行しなかった（--no-pytest）")
    else:
        p = r.pytest
        out.append(f"- 通過 {p.passed} / 失敗 {p.failed} / エラー {p.errors} / xfail {p.xfailed}"
                   f" / xpass {p.xpassed} / skip {p.skipped}（終了コード {p.returncode}）")
        if p.summary:
            out.append(f"- pytest の要約：`{p.summary}`")
        if p.failed_tests:
            out.append("- 失敗したテスト：")
            out.extend(f"  - `{t}`" for t in p.failed_tests)
    out.append("")

    out.append("## 2. 断定の言葉（" + "・".join(FORBIDDEN_DIRS) + "）")
    out.append("テストの中の禁止語リスト（禁止語を2つ以上引用符で並べた行）は除外しています。")
    if r.forbidden:
        out.extend(f"- `{h.path}:{h.line}` 「{h.word}」" for h in r.forbidden)
    else:
        out.append("- 見つからなかった")
    out.append("")

    out.append("## 3. 秘密の情報らしい文字列（値は表示しません）")
    if r.secrets:
        out.extend(f"- `{h.path}:{h.line}` {h.kind}" for h in r.secrets)
    else:
        out.append("- 見つからなかった")
    out.append("")

    out.append("## 4. 追跡している JBI（samples/dummy/ の中だけ許可）")
    if r.jbi:
        out.extend(f"- `{f}`" for f in r.jbi)
    else:
        out.append("- samples/dummy/ の外には無い")
    out.append("")

    out.append(f"**結果：{'引っかかったものは無い' if r.ok else '要確認の項目がある'}**")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="品質レポートを Markdown で出す")
    ap.add_argument("--root", default=str(REPO_ROOT), help="点検するリポジトリ（既定：このリポジトリ）")
    ap.add_argument("--out", nargs="?", const="", default=None,
                    help=f"ファイルにも書く（パス省略時は <root>/{DEFAULT_OUT.as_posix()}）")
    ap.add_argument("--no-pytest", action="store_true", help="pytest を実行しない")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    report = build_report(root, run_tests=not args.no_pytest)
    text = render_report(report)

    if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.write(text)

    if args.out is not None:
        out = Path(args.out) if args.out else root / DEFAULT_OUT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
