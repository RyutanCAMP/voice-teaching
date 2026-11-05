"""Claude APIにつながるかを確かめる小さなプログラム。

使い方（リポジトリのフォルダで）:
    python tools/check_api.py

- .env ファイルの ANTHROPIC_API_KEY を読みます（キーは画面に表示しません）
- Claudeに短いあいさつを送り、返事が来れば「つながりました」と表示します
- 使う料金はごくわずかです（数十トークン）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("VT_MODEL", "claude-haiku-5-5")


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or "ここに" in key:
        print("× APIキーが見つかりません。.env ファイルに ANTHROPIC_API_KEY=… を書いてください。")
        return 1
    try:
        import anthropic
    except ImportError:
        print("× anthropic の部品が入っていません。次を実行してください： python -m pip install -r requirements.txt")
        return 1
    print(f"… Claudeに接続しています（モデル：{MODEL}）")
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=50,
            messages=[{"role": "user", "content": "「接続できました」とだけ日本語で答えてください。"}],
        )
    except anthropic.AuthenticationError:
        print("× APIキーが正しくありません。キーをもう一度コピーして .env に貼り直してください。")
        return 1
    except anthropic.APIConnectionError:
        print("× インターネット経由でClaudeにつながりません。社内ネットワークの制限の可能性があります。")
        return 1
    except anthropic.NotFoundError:
        print(f"× モデル名 {MODEL} が見つかりません。クロに知らせてください。")
        return 1
    except anthropic.APIError as e:
        print(f"× エラーが出ました：{type(e).__name__}。この表示をクロに送ってください。")
        return 1
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    print(f"○ つながりました。Claudeの返事：{text}")
    print(f"  使ったトークン：入力 {msg.usage.input_tokens} ／ 出力 {msg.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
