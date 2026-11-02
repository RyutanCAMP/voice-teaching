import json
from unittest.mock import patch
import pytest
from voice_teaching.claude_interpreter import ClaudeInterpreter
from voice_teaching.preview import PreviewError


def test_missing_credentials_stops_without_fallback():
    with pytest.raises(PreviewError, match="未設定"):
        ClaudeInterpreter("", "")("この位置を上に10mm", "C00004", ["C00004"])


def test_tool_input_only_is_returned_and_job_bytes_are_not_sent():
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, *_):
            return json.dumps({"stop_reason": "tool_use", "content": [
                {"type": "text", "text": "安全です"},
                {"type": "tool_use", "name": "propose_position", "input": {
                    "position": "C00004", "direction": "上", "amount_mm": 10}}]}).encode()
    with patch("voice_teaching.claude_interpreter.urlopen", return_value=Response()) as send:
        result = ClaudeInterpreter("test-key", "test-model")("この位置を上に10mm", "C00004", ["C00004"])
    request = send.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert payload["model"] == "test-model"
    assert "/JOB" not in request.data.decode()
    assert result["amount_mm"] == 10
    assert "text" not in result


def test_network_failure_is_fixed_message_without_secret():
    with patch("voice_teaching.claude_interpreter.urlopen", side_effect=OSError("SECRET")):
        with pytest.raises(PreviewError, match="接続") as error:
            ClaudeInterpreter("test-key", "test-model")("この位置を上に10mm", "C00004", [])
    assert "SECRET" not in str(error.value)
