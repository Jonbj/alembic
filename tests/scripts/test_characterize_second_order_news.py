"""#408 — report end-to-end della caratterizzazione second-order."""

import json
from datetime import datetime, timezone

import scripts.characterize_second_order_news as script
from src.analysis.second_order_news import CompanyIdentity


UTC = timezone.utc
NOW = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)


def _fixture_inputs():
    companies = [
        CompanyIdentity("ADBE", "Adobe Inc", ("Adobe Systems",)),
        CompanyIdentity("CRM", "Salesforce Inc", ("Salesforce.com Inc",)),
        CompanyIdentity("V", "Visa Inc", ("Visa International",)),
    ]
    news = [
        {
            "news_log_id": 1,
            "ticker": "ADBE",
            "title": "Adobe stock rises following Salesforce earnings",
            "fetched_at": datetime(2026, 8, 27, 14, 0, tzinfo=UTC),
        },
        {
            "news_log_id": 2,
            "ticker": "V",
            "title": "Visa raises full-year guidance",
            "fetched_at": datetime(2026, 8, 28, 14, 0, tzinfo=UTC),
        },
        {
            "news_log_id": 3,
            "ticker": "MISSING",
            "title": "Missing rises following Salesforce earnings",
            "fetched_at": datetime(2026, 8, 29, 14, 0, tzinfo=UTC),
        },
    ]
    signals = [
        {
            "signal_id": 101,
            "news_log_id": 1,
            "forward_return": 0.06,
            "forward_return_3d": 0.09,
            "forward_return_5d": None,
        },
        {
            "signal_id": 102,
            "news_log_id": 2,
            "forward_return": -0.01,
            "forward_return_3d": 0.02,
            "forward_return_5d": 0.03,
        },
    ]
    responses = [
        {"signal_id": 101, "model_id": "glm52", "directness": "competitor_readthrough"},
        {"signal_id": 101, "model_id": "gptoss", "directness": "direct"},
        {"signal_id": 102, "model_id": "glm52", "directness": "direct"},
    ]
    return news, companies, signals, responses


def test_report_conta_la_popolazione_forward_return_e_agreement_indipendenti():
    report = script.build_report(*_fixture_inputs(), generated_at=NOW)

    assert report["schema_version"] == "1.0"
    assert report["window"] == {
        "start": "2026-08-27T14:00:00+00:00",
        "end": "2026-08-29T14:00:00+00:00",
    }
    assert report["population"] == {
        "news_rows_total": 3,
        "news_rows_with_known_ticker": 2,
        "second_order": 1,
        "other": 1,
        "unknown_ticker": 1,
        "second_order_rate": 0.5,
    }
    assert report["forward_returns"]["unit"] == "sentiment_signal"
    assert report["forward_returns"]["second_order"]["forward_return"] == {
        "n": 1,
        "mean": 0.06,
        "median": 0.06,
    }
    assert report["forward_returns"]["second_order"]["forward_return_5d"]["n"] == 0
    assert report["forward_returns"]["other"]["forward_return"]["mean"] == -0.01

    agreement = report["directness_agreement"]
    assert agreement["unit"] == "llm_response"
    assert agreement["responses_with_directness"] == 2
    assert agreement["spillover_labels"] == ["competitor_readthrough", "sector"]
    assert agreement["spillover"] == {"n": 1, "rate": 0.5}
    assert agreement["by_bucket"] == {"competitor_readthrough": 1, "direct": 1}

    assert report["classifications"] == [{
        "news_log_id": 1,
        "ticker": "ADBE",
        "title": "Adobe stock rises following Salesforce earnings",
        "fetched_at": "2026-08-27T14:00:00+00:00",
        "category": "second_order",
        "connector": "following",
        "third_party_ticker": "CRM",
        "third_party_company": "Salesforce Inc",
    }]
    assert "1 su 2" in report["sintesi"]
    assert "non causale" in report["sintesi"]


def test_main_usa_il_loader_iniettato_e_scrive_json_atomico(tmp_path, monkeypatch):
    output = tmp_path / "second_order_news.json"
    fake_conn = object()
    monkeypatch.setattr(script, "_connect", lambda: fake_conn)
    monkeypatch.setattr(script, "load_inputs", lambda conn, since, until: _fixture_inputs())
    monkeypatch.setattr(script, "_utc_now", lambda: NOW)

    result = script.main([
        "--since", "2026-08-24",
        "--until", "2026-08-29",
        "--output", str(output),
    ])

    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8"))["population"]["second_order"] == 1
    assert not output.with_suffix(".json.tmp").exists()


def test_report_senza_popolazione_non_inventa_tassi():
    report = script.build_report([], [], [], [], generated_at=NOW)

    assert report["window"] == {"start": None, "end": None}
    assert report["population"]["second_order_rate"] is None
    assert report["directness_agreement"]["spillover"]["rate"] is None
