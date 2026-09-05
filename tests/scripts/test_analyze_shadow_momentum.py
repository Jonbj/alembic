"""CLI riproducibile dell'analisi shadow #451."""

import json

from scripts import analyze_shadow_momentum


def test_cli_pubblica_specifica_provenienza_sintesi_e_righe(tmp_path, capsys):
    days = ["10", "11", "12", "13", "14"]
    for day in days:
        payload = {
            "data": f"2026-08-{day}",
            "mercato": {"rendimenti": {"AAA": 0.01}},
            "candidati_miss": [],
        }
        (tmp_path / f"2026-08-{day}.json").write_text(json.dumps(payload))
    event = {
        "data": "2026-08-17",
        "mercato": {"rendimenti": {"AAA": 0.04}},
        "candidati_miss": [
            {
                "symbol": "AAA",
                "causa": "NO_NEWS",
                "return": 0.04,
                "opportunity_v2": {"accessible_opportunity_usd": 25.0},
            }
        ],
    }
    (tmp_path / "2026-08-17.json").write_text(json.dumps(event))
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "sample.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "data": "2026-08-17",
                    "symbol": "AAA",
                    "causa": "NO_NEWS",
                    "source": "docs/ALPHA_MISS_REPORT_2026-08-17.md",
                }
            ]
        )
    )

    exit_code = analyze_shadow_momentum.main(
        [
            "--dossier-dir", str(tmp_path),
            "--sample-manifest", str(manifest_path),
            "--start", "2026-08-17",
            "--end", "2026-08-17",
            "--bootstrap-resamples", "20",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["specification"]["preregistration"].endswith(
        "PREREGISTRAZIONE_SHADOW_MOMENTUM_451.md"
    )
    assert output["specification"]["lookback_sessions"] == 5
    assert output["provenance"]["dossier_count"] == 6
    assert output["provenance"]["dossier_dates"][-1] == "2026-08-17"
    assert output["summary"]["counts"]["population"] == 1
    assert output["observations"][0]["symbol"] == "AAA"
