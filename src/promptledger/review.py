"""Review domain objects and heuristic semantic summaries."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


def _sorted_jsonish(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted_jsonish(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_jsonish(item) for item in value]
    return value


@dataclass(frozen=True)
class ReviewRef:
    input_ref: str
    resolved_version: int
    ref_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetadataChange:
    field: str
    old_value: Any
    new_value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "old_value": _sorted_jsonish(self.old_value),
            "new_value": _sorted_jsonish(self.new_value),
        }


@dataclass(frozen=True)
class SemanticChange:
    category: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewWarning:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewResult:
    prompt_id: str
    from_ref: ReviewRef
    to_ref: ReviewRef
    semantic_summary: list[SemanticChange]
    metadata_changes: list[MetadataChange]
    label_context: dict[str, Any]
    warnings: list[ReviewWarning]
    notes: list[str]
    text_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "from_ref": self.from_ref.to_dict(),
            "to_ref": self.to_ref.to_dict(),
            "semantic_summary": [item.to_dict() for item in self.semantic_summary],
            "metadata_changes": [item.to_dict() for item in self.metadata_changes],
            "label_context": _sorted_jsonish(self.label_context),
            "warnings": [item.to_dict() for item in self.warnings],
            "notes": list(self.notes),
            "text_changed": self.text_changed,
        }


_FORMAL_WORDS = {
    "ensure",
    "provide",
    "maintain",
    "assist",
    "therefore",
    "please",
    "professional",
    "formal",
}
_CASUAL_WORDS = {
    "friendly",
    "casual",
    "simple",
    "short",
    "quick",
    "chatty",
    "warm",
}
_STRICT_WORDS = {
    "must",
    "always",
    "never",
    "only",
    "exactly",
    "strictly",
    "required",
    "do not",
}
_SAFETY_WORDS = {
    "safe",
    "safety",
    "policy",
    "harm",
    "sensitive",
    "privacy",
    "refuse",
    "refusal",
}
_REFUSAL_WORDS = {
    "refuse",
    "decline",
    "cannot comply",
    "should not",
    "not allowed",
    "disallowed",
}
_BULLET_HINTS = ("bullet", "bullets", "- ", "* ", "•")
_TABLE_HINTS = ("table", "|", "columns")
_JSON_HINTS = ("json", "schema", "\"{", "{\"")


def summarize_semantic_changes(old_text: str, new_text: str) -> list[SemanticChange]:
    """Return conservative, rule-based change summaries."""
    old_norm = old_text.strip()
    new_norm = new_text.strip()
    if old_norm == new_norm:
        return []

    changes: list[SemanticChange] = []

    tone_change = _detect_tone_change(old_norm, new_norm)
    if tone_change:
        changes.append(SemanticChange(category="tone", summary=tone_change))

    constraint_change = _detect_constraint_change(old_norm, new_norm)
    if constraint_change:
        changes.append(SemanticChange(category="constraints", summary=constraint_change))

    format_change = _detect_output_format_change(old_norm, new_norm)
    if format_change:
        changes.append(SemanticChange(category="format", summary=format_change))

    specificity_change = _detect_specificity_change(old_norm, new_norm)
    if specificity_change:
        changes.append(SemanticChange(category="specificity", summary=specificity_change))

    safety_change = _detect_safety_change(old_norm, new_norm)
    if safety_change:
        changes.append(SemanticChange(category="safety", summary=safety_change))

    length_change = _detect_length_change(old_norm, new_norm)
    if length_change:
        changes.append(SemanticChange(category="length", summary=length_change))

    refusal_change = _detect_refusal_change(old_norm, new_norm)
    if refusal_change:
        changes.append(SemanticChange(category="refusal", summary=refusal_change))

    return changes


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"\b[\w'-]+\b", text)}


def _count_matches(text: str, terms: set[str]) -> int:
    lower = text.lower()
    count = 0
    for term in terms:
        if " " in term:
            count += lower.count(term)
        else:
            count += len(re.findall(rf"\b{re.escape(term)}\b", lower))
    return count


def _extract_length_constraints(text: str) -> list[str]:
    patterns = [
        r"\b\d+\s+(?:bullet|bullets|sentence|sentences|word|words|paragraph|paragraphs)\b",
        r"\b(?:brief|concise|detailed|short|long-form|long form)\b",
    ]
    found: list[str] = []
    lower = text.lower()
    for pattern in patterns:
        for match in re.findall(pattern, lower):
            if match not in found:
                found.append(match)
    return found


def _detect_tone_change(old_text: str, new_text: str) -> str | None:
    old_formal = _count_matches(old_text, _FORMAL_WORDS)
    new_formal = _count_matches(new_text, _FORMAL_WORDS)
    old_casual = _count_matches(old_text, _CASUAL_WORDS)
    new_casual = _count_matches(new_text, _CASUAL_WORDS)

    if new_formal >= old_formal + 2 and new_casual <= old_casual:
        return "Tone became more formal."
    if new_casual >= old_casual + 2 and new_formal <= old_formal:
        return "Tone softened."
    return None


def _detect_constraint_change(old_text: str, new_text: str) -> str | None:
    old_strict = _count_matches(old_text, _STRICT_WORDS)
    new_strict = _count_matches(new_text, _STRICT_WORDS)
    if new_strict >= old_strict + 2:
        return "Constraints tightened."
    if old_strict >= new_strict + 2:
        return "Constraints loosened."
    return None


def _classify_format(text: str) -> str | None:
    lower = text.lower()
    if any(hint in lower for hint in _JSON_HINTS):
        return "json"
    if any(hint in lower for hint in _TABLE_HINTS):
        return "table"
    if any(hint in lower for hint in _BULLET_HINTS):
        return "bullets"
    return None


def _detect_output_format_change(old_text: str, new_text: str) -> str | None:
    old_format = _classify_format(old_text)
    new_format = _classify_format(new_text)
    if old_format and new_format and old_format != new_format:
        return f"Output format changed from {old_format} to {new_format}."
    if old_format is None and new_format:
        return f"Output format now emphasizes {new_format}."
    if old_format and new_format is None:
        return f"Explicit {old_format} formatting guidance was removed."
    return None


def _specificity_score(text: str) -> int:
    lower = text.lower()
    score = len(re.findall(r"\b\d+\b", lower))
    score += _count_matches(lower, {"exactly", "specific", "step-by-step", "include", "using"})
    return score


def _detect_specificity_change(old_text: str, new_text: str) -> str | None:
    old_score = _specificity_score(old_text)
    new_score = _specificity_score(new_text)
    word_delta = len(_tokenize(new_text)) - len(_tokenize(old_text))
    if new_score >= old_score + 2 and word_delta >= 2:
        return "Prompt became more specific."
    if old_score >= new_score + 2 and word_delta <= -2:
        return "Prompt became broader."
    return None


def _detect_safety_change(old_text: str, new_text: str) -> str | None:
    old_safety = _count_matches(old_text, _SAFETY_WORDS)
    new_safety = _count_matches(new_text, _SAFETY_WORDS)
    if new_safety >= old_safety + 2:
        return "Safety-related instructions were added or strengthened."
    if old_safety >= new_safety + 2:
        return "Safety-related instructions were removed or weakened."
    return None


def _detect_length_change(old_text: str, new_text: str) -> str | None:
    old_constraints = _extract_length_constraints(old_text)
    new_constraints = _extract_length_constraints(new_text)
    if old_constraints == new_constraints:
        return None
    if new_constraints and not old_constraints:
        return "Length requirements were added."
    if old_constraints and not new_constraints:
        return "Length requirements were removed."
    if new_constraints and old_constraints:
        return (
            "Length requirements changed: "
            + ", ".join(old_constraints)
            + " -> "
            + ", ".join(new_constraints)
            + "."
        )
    return None


def _detect_refusal_change(old_text: str, new_text: str) -> str | None:
    old_refusal = _count_matches(old_text, _REFUSAL_WORDS)
    new_refusal = _count_matches(new_text, _REFUSAL_WORDS)
    if new_refusal >= old_refusal + 1:
        return "Refusal or policy wording became more explicit."
    if old_refusal >= new_refusal + 1:
        return "Refusal or policy wording became less explicit."
    return None
