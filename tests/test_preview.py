"""プレビューの境界と承認を先に定義する。枠の数値はテスト専用の架空値。"""
from pathlib import Path
import copy

import pytest

from voice_teaching.preview import PreviewSession, PreviewError, inspect_job


RAW = (Path(__file__).resolve().parents[1] / "samples/dummy/DEMO_PLACE.JBI").read_bytes()


def session():
    s = PreviewSession()
    s.load(RAW, "utf-8")
    return s


def policy(s):
    return {"preview_only": True, "baseline_hash": s.state()["baseline_hash"],
            "right_axis": "Y", "right_sign": 1,
            "positions": {"C00004": {"Y": {"min": -12, "max": 12, "step": 10},
                                      "Z": {"min": -20, "max": 20, "step": 10}}}}


def propose(s, text="C00004を右に10ミリ", answer=None):
    token = s.begin_input("C00004")
    def interpreter(text, selected, names):
        return answer or {"position": "C00004", "direction": "右", "amount_mm": 10}
    return s.propose(token, text, interpreter)


def test_read_only_load_and_path_order():
    s = session()
    view = s.state()["current"]
    assert view["positions"]["C00004"] == [450, 190, 120]
    assert [m["position"] for m in view["moves"]][-2:] == ["C00005", "C00000"]
    assert view["playable"]
    assert s.original_bytes == RAW


@pytest.mark.parametrize("change", [
    lambda t: t.replace("///POSTYPE ROBOT", "///POSTYPE PULSE"),
    lambda t: t.replace("C00004=", "///POSTYPE PULSE\nC00004="),
    lambda t: t.replace("///RECTAN", "///RECTAN\n///USER 1"),
    lambda t: t.replace("C00004=450.000", "C00004=nan"),
    lambda t: t.replace("C00004=450.000", "C00004=1e999"),
    lambda t: t.replace("//INST", "C00004=1,2,3,4,5,6\n//INST"),
])
def test_uncertain_coordinates_are_never_drawn_as_xyz(change):
    s = PreviewSession()
    s.load(change(RAW.decode()).encode(), "utf-8")
    assert s.state()["current"]["positions"] == {}
    assert not s.state()["current"]["playable"]


@pytest.mark.parametrize("line", ["MOVJ C00003 VJ=20", "CALL JOB:OTHER", "JUMP *LABEL",
                                      "MOVL C00099 V=10", "MOVL C00003 V=20 PL=0"])
def test_unsupported_instructions_disable_playback_without_skipping(line):
    view = inspect_job(RAW.decode().replace("MOVL C00003 V=250.0", line))
    assert not view["playable"]
    assert view["issues"]


def test_no_default_limits():
    s = session()
    with pytest.raises(PreviewError, match="枠"):
        propose(s)
    assert s.state()["candidate"] is None


def test_candidate_does_not_change_current_until_button_approval():
    s = session()
    s.set_policy(policy(s))
    c = propose(s)
    assert s.state()["current"]["positions"]["C00004"][1] == 190
    assert c["after"][1] == 200
    assert len(c["affected_segments"]) == 2
    s.approve(c["id"])
    assert s.state()["current"]["positions"]["C00004"][1] == 200
    assert s.original_bytes == RAW
    with pytest.raises(PreviewError):
        s.approve(c["id"])


def test_cumulative_limits_and_rejection_clears_previous_candidate():
    s = session()
    s.set_policy(policy(s))
    s.approve(propose(s)["id"])
    with pytest.raises(PreviewError, match="範囲"):
        propose(s)
    assert s.state()["candidate"] is None


def test_new_input_or_policy_invalidates_approval():
    s = session()
    s.set_policy(policy(s))
    c = propose(s)
    s.begin_input("C00001")
    with pytest.raises(PreviewError):
        s.approve(c["id"])
    c = propose(s)
    s.set_policy(policy(s))
    with pytest.raises(PreviewError):
        s.approve(c["id"])


def test_selection_is_captured_at_input_start():
    s = session()
    s.set_policy(policy(s))
    token = s.begin_input("C00004")
    c = s.propose(token, "この位置を右に10mm", lambda *_: {
        "position": "C00004", "direction": "右", "amount_mm": 10})
    assert c["position"] == "C00004"


@pytest.mark.parametrize("text,answer", [
    ("C00004を右に10mm", {"position": "C00004", "direction": "右", "amount_mm": 9}),
    ("C00004を右に10mm", {"position": "C00003", "direction": "右", "amount_mm": 10}),
    ("C00004を右に10mm", {"position": "C00004", "direction": "左", "amount_mm": 10}),
    ("C00004とC00005を右に10mm", None),
    ("C00004を右に十ミリ", None),
    ("C00004を右に10mmと上に2mm", None),
    ("C00004を右に-10mm", None),
    ("C00004を右に半分", None),
])
def test_interpretation_must_match_unambiguous_user_request(text, answer):
    s = session()
    s.set_policy(policy(s))
    with pytest.raises(PreviewError):
        propose(s, text, answer)
    assert s.state()["candidate"] is None


def test_same_utterance_cannot_be_retried_after_rejection():
    s = session()
    s.set_policy(policy(s))
    token = s.begin_input("C00004")
    with pytest.raises(PreviewError):
        s.propose(token, "右に30mm", lambda *_: {})
    with pytest.raises(PreviewError, match="新しい入力"):
        s.propose(token, "右に1mm", lambda *_: {})


def test_right_mapping_is_not_assumed():
    s = session()
    p = policy(s)
    p["right_axis"] = None
    s.set_policy(p)
    with pytest.raises(PreviewError, match="左右"):
        propose(s)


def test_failed_reload_clears_existing_state():
    s = session()
    s.set_policy(policy(s))
    propose(s)
    with pytest.raises(PreviewError):
        s.load(b"\xff", "utf-8")
    assert s.state()["candidate"] is None
    assert s.state()["current"] is None


def test_cp932_original_bytes_remain_in_memory():
    raw = RAW.decode().replace("\r\n", "\n").replace("NOP", "NOP\n' 日本語").replace("\n", "\r\n").encode("cp932")
    s = PreviewSession()
    s.load(raw, "cp932")
    assert s.original_bytes == raw
    assert s.state()["current"]["playable"]


def test_policy_is_copied_and_bound_to_baseline():
    s = session()
    p = policy(s)
    s.set_policy(p)
    p["positions"]["C00004"]["Y"]["max"] = 1000
    with pytest.raises(PreviewError):
        propose(s, "C00004を右に30mm", {"position": "C00004", "direction": "右", "amount_mm": 30})
    bad = copy.deepcopy(policy(s))
    bad["baseline_hash"] = "other"
    with pytest.raises(PreviewError):
        s.set_policy(bad)


def test_api_failure_cannot_leave_a_candidate():
    s = session()
    s.set_policy(policy(s))
    propose(s)
    def fail(*_):
        raise PreviewError("Claude APIに接続できません")
    token = s.begin_input("C00004")
    with pytest.raises(PreviewError):
        s.propose(token, "C00004を右に10mm", fail)
    assert s.state()["candidate"] is None
