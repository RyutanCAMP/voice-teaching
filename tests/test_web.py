import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from voice_teaching.web import make_server


@pytest.fixture
def server():
    app = make_server(0)
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{app.server_port}"
    app.shutdown()
    app.server_close()
    thread.join()


def send(url, data=None, session=None, origin=None):
    headers = {}
    if session:
        headers["X-Session"] = session
    if origin:
        headers["Origin"] = origin
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers)
    try:
        response = urlopen(request)
    except HTTPError as response:
        return response.code, json.load(response)
    with response:
        return response.status, json.load(response)


def test_browser_sessions_are_isolated(server):
    _, first = send(server + "/api/bootstrap")
    _, second = send(server + "/api/bootstrap")
    code, loaded = send(server + "/api/load", {"dummy": True}, first["session"], server)
    assert code == 200 and loaded["state"]["current"]
    code, untouched = send(server + "/api/invalidate", {}, second["session"], server)
    assert code == 200 and untouched["state"]["current"] is None


def test_no_export_or_transfer_routes_even_after_loading(server):
    _, page = send(server + "/api/bootstrap")
    for name in ("export", "transfer", "start_robot"):
        code, _ = send(server + "/api/" + name, {}, page["session"], server)
        assert code == 404


def test_external_origin_and_missing_session_are_rejected(server):
    assert send(server + "/api/bootstrap", origin="https://example.com")[0] == 403
    assert send(server + "/api/load", {"dummy": True}, origin=server)[0] == 403


def test_invalid_base64_reload_clears_job(server):
    _, page = send(server + "/api/bootstrap")
    send(server + "/api/load", {"dummy": True}, page["session"], server)
    code, failed = send(server + "/api/load", {"bytes": "bad!"}, page["session"], server)
    assert code == 400 and failed["state"]["current"] is None
