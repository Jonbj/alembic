#!/usr/bin/env python3
"""Evidence-bound literature extraction on the two local Qwen nodes.

The script never lets a model add sources or persist an unsupported quotation.
Outputs are append-only JSONL and safe to resume after interruption.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import re
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


NODE1 = "http://192.168.178.184:8080/v1/chat/completions"
NODE2 = "http://192.168.178.164:8080/v1/chat/completions"
MODEL1 = "qwen3.8-27b-implementer"
MODEL2 = "qwen3.8-27b-reviewer"
PROTOCOL_VERSION = 4
ALLOWED_STANCES = {"SUPPORTS", "CONTRADICTS", "QUALIFIES", "METHOD_ONLY"}
ALLOWED_HYPOTHESES = {f"H{i:02d}" for i in range(1, 23)}
ALLOWED_REVIEW_VERDICTS = {"SUPPORTED", "OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE"}
NODE2_BATCH_SIZE = 1
JSONL_LOCK = threading.Lock()
ChunkId = int | str


def normalize(text: str) -> str:
    """Normalize extracted text without changing its semantic content."""
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_text(row: dict[str, str], cache: Path) -> tuple[str, str]:
    """Fetch and mechanically extract one manifested source, with a local cache."""
    cache.mkdir(parents=True, exist_ok=True)
    raw_path = cache / f"{row['source_id']}.raw"
    text_path = cache / f"{row['source_id']}.txt"
    if text_path.exists():
        return text_path.read_text(errors="replace"), hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()

    response = requests.get(
        row["url"],
        headers={"User-Agent": "Alembic-S4-literature-audit/1.0 research contact"},
        timeout=180,
    )
    response.raise_for_status()
    raw_path.write_bytes(response.content)
    digest = hashlib.sha256(response.content).hexdigest()

    is_pdf = row["format"] == "pdf" or response.content[:4] == b"%PDF"
    if is_pdf:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as pdf:
            pdf.write(response.content)
            pdf.flush()
            proc = subprocess.run(
                ["pdftotext", "-layout", pdf.name, "-"],
                check=True,
                capture_output=True,
                text=True,
            )
            text = proc.stdout
    else:
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "form", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")

    text = normalize(text)
    if len(text) < 500:
        raise ValueError(f"extracted text too short: {len(text)} chars")
    text_path.write_text(text)
    return text, digest


def chunks(
    text: str, size: int = 9000, overlap: int = 500
) -> Iterator[tuple[int, str]]:
    """Yield stable overlapping source chunks with integer identifiers."""
    start = 0
    idx = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            paragraph = text.rfind("\n\n", start + size // 2, end)
            if paragraph > start:
                end = paragraph
        yield idx, text[start:end]
        idx += 1
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)


def is_context_overflow(exc: Exception) -> bool:
    """Return whether llama.cpp rejected a prompt for exceeding its context."""
    message = str(exc).lower()
    return (
        "exceeds the available context size" in message
        or "exceed_context_size" in message
    )


def split_for_context(text: str) -> tuple[str, str] | None:
    """Split one oversized work unit without changing global source chunk boundaries."""
    if len(text) < 1000:
        return None
    midpoint = len(text) // 2
    candidates = [
        text.rfind("\n\n", 0, midpoint),
        text.find("\n\n", midpoint),
        text.rfind("\n", 0, midpoint),
        text.find("\n", midpoint),
    ]
    split_at = min(
        (position for position in candidates if position > 0),
        key=lambda position: abs(position - midpoint),
        default=midpoint,
    )
    left = text[:split_at]
    right = text[split_at:]
    if not left or not right:
        return None
    if left + right != text:
        raise AssertionError("context split must preserve the parent byte-for-byte")
    return left, right


def hash_text(text: str) -> str:
    """Return the UTF-8 SHA-256 used for source and chunk coverage proofs."""
    return hashlib.sha256(text.encode()).hexdigest()


def node1_response_format(source_id: str, chunk_id: ChunkId) -> dict[str, Any]:
    """Build the strict JSON schema for one node-1 evidence card."""
    claim_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "claim_id",
            "hypotheses",
            "stance",
            "claim",
            "evidence_lines",
            "limitations",
            "transferability",
        ],
        "properties": {
            "claim_id": {"type": "string"},
            "hypotheses": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(ALLOWED_HYPOTHESES)},
            },
            "stance": {"type": "string", "enum": sorted(ALLOWED_STANCES)},
            "claim": {"type": "string"},
            "evidence_lines": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
            },
            "limitations": {"type": "string"},
            "transferability": {"type": "string"},
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "node1_evidence_card",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "chunk_id", "claims", "unverified_followups"],
                "properties": {
                    "source_id": {"const": source_id},
                    "chunk_id": {"const": chunk_id},
                    "claims": {"type": "array", "items": claim_schema},
                    "unverified_followups": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    }


def node2_response_format(source_id: str, claim_ids: list[str]) -> dict[str, Any]:
    """Build the strict JSON schema for one complete adversarial review batch."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "node2_review_batch",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "reviews"],
                "properties": {
                    "source_id": {"const": source_id},
                    "reviews": {
                        "type": "array",
                        "minItems": len(claim_ids),
                        "maxItems": len(claim_ids),
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "claim_id",
                                "verdict",
                                "reason_codes",
                                "reason",
                                "minimal_correction",
                            ],
                            "properties": {
                                "claim_id": {"type": "string", "enum": claim_ids},
                                "verdict": {
                                    "type": "string",
                                    "enum": sorted(ALLOWED_REVIEW_VERDICTS),
                                },
                                "reason_codes": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "reason": {"type": "string"},
                                "minimal_correction": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def chat(
    url: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Call one llama.cpp chat-completions endpoint and return message content."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "stream": False,
        "response_format": response_format or {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    response = requests.post(url, json=payload, timeout=4 * 60 * 60)
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    return data["choices"][0]["message"].get("content", "")


def parse_json(text: str) -> dict:
    """Parse one object, appending only missing closing containers once."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as original_error:
        repaired = append_missing_json_closers(text)
        if repaired == text:
            raise
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            raise original_error
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    return parsed


def append_missing_json_closers(text: str) -> str:
    """Append only structurally required `]`/`}` suffixes to truncated JSON."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]":
            if not stack or stack.pop() != char:
                return text
    stripped = text.rstrip()
    if in_string or not stack or not stripped or stripped[-1] in ",:":
        return text
    return stripped + "".join(reversed(stack))


def chat_json(
    url: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    response_format: dict[str, Any],
) -> dict:
    """Request strict schema-constrained JSON and parse it without model repair."""
    raw = chat(url, model, system, user, max_tokens, response_format)
    return parse_json(raw)


def append_jsonl(path: Path, item: dict) -> None:
    """Append one JSON object atomically with respect to coordinator threads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def invalidated_campaigns(path: Path) -> set[str]:
    """Return retry campaigns explicitly excluded by append-only audit events."""
    campaigns: set[str] = set()
    if not path.exists():
        return campaigns
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        campaign = item.get("invalidated_campaign")
        if (
            item.get("protocol_version") == PROTOCOL_VERSION
            and item.get("event") == "CAMPAIGN_INVALIDATED"
            and isinstance(campaign, str)
        ):
            campaigns.add(campaign)
    return campaigns


def completed_keys(
    path: Path,
    source_id: str,
    source_sha256: str,
    excluded_campaigns: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Return completed chunks for the current immutable representation."""
    excluded_campaigns = excluded_campaigns or set()
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
            if (
                item.get("protocol_version") == PROTOCOL_VERSION
                and item.get("source_id") == source_id
                and item.get("source_sha256") == source_sha256
                and item.get("retry_campaign") not in excluded_campaigns
            ):
                keys.add((str(item["source_id"]), str(item["chunk_id"])))
        except (json.JSONDecodeError, KeyError):
            continue
    return keys


def recovered_chunk_keys(
    ledger_path: Path,
    node1_path: Path,
    source_id: str,
    parent_chunks: dict[str, str],
    source_sha256: str,
    excluded_campaigns: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Return parents whose proof matches source text and persisted leaf cards."""
    excluded_campaigns = excluded_campaigns or set()
    if not ledger_path.exists() or not node1_path.exists():
        return set()

    events: list[dict[str, Any]] = []
    for line in ledger_path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("protocol_version") == PROTOCOL_VERSION
            and item.get("event") == "CHUNK_RECOVERED"
            and item.get("source_id") == source_id
            and item.get("source_sha256") == source_sha256
            and item.get("retry_campaign") not in excluded_campaigns
        ):
            events.append(item)

    cards: list[dict[str, Any]] = []
    for line in node1_path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("protocol_version") == PROTOCOL_VERSION
            and item.get("source_id") == source_id
            and item.get("source_sha256") == source_sha256
            and item.get("retry_campaign") not in excluded_campaigns
        ):
            cards.append(item)

    def has_leaf_card(child_id: str, child_sha256: str) -> bool:
        return any(
            str(card.get("chunk_id")) == child_id
            and card.get("chunk_sha256") == child_sha256
            for card in cards
        )

    sha256_pattern = re.compile(r"^[0-9a-f]{64}$")

    def verify_event(
        event: dict[str, Any], parent_text: str, ancestry: set[tuple[str, str, str]]
    ) -> bool:
        parent_id = str(event.get("chunk_id"))
        run_id = str(event.get("run_id"))
        campaign = str(event.get("retry_campaign"))
        identity = (parent_id, run_id, campaign)
        if identity in ancestry:
            return False
        parent_sha256 = hash_text(parent_text)
        if (
            event.get("coverage_verified") is not True
            or event.get("source_sha256") != source_sha256
            or event.get("parent_sha256") != parent_sha256
            or event.get("coverage_sha256") != parent_sha256
            or event.get("parent_chars") != len(parent_text)
        ):
            return False
        children = event.get("children")
        if not isinstance(children, list) or len(children) != 2:
            return False
        expected_start = 0
        next_ancestry = ancestry | {identity}
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                return False
            child_id = child.get("chunk_id")
            child_sha256 = child.get("sha256")
            start = child.get("start")
            end = child.get("end")
            if (
                child_id != f"{parent_id}.{index}"
                or type(start) is not int
                or type(end) is not int
                or start != expected_start
                or end <= start
                or end > len(parent_text)
                or not isinstance(child_sha256, str)
                or not sha256_pattern.fullmatch(child_sha256)
            ):
                return False
            child_text = parent_text[start:end]
            if hash_text(child_text) != child_sha256:
                return False
            if not has_leaf_card(child_id, child_sha256):
                nested = [
                    candidate
                    for candidate in events
                    if str(candidate.get("chunk_id")) == child_id
                ]
                if not any(
                    verify_event(candidate, child_text, next_ancestry)
                    for candidate in nested
                ):
                    return False
            expected_start = end
        return expected_start == len(parent_text)

    recovered: set[tuple[str, str]] = set()
    for event in events:
        chunk_id = str(event.get("chunk_id"))
        parent_text = parent_chunks.get(chunk_id)
        if parent_text is not None and verify_event(event, parent_text, set()):
            recovered.add((source_id, chunk_id))
    return recovered


def prior_claims(
    path: Path,
    source_id: str,
    source_sha256: str,
    excluded_campaigns: set[str] | None = None,
) -> list[dict]:
    """Return prior claims for the current immutable source representation."""
    excluded_campaigns = excluded_campaigns or set()
    if not path.exists():
        return []
    claims = []
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("source_id") == source_id
            and item.get("source_sha256") == source_sha256
            and item.get("protocol_version") == PROTOCOL_VERSION
            and item.get("retry_campaign") not in excluded_campaigns
        ):
            claims.extend(item.get("claims", []))
    return claims


def reviewed_claim_ids(
    path: Path,
    source_id: str,
    source_sha256: str,
    excluded_campaigns: set[str] | None = None,
) -> set[str]:
    """Return claim ids reviewed for the current source representation.

    Resume must be idempotent at claim level: a source may have gained claims from
    chunks that failed during an earlier pass, so batch ids alone are not stable.
    """
    excluded_campaigns = excluded_campaigns or set()
    if not path.exists():
        return set()
    claim_ids: set[str] = set()
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("protocol_version") != PROTOCOL_VERSION:
            continue
        if item.get("source_id") != source_id:
            continue
        if item.get("source_sha256") != source_sha256:
            continue
        if item.get("retry_campaign") in excluded_campaigns:
            continue
        for review in item.get("reviews", []):
            claim_id = review.get("claim_id")
            if isinstance(claim_id, str) and claim_id:
                claim_ids.add(claim_id)
    return claim_ids


def next_review_batch_id(
    path: Path,
    source_id: str,
) -> int:
    """Choose a monotonic per-source batch id for append-only review output."""
    if not path.exists():
        return 0
    batch_ids = []
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("protocol_version") != PROTOCOL_VERSION:
            continue
        if item.get("source_id") != source_id:
            continue
        try:
            batch_ids.append(int(item["batch_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return max(batch_ids, default=-1) + 1


NODE1_SYSTEM = """You are an evidence extraction worker, not a general researcher.
Use ONLY SOURCE_TEXT. Never rely on memory. Never invent a paper, result, number, method, or quote.
Return one JSON object and no other text. If there is no relevant evidence, return an empty claims list.
For every claim cite a short consecutive line range from the numbered SOURCE_TEXT.
The orchestrator, not you, will copy the quotation from those lines. Conservative qualification is mandatory."""


def node1_prompt(
    row: dict[str, str], chunk_id: ChunkId, text: str, hypothesis_registry: str
) -> str:
    """Build the evidence-bound extraction prompt for one source chunk."""
    numbered = "\n".join(
        f"L{line_no:04d}: {line}" for line_no, line in enumerate(text.splitlines(), 1)
    )
    return f"""SOURCE_ID: {row["source_id"]}
CHUNK_ID: {json.dumps(chunk_id)}
SOURCE_CLASS: {row["class"]}
TITLE: {row["title"]}

HYPOTHESIS_REGISTRY:
<<<
{hypothesis_registry}
>>>

Evaluate only hypotheses from HYPOTHESIS_REGISTRY. Output schema:
{{"source_id":"{row["source_id"]}","chunk_id":{json.dumps(chunk_id)},"claims":[{{"claim_id":"{row["source_id"]}-C{chunk_id}-01","hypotheses":["H02"],"stance":"SUPPORTS|CONTRADICTS|QUALIFIES|METHOD_ONLY","claim":"one cautious sentence","evidence_lines":[12,14],"limitations":"sample/method limits stated or inferable from this chunk","transferability":"what this can and cannot establish for S4"}}],"unverified_followups":["bibliographic hint only"]}}

Rules:
- A claim must be materially relevant to at least one H01-H22.
- Do not turn association into causality.
- Record horizon, sample, event type, long-only/long-short, provider and costs when present.
- A vendor backtest is industry evidence, not independent validation.
- If a fact is outside this chunk, omit it.
- evidence_lines must contain exactly [start_line, end_line], use 1 to 6 consecutive lines, and
  those lines must directly support the claim. Never cite a range merely because it is nearby.

NUMBERED_SOURCE_TEXT:
<<<
{numbered}
>>>"""


def validate_card(
    card: dict,
    row: dict[str, str],
    chunk_id: ChunkId,
    text: str,
) -> tuple[list[dict], list[dict]]:
    """Partition candidate claims into evidence-valid and rejected records."""
    if card.get("source_id") != row["source_id"] or str(
        card.get("chunk_id", "")
    ) != str(chunk_id):
        raise ValueError("node1 source or chunk identity mismatch")
    claims = card.get("claims")
    if not isinstance(claims, list):
        raise ValueError("node1 claims is not a list")
    followups = card.get("unverified_followups")
    if not isinstance(followups, list) or any(
        not isinstance(followup, str) for followup in followups
    ):
        raise ValueError("node1 unverified_followups is not a string list")
    valid, rejected = [], []
    lines = text.splitlines()
    seen_claim_ids: set[str] = set()
    expected_id = re.compile(
        rf"^{re.escape(row['source_id'])}-C{re.escape(str(chunk_id))}-[0-9]{{2}}$"
    )
    for claim in claims:
        reasons = []
        if not isinstance(claim, dict):
            rejected.append({"claim": claim, "reasons": ["INVALID_CLAIM_OBJECT"]})
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not expected_id.fullmatch(claim_id):
            reasons.append("INVALID_CLAIM_ID")
        elif claim_id in seen_claim_ids:
            reasons.append("DUPLICATE_CLAIM_ID")
        else:
            seen_claim_ids.add(claim_id)
        for field in ("claim", "limitations", "transferability"):
            if not isinstance(claim.get(field), str):
                reasons.append(f"INVALID_{field.upper()}")
        evidence_lines = claim.get("evidence_lines")
        start = end = -1
        if (
            not isinstance(evidence_lines, list)
            or len(evidence_lines) != 2
            or not all(type(n) is int for n in evidence_lines)
        ):
            reasons.append("INVALID_LINE_REFERENCE")
        else:
            start, end = evidence_lines
            if start < 1 or end < start or end > len(lines) or end - start > 5:
                reasons.append("INVALID_LINE_RANGE")
        if claim.get("stance") not in ALLOWED_STANCES:
            reasons.append("INVALID_STANCE")
        hypotheses = claim.get("hypotheses", [])
        if not hypotheses or any(h not in ALLOWED_HYPOTHESES for h in hypotheses):
            reasons.append("INVALID_HYPOTHESIS")
        if reasons:
            rejected.append({"claim": claim, "reasons": reasons})
            continue
        exact_evidence = normalize("\n".join(lines[start - 1 : end]))
        if not exact_evidence:
            rejected.append({"claim": claim, "reasons": ["EMPTY_REFERENCED_LINES"]})
            continue
        claim["evidence_quote"] = exact_evidence
        claim["evidence_context"] = normalize(
            "\n".join(lines[max(0, start - 3) : min(len(lines), end + 2)])
        )
        valid.append(claim)
    return valid, rejected


NODE2_SYSTEM = """You are an adversarial evidence reviewer. Review only the supplied claim,
exact quote, and surrounding context. Do not add facts or citations. Return one JSON object only.
Prefer AMBIGUOUS to guessing. Detect causal overclaim, sample/horizon mismatch, provider dependence,
pseudo-replication, and long-short to long-only transfer errors. Check every direction, comparison,
number, denominator, and inequality against the exact quote. A quote that supports only part of a
claim is not sufficient."""


def review_claims(source_id: str, claims: list[dict], hypothesis_registry: str) -> dict:
    """Ask node 2 to adversarially review one compact batch of claims."""
    compact = [
        {
            "claim_id": c.get("claim_id"),
            "hypotheses": c.get("hypotheses"),
            "stance": c.get("stance"),
            "claim": c.get("claim"),
            "evidence_quote": c.get("evidence_quote"),
            "evidence_context": c.get("evidence_context"),
            "limitations": c.get("limitations"),
            "transferability": c.get("transferability"),
        }
        for c in claims
    ]
    prompt = f"""SOURCE_ID: {source_id}
HYPOTHESIS_REGISTRY:
<<<
{hypothesis_registry}
>>>

Review every claim below. Output schema:
{{"source_id":"{source_id}","reviews":[{{"claim_id":"...","verdict":"SUPPORTED|OVERSTATED|AMBIGUOUS|NOT_APPLICABLE","reason_codes":["..."],"reason":"one concise sentence","minimal_correction":"corrected claim or empty"}}]}}

CLAIMS_AND_CONTEXT:
{json.dumps(compact, ensure_ascii=False)}"""
    claim_ids = [str(claim.get("claim_id")) for claim in claims]
    return chat_json(
        NODE2,
        MODEL2,
        NODE2_SYSTEM,
        prompt,
        900,
        node2_response_format(source_id, claim_ids),
    )


def review_batch_key(claims: list[dict]) -> str:
    """Return a stable identity for a set of claim IDs sent to node 2."""
    claim_ids = sorted(str(claim.get("claim_id", "")) for claim in claims)
    return hashlib.sha256("|".join(claim_ids).encode()).hexdigest()[:16]


def attempt_counts(
    path: Path,
    event: str,
    unit_field: str,
    retry_campaign: str | None = None,
) -> dict[tuple[str, str, str], int]:
    """Highest attempt per source digest/unit in one retry campaign."""
    counts: dict[tuple[str, str, str], int] = {}
    if not path.exists():
        return counts
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("protocol_version") != PROTOCOL_VERSION
            or item.get("event") != event
        ):
            continue
        if item.get("retry_campaign") != retry_campaign:
            continue
        source_id = item.get("source_id")
        source_sha256 = item.get("source_sha256")
        unit_id = item.get(unit_field)
        try:
            attempt = int(item.get("attempt", 0))
        except (TypeError, ValueError):
            continue
        if source_id is None or source_sha256 is None or unit_id is None:
            continue
        key = (str(source_id), str(source_sha256), str(unit_id))
        counts[key] = max(counts.get(key, 0), attempt)
    return counts


def split_candidate_keys(
    path: Path, retry_campaign: str | None = None
) -> set[tuple[str, str, str]]:
    """Return exhausted node-1 units whose persisted failure permits splitting."""
    candidates: set[tuple[str, str, str]] = set()
    if not path.exists():
        return candidates
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("protocol_version") != PROTOCOL_VERSION
            or item.get("event") != "NODE1_ATTEMPT_FAILED"
            or item.get("retry_campaign") != retry_campaign
            or item.get("split_eligible") is not True
        ):
            continue
        source_id = item.get("source_id")
        source_sha256 = item.get("source_sha256")
        chunk_id = item.get("chunk_id")
        if source_id is not None and source_sha256 is not None and chunk_id is not None:
            candidates.add((str(source_id), str(source_sha256), str(chunk_id)))
    return candidates


def terminal_sources(
    path: Path,
    source_id: str,
    source_sha256: str,
    excluded_campaigns: set[str] | None = None,
) -> set[str]:
    """Return a finalized source only when its current digest was finalized."""
    excluded_campaigns = excluded_campaigns or set()
    sources: set[str] = set()
    if not path.exists():
        return sources
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("protocol_version") != PROTOCOL_VERSION:
            continue
        if item.get("retry_campaign") in excluded_campaigns:
            continue
        event = item.get("event")
        completed = event in {"SOURCE_PASS_COMPLETE", "SOURCE_NO_RELEVANT_CLAIMS"}
        if (
            completed
            and item.get("source_id") == source_id
            and item.get("source_sha256") == source_sha256
        ):
            sources.add(source_id)
    return sources


def validate_review(review: dict, source_id: str, claims: list[dict]) -> None:
    """Reject incomplete or invented node2 review rows before persistence."""
    if review.get("source_id") != source_id:
        raise ValueError("node2 source identity mismatch")
    expected_ids = {claim.get("claim_id") for claim in claims}
    rows = review.get("reviews")
    if not isinstance(rows, list):
        raise ValueError("node2 reviews is not a list")
    required_fields = {
        "claim_id": str,
        "verdict": str,
        "reason_codes": list,
        "reason": str,
        "minimal_correction": str,
    }
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("node2 review row is not an object")
        for field, expected_type in required_fields.items():
            if not isinstance(row.get(field), expected_type):
                raise ValueError(f"node2 invalid or missing {field}")
        if any(not isinstance(code, str) for code in row["reason_codes"]):
            raise ValueError("node2 reason_codes is not a string list")
    actual_ids = [row.get("claim_id") for row in rows if isinstance(row, dict)]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("node2 returned duplicate claim ids")
    if set(actual_ids) != expected_ids:
        raise ValueError(
            "node2 claim coverage mismatch: "
            f"expected={sorted(str(item) for item in expected_ids)} "
            f"actual={sorted(str(item) for item in actual_ids)}"
        )
    invalid = [
        row.get("verdict")
        for row in rows
        if row.get("verdict") not in ALLOWED_REVIEW_VERDICTS
    ]
    if invalid:
        raise ValueError(f"node2 invalid verdicts: {invalid}")


def main() -> int:
    """Run or administratively invalidate one append-only coordinator campaign."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", default="/tmp/s4-literature-cache", type=Path)
    parser.add_argument(
        "--source", action="append", help="Run only selected source_id; repeatable"
    )
    parser.add_argument(
        "--retry-campaign",
        help="Append-only retry namespace for explicitly selected failed sources",
    )
    parser.add_argument(
        "--invalidate-campaign",
        help="Append an audit event excluding every artifact from this campaign",
    )
    parser.add_argument(
        "--invalidation-reason",
        help="Required explanation for --invalidate-campaign",
    )
    args = parser.parse_args()
    if args.retry_campaign and not args.source:
        parser.error("--retry-campaign requires at least one --source")
    if args.invalidate_campaign and not args.invalidation_reason:
        parser.error("--invalidate-campaign requires --invalidation-reason")
    if args.invalidate_campaign and args.retry_campaign:
        parser.error("campaign invalidation and retry cannot run together")

    node1_path = args.output_dir / "node1_cards.jsonl"
    node2_path = args.output_dir / "node2_reviews.jsonl"
    ledger_path = args.output_dir / "run_ledger.jsonl"
    hypothesis_path = args.manifest.parent / "HYPOTHESES.md"
    hypothesis_registry = hypothesis_path.read_text(encoding="utf-8")
    run_id = str(uuid.uuid4())

    def record_event(item: dict) -> None:
        """Append a ledger event with this run's retry provenance."""
        if args.retry_campaign:
            item = {**item, "retry_campaign": args.retry_campaign}
        append_jsonl(ledger_path, item)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock_handle = (args.output_dir / ".orchestrator.lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another S4 literature orchestrator already holds the output lock")
        return 2
    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(f"run_id={run_id}\n")
    lock_handle.flush()

    if args.invalidate_campaign:
        record_event(
            {
                "event": "CAMPAIGN_INVALIDATED",
                "protocol_version": PROTOCOL_VERSION,
                "run_id": run_id,
                "invalidated_campaign": args.invalidate_campaign,
                "reason": args.invalidation_reason,
                "ts": time.time(),
            }
        )
        return 0

    excluded_campaigns = invalidated_campaigns(ledger_path)
    if args.retry_campaign in excluded_campaigns:
        parser.error(f"retry campaign was invalidated: {args.retry_campaign}")

    record_event(
        {
            "event": "RUN_START",
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "hypothesis_sha256": hashlib.sha256(
                hypothesis_registry.encode()
            ).hexdigest(),
            "ts": time.time(),
        },
    )
    done: set[tuple[str, str]] = set()
    reviewed: set[str] = set()
    node1_failures = attempt_counts(
        ledger_path, "NODE1_ATTEMPT_FAILED", "chunk_id", args.retry_campaign
    )
    node2_failures = attempt_counts(
        ledger_path, "NODE2_REVIEW_FAILED", "batch_key", args.retry_campaign
    )
    node1_split_candidates = split_candidate_keys(ledger_path, args.retry_campaign)
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if args.source:
        selected = set(args.source)
        rows = [row for row in rows if row["source_id"] in selected]

    reviewed_lock = threading.Lock()
    review_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="s4-node2")
    source_results: list[dict] = []

    def run_review_batch(
        source_id: str,
        source_sha256: str,
        batch: list[dict],
        batch_id: int,
        batch_key: str,
    ) -> str | None:
        failure_key = (source_id, source_sha256, batch_key)
        attempts_used = node2_failures.get(failure_key, 0)
        for attempt in range(attempts_used + 1, 3):
            try:
                review = review_claims(source_id, batch, hypothesis_registry)
                validate_review(review, source_id, batch)
                review.update(
                    {
                        "model": MODEL2,
                        "source_sha256": source_sha256,
                        "batch_id": batch_id,
                        "batch_key": batch_key,
                        "attempt": attempt,
                        "run_id": run_id,
                        "ts": time.time(),
                    }
                )
                review["protocol_version"] = PROTOCOL_VERSION
                if args.retry_campaign:
                    review["retry_campaign"] = args.retry_campaign
                append_jsonl(node2_path, review)
                with reviewed_lock:
                    for item in review.get("reviews", []):
                        claim_id = item.get("claim_id")
                        if isinstance(claim_id, str) and claim_id:
                            reviewed.add(claim_id)
                return None
            except Exception as exc:
                node2_failures[failure_key] = attempt
                record_event(
                    {
                        "event": "NODE2_REVIEW_FAILED",
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "source_id": source_id,
                        "source_sha256": source_sha256,
                        "batch_id": batch_id,
                        "batch_key": batch_key,
                        "attempt": attempt,
                        "error": repr(exc),
                        "ts": time.time(),
                    },
                )
        return batch_key

    for row in rows:
        try:
            text, digest = fetch_text(row, args.cache_dir)
            record_event(
                {
                    "event": "SOURCE_READY",
                    "protocol_version": PROTOCOL_VERSION,
                    "run_id": run_id,
                    "source_id": row["source_id"],
                    "sha256": digest,
                    "chars": len(text),
                    "ts": time.time(),
                }
            )
        except Exception as exc:
            record_event(
                {
                    "event": "SOURCE_UNAVAILABLE",
                    "protocol_version": PROTOCOL_VERSION,
                    "run_id": run_id,
                    "source_id": row["source_id"],
                    "error": repr(exc),
                    "ts": time.time(),
                }
            )
            continue

        terminal = terminal_sources(
            ledger_path,
            row["source_id"],
            digest,
            excluded_campaigns,
        )
        if row["source_id"] in terminal:
            continue
        done.update(
            completed_keys(
                node1_path,
                row["source_id"],
                digest,
                excluded_campaigns,
            )
        )
        reviewed.update(
            reviewed_claim_ids(
                node2_path,
                row["source_id"],
                digest,
                excluded_campaigns,
            )
        )
        source_claims = prior_claims(
            node1_path,
            row["source_id"],
            digest,
            excluded_campaigns,
        )
        source_chunks = list(chunks(text))
        recovered = recovered_chunk_keys(
            ledger_path,
            node1_path,
            row["source_id"],
            {str(chunk_id): chunk_text for chunk_id, chunk_text in source_chunks},
            digest,
            excluded_campaigns,
        )
        pending_chunks = [
            (chunk_id, chunk_text)
            for chunk_id, chunk_text in source_chunks
            if (row["source_id"], str(chunk_id)) not in done | recovered
        ]
        with reviewed_lock:
            pending_reviews = [
                claim
                for claim in source_claims
                if claim.get("claim_id") not in reviewed
            ]

        def process_split(
            chunk_id: ChunkId,
            chunk_text: str,
            split: tuple[str, str],
        ) -> list[ChunkId]:
            """Persist a complete, hash-proven split and recursively run its children."""
            done_key = (row["source_id"], str(chunk_id))
            child_ids = [f"{chunk_id}.0", f"{chunk_id}.1"]
            parent_sha256 = hash_text(chunk_text)
            children = []
            offset = 0
            for child_id, child_text in zip(child_ids, split, strict=True):
                end = offset + len(child_text)
                children.append(
                    {
                        "chunk_id": child_id,
                        "start": offset,
                        "end": end,
                        "sha256": hash_text(child_text),
                    }
                )
                offset = end
            coverage_text = "".join(split)
            coverage_sha256 = hash_text(coverage_text)
            coverage_verified = coverage_text == chunk_text
            if not coverage_verified or coverage_sha256 != parent_sha256:
                raise AssertionError("split children do not cover their parent")
            record_event(
                {
                    "event": "CHUNK_SPLIT",
                    "protocol_version": PROTOCOL_VERSION,
                    "run_id": run_id,
                    "source_id": row["source_id"],
                    "source_sha256": digest,
                    "chunk_id": chunk_id,
                    "parent_sha256": parent_sha256,
                    "parent_chars": len(chunk_text),
                    "children": children,
                    "ts": time.time(),
                }
            )
            child_failures: list[ChunkId] = []
            for child_id, child_text in zip(child_ids, split, strict=True):
                child_failures.extend(process_chunk(child_id, child_text))
            if not child_failures:
                done.add(done_key)
                record_event(
                    {
                        "event": "CHUNK_RECOVERED",
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "source_id": row["source_id"],
                        "source_sha256": digest,
                        "chunk_id": chunk_id,
                        "parent_sha256": parent_sha256,
                        "parent_chars": len(chunk_text),
                        "children": children,
                        "coverage_sha256": coverage_sha256,
                        "coverage_verified": coverage_verified,
                        "ts": time.time(),
                    }
                )
            return child_failures

        def process_chunk(chunk_id: ChunkId, chunk_text: str) -> list[ChunkId]:
            """Persist one chunk, splitting on overflow or exhausted invalid output."""
            done_key = (row["source_id"], str(chunk_id))
            if done_key in done:
                return []
            failure_key = (row["source_id"], digest, str(chunk_id))
            attempts_used = node1_failures.get(failure_key, 0)
            if failure_key in node1_split_candidates:
                resume_split = split_for_context(chunk_text)
                if resume_split is not None:
                    return process_split(chunk_id, chunk_text, resume_split)
            for attempt in range(attempts_used + 1, 3):
                try:
                    card = chat_json(
                        NODE1,
                        MODEL1,
                        NODE1_SYSTEM,
                        node1_prompt(row, chunk_id, chunk_text, hypothesis_registry),
                        1200,
                        node1_response_format(row["source_id"], chunk_id),
                    )
                    valid, rejected = validate_card(card, row, chunk_id, chunk_text)
                    if card.get("claims") and not valid:
                        reasons = sorted(
                            {
                                reason
                                for rejected_claim in rejected
                                for reason in rejected_claim.get("reasons", [])
                            }
                        )
                        raise ValueError(f"all candidate claims rejected: {reasons}")
                    record = {
                        "source_id": row["source_id"],
                        "chunk_id": chunk_id,
                        "protocol_version": PROTOCOL_VERSION,
                        "run_id": run_id,
                        "source_sha256": digest,
                        "chunk_sha256": hashlib.sha256(chunk_text.encode()).hexdigest(),
                        "hypothesis_sha256": hashlib.sha256(
                            hypothesis_registry.encode()
                        ).hexdigest(),
                        "claims": valid,
                        "rejected_claims": rejected,
                        "unverified_followups": card.get("unverified_followups", []),
                        "attempt": attempt,
                        "model": MODEL1,
                    }
                    if args.retry_campaign:
                        record["retry_campaign"] = args.retry_campaign
                    append_jsonl(node1_path, record)
                    source_claims.extend(valid)
                    done.add(done_key)
                    return []
                except Exception as exc:
                    node1_failures[failure_key] = attempt
                    should_split = is_context_overflow(exc) or (
                        attempt == 2
                        and isinstance(exc, (json.JSONDecodeError, ValueError))
                    )
                    record_event(
                        {
                            "event": "NODE1_ATTEMPT_FAILED",
                            "protocol_version": PROTOCOL_VERSION,
                            "run_id": run_id,
                            "source_id": row["source_id"],
                            "source_sha256": digest,
                            "chunk_id": chunk_id,
                            "attempt": attempt,
                            "error": repr(exc),
                            "split_eligible": should_split,
                            "ts": time.time(),
                        }
                    )
                    split = split_for_context(chunk_text) if should_split else None
                    if split is not None:
                        return process_split(chunk_id, chunk_text, split)
            record_event(
                {
                    "event": "CHUNK_FAILED",
                    "protocol_version": PROTOCOL_VERSION,
                    "run_id": run_id,
                    "source_id": row["source_id"],
                    "chunk_id": chunk_id,
                    "ts": time.time(),
                }
            )
            return [chunk_id]

        failed_chunks: list[ChunkId] = []
        for chunk_id, chunk_text in pending_chunks:
            failed_chunks.extend(process_chunk(chunk_id, chunk_text))

        with reviewed_lock:
            pending_reviews = [
                claim
                for claim in source_claims
                if claim.get("claim_id") not in reviewed
            ]
        review_futures: list[tuple[str, Future[str | None]]] = []
        if pending_reviews:
            first_batch_id = next_review_batch_id(node2_path, row["source_id"])
            for batch_offset, start in enumerate(
                range(0, len(pending_reviews), NODE2_BATCH_SIZE)
            ):
                batch_id = first_batch_id + batch_offset
                batch = pending_reviews[start : start + NODE2_BATCH_SIZE]
                batch_key = review_batch_key(batch)
                future = review_executor.submit(
                    run_review_batch,
                    row["source_id"],
                    digest,
                    batch,
                    batch_id,
                    batch_key,
                )
                review_futures.append((batch_key, future))

        source_results.append(
            {
                "source_id": row["source_id"],
                "source_sha256": digest,
                "source_claims": source_claims,
                "failed_chunks": failed_chunks,
                "review_futures": review_futures,
            }
        )

    review_executor.shutdown(wait=True)
    for source_result in source_results:
        source_claims = source_result["source_claims"]
        failed_chunks = source_result["failed_chunks"]
        failed_review_batches = [
            batch_key
            for batch_key, future in source_result["review_futures"]
            if future.result() is not None
        ]
        with reviewed_lock:
            unreviewed_claim_ids = sorted(
                str(claim.get("claim_id"))
                for claim in source_claims
                if claim.get("claim_id") not in reviewed
            )
        if failed_chunks or failed_review_batches or unreviewed_claim_ids:
            event = "SOURCE_INCOMPLETE"
        elif source_claims:
            event = "SOURCE_PASS_COMPLETE"
        else:
            event = "SOURCE_NO_RELEVANT_CLAIMS"
        record_event(
            {
                "event": event,
                "protocol_version": PROTOCOL_VERSION,
                "run_id": run_id,
                "source_id": source_result["source_id"],
                "source_sha256": source_result["source_sha256"],
                "valid_claims": len(source_claims),
                "failed_chunks": failed_chunks,
                "failed_review_batches": failed_review_batches,
                "unreviewed_claim_ids": unreviewed_claim_ids,
                "ts": time.time(),
            },
        )
    record_event(
        {
            "event": "RUN_COMPLETE",
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run_id,
            "ts": time.time(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
