"""#295: validazione read-only della coverage lifecycle su finestra dichiarata."""

from __future__ import annotations

import json

import scripts.validate_s4_lifecycles as validator


def _rows(reconstructible: int, residuals: dict[str, int]):
    rows = [{"reconstructible": True, "reason_code": "BROKER_FILLED"}]
    rows *= reconstructible
    for reason, count in residuals.items():
        rows.extend({"reconstructible": False, "reason_code": reason} for _ in range(count))
    return rows


def test_report_passa_esattamente_al_95_percento_e_quantifica_i_residui():
    report = validator.summarize(
        _rows(95, {"BROKER_POSITION_MISSING": 3, "CORPORATE_ACTION": 2}),
        start="2026-08-25",
        end="2026-08-29",
    )

    assert report == {
        "window_start": "2026-08-25",
        "window_end": "2026-08-29",
        "minimum_coverage": 0.95,
        "total": 100,
        "reconstructible": 95,
        "coverage": 0.95,
        "meets_minimum": True,
        "residual_by_reason": {
            "BROKER_POSITION_MISSING": 3,
            "CORPORATE_ACTION": 2,
        },
    }


def test_cli_fallisce_sotto_soglia_e_stampa_json(monkeypatch, capsys):
    monkeypatch.setattr(
        validator,
        "_fetch_rows",
        lambda start, end: _rows(94, {"MISSING_FILL": 6}),
    )

    exit_code = validator.main(["--start", "2026-08-25", "--end", "2026-08-29"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["coverage"] == 0.94
    assert payload["residual_by_reason"] == {"MISSING_FILL": 6}


def test_cli_distingue_finestra_senza_lifecycle(monkeypatch, capsys):
    monkeypatch.setattr(validator, "_fetch_rows", lambda start, end: [])

    exit_code = validator.main(["--start", "2026-08-25", "--end", "2026-08-29"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["coverage"] is None
    assert payload["meets_minimum"] is False
