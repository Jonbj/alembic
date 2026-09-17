from __future__ import annotations

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
