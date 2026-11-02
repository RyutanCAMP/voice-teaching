"""127.0.0.1限定のプレビューUI。入力はメモリー内だけ。出力・転送ルートは存在しない。"""
import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer

from .claude_interpreter import ClaudeInterpreter
from .preview import PreviewError, PreviewSession

ROOT = Path(__file__).resolve().parent
DUMMY = ROOT.parent / "samples/dummy/DEMO_PLACE.JBI"
STATIC = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
          "/vendor/three.module.js": "vendor/three.module.js",
          "/vendor/three.core.js": "vendor/three.core.js",
          "/vendor/OrbitControls.js": "vendor/OrbitControls.js"}


def make_server(port=8765, interpreter=None):
    interpreter = interpreter or ClaudeInterpreter(os.environ.get("ANTHROPIC_API_KEY", ""), os.environ.get("ANTHROPIC_MODEL", ""))
    sessions = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # ファイル名・指示・API情報をログに残さない

        def reply(self, status, body, mime="application/json; charset=utf-8"):
            raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode() if not isinstance(body, bytes) else body
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def trusted(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected and self.headers.get("Origin", f"http://{expected}") == f"http://{expected}"

        def do_GET(self):
            if not self.trusted():
                return self.reply(403, {"error": "接続元を確認してください。"})
            if self.path == "/api/bootstrap":
                if len(sessions) >= 100:
                    return self.reply(429, {"error": "サーバーを再起動してください。"})
                key = secrets.token_hex(32)
                sessions[key] = PreviewSession()
                return self.reply(200, {"session": key, "claude_configured": getattr(interpreter, "configured", False), "state": sessions[key].state()})
            if self.path not in STATIC:
                return self.reply(404, {"error": "この操作はありません。"})
            path = ROOT / "static" / STATIC[self.path]
            return self.reply(200, path.read_bytes(), (mimetypes.guess_type(path.name)[0] or "application/octet-stream") + "; charset=utf-8")

        def do_POST(self):
            if not self.trusted() or self.headers.get("Content-Type") != "application/json":
                return self.reply(403, {"error": "接続元と入力形式を確認してください。"})
            session = sessions.get(self.headers.get("X-Session"))
            if session is None:
                return self.reply(403, {"error": "画面を開き直してください。"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 3_000_000:
                    raise PreviewError("入力サイズを確認してください。")
                data = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if self.path == "/api/clear":
                    session.clear()
                elif self.path == "/api/load":
                    # 読込失敗でも既存の候補を使い回さない
                    session.clear()
                    raw = DUMMY.read_bytes() if data.get("dummy") is True else base64.b64decode(data["bytes"], validate=True)
                    session.load(raw, data.get("encoding", "utf-8"))
                elif self.path == "/api/policy":
                    session.set_policy(data["policy"])
                elif self.path == "/api/begin":
                    token = session.begin_input(data["selected"])
                    return self.reply(200, {"input_token": token, "state": session.state()})
                elif self.path == "/api/invalidate":
                    session.invalidate()
                elif self.path == "/api/propose":
                    session.propose(data["input_token"], data["text"], interpreter)
                elif self.path == "/api/approve":
                    session.approve(data["candidate_id"])
                else:
                    return self.reply(404, {"error": "この操作はありません。出力・転送は未実装です。"})
                return self.reply(200, {"state": session.state()})
            except (PreviewError, ValueError, KeyError, TypeError):
                import sys
                error = sys.exception()
                session.invalidate()
                message = str(error) if isinstance(error, PreviewError) else "入力形式を確認してください。"
                return self.reply(400, {"error": message, "state": session.state()})

    return HTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    load_local_environment()
    server = make_server(args.port)
    print(f"Voice Teaching: http://127.0.0.1:{server.server_port} （プレビュー専用）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def load_local_environment():
    """ローカルの2つの設定だけ読む。コマンド展開や上書きは行わない。"""
    path = ROOT.parent / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    main()
