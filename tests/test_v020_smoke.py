import json
import hashlib

from promptledger.core import PromptLedger
from promptledger import db


def test_v020_smoke(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("PROMPTLEDGER_HOME", str(home))
    ledger = PromptLedger()
    ledger.init()

    ledger.add("alpha", "line1\nline2", reason="first", env="dev", tags=["a"])
    ledger.add("alpha", "line1\nline3", reason="second", env="prod", tags=["b"])
    ledger.set_label("alpha", 1, "prod")
    ledger.set_label("alpha", 2, "staging")
    ledger.set_label("alpha", 2, "prod")

    events = ledger.list_label_events(prompt_id="alpha", label="prod")
    assert len(events) == 2
    assert events[0]["new_version"] == 2

    status = ledger.status()
    assert status["alpha"]["latest_version"] == 2
    assert status["alpha"]["labels"]["prod"] == 2

    unified = ledger.diff("alpha", 1, 2, mode="unified")
    context = ledger.diff("alpha", 1, 2, mode="context")
    ndiff = ledger.diff("alpha", 1, 2, mode="ndiff")
    summary = ledger.diff("alpha", 1, 2, mode="summary")
    assert unified
    assert context
    assert ndiff
    assert summary == "No confident semantic change detected."

    content = "same content"
    hash_value = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with db.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "meta",
                1,
                content,
                hash_value,
                "first",
                "alice",
                json.dumps(["a"]),
                "dev",
                json.dumps({"score": 1}),
                "2024-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "meta",
                2,
                content,
                hash_value,
                "second",
                "alice",
                json.dumps(["b"]),
                "prod",
                json.dumps({"score": 2}),
                "2024-01-01T00:00:01Z",
            ),
        )
        conn.commit()

    meta_diff = ledger.diff("meta", 1, 2, mode="metadata")
    assert meta_diff

    ledger.add(
        "review-demo",
        "Write a friendly answer in bullets.",
        reason="draft",
        env="dev",
        tags=["draft"],
    )
    ledger.add(
        "review-demo",
        "Please provide a professional response in JSON only.",
        reason="release",
        env="prod",
        tags=["release"],
    )
    ledger.set_label("review-demo", 1, "staging")
    ledger.set_label("review-demo", 2, "prod")

    review = ledger.review("review-demo", "staging", "prod")
    assert review.from_ref.ref_kind == "label"
    assert review.to_ref.resolved_version == 2
    assert [item.field for item in review.metadata_changes] == ["reason", "tags", "env"]
    assert any(item.summary == "Tone became more formal." for item in review.semantic_summary)
    assert any(item.summary == "Output format changed from bullets to json." for item in review.semantic_summary)

    review_markdown_a = ledger.export_review_markdown("review-demo", "staging", "prod")
    review_markdown_b = ledger.export_review_markdown("review-demo", "staging", "prod")
    assert review_markdown_a == review_markdown_b
    assert "# Prompt Review: `review-demo`" in review_markdown_a
