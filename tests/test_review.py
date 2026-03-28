import hashlib
import json

from promptledger import db
from promptledger.core import PromptLedger
from promptledger.review import summarize_semantic_changes
from promptledger.ui import _review_badges, _review_metadata_rows


def _summaries(items) -> list[str]:
    return [item.summary for item in items]


def test_review_resolves_version_to_version(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "Write a short answer.")
    ledger.add("demo", "Write a detailed answer.")

    review = ledger.review("demo", 1, 2)
    assert review.from_ref.ref_kind == "version"
    assert review.from_ref.resolved_version == 1
    assert review.to_ref.resolved_version == 2


def test_review_resolves_label_to_version(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "one")
    ledger.add("demo", "two")
    ledger.set_label("demo", 1, "prod")

    review = ledger.review("demo", "prod", 2)
    assert review.from_ref.ref_kind == "label"
    assert review.from_ref.resolved_version == 1
    assert review.to_ref.ref_kind == "version"


def test_review_resolves_label_to_label(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "one")
    ledger.add("demo", "two")
    ledger.set_label("demo", 1, "prod")
    ledger.set_label("demo", 2, "staging")

    review = ledger.review("demo", "prod", "staging")
    assert review.from_ref.ref_kind == "label"
    assert review.to_ref.ref_kind == "label"
    assert review.label_context["labels_by_version"][1] == ["prod"]
    assert review.label_context["labels_by_version"][2] == ["staging"]


def test_semantic_summary_detects_tone_constraint_and_format():
    old = "Write a friendly answer in bullets."
    new = "Please provide a professional response. You must return JSON only."
    summaries = _summaries(summarize_semantic_changes(old, new))
    assert "Tone became more formal." in summaries
    assert "Constraints tightened." in summaries
    assert "Output format changed from bullets to json." in summaries


def test_semantic_summary_detects_length_and_safety_and_refusal():
    old = "Answer the question."
    new = (
        "Answer the question in exactly 3 bullets. Follow safety policy. "
        "Refuse harmful requests."
    )
    summaries = _summaries(summarize_semantic_changes(old, new))
    assert "Length requirements were added." in summaries
    assert "Safety-related instructions were added or strengthened." in summaries
    assert "Refusal or policy wording became more explicit." in summaries


def test_semantic_summary_stays_conservative_for_noisy_change():
    old = "Summarize the document."
    new = "Summarize the provided document carefully."
    assert summarize_semantic_changes(old, new) == []


def test_review_handles_same_version(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "same")

    review = ledger.review("demo", 1, 1)
    assert review.text_changed is False
    assert any(item.code == "same-version" for item in review.warnings)


def test_review_metadata_only_change_no_semantic_change(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    content = "same content"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with db.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("demo", 1, content, content_hash, "first", None, None, "dev", None, "2024-01-01T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("demo", 2, content, content_hash, "second", None, None, "prod", None, "2024-01-01T00:00:01Z"),
        )
        conn.commit()

    review = ledger.review("demo", 1, 2)
    assert review.semantic_summary == []
    assert [item.field for item in review.metadata_changes] == ["reason", "env"]
    assert any(item.code == "metadata-only" for item in review.warnings)


def test_diff_summary_ignores_newline_only_changes(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    content_crlf = "line1\r\nline2"
    content_lf = "line1\nline2"
    with db.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO prompt_versions (
                prompt_id, version, content, content_hash, reason, author, tags, env, metrics, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "demo",
                1,
                content_crlf,
                hashlib.sha256(content_crlf.encode("utf-8")).hexdigest(),
                None,
                None,
                None,
                None,
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
                "demo",
                2,
                content_lf,
                hashlib.sha256(content_lf.encode("utf-8")).hexdigest(),
                None,
                None,
                None,
                None,
                json.dumps({"score": 2}),
                "2024-01-01T00:00:01Z",
            ),
        )
        conn.commit()

    summary = ledger.diff("demo", 1, 2, mode="summary")
    assert summary == "No confident semantic change detected."


def test_markdown_export_is_deterministic(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "Write a friendly answer in bullets.", reason="first", env="dev")
    ledger.add("demo", "Please provide JSON only.", reason="second", env="prod")
    ledger.set_label("demo", 1, "prod")
    ledger.set_label("demo", 2, "staging")

    first = ledger.export_review_markdown("demo", "prod", "staging")
    second = ledger.export_review_markdown("demo", "prod", "staging")
    assert first == second
    assert "# Prompt Review: `demo`" in first
    assert "## Reviewer notes" in first


def test_ui_review_helpers(tmp_path):
    ledger = PromptLedger(root=tmp_path)
    ledger.init()
    ledger.add("demo", "Answer plainly.")
    ledger.add("demo", "Answer plainly in exactly 2 bullets.", env="prod")

    review = ledger.review("demo", 1, 2)
    badges = _review_badges(review)
    rows = _review_metadata_rows(review)

    assert isinstance(badges, list)
    assert rows == [{"field": "env", "from": "(empty)", "to": "prod"}]
