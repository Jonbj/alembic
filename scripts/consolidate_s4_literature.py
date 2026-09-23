"""Build an auditable, read-only consolidation of S4 two-node literature output."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def hypothesis_ids(path: Path) -> list[str]:
    return [line.split("|")[1].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("| H")]


def invalidated_campaigns(ledger: list[dict[str, Any]]) -> set[str]:
    return {
        row["invalidated_campaign"]
        for row in ledger
        if row.get("event") == "CAMPAIGN_INVALIDATED"
    }


def build_claims(
    cards: list[dict[str, Any]],
    review_batches: list[dict[str, Any]],
    invalidated: set[str],
) -> list[dict[str, Any]]:
    """Join protocol-v4 claims to reviews, preserving all evidence fields."""
    reviews = {
        review["claim_id"]: review
        for batch in review_batches
        if batch.get("protocol_version") == 4
        and batch.get("retry_campaign") not in invalidated
        for review in batch.get("reviews", [])
    }
    joined: dict[str, dict[str, Any]] = {}
    for card in cards:
        if card.get("protocol_version") != 4 or card.get("retry_campaign") in invalidated:
            continue
        for claim in card.get("claims", []):
            review = reviews.get(claim["claim_id"])
            if review is None:
                continue
            joined[claim["claim_id"]] = {
                "claim_id": claim["claim_id"],
                "source_id": card["source_id"],
                "source_sha256": card["source_sha256"],
                "chunk_id": card["chunk_id"],
                "chunk_sha256": card["chunk_sha256"],
                "retry_campaign": card.get("retry_campaign"),
                "hypotheses": claim["hypotheses"],
                "stance": claim["stance"],
                "claim": claim["claim"],
                "evidence_quote": claim["evidence_quote"],
                "limitations": claim["limitations"],
                "transferability": claim["transferability"],
                "review": review,
            }
    return [joined[key] for key in sorted(joined)]


def assessment(stances: set[str]) -> str:
    if not stances:
        return "INSUFFICIENT"
    if stances == {"SUPPORTS"}:
        return "SUPPORTS"
    if stances == {"CONTRADICTS"}:
        return "CONTRADICTS"
    return "QUALIFIES"


def report(hypotheses: list[str], claims: list[dict[str, Any]], invalidated: set[str]) -> str:
    by_hypothesis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        if claim["review"]["verdict"] == "SUPPORTED":
            for hypothesis in claim["hypotheses"]:
                by_hypothesis[hypothesis].append(claim)

    lines = [
        "# S4 deep web validation — consolidated evidence",
        "",
        "This is a deterministic, read-only synthesis of protocol-v4 node output. A claim is evidence for the matrix only when node2 marked it `SUPPORTED`; the audit JSONL retains every joined claim and its adversarial review.",
        "",
        f"Excluded invalidated campaigns: {', '.join(sorted(invalidated)) or 'none'}.",
        "",
        "| Hypothesis | Assessment | Supported claims | Sources |",
        "|---|---|---:|---|",
    ]
    for hypothesis in hypotheses:
        evidence = by_hypothesis[hypothesis]
        stances = {claim["stance"] for claim in evidence}
        sources = ", ".join(sorted({claim["source_id"] for claim in evidence})) or "—"
        lines.append(f"| {hypothesis} | {assessment(stances)} | {len(evidence)} | {sources} |")

    lines.extend(["", "## Boundaries", "", "- `ACA009` remains unavailable (the frozen published version returned HTTP 403). `ACA010` is a separately identified accepted-author manuscript, not a silent replacement.", "- This report does not validate an Alembic strategy, change S4, or turn a long-short historical result into a live long-only recommendation.", "- For quote, digest, limitation, transferability and node2 critique of each record, use `s4-web-validation-2026-08-28/node-output/consolidated_claims.jsonl`.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    root = args.workspace
    output = root / "node-output"
    ledger = read_jsonl(output / "run_ledger.jsonl")
    claims = build_claims(read_jsonl(output / "node1_cards.jsonl"), read_jsonl(output / "node2_reviews.jsonl"), invalidated_campaigns(ledger))
    (output / "consolidated_claims.jsonl").write_text("".join(json.dumps(claim, ensure_ascii=False, sort_keys=True) + "\n" for claim in claims), encoding="utf-8")
    (root.parent / "2026-08-28-s4-deep-web-validation.md").write_text(report(hypothesis_ids(root / "HYPOTHESES.md"), claims, invalidated_campaigns(ledger)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
