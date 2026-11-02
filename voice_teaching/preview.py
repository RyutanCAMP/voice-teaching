"""UIと将来の接続層で共有するプレビュー専用処理。ファイル出力・実機接続は持たない。"""
from __future__ import annotations

import copy
import hashlib
import math
import re
import secrets
import unicodedata

from . import jbi


class PreviewError(ValueError):
    pass


NOTICE = "この図で離れて見えても、当たらないとは限りません。腕やツールの根元は描いていません。干渉・到達性・安全を保証しません。"
NUMBER = r"[+-]?\d+(?:\.\d+)?"
POSITION = re.compile(rf"(C\d{{5}})=({NUMBER}(?:,{NUMBER}){{5}})")
MOVE = re.compile(r"MOVL (C\d{5}) V=(\d+(?:\.\d+)?)")


def inspect_job(text: str) -> dict:
    """不明な座標は描かず、不明な命令は飛ばして再生しない。速度単位は推定しない。"""
    lines = text.splitlines()
    issues, points, moves = [], {}, []
    coordinate_ok = True
    if lines.count("//POS") != 1 or lines.count("//INST") != 1:
        return {"positions": {}, "moves": [], "instructions": [], "issues": ["POS／INSTの構成を確認できません。"], "playable": False, "name": ""}
    start, end = lines.index("//POS"), lines.index("//INST")
    pos_lines = lines[start + 1:end]
    if start >= end or pos_lines.count("///POSTYPE ROBOT") != 1 or pos_lines.count("///RECTAN") != 1:
        coordinate_ok = False
    for body in pos_lines:
        if not body:
            continue
        match = POSITION.fullmatch(body)
        if match:
            values = [float(v) for v in match[2].split(",")]
            if match[1] in points or not all(math.isfinite(v) for v in values):
                coordinate_ok = False
            points[match[1]] = values[:3]
        elif (body in ("///POSTYPE ROBOT", "///RECTAN") or
              re.fullmatch(r"///NPOS \d+(?:,\d+){5}", body) or
              re.fullmatch(r"///TOOL \d+", body) or
              re.fullmatch(r"///RCONF \d+(?:,\d+){7}", body)):
            continue
        else:
            coordinate_ok = False
    if not coordinate_ok or not points:
        issues.append("座標形式が未対応・不明または重複しています。mmの位置・経路としては描画しません。")
        points = {}
    instructions = []
    for index, body in enumerate(lines[end + 1:], end + 2):
        if not body or body.startswith("'"):
            continue
        if body.startswith("///"):
            if not (re.fullmatch(r"///DATE .+", body) or body == "///ATTR SC,RW" or body == "///GROUP1 RB1"):
                issues.append(f"{index}行目：未対応の命令ヘッダーです。")
            continue
        instructions.append({"line": index, "text": body})
        match = MOVE.fullmatch(body)
        if match:
            if match[1] not in points:
                issues.append(f"{index}行目：移動先の座標を確認できません。")
            moves.append({"line": index, "position": match[1]})
        elif (body in ("NOP", "END") or re.fullmatch(r"TIMER T=\d+(?:\.\d+)?", body) or
              re.fullmatch(r"DOUT OT#\(\d+\) (ON|OFF)", body)):
            continue
        else:
            issues.append(f"{index}行目：未対応命令です。読み飛ばして再生しません。")
    bodies = [i["text"] for i in instructions]
    if not bodies or bodies[-1] != "END" or bodies.count("END") != 1:
        issues.append("終了命令の構成を確認できません。")
    return {"name": jbi.parse(text).name, "positions": points, "moves": moves,
            "instructions": instructions, "issues": issues,
            "playable": bool(points and len(moves) >= 2 and not issues)}


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise PreviewError("枠または指示の数値を確認できません。")
    return value


def request_facts(text, selected, names):
    """APIの解釈を検証する保守的な照合。自由文の意味を推測して変更しない。"""
    text = unicodedata.normalize("NFKC", text).strip()
    quantities = re.findall(r"(?<![\d.+-])(\d+(?:\.\d+)?)\s*(?:mm|ミリ)", text, re.I)
    if len(quantities) != 1 or re.search(r"[+\-]\s*\d|[%％]|[一二三四五六七八九十百千万半]", text):
        raise PreviewError("1つの位置・方向・算用数字の量（mm／ミリ）で指示してください。")
    targets = re.findall(r"C\d{5}", text, re.I)
    if len(targets) > 1:
        raise PreviewError("位置は1つずつ指定してください。")
    if targets:
        target = targets[0].upper()
    elif any(word in text for word in ("この位置", "選択した位置", "選択位置")):
        target = selected
    else:
        raise PreviewError("位置番号か「この位置」を指定してください。")
    if target not in names:
        raise PreviewError("対象の位置番号を確認してください。")
    directions = [d for d in ("右", "左", "上", "下") if d in text]
    if len(directions) != 1:
        raise PreviewError("右・左・上・下の1方向を指定してください。")
    # 追加の操作・指示が混ざる場合は保留。対応する文型を明示して狭く受ける。
    pattern = r"(?:C\d{5}|この位置|選択した位置|選択位置)を(?:右|左|上|下)(?:に|へ)\s*\d+(?:\.\d+)?\s*(?:mm|ミリ)(?:動かして|移動して|ずらして|上げて|下げて)?[。.!！]?"
    if not re.fullmatch(pattern, text, re.I):
        raise PreviewError("指示を確認してください。例：C00004を右に10ミリ動かして")
    amount = float(quantities[0])
    if not math.isfinite(amount) or amount <= 0:
        raise PreviewError("変更量は正の有限な数値で指定してください。")
    return {"position": target, "direction": directions[0], "amount_mm": amount}


class PreviewSession:
    def __init__(self):
        self.clear()

    def clear(self):
        self.original_bytes = b""
        self.original_text = self.text = ""
        self.policy = self.candidate = self.input_context = None
        self.history = []
        self.revision = secrets.token_hex(16)

    def load(self, raw: bytes, encoding: str):
        self.clear()
        if encoding not in ("utf-8", "cp932") or not raw or len(raw) > 2_000_000:
            raise PreviewError("文字コード（UTF-8／CP932）とファイルの大きさを確認してください。")
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeError:
            raise PreviewError("指定の文字コードで読み込めません。文字コードを選び直してください。") from None
        if not text.startswith("/JOB\n") and not text.startswith("/JOB\r\n"):
            raise PreviewError("JBIの先頭行（/JOB）を確認してください。")
        self.original_bytes = bytes(raw)
        self.original_text = self.text = text

    def state(self):
        return {"current": inspect_job(self.text) if self.text else None,
                "baseline_hash": hashlib.sha256(self.original_bytes).hexdigest(),
                "candidate": copy.deepcopy(self.candidate),
                "policy": copy.deepcopy(self.policy), "history": copy.deepcopy(self.history),
                "revision": self.revision, "notice": NOTICE, "export_enabled": False,
                "robot_model": "未設定：HC20本体の関節動作は表示していません。"}

    def set_policy(self, policy):
        self.policy = self.candidate = self.input_context = None
        if not isinstance(policy, dict) or policy.get("preview_only") is not True:
            raise PreviewError("プレビュー専用の枠を指定してください。実機用の枠とは扱いません。")
        if policy.get("baseline_hash") != self.state()["baseline_hash"] or not self.text:
            raise PreviewError("枠の基準ファイルが一致しません。専門家の確認が必要です。")
        if policy.get("right_axis") not in (None, "X", "Y") or type(policy.get("right_sign")) is not int or policy["right_sign"] not in (-1, 1):
            raise PreviewError("左右の軸と向きの設定を確認してください。")
        positions = policy.get("positions")
        if not isinstance(positions, dict) or not positions:
            raise PreviewError("許可する位置と枠が必要です。")
        for name, axes in positions.items():
            if name not in inspect_job(self.text)["positions"] or not isinstance(axes, dict) or not axes:
                raise PreviewError("枠の位置番号を確認してください。")
            for axis, bounds in axes.items():
                if axis not in jbi.AXES or not isinstance(bounds, dict) or set(bounds) != {"min", "max", "step"}:
                    raise PreviewError("枠の軸と下限・上限・1回の量を確認してください。")
                low, high, step = (_number(bounds[k]) for k in ("min", "max", "step"))
                if not low <= 0 <= high or step <= 0:
                    raise PreviewError("枠の数値の順序を確認してください。")
        self.policy = copy.deepcopy(policy)

    def begin_input(self, selected):
        self.candidate = self.input_context = None
        if not self.text or selected not in inspect_job(self.text)["positions"]:
            raise PreviewError("読込済みの位置を選択してください。")
        token = secrets.token_hex(16)
        self.input_context = (token, selected, self.revision)
        return token

    def invalidate(self):
        self.candidate = self.input_context = None

    def propose(self, token, text, interpreter):
        self.candidate = None
        context, self.input_context = self.input_context, None  # 成否にかかわらず1回だけ
        if not context or token != context[0] or self.revision != context[2]:
            raise PreviewError("新しい入力からやり直してください。")
        if not self.policy:
            raise PreviewError("専門家の枠が未設定のため、変更案を作りません。")
        view = inspect_job(self.text)
        if not view["playable"]:
            raise PreviewError("未対応・不明な形式があるため、このジョブは変更しません。")
        facts = request_facts(text, context[1], view["positions"])
        answer = interpreter(text, context[1], list(view["positions"]))
        if not isinstance(answer, dict) or set(answer) != set(facts):
            raise PreviewError("Claudeの解釈を確認できません。位置・方向・量を指定し直してください。")
        _number(answer["amount_mm"])
        if answer != facts:
            raise PreviewError("Claudeの解釈が入力と一致しません。変更案は作りません。")
        direction, name, amount = facts["direction"], facts["position"], facts["amount_mm"]
        axis, sign = "Z", 1 if direction == "上" else -1
        if direction in ("右", "左"):
            axis = self.policy["right_axis"]
            if axis is None:
                raise PreviewError("左右の軸が未設定です。専門家による確認が必要です。")
            sign = self.policy["right_sign"] * (1 if direction == "右" else -1)
        bounds = self.policy["positions"].get(name, {}).get(axis)
        if not bounds:
            raise PreviewError("この位置・軸の変更は枠で許可されていません。")
        if amount > bounds["step"]:
            raise PreviewError("1回の変更量が専門家の枠を超えます。")
        uses = [i for i, move in enumerate(view["moves"]) if move["position"] == name]
        if len(uses) != 1 or uses[0] == 0 or uses[0] == len(view["moves"]) - 1:
            raise PreviewError("共用位置・開始点・終了点の扱いが未確定のため、この位置は変更しません。")
        job = jbi.parse(self.text)
        changed = job.shift_position(name, axis, sign * amount)
        before, after = job.positions[name].xyz, changed.positions[name].xyz
        k = jbi.AXES[axis]
        actual = after[k] - before[k]
        if not math.isclose(actual, sign * amount, rel_tol=0, abs_tol=1e-9):
            raise PreviewError("元の桁数では指示量を保持できません。変更量を確認してください。")
        cumulative = after[k] - jbi.parse(self.original_text).positions[name].xyz[k]
        if not bounds["min"] <= cumulative <= bounds["max"]:
            raise PreviewError("基準からの累積変更が専門家の範囲を超えます。")
        changed_lines = [(n, old, new) for n, (old, new) in enumerate(zip(job.lines, changed.lines)) if old != new]
        if len(changed_lines) != 1 or changed_lines[0][0] != job.positions[name].line_index:
            raise PreviewError("対象以外の差分があるため、変更案を作りません。")
        i = uses[0]
        self.candidate = {"id": secrets.token_hex(16), "revision": self.revision,
                          "position": name, "axis": axis, "delta_mm": actual,
                          "before": list(before), "after": list(after),
                          "view": inspect_job(changed.render()),
                          "affected_segments": [[view["moves"][i - 1]["position"], name], [name, view["moves"][i + 1]["position"]]],
                          "diff": {"before": changed_lines[0][1].rstrip(), "after": changed_lines[0][2].rstrip()},
                          "confirmation": f"{name}の{axis}座標を{actual:+g} mm変更します。前後の区間も変わります。プレビュー案を承認しますか？"}
        return copy.deepcopy(self.candidate)

    def approve(self, candidate_id):
        c = self.candidate
        if not c or c["id"] != candidate_id or c["revision"] != self.revision:
            raise PreviewError("承認する候補が一致しません。再度確認してください。")
        changed = jbi.parse(self.text).shift_position(c["position"], c["axis"], c["delta_mm"])
        if inspect_job(changed.render()) != c["view"]:
            self.invalidate()
            raise PreviewError("候補の内容が変わっています。再度確認してください。")
        self.text = changed.render()
        self.history.append({"position": c["position"], "axis": c["axis"], "delta_mm": c["delta_mm"], "kind": "preview_only"})
        self.revision = secrets.token_hex(16)
        self.invalidate()
