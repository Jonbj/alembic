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
NODE2_BATCH_SIZE = 3
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


def chunks(text: str, size: int = 9000, overlap: int = 500):
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
    """Parse a single JSON object, tolerating only surrounding Markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def chat_json(
    url: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    response_format: dict[str, Any],
) -> dict:
    """Regenerate invalid JSON once under a strict schema, then parse it."""
    raw = chat(url, model, system, user, max_tokens)
    try:
        return parse_json(raw)
    except json.JSONDecodeError:
        regenerated = chat(
            url,
            model,
            system,
            user,
            max_tokens,
            response_format,
        )
        return parse_json(regenerated)


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
    path: Path, excluded_campaigns: set[str] | None = None
) -> set[tuple[str, str]]:
    """Return completed source/chunk identities excluding invalidated campaigns."""
    excluded_campaigns = excluded_campaigns or set()
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
            if (
                item.get("protocol_version") == PROTOCOL_VERSION
                and item.get("retry_campaign") not in excluded_campaigns
            ):
                keys.add((str(item["source_id"]), str(item["chunk_id"])))
        except (json.JSONDecodeError, KeyError):
            continue
    return keys


def recovered_chunk_keys(
    path: Path, excluded_campaigns: set[str] | None = None
) -> set[tuple[str, str]]:
    """Return parent chunks fully covered by append-only split-child records."""
    excluded_campaigns = excluded_campaigns or set()
    recovered: set[tuple[str, str]] = set()
    if not path.exists():
        return recovered
    for line in path.read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("protocol_version") != PROTOCOL_VERSION:
            continue
        if item.get("event") != "CHUNK_RECOVERED":
            continue
        if item.get("retry_campaign") in excluded_campaigns:
            continue
        source_id = item.get("source_id")
        chunk_id = item.get("chunk_id")
        if source_id is not None and chunk_id is not None:
            recovered.add((str(source_id), str(chunk_id)))
    return recovered


def prior_claims(
    path: Path,
    source_id: str,
    excluded_campaigns: set[str] | None = None,
) -> list[dict]:
    """Return prior valid claims for a source outside invalidated campaigns."""
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
            and item.get("protocol_version") == PROTOCOL_VERSION
            and item.get("retry_campaign") not in excluded_campaigns
        ):
            claims.extend(item.get("claims", []))
    return claims


def reviewed_claim_ids(
    path: Path, excluded_campaigns: set[str] | None = None
) -> set[str]:
    """Return claim ids already reviewed under the current protocol.

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
    excluded_campaigns: set[str] | None = None,
) -> int:
    """Choose a monotonic per-source batch id for append-only review output."""
    excluded_campaigns = excluded_campaigns or set()
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
        if item.get("retry_campaign") in excluded_campaigns:
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
    valid, rejected = [], []
    lines = text.splitlines()
    for claim in card.get("claims", []):
        reasons = []
        evidence_lines = claim.get("evidence_lines")
        start = end = -1
        if (
            not isinstance(evidence_lines, list)
            or len(evidence_lines) != 2
            or not all(isinstance(n, int) for n in evidence_lines)
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
        if card.get("source_id") != row["source_id"] or str(
            card.get("chunk_id", "")
        ) != str(chunk_id):
            reasons.append("IDENTITY_MISMATCH")
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
) -> dict[tuple[str, str], int]:
    """Highest attempt per source/unit in one protocol retry campaign."""
    counts: dict[tuple[str, str], int] = {}
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
        unit_id = item.get(unit_field)
        try:
            attempt = int(item.get("attempt", 0))
        except (TypeError, ValueError):
            continue
        if source_id is None or unit_id is None:
            continue
        key = (str(source_id), str(unit_id))
        counts[key] = max(counts.get(key, 0), attempt)
    return counts


def terminal_sources(
    path: Path,
    retry_sources: set[str] | None = None,
    retry_campaign: str | None = None,
    excluded_campaigns: set[str] | None = None,
) -> set[str]:
    """Sources that should not be visited in this protocol campaign."""
    retry_sources = retry_sources or set()
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
        source_id = item.get("source_id")
        event = item.get("event")
        completed = event in {"SOURCE_PASS_COMPLETE", "SOURCE_NO_RELEVANT_CLAIMS"}
        unavailable_outside_retry = event == "SOURCE_UNAVAILABLE" and not (
            retry_campaign is not None and source_id in retry_sources
        )
        if (completed or unavailable_outside_retry) and isinstance(source_id, str):
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
    retry_sources = set(args.source or [])

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
    excluded_campaigns = invalidated_campaigns(ledger_path)
    done = completed_keys(node1_path, excluded_campaigns) | recovered_chunk_keys(
        ledger_path, excluded_campaigns
    )
    reviewed = reviewed_claim_ids(node2_path, excluded_campaigns)
    node1_failures = attempt_counts(
        ledger_path, "NODE1_ATTEMPT_FAILED", "chunk_id", args.retry_campaign
    )
    node2_failures = attempt_counts(
        ledger_path, "NODE2_REVIEW_FAILED", "batch_key", args.retry_campaign
    )
    terminal = terminal_sources(
        ledger_path,
        retry_sources,
        args.retry_campaign,
        excluded_campaigns,
    )

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
        batch: list[dict],
        batch_id: int,
        batch_key: str,
    ) -> str | None:
        failure_key = (source_id, batch_key)
        attempts_used = node2_failures.get(failure_key, 0)
        for attempt in range(attempts_used + 1, 3):
            try:
                review = review_claims(source_id, batch, hypothesis_registry)
                validate_review(review, source_id, batch)
                review.update(
                    {
                        "model": MODEL2,
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
                        "batch_id": batch_id,
                        "batch_key": batch_key,
                        "attempt": attempt,
                        "error": repr(exc),
                        "ts": time.time(),
                    },
                )
        return batch_key

    for row in rows:
        if row["source_id"] in terminal:
            continue
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

        source_claims = prior_claims(node1_path, row["source_id"], excluded_campaigns)
        source_chunks = list(chunks(text))
        pending_chunks = [
            (chunk_id, chunk_text)
            for chunk_id, chunk_text in source_chunks
            if (row["source_id"], str(chunk_id)) not in done
        ]
        with reviewed_lock:
            pending_reviews = [
                claim
                for claim in source_claims
                if claim.get("claim_id") not in reviewed
            ]

        def process_chunk(chunk_id: ChunkId, chunk_text: str) -> list[ChunkId]:
            """Persist one chunk, recursively splitting only on context overflow."""
            done_key = (row["source_id"], str(chunk_id))
            if done_key in done:
                return []
            failure_key = (row["source_id"], str(chunk_id))
            attempts_used = node1_failures.get(failure_key, 0)
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
                    record_event(
                        {
                            "event": "NODE1_ATTEMPT_FAILED",
                            "protocol_version": PROTOCOL_VERSION,
                            "run_id": run_id,
                            "source_id": row["source_id"],
                            "chunk_id": chunk_id,
                            "attempt": attempt,
                            "error": repr(exc),
                            "ts": time.time(),
                        }
                    )
                    split = (
                        split_for_context(chunk_text)
                        if is_context_overflow(exc)
                        else None
                    )
                    if split is not None:
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
                            raise AssertionError(
                                "split children do not cover their parent"
                            )
                        record_event(
                            {
                                "event": "CHUNK_SPLIT",
                                "protocol_version": PROTOCOL_VERSION,
                                "run_id": run_id,
                                "source_id": row["source_id"],
                                "chunk_id": chunk_id,
                                "parent_sha256": parent_sha256,
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
                                    "chunk_id": chunk_id,
                                    "parent_sha256": parent_sha256,
                                    "children": children,
                                    "coverage_sha256": coverage_sha256,
                                    "coverage_verified": coverage_verified,
                                    "ts": time.time(),
                                }
                            )
                        return child_failures
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
            first_batch_id = next_review_batch_id(
                node2_path, row["source_id"], excluded_campaigns
            )
            for batch_offset, start in enumerate(
                range(0, len(pending_reviews), NODE2_BATCH_SIZE)
            ):
                batch_id = first_batch_id + batch_offset
                batch = pending_reviews[start : start + NODE2_BATCH_SIZE]
                batch_key = review_batch_key(batch)
                future = review_executor.submit(
                    run_review_batch,
                    row["source_id"],
                    batch,
                    batch_id,
                    batch_key,
                )
                review_futures.append((batch_key, future))

        source_results.append(
            {
                "source_id": row["source_id"],
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
