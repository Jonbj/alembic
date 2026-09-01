"""CLI contract tests for the two-node S4 literature coordinator."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

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


def test_cli_regenerates_invalid_json_with_a_schema_before_another_job_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, output_dir, cache_dir = _write_fixture(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> _ChatResponse:
        del url, timeout
        calls.append(json)
        response_format = json["response_format"]
        if response_format["type"] != "json_schema":
            return _ChatResponse('{"source_id":"SRC001","chunk_id":0,"claims":[')
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
        ],
    )

    assert coordinator.main() == 0

    cards = [
        json.loads(line)
        for line in (output_dir / "node1_cards.jsonl").read_text().splitlines()
    ]
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[1]["response_format"]["type"] == "json_schema"
    assert calls[1]["messages"] == calls[0]["messages"]
    assert cards[0]["chunk_id"] == 0
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
