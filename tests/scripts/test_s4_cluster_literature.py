"""CLI contract tests for the two-node S4 literature coordinator."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

import scripts.s4_cluster_literature as coordinator


class _ChatResponse:
    """Minimal successful llama.cpp response used at the HTTP boundary."""

    ok = True
    status_code = 200
    text = ""

    def __init__(self, content: dict[str, object] | str) -> None:
        self._content = content

    def json(self) -> dict[str, object]:
        content = (
            self._content
            if isinstance(self._content, str)
            else json.dumps(self._content)
        )
        return {"choices": [{"message": {"content": content}}]}


class _ContextOverflowResponse:
    """llama.cpp response when a request exceeds the configured context."""

    ok = False
    status_code = 400
    text = '{"error":{"message":"request exceeds the available context size"}}'


def _write_fixture(
    tmp_path: Path, source_text: str = "Evidence line.\n" * 50
) -> tuple[Path, Path, Path]:
    manifest_dir = tmp_path / "manifest"
    output_dir = tmp_path / "output"
    cache_dir = tmp_path / "cache"
    manifest_dir.mkdir()
    output_dir.mkdir()
    cache_dir.mkdir()
    (manifest_dir / "HYPOTHESES.md").write_text("H01: fixture hypothesis\n")
    with (manifest_dir / "SOURCE_MANIFEST.tsv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_id", "class", "format", "url", "title"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_id": "SRC001",
                "class": "academic",
                "format": "pdf",
                "url": "https://example.invalid/source.pdf",
                "title": "Fixture source",
            }
        )
    (cache_dir / "SRC001.raw").write_bytes(source_text.encode())
    (cache_dir / "SRC001.txt").write_text(source_text)
    return manifest_dir / "SOURCE_MANIFEST.tsv", output_dir, cache_dir


def _ledger_events(output_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (output_dir / "run_ledger.jsonl").read_text().splitlines()
    ]


def test_retry_campaign_reopens_an_unavailable_source_without_rewriting_history(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    old_event = {
        "event": "SOURCE_UNAVAILABLE",
        "protocol_version": 4,
        "run_id": "old-run",
        "source_id": "SRC001",
        "error": "HTTP 403",
        "ts": 1.0,
    }
    (output_dir / "run_ledger.jsonl").write_text(json.dumps(old_event) + "\n")

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        del url, timeout
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": 0,
                "claims": [],
                "unverified_followups": [],
            }
        )

    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "recovery-2026-09-01",
        ],
    )

    assert coordinator.main() == 0

    events = _ledger_events(output_dir)
    assert events[0] == old_event
    assert events[-2]["event"] == "SOURCE_NO_RELEVANT_CLAIMS"
    assert events[-2]["retry_campaign"] == "recovery-2026-09-01"
    assert events[-1]["event"] == "RUN_COMPLETE"


def test_cli_repairs_only_missing_json_closers_without_reinference(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        del url, timeout
        calls.append(json)
        return _ChatResponse(
            '{"source_id":"SRC001","chunk_id":0,"claims":[],"unverified_followups":[]'
        )

    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
        ],
    )

    assert coordinator.main() == 0

    cards = [
        json.loads(line)
        for line in (output_dir / "node1_cards.jsonl").read_text().splitlines()
    ]
    assert len(calls) == 1
    assert calls[0]["response_format"]["type"] == "json_schema"
    failures = [
        event
        for event in _ledger_events(output_dir)
        if event["event"] == "NODE1_ATTEMPT_FAILED"
    ]
    assert failures == []
    assert cards[0]["chunk_id"] == 0
    assert cards[0]["attempt"] == 1
    assert _ledger_events(output_dir)[-2]["event"] == "SOURCE_NO_RELEVANT_CLAIMS"


def test_cli_splits_only_an_overflowing_chunk_and_records_parent_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    source_text = ("First supported paragraph.\n\n" * 100) + (
        "Second supported paragraph.\n\n" * 100
    )
    manifest, output_dir, cache_dir = _write_fixture(tmp_path, source_text)

    def fake_post(url: str, *, json: dict[str, object], timeout: int):
        del url, timeout
        user = str(json["messages"][1]["content"])
        raw_chunk_id = re.search(r"^CHUNK_ID: (.+)$", user, re.MULTILINE).group(1)
        chunk_id = json_module.loads(raw_chunk_id)
        if chunk_id == 0:
            return _ContextOverflowResponse()
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": chunk_id,
                "claims": [],
                "unverified_followups": [],
            }
        )

    json_module = json
    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "overflow-recovery",
        ],
    )

    assert coordinator.main() == 0

    cards = [
        json.loads(line)
        for line in (output_dir / "node1_cards.jsonl").read_text().splitlines()
    ]
    assert [card["chunk_id"] for card in cards] == ["0.0", "0.1"]
    events = _ledger_events(output_dir)
    split_event = next(event for event in events if event["event"] == "CHUNK_SPLIT")
    recovered_event = next(
        event for event in events if event["event"] == "CHUNK_RECOVERED"
    )
    assert split_event["parent_sha256"] == coordinator.hash_text(source_text)
    assert split_event["children"][0]["start"] == 0
    assert split_event["children"][1]["end"] == len(source_text)
    assert recovered_event["coverage_sha256"] == split_event["parent_sha256"]
    assert recovered_event["coverage_verified"] is True
    assert events[-2]["event"] == "SOURCE_NO_RELEVANT_CLAIMS"


def test_cli_splits_a_chunk_after_two_invalid_json_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    source_text = "Evidence-bearing source line.\n" * 100
    manifest, output_dir, cache_dir = _write_fixture(tmp_path, source_text)

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        del url, timeout
        user = str(json["messages"][1]["content"])
        raw_chunk_id = re.search(r"^CHUNK_ID: (.+)$", user, re.MULTILINE).group(1)
        chunk_id = json_module.loads(raw_chunk_id)
        if chunk_id == 0:
            return _ChatResponse('{"source_id":"SRC001","chunk_id":0,"claims":[')
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": chunk_id,
                "claims": [],
                "unverified_followups": [],
            }
        )

    json_module = json
    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "invalid-json-split",
        ],
    )

    assert coordinator.main() == 0

    cards = [
        json.loads(line)
        for line in (output_dir / "node1_cards.jsonl").read_text().splitlines()
    ]
    assert [card["chunk_id"] for card in cards] == ["0.0", "0.1"]
    events = _ledger_events(output_dir)
    assert [event["event"] for event in events].count("NODE1_ATTEMPT_FAILED") == 2
    assert any(event["event"] == "CHUNK_RECOVERED" for event in events)
    assert events[-2]["event"] == "SOURCE_NO_RELEVANT_CLAIMS"


def test_cli_resumes_an_eligible_split_after_two_persisted_failures(
    tmp_path: Path, monkeypatch
) -> None:
    source_text = "Evidence-bearing source line.\n" * 100
    manifest, output_dir, cache_dir = _write_fixture(tmp_path, source_text)
    source_digest = hashlib.sha256((cache_dir / "SRC001.raw").read_bytes()).hexdigest()
    failures = [
        {
            "event": "NODE1_ATTEMPT_FAILED",
            "protocol_version": 4,
            "source_id": "SRC001",
            "source_sha256": source_digest,
            "chunk_id": 0,
            "attempt": attempt,
            "error": "invalid output",
            "split_eligible": attempt == 2,
            "retry_campaign": "resume-invalid-json-split",
        }
        for attempt in (1, 2)
    ]
    (output_dir / "run_ledger.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in failures)
    )
    seen_chunk_ids: list[str | int] = []

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        del url, timeout
        user = str(json["messages"][1]["content"])
        raw_chunk_id = re.search(r"^CHUNK_ID: (.+)$", user, re.MULTILINE).group(1)
        chunk_id = json_module.loads(raw_chunk_id)
        seen_chunk_ids.append(chunk_id)
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": chunk_id,
                "claims": [],
                "unverified_followups": [],
            }
        )

    json_module = json
    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "resume-invalid-json-split",
        ],
    )

    assert coordinator.main() == 0

    assert seen_chunk_ids == ["0.0", "0.1"]
    events = _ledger_events(output_dir)
    assert any(event["event"] == "CHUNK_RECOVERED" for event in events)
    assert events[-2]["event"] == "SOURCE_NO_RELEVANT_CLAIMS"


def test_cli_keeps_source_incomplete_when_every_claim_fails_quote_validation(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    calls = 0

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        nonlocal calls
        del url, json, timeout
        calls += 1
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": 0,
                "claims": [
                    {
                        "claim_id": "SRC001-C0-01",
                        "hypotheses": ["H01"],
                        "stance": "SUPPORTS",
                        "claim": "Unsupported fixture claim.",
                        "evidence_lines": [999, 1000],
                        "limitations": "Fixture only.",
                        "transferability": "Fixture only.",
                    }
                ],
                "unverified_followups": [],
            }
        )

    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
        ],
    )

    assert coordinator.main() == 0

    assert calls == 2
    assert not (output_dir / "node1_cards.jsonl").exists()
    events = _ledger_events(output_dir)
    assert [event["event"] for event in events].count("NODE1_ATTEMPT_FAILED") == 2
    assert events[-2]["event"] == "SOURCE_INCOMPLETE"


def test_invalidated_campaign_artifacts_are_ignored_by_a_new_retry(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    (output_dir / "node1_cards.jsonl").write_text(
        json.dumps(
            {
                "source_id": "SRC001",
                "chunk_id": 0,
                "protocol_version": 4,
                "retry_campaign": "bad-campaign",
                "claims": [],
            }
        )
        + "\n"
    )
    (output_dir / "run_ledger.jsonl").write_text(
        json.dumps(
            {
                "event": "CAMPAIGN_INVALIDATED",
                "protocol_version": 4,
                "invalidated_campaign": "bad-campaign",
                "reason": "failed integrity review",
            }
        )
        + "\n"
    )
    calls = 0

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        nonlocal calls
        del url, json, timeout
        calls += 1
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": 0,
                "claims": [],
                "unverified_followups": [],
            }
        )

    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "good-campaign",
        ],
    )

    assert coordinator.main() == 0

    assert calls == 1
    events = _ledger_events(output_dir)
    assert events[-2]["event"] == "SOURCE_NO_RELEVANT_CLAIMS"


def test_cli_rejects_reuse_of_an_invalidated_campaign_name(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    invalidation = {
        "event": "CAMPAIGN_INVALIDATED",
        "protocol_version": 4,
        "invalidated_campaign": "bad-campaign",
        "reason": "failed integrity review",
    }
    (output_dir / "run_ledger.jsonl").write_text(json.dumps(invalidation) + "\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "bad-campaign",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        coordinator.main()

    assert exc_info.value.code == 2
    assert _ledger_events(output_dir) == [invalidation]


def test_recovered_chunks_require_a_complete_consistent_coverage_proof(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "run_ledger.jsonl"
    cards = tmp_path / "node1_cards.jsonl"
    source_digest = "f" * 64
    parent_text = "abcdefghij"
    child_texts = [parent_text[:5], parent_text[5:]]
    base: dict[str, object] = {
        "event": "CHUNK_RECOVERED",
        "protocol_version": 4,
        "source_id": "SRC001",
        "source_sha256": source_digest,
        "run_id": "run-1",
        "retry_campaign": "campaign-1",
        "coverage_verified": True,
        "parent_chars": len(parent_text),
    }
    events = [
        {
            **base,
            "chunk_id": 0,
            "parent_sha256": coordinator.hash_text(parent_text),
            "coverage_sha256": coordinator.hash_text(parent_text),
            "children": [
                {
                    "chunk_id": "wrong.0",
                    "start": 0,
                    "end": 5,
                    "sha256": coordinator.hash_text(child_texts[0]),
                },
                {
                    "chunk_id": "wrong.1",
                    "start": 5,
                    "end": 10,
                    "sha256": coordinator.hash_text(child_texts[1]),
                },
            ],
        },
        {
            **base,
            "chunk_id": 1,
            "parent_sha256": "a" * 64,
            "coverage_sha256": "a" * 64,
            "children": [
                {"chunk_id": "1.0", "start": 0, "end": 5, "sha256": "b" * 64},
                {"chunk_id": "1.1", "start": 5, "end": 10, "sha256": "b" * 64},
            ],
        },
        {
            **base,
            "chunk_id": 2,
            "parent_sha256": coordinator.hash_text(parent_text),
            "coverage_sha256": coordinator.hash_text(parent_text),
            "children": [
                {
                    "chunk_id": "2.0",
                    "start": 0,
                    "end": 5,
                    "sha256": coordinator.hash_text(child_texts[0]),
                },
                {
                    "chunk_id": "2.1",
                    "start": 5,
                    "end": 10,
                    "sha256": coordinator.hash_text(child_texts[1]),
                },
            ],
        },
    ]
    ledger.write_text("".join(json.dumps(event) + "\n" for event in events))
    cards.write_text(
        "".join(
            json.dumps(
                {
                    "protocol_version": 4,
                    "source_id": "SRC001",
                    "source_sha256": source_digest,
                    "chunk_id": f"2.{index}",
                    "chunk_sha256": coordinator.hash_text(child_text),
                    "run_id": f"run-{index + 1}",
                    "retry_campaign": "campaign-1",
                    "claims": [],
                }
            )
            + "\n"
            for index, child_text in enumerate(child_texts)
        )
    )

    assert coordinator.recovered_chunk_keys(
        ledger,
        cards,
        "SRC001",
        {"0": parent_text, "1": parent_text, "2": parent_text},
        source_digest,
    ) == {("SRC001", "2")}


def test_validators_reject_missing_required_semantic_fields() -> None:
    card = {
        "source_id": "SRC001",
        "chunk_id": 0,
        "claims": [
            {
                "claim_id": "SRC001-C0-01",
                "hypotheses": ["H01"],
                "stance": "SUPPORTS",
                "evidence_lines": [1, 1],
                "limitations": "Fixture only.",
                "transferability": "Fixture only.",
            }
        ],
        "unverified_followups": [],
    }
    valid, rejected = coordinator.validate_card(
        card,
        {
            "source_id": "SRC001",
            "class": "academic",
            "format": "pdf",
            "url": "https://example.invalid/source.pdf",
            "title": "Fixture source",
        },
        0,
        "Evidence line.",
    )

    assert valid == []
    assert rejected[0]["reasons"] == ["INVALID_CLAIM"]
    with pytest.raises(ValueError, match="invalid or missing reason"):
        coordinator.validate_review(
            {
                "source_id": "SRC001",
                "reviews": [
                    {
                        "claim_id": "SRC001-C0-01",
                        "verdict": "SUPPORTED",
                        "reason_codes": [],
                        "minimal_correction": "",
                    }
                ],
            },
            "SRC001",
            [{"claim_id": "SRC001-C0-01"}],
        )


def test_review_batch_ids_remain_monotonic_across_invalidated_campaigns(
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "node2_reviews.jsonl"
    reviews.write_text(
        json.dumps(
            {
                "protocol_version": 4,
                "source_id": "SRC001",
                "batch_id": 7,
                "retry_campaign": "invalidated-campaign",
            }
        )
        + "\n"
    )

    assert coordinator.next_review_batch_id(reviews, "SRC001") == 8


def test_parse_json_rejects_surrounding_prose() -> None:
    with pytest.raises(json.JSONDecodeError):
        coordinator.parse_json('Here is the result: {"ok": true}')
    with pytest.raises(json.JSONDecodeError):
        coordinator.parse_json('{"claim":"unterminated}')
    with pytest.raises(ValueError, match="not a JSON object"):
        coordinator.parse_json("[]")


def test_cli_does_not_reuse_cards_or_terminal_state_from_an_old_source_digest(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    stale_digest = "0" * 64
    stale_claim = {
        "claim_id": "SRC001-C0-01",
        "hypotheses": ["H01"],
        "stance": "SUPPORTS",
        "claim": "Stale fixture claim.",
        "evidence_quote": "Old evidence.",
        "evidence_context": "Old evidence.",
        "limitations": "Old representation.",
        "transferability": "Old representation.",
    }
    (output_dir / "node1_cards.jsonl").write_text(
        json.dumps(
            {
                "source_id": "SRC001",
                "source_sha256": stale_digest,
                "chunk_id": 0,
                "chunk_sha256": stale_digest,
                "protocol_version": 4,
                "claims": [stale_claim],
            }
        )
        + "\n"
    )
    stale_events = [
        {
            "event": "SOURCE_PASS_COMPLETE",
            "protocol_version": 4,
            "source_id": "SRC001",
            "source_sha256": stale_digest,
        },
        *[
            {
                "event": "NODE1_ATTEMPT_FAILED",
                "protocol_version": 4,
                "source_id": "SRC001",
                "source_sha256": stale_digest,
                "chunk_id": 0,
                "attempt": attempt,
                "retry_campaign": "fresh-digest",
            }
            for attempt in (1, 2)
        ],
    ]
    (output_dir / "run_ledger.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in stale_events)
    )
    calls = 0

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        nonlocal calls
        del url, json, timeout
        calls += 1
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "chunk_id": 0,
                "claims": [],
                "unverified_followups": [],
            }
        )

    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "fresh-digest",
        ],
    )

    assert coordinator.main() == 0

    current_digest = hashlib.sha256((cache_dir / "SRC001.raw").read_bytes()).hexdigest()
    cards = [
        json.loads(line)
        for line in (output_dir / "node1_cards.jsonl").read_text().splitlines()
    ]
    assert calls == 1
    assert cards[-1]["source_sha256"] == current_digest
    assert cards[-1]["claims"] == []
    assert not (output_dir / "node2_reviews.jsonl").exists()


def test_retry_campaign_gives_an_exhausted_node2_batch_a_fresh_budget(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    claim = {
        "claim_id": "SRC001-C0-01",
        "hypotheses": ["H01"],
        "stance": "SUPPORTS",
        "claim": "Fixture claim.",
        "evidence_quote": "Evidence line.",
        "evidence_context": "Evidence line.",
        "limitations": "Fixture only.",
        "transferability": "Fixture only.",
    }
    (output_dir / "node1_cards.jsonl").write_text(
        json.dumps(
            {
                "source_id": "SRC001",
                "source_sha256": hashlib.sha256(
                    (cache_dir / "SRC001.raw").read_bytes()
                ).hexdigest(),
                "chunk_id": 0,
                "protocol_version": 4,
                "claims": [claim],
            }
        )
        + "\n"
    )
    old_failures = [
        {
            "event": "NODE2_REVIEW_FAILED",
            "protocol_version": 4,
            "run_id": "old-run",
            "source_id": "SRC001",
            "batch_key": coordinator.review_batch_key([claim]),
            "attempt": attempt,
            "error": "invalid JSON",
        }
        for attempt in (1, 2)
    ]
    (output_dir / "run_ledger.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in old_failures)
    )

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        del url, json, timeout
        return _ChatResponse(
            {
                "source_id": "SRC001",
                "reviews": [
                    {
                        "claim_id": "SRC001-C0-01",
                        "verdict": "SUPPORTED",
                        "reason_codes": [],
                        "reason": "The quote supports the fixture claim.",
                        "minimal_correction": "",
                    }
                ],
            }
        )

    monkeypatch.setattr(coordinator.requests, "post", fake_post)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s4_cluster_literature.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
            "--source",
            "SRC001",
            "--retry-campaign",
            "node2-recovery",
        ],
    )

    assert coordinator.main() == 0

    reviews = [
        json.loads(line)
        for line in (output_dir / "node2_reviews.jsonl").read_text().splitlines()
    ]
    assert reviews[0]["attempt"] == 1
    assert reviews[0]["retry_campaign"] == "node2-recovery"
    assert _ledger_events(output_dir)[-2]["event"] == "SOURCE_PASS_COMPLETE"
