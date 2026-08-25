"""#296: validazione operativa della comparabilita' P0."""

from __future__ import annotations

import json

import scripts.validate_s4_p0 as validator


def _rows(comparable: int, residuals: dict[str, int]):
    rows = [{"comparable": True, "reason_code": "P0_TARGET_ZERO_EXPIRED"}]
    rows *= comparable
    for reason, count in residuals.items():
        rows.extend({"comparable": False, "reason_code": reason} for _ in range(count))
    return rows


def test_report_passa_esattamente_al_95_percento_e_classifica_il_residuo():
    report = validator.summarize(
        _rows(95, {"P0_EXIT_FILL_MISSING": 3, "P0_TAKE_PROFIT_DISABLED": 2}),
        start="2026-08-25",
        end="2026-09-28",
    )

    assert report["total"] == 100
    assert report["comparable"] == 95
    assert report["coverage"] == 0.95
    assert report["meets_minimum"] is True
    assert report["take_profit_live_count"] == 2
    assert report["take_profit_live_rate"] == 0.02
    assert report["residual_by_reason"] == {
        "P0_EXIT_FILL_MISSING": 3,
        "P0_TAKE_PROFIT_DISABLED": 2,
    }


def test_cli_fallisce_sotto_soglia_e_stampa_json(monkeypatch, capsys):
    monkeypatch.setattr(
        validator,
        "_fetch_rows",
        lambda start, end: _rows(94, {"P0_EXIT_FILL_MISSING": 6}),
    )

    exit_code = validator.main(["--start", "2026-08-25", "--end", "2026-09-28"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["coverage"] == 0.94


def test_cli_distingue_finestra_senza_eventi_p0(monkeypatch, capsys):
    monkeypatch.setattr(validator, "_fetch_rows", lambda start, end: [])

    exit_code = validator.main(["--start", "2026-08-25", "--end", "2026-09-28"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["coverage"] is None
    assert payload["meets_minimum"] is False
