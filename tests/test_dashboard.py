import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from promptledger.cli import main
from promptledger.core import PromptLedger
from promptledger.dashboard import api
from promptledger.dashboard.server import create_handler


def _seed_dashboard_ledger(tmp_path):
    ledger = PromptLedger(db_path=tmp_path / "promptledger.db")
    ledger.init()
    ledger.add(
        "alpha",
        "System prompt one",
        reason="initial",
        tags=["core", "draft"],
        env="dev",
        collection="support-bot",
        role="system",
    )
    ledger.add(
        "alpha",
        "System prompt two with guardrails",
        reason="guardrails",
        tags=["core"],
        env="prod",
        collection="support-bot",
        role="system",
    )
    ledger.add(
        "beta",
        "Evaluation prompt",
        tags=["eval"],
        env="staging",
        collection="quality",
        role="eval",
    )
    ledger.set_label("alpha", 2, "prod")
    ledger.set_marker("alpha", 2, "stable")
    return ledger


def test_dashboard_prompt_endpoints_return_expected_shapes(tmp_path):
    ledger = _seed_dashboard_ledger(tmp_path)

    prompts = api.list_prompts(ledger)
    prompt = api.get_prompt(ledger, "alpha")
    versions = api.get_versions(ledger, "alpha")
    version = api.get_version(ledger, "alpha", 2)

    assert {item["prompt_id"] for item in prompts["prompts"]} == {"alpha", "beta"}
    assert prompts["facets"]["collections"] == ["quality", "support-bot"]
    assert prompt["latest"]["version"] == 2
    assert prompt["latest"]["updated_at"] == prompt["latest"]["created_at"]
    assert "guardrails" in prompt["latest"]["content_preview"]
    assert prompt["version_count"] == 2
    assert [item["version"] for item in versions["versions"]] == [2, 1]
    assert version["content"] == "System prompt two with guardrails"
    assert version["labels"] == ["prod"]
    assert version["markers"] == ["stable"]


def test_dashboard_search_filters_by_metadata_marker_and_label(tmp_path):
    ledger = _seed_dashboard_ledger(tmp_path)

    by_collection = api.search_prompts(ledger, collection="support-bot")
    by_marker = api.search_prompts(ledger, marker="stable")
    by_label = api.search_prompts(ledger, label="prod")
    by_text_and_role = api.search_prompts(ledger, contains="Evaluation", role="eval")

    assert by_collection["count"] == 2
    assert [item["version"] for item in by_marker["results"]] == [2]
    assert [item["version"] for item in by_label["results"]] == [2]
    assert by_text_and_role["count"] == 1
    assert by_text_and_role["results"][0]["prompt_id"] == "beta"


def test_dashboard_stats(tmp_path):
    ledger = _seed_dashboard_ledger(tmp_path)

    stats = api.stats(ledger)

    assert stats == {
        "prompt_ids": 2,
        "versions": 3,
        "collections": 2,
        "roles": 2,
        "marked_versions": 1,
    }


def test_dashboard_command_wiring(monkeypatch):
    calls = []

    def fake_launch_dashboard(host, port, open_browser):
        calls.append({"host": host, "port": port, "open_browser": open_browser})

    monkeypatch.setattr("promptledger.cli.launch_dashboard", fake_launch_dashboard)

    result = main(["dashboard", "--host", "127.0.0.1", "--port", "9999", "--no-open"])

    assert result == 0
    assert calls == [{"host": "127.0.0.1", "port": 9999, "open_browser": False}]


def _request_json(base_url: str, path: str, method: str = "GET"):
    request = Request(f"{base_url}{path}", method=method)
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_dashboard_marker_post_and_delete_endpoint(tmp_path):
    ledger = _seed_dashboard_ledger(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(ledger))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        posted = _request_json(
            base_url,
            "/api/prompts/beta/versions/1/markers/milestone",
            method="POST",
        )
        assert posted["ok"] is True
        assert posted["version"]["markers"] == ["milestone"]
        assert api.get_version(ledger, "beta", 1)["markers"] == ["milestone"]

        deleted = _request_json(
            base_url,
            "/api/prompts/beta/versions/1/markers/milestone",
            method="DELETE",
        )
        assert deleted["ok"] is True
        assert deleted["version"]["markers"] == []
        assert api.get_version(ledger, "beta", 1)["markers"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_marker_endpoint_rejects_invalid_marker(tmp_path):
    ledger = _seed_dashboard_ledger(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(ledger))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            _request_json(base_url, "/api/prompts/beta/versions/1/markers/gold", method="POST")
        except HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
            assert "Unsupported marker" in payload["error"]
        else:
            raise AssertionError("Expected invalid marker request to fail.")
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_marker_update_reflected_in_filter(tmp_path):
    ledger = _seed_dashboard_ledger(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(ledger))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        before = _request_json(base_url, "/api/search?marker=milestone")
        assert before["count"] == 0

        _request_json(base_url, "/api/prompts/beta/versions/1/markers/milestone", method="POST")
        after = _request_json(base_url, "/api/search?marker=milestone")
        assert after["count"] == 1
        assert after["results"][0]["prompt_id"] == "beta"
        assert after["results"][0]["markers"] == ["milestone"]
    finally:
        server.shutdown()
        server.server_close()
