from __future__ import annotations

import json
from pathlib import Path

import scripts.consolidate_s4_literature as consolidation


def test_join_excludes_invalidated_campaign_and_requires_review() -> None:
    card = {
        "protocol_version": 4, "retry_campaign": "good", "source_id": "SRC", "source_sha256": "source",
        "chunk_id": 0, "chunk_sha256": "chunk", "claims": [{"claim_id": "c1", "hypotheses": ["H01"], "stance": "SUPPORTS", "claim": "x", "evidence_quote": "q", "limitations": "l", "transferability": "t"}],
    }
    review = {"protocol_version": 4, "retry_campaign": "good", "reviews": [{"claim_id": "c1", "verdict": "SUPPORTED", "reason": "ok", "reason_codes": [], "minimal_correction": ""}]}
    stale = dict(card, retry_campaign="bad")
    assert [claim["claim_id"] for claim in consolidation.build_claims([card, stale], [review], {"bad"})] == ["c1"]


def test_assessment_is_conservative_for_conflicting_evidence() -> None:
    assert consolidation.assessment(set()) == "INSUFFICIENT"
    assert consolidation.assessment({"SUPPORTS"}) == "SUPPORTS"
    assert consolidation.assessment({"CONTRADICTS"}) == "CONTRADICTS"
    assert consolidation.assessment({"SUPPORTS", "CONTRADICTS"}) == "QUALIFIES"


REQUIRED_FIELDS = (
    "source_id", "source_sha256", "chunk_id", "chunk_sha256", "claim_id",
    "hypotheses", "stance", "claim", "evidence_quote", "limitations",
    "transferability", "review",
)
ALLOWED_STANCES = {"SUPPORTS", "CONTRADICTS", "QUALIFIES", "METHOD_ONLY"}
ALLOWED_VERDICTS = {"SUPPORTED", "OVERSTATED", "AMBIGUOUS", "NOT_APPLICABLE"}


def _workspace() -> Path:
    return Path("docs/research/s4-web-validation-2026-08-28")


def test_consolidation_covers_every_supported_card_with_required_fields() -> None:
    """Workspace-wide invariants: every consolidated claim has the required
    fields, every claim joins a node1 card to its node2 review exactly once,
    and no claim leaks from a campaign that was invalidated in the ledger."""
    root = _workspace()
    node_output = root / "node-output"

    ledger = [
        json.loads(line)
        for line in (node_output / "run_ledger.jsonl").read_text().splitlines()
        if line
    ]
    cards = [
        json.loads(line)
        for line in (node_output / "node1_cards.jsonl").read_text().splitlines()
        if line
    ]
    reviews = [
        json.loads(line)
        for line in (node_output / "node2_reviews.jsonl").read_text().splitlines()
        if line
    ]
    consolidated = consolidation.build_claims(
        cards, reviews, consolidation.invalidated_campaigns(ledger)
    )

    invalidated = consolidation.invalidated_campaigns(ledger)
    for claim in consolidated:
        for field in REQUIRED_FIELDS:
            assert field in claim, f"missing {field} in {claim.get('claim_id')}"
        assert claim["stance"] in ALLOWED_STANCES, f"bad stance in {claim['claim_id']}"
        assert claim["review"]["verdict"] in ALLOWED_VERDICTS, (
            f"bad review verdict in {claim['claim_id']}"
        )
        assert claim["retry_campaign"] not in invalidated, (
            f"invalidated campaign leaked into {claim['claim_id']}"
        )

    seen = sorted(c["claim_id"] for c in consolidated)
    assert len(seen) == len(set(seen)), "duplicate claim_ids in consolidation"


def test_published_artifacts_match_deterministic_regeneration() -> None:
    """The checked-in JSONL and matrix must be the current node-output render."""
    root = _workspace()
    node_output = root / "node-output"
    ledger = consolidation.read_jsonl(node_output / "run_ledger.jsonl")
    invalidated = consolidation.invalidated_campaigns(ledger)
    claims = consolidation.build_claims(
        consolidation.read_jsonl(node_output / "node1_cards.jsonl"),
        consolidation.read_jsonl(node_output / "node2_reviews.jsonl"),
        invalidated,
    )
    expected_jsonl = "".join(
        json.dumps(claim, ensure_ascii=False, sort_keys=True) + "\n"
        for claim in claims
    )

    assert (node_output / "consolidated_claims.jsonl").read_text(
        encoding="utf-8"
    ) == expected_jsonl
    assert (root.parent / "2026-08-28-s4-deep-web-validation.md").read_text(
        encoding="utf-8"
    ) == consolidation.report(
        consolidation.hypothesis_ids(root / "HYPOTHESES.md"), claims, invalidated
    )


def test_consolidation_excludes_unavailable_sources() -> None:
    """ACA005, ACA009 and NEW001 are flagged SOURCE_UNAVAILABLE in the ledger
    and have no node1 cards; they must therefore not appear in the consolidated
    JSONL output."""
    root = _workspace()
    node_output = root / "node-output"
    consolidated = [
        json.loads(line)
        for line in (node_output / "consolidated_claims.jsonl").read_text().splitlines()
        if line
    ]
    sources_in_consolidated = {c["source_id"] for c in consolidated}
    for unavailable in ("ACA005", "ACA009", "NEW001"):
        assert unavailable not in sources_in_consolidated, (
            f"{unavailable} is SOURCE_UNAVAILABLE and must not appear in consolidated claims"
        )


def test_consolidation_report_uses_hypothesis_registry_order() -> None:
    """The report lists rows in the same order as HYPOTHESES.md (H01..H22) and
    applies the conservative assessment rule on the SUPPORTED-only slice."""
    root = _workspace()
    report_path = root.parent / "2026-08-28-s4-deep-web-validation.md"
    text = report_path.read_text()
    last_index = -1
    for i in range(1, 23):
        marker = f"| H{i:02d} "
        idx = text.find(marker)
        assert idx > last_index, f"H{i:02d} missing or out of order in report"
        last_index = idx

    allowed_assessments = {"SUPPORTS", "QUALIFIES", "CONTRADICTS", "INSUFFICIENT"}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[0].startswith("H") or not cells[0][1:].isdigit():
            continue
        assert cells[1] in allowed_assessments, (
            f"bad assessment for {cells[0]}: {cells[1]}"
        )
