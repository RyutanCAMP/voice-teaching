"""クローク：最終承認 → シミュレーション用 JOB 出力の再現テスト（2026-11-06・Issue #8 の追加決定）。

撮影の流れ（DEMO_C_PLACE・C00005・Z プラス 5mm）で、次を確かめる。
- AE-1 変更前後の差分が、そのまま承認の対象になる（承認の指紋が候補の中身と同じ）
- AE-2 承認は画面のボタン（approve）だけ。声・文字・Claude に聞く道では承認も出力もされない
- AE-3 取消・言い直し・保留・古い世代では、承認も出力もできない
- AE-4 R-5：出力の最中に JOB を読み直したとき・読み直しの最中に出力したとき（順番を強制する）
- AE-5 並行の操作（承認・出力・言い直し・読み直しを同時に投げる）で、承認と候補の食い違いが起きない
- AE-6 出力したシミュレーション用 JOB の中身が、承認した差分と同じ（変わるのは承認した位置の1行とジョブ名の行だけ）

偽の Claude・合成ジョブだけ。出力は一時フォルダ。実機への転送・起動はしない。
同じ Claude（クローク）が書いたテスト。外部の独立レビュー・実機の安全の認証の代わりにはならない。
"""
import hashlib
import random
import threading
import time
from pathlib import Path

import pytest

import test_claude_talk as T
from voice_teaching import jbi, sim

CP = T.OTHER.read_bytes()  # samples/dummy/DEMO_C_PLACE.JBI（撮影の合成ジョブ）
SIM_NAME = "DEMO_C_PLACE_SIM.JBI.txt"


@pytest.fixture
def out(tmp_path, monkeypatch):
    d = tmp_path / "out"
    monkeypatch.setattr(sim, "DEFAULT_OUT_DIR", d)
    return d


def files(d: Path) -> list:
    return sorted(p for p in d.iterdir()) if d.exists() else []


def fakes(n=60):
    return [T.answer("この位置へ動く動作です。", (21, 22, 23, 24, 25, 26)) for _ in range(n)]


def made(tmp_path, said="Zプラス方向に5ミリ"):
    w, _ = T.flow(tmp_path, *fakes())
    sid = w.load(CP)["session_id"]
    w.select(sid, "C00005")
    w.talk(sid, said)
    assert w._entries[sid].session.candidate is not None, "撮影の流れで候補ができない"
    return w, sid


def approve(w, sid, gen=None):
    return w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid) if gen is None else gen)


def export(w, sid, gen=None):
    return w.export(sid, candidate_gen=w.candidate_gen_of(sid) if gen is None else gen)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def z_of(data: bytes, pos="C00005") -> float:
    return jbi.parse_bytes(data).positions[pos].values[jbi.AXES["Z"]]


def assert_file_is_the_approved_diff(path: Path, approval, after_z=205.0):
    """AE-6：出力の中身 = 元のジョブ − 承認した位置の1行 − //NAME の1行。名前の行を戻すと、承認した中身の指紋と同じ。"""
    data = path.read_bytes()
    orig = jbi.parse_bytes(CP)
    got = jbi.parse_bytes(data)
    diff = [i for i, (a, b) in enumerate(zip(orig.lines, got.lines)) if a != b]
    assert len(orig.lines) == len(got.lines)
    assert len(diff) == 2, diff
    name_i = next(i for i, l in enumerate(got.lines) if l.startswith("//NAME"))
    pos_i = orig.positions["C00005"].line_index
    assert sorted(diff) == sorted([name_i, pos_i])
    assert got.lines[name_i].startswith("//NAME DEMO_C_PLACE_SIM")
    assert z_of(data) == after_z
    for p, v in orig.positions.items():  # ほかの位置は1つも変わらない
        if p != "C00005":
            assert got.positions[p].values == v.values, p
    restored = list(got.lines)
    restored[name_i] = orig.lines[name_i]
    assert sha("".join(restored).encode(got.encoding)) == approval.new_sha256  # 承認した中身と同じ


# ---- AE-1：差分がそのまま承認の対象になる ----
def test_ae1_approval_fingerprints_are_the_candidate_diff(tmp_path, out):
    w, sid = made(tmp_path)
    e = w._entries[sid]
    ch = e.session.candidate
    st = w.state(sid)["state"]["candidate"]
    assert (ch.target, ch.before_value, ch.after_value) == ("C00005 Z", 200.0, 205.0)
    assert st["target"] == "C00005 Z" and st["delta"] == "+5.000"
    assert approve(w, sid)["ok"]
    assert e.approval.original_sha256 == sha(CP)
    assert e.approval.new_sha256 == sha(ch.new_job.render_bytes())
    assert e.approved_candidate is ch and e.approval_gen == e.cand_gen


# ---- AE-2：承認・出力は画面のボタンだけ ----
VOICE_APPROVE = ["承認して", "承認します", "OK、承認", "はい、承認お願いします", "承認ボタンを押して", "出力して",
                 "これで出力して", "シミュレーション用に出力", "はい", "OK", "お願いします", "いいよ、出して"]


@pytest.mark.parametrize("said", VOICE_APPROVE)
@pytest.mark.parametrize("path", ["talk_text", "talk_voice", "hear", "ask"])
def test_ae2_words_never_approve_or_export(tmp_path, out, said, path):
    w, sid = made(tmp_path)
    call = {"talk_text": lambda: w.talk(sid, said, "text"), "talk_voice": lambda: w.talk(sid, said, "voice"),
            "hear": lambda: w.hear(sid, said, "voice"), "ask": lambda: w.ask(sid, said, source="voice")}[path]
    call()
    e = w._entries[sid]
    assert e.approval is None, (path, said)
    assert files(out) == []
    assert not export(w, sid)["ok"]  # 承認していないので、ボタンの出力も断る
    assert files(out) == []


@pytest.mark.parametrize("said", VOICE_APPROVE)
def test_ae2_words_after_approval_never_export(tmp_path, out, said):
    w, sid = made(tmp_path)
    assert approve(w, sid)["ok"]
    w.talk(sid, said, "voice")
    assert files(out) == []  # 声・文字では出力しない（出力ボタンだけ）


# ---- AE-3：取消・言い直し・保留・古い世代では承認・出力できない ----
AFTER = ["取り消して", "やっぱり3ミリ", "いやZプラス3ミリ", "いや、Zプラス3ミリ", "ちょっと待って", "違くない？",
         "今のなし", "Zプラス5ミリ、いや3ミリ"]


@pytest.mark.parametrize("said", AFTER)
def test_ae3_after_cancel_or_hold_old_candidate_cannot_be_exported(tmp_path, out, said):
    w, sid = made(tmp_path)
    g0 = w.candidate_gen_of(sid)
    assert approve(w, sid)["ok"]
    w.talk(sid, said, "voice")
    assert not export(w, sid, g0)["ok"]          # 前の世代で
    assert not export(w, sid)["ok"]              # 今の世代で（承認し直していない）
    e = w._entries[sid]
    if e.session.candidate is not None and e.session.candidate.after_value == 205.0:
        # 古い候補が残る場面（保留）：保留を解かずにボタンで承認し直せない
        assert e.hold, said
        assert not approve(w, sid)["ok"]
    assert files(out) == []


def test_ae3_undo_select_reload_refuse(tmp_path, out):
    for op in ("undo", "select", "reload"):
        w, sid = made(tmp_path / op)
        g0 = w.candidate_gen_of(sid)
        assert approve(w, sid)["ok"]
        if op == "undo":
            w.undo(sid)
        elif op == "select":
            w.select(sid, "C00004")
        else:
            w.load(CP, previous=sid)
        assert not export(w, sid, g0)["ok"], op
        assert not approve(w, sid, g0)["ok"], op
    assert files(out) == []


# ---- AE-4：R-5（出力と JOB の読み直しが同時） ----
def _gate(monkeypatch, target_name: str, thread_name: str):
    """sim.<target_name> の入口で、決めたスレッドだけを止める（画面の錠を持ったまま止まる）。"""
    real = getattr(sim, target_name)
    entered, go = threading.Event(), threading.Event()

    def gated(*a, **k):
        if threading.current_thread().name == thread_name:
            entered.set()
            assert go.wait(10)
        return real(*a, **k)
    monkeypatch.setattr(sim, target_name, gated)
    return entered, go


def test_ae4_reload_during_export_waits_and_old_screen_cannot_write_after(tmp_path, out, monkeypatch):
    """出力が錠を持って書いている最中に読み直し：読み直しは、その出力が終わるまで返らない。
    返ったあと、前の画面からはもう書けない。残ったファイルは、人が承認した差分と同じ。"""
    w, sid = made(tmp_path)
    gen = w.candidate_gen_of(sid)
    assert approve(w, sid)["ok"]
    approval = w._entries[sid].approval
    entered, go = _gate(monkeypatch, "export_sim", "exp")
    res, loaded = {}, {}
    a = threading.Thread(target=lambda: res.update(r=w.export(sid, candidate_gen=gen)), name="exp")
    a.start()
    assert entered.wait(5)                       # 出力が錠を持って、書く直前で止まっている
    b = threading.Thread(target=lambda: loaded.update(r=w.load(CP, previous=sid)), name="reload")
    b.start()
    time.sleep(0.3)
    assert b.is_alive(), "読み直しが、書いている最中の出力を待たずに返った"
    assert sid not in w._entries                 # ただし前の画面はもう閉じた印（新しい要求は断る）
    go.set()
    a.join(5), b.join(5)
    assert not a.is_alive() and not b.is_alive()
    assert res["r"]["ok"] is True                # 読み直しより先に錠を取った出力は書かれる（設計 0-2 (3) の今の挙動）
    assert loaded["r"]["ok"] is True
    assert [p.name for p in files(out)] == [SIM_NAME]
    assert_file_is_the_approved_diff(files(out)[0], approval)
    assert approval.revocation.revoked           # 前の画面の承認は取り消しの印（手に持っても書けない）
    with pytest.raises(sim.SimError):
        sim.export_sim(_proposal_of(), approval)  # 取り消しの印のある承認を手に持って直接呼んでも書かない
    r = w.export(sid, candidate_gen=gen)
    assert r["ok"] is False and r.get("session_closed") is True
    assert [p.name for p in files(out)] == [SIM_NAME]


def _proposal_of():
    # 2層目の確かめ用：同じ中身の候補をもう一度作る（取り消しの印のある承認では書けないこと）
    return sim.simulate_shift(jbi.parse_bytes(CP), "C00005", "Z", 5.0)


def test_ae4_export_after_reload_started_is_refused(tmp_path, out, monkeypatch):
    """読み直しが前の画面を閉じたあとに出力ボタン：書かない（錠を待っていた出力も断る：既存 test_p0_reload_close 9章）。"""
    w, sid = made(tmp_path)
    gen = w.candidate_gen_of(sid)
    assert approve(w, sid)["ok"]
    w.load(CP, previous=sid)
    r = w.export(sid, candidate_gen=gen)
    assert r["ok"] is False and r.get("session_closed") is True
    assert files(out) == []


def test_ae4_reload_during_approve_leaves_no_usable_approval(tmp_path, out, monkeypatch):
    """承認の最中（錠の中）に読み直し：承認は終わるが、読み直しが返ったあとは取り消しの印で、どこからも出力できない。"""
    w, sid = made(tmp_path)
    gen = w.candidate_gen_of(sid)
    entered, go = _gate(monkeypatch, "approve", "apv")
    res, loaded = {}, {}
    a = threading.Thread(target=lambda: res.update(r=w.approve(sid, "QA", candidate_gen=gen)), name="apv")
    a.start()
    assert entered.wait(5)
    b = threading.Thread(target=lambda: loaded.update(r=w.load(CP, previous=sid)), name="reload")
    b.start()
    time.sleep(0.3)
    assert b.is_alive()
    go.set()
    a.join(5), b.join(5)
    e = w._entries.get(sid)
    assert e is None
    r = w.export(sid, candidate_gen=gen)
    assert r["ok"] is False and r.get("session_closed") is True
    assert files(out) == []


@pytest.mark.xfail(strict=True, reason="R-5 の知らせ（設計 0-2 (3)）：前の画面で出力したファイルを、新しい画面に知らせる文は未実装。"
                                       "表示は UI（シクロ）と一緒に決める")
def test_ae4_new_screen_tells_about_export_from_closed_screen(tmp_path, out, monkeypatch):
    w, sid = made(tmp_path)
    gen = w.candidate_gen_of(sid)
    assert approve(w, sid)["ok"]
    entered, go = _gate(monkeypatch, "export_sim", "exp")
    loaded = {}
    a = threading.Thread(target=lambda: w.export(sid, candidate_gen=gen), name="exp")
    a.start()
    assert entered.wait(5)
    b = threading.Thread(target=lambda: loaded.update(r=w.load(CP, previous=sid)), name="reload")
    b.start()
    time.sleep(0.2)
    go.set()
    a.join(5), b.join(5)
    assert SIM_NAME in repr(loaded["r"])  # 新しい画面の答えに、前の画面で出力したファイルの名前がある


# ---- AE-5：並行の操作 ----
def test_ae5_concurrent_operations_keep_approval_consistent(tmp_path, out):
    """承認・出力・言い直し・取消・保留・選び直し・読み直しを、同時に投げる（400回）。
    どの時点でも：承認があれば、それは今の候補・今の世代のもの・取り消しの印なし。
    書かれたファイルは、どれも人が承認した差分（Z 205 か 203）と同じ。"""
    w, sid0 = made(tmp_path)
    sids = [sid0]
    lock = threading.Lock()
    errors = []
    oks = {"approve": 0, "export": 0, "reload": 0}
    rnd = random.Random(1106)

    def cur():
        with lock:
            return sids[-1]

    def op(kind):
        sid = cur()
        try:
            if kind == "approve":
                if w.approve(sid, "QA", candidate_gen=w.candidate_gen_of(sid)).get("ok"):
                    with lock:
                        oks["approve"] += 1
            elif kind == "export":
                r = w.export(sid, candidate_gen=w.candidate_gen_of(sid))
                if r.get("ok"):
                    with lock:
                        oks["export"] += 1
                    # 次の回も出力の道を通るように、書けたファイルは片づける（同じ名前は上書きしないため）
                    for f in files(out):
                        assert z_of(f.read_bytes()) in (205.0, 203.0)
                        f.unlink()
            elif kind == "make5":
                w.talk(sid, "Zプラス方向に5ミリ")
            elif kind == "make3":
                w.talk(sid, "いやZプラス3ミリ")
            elif kind == "cancel":
                w.talk(sid, "取り消して")
            elif kind == "hold":
                w.talk(sid, "ちょっと待って")
            elif kind == "keep":
                w.talk(sid, "このままでいい")
            elif kind == "select":
                w.select(sid, "C00005")
            elif kind == "reload":
                r = w.load(CP, previous=sid)
                if r.get("ok"):
                    with lock:
                        sids.append(r["session_id"])
                        oks["reload"] += 1
                    w.select(r["session_id"], "C00005")
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{kind}: {ex!r}")

    kinds = (["approve"] * 4 + ["export"] * 4 + ["make5"] * 3 + ["make3"] * 2 + ["cancel", "hold", "keep", "select", "reload"])
    for _ in range(40):
        ts = [threading.Thread(target=op, args=(rnd.choice(kinds),)) for _ in range(10)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        for s in list(w._entries):
            e = w._entries[s]
            with e.lock:
                if e.approval is not None:
                    assert e.approved_candidate is e.session.candidate
                    assert e.approval_gen == e.cand_gen
                    assert not e.approval.revocation.revoked
                    assert e.approval.new_sha256 == sha(e.session.candidate.new_job.render_bytes())
        for p in files(out):  # 書けたファイルは、どれも承認した差分（同じ名前は上書きしないので最大1つ）
            data = p.read_bytes()
            assert z_of(data) in (205.0, 203.0)
            orig = jbi.parse_bytes(CP)
            got = jbi.parse_bytes(data)
            assert sum(a != b for a, b in zip(orig.lines, got.lines)) == 2
    assert errors == []
    assert len(files(out)) <= 1  # 同じ名前は上書きしない
    assert oks["approve"] > 0 and oks["export"] > 0 and oks["reload"] > 0, oks  # 承認・出力・読み直しの道を実際に通った


# ---- AE-6：出力の中身 = 承認した差分 ----
def test_ae6_exported_file_is_exactly_the_approved_diff(tmp_path, out):
    w, sid = made(tmp_path)
    assert approve(w, sid)["ok"]
    approval = w._entries[sid].approval
    r = export(w, sid)
    assert r["ok"], r
    assert r["file_name"] == SIM_NAME
    assert [p.name for p in files(out)] == [SIM_NAME]
    assert_file_is_the_approved_diff(files(out)[0], approval)
    assert T.OTHER.read_bytes() == CP  # 元のジョブは変わらない
    again = export(w, sid)
    assert again["ok"] is False  # 同じ名前は上書きしない
    assert [p.name for p in files(out)] == [SIM_NAME]


def test_ae6_existing_output_is_never_overwritten_even_from_a_new_screen(tmp_path, out):
    """同じ名前の出力ファイルがあると、同じ画面でも、読み直した新しい画面でも、出力を断る（上書きしない）。
    前のファイルの中身は変わらない。撮影の2テイク目では、前の出力ファイルを人が別の場所へ移す必要がある（記録）。"""
    w, sid = made(tmp_path)
    assert approve(w, sid)["ok"]
    assert export(w, sid)["ok"]
    first = files(out)[0].read_bytes()
    sid2 = w.load(CP, previous=sid)["session_id"]
    w.select(sid2, "C00005")
    w.talk(sid2, "Zプラス方向に3ミリ")
    assert w._entries[sid2].session.candidate.after_value == 203.0
    assert approve(w, sid2)["ok"]
    r = export(w, sid2)
    assert r["ok"] is False and "上書きしません" in r["error"]
    assert [p.name for p in files(out)] == [SIM_NAME] and files(out)[0].read_bytes() == first


def test_ae6_f2_after_export_unmarked_new_value_keeps_old_candidate(tmp_path, out):
    """F-2／Q-3（未解決・記録）：出力のあとに印の無い新しい値（「Zプラス方向に3ミリ」）を言うと、承認は取り消されるが、
    古い 205 の候補が残り、ボタンでもう一度承認できる。上書きはしないので、新しいファイルは書かれない。"""
    w, sid = made(tmp_path)
    assert approve(w, sid)["ok"]
    assert export(w, sid)["ok"]
    w.talk(sid, "Zプラス方向に3ミリ")
    e = w._entries[sid]
    assert e.approval is None
    assert e.session.candidate is not None and e.session.candidate.after_value == 205.0  # F-2：今の挙動（Q-3 の判断待ち）
    assert [p.name for p in files(out)] == [SIM_NAME]
