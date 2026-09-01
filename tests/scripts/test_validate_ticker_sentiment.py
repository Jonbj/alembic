"""Golden set canonico per la misura extraction_method (#405).

Lo schema 046 conserva due righe per articolo, una per annotatore. La misura
non deve scambiarle per due ground truth indipendenti ne' includere un
disaccordo ancora aperto.
"""

from scripts import validate_ticker_sentiment as validation


def _label(
    label_id: int,
    news_log_id: int,
    annotator_id: str,
    tickers: list[str],
    *,
    relevance: str = "company_specific",
    sentiment: str = "positive",
    strength: float = 0.7,
    adjudicated: bool = False,
) -> dict:
    return {
        "label_id": label_id,
        "news_log_id": news_log_id,
        "url": f"https://example.test/{news_log_id}",
        "source": "alpaca_benzinga",
        "annotator_id": annotator_id,
        "label_date": f"2026-08-{label_id:02d}T12:00:00+00:00",
        "adjudicated": adjudicated,
        "gt_tickers": tickers,
        "gt_relevance": relevance,
        "gt_sentiment_dir": sentiment,
        "gt_sentiment_strength": strength,
        "text_adequacy": "full",
    }


def test_seleziona_una_ground_truth_per_articolo_senza_inventare_i_disaccordi():
    rows = [
        # Coppia concorde: vale un articolo, anche se l'ordine dell'array cambia.
        _label(1, 101, "a", ["MSFT", "AAPL"]),
        # La strength continua puo' differire: #54 non la manda in adjudication.
        _label(2, 101, "b", ["AAPL", "MSFT"], strength=0.4),
        # Disaccordo aperto: non e' ancora una ground truth.
        _label(3, 102, "a", ["NVO"]),
        _label(4, 102, "b", ["BSX"]),
        # Terza decisione esplicita: e' l'unica riga adjudicated e prevale.
        _label(5, 103, "a", ["LLY"]),
        _label(6, 103, "b", ["GOOGL"]),
        _label(7, 103, "adjudicator", ["GOOGL"], adjudicated=True),
        # Una sola annotazione nel nuovo schema non soddisfa il protocollo #54.
        _label(8, 104, "a", ["NVDA"]),
        # Marcare due verdetti discordi come adjudicated non dice quale abbia
        # vinto: senza una decisione canonica il dato resta fuori misura.
        _label(9, 105, "a", ["META"], adjudicated=True),
        _label(10, 105, "b", ["AMZN"], adjudicated=True),
    ]

    selected = validation._select_measurement_labels(
        rows, two_annotator_schema=True
    )

    assert [row["news_log_id"] for row in selected] == [101, 103]
    assert selected[0]["label_id"] == 2
    assert selected[1]["label_id"] == 7


def test_schema_legacy_conserva_la_singola_label_per_url():
    rows = [
        {"label_id": 1, "url": "https://example.test/a", "gt_tickers": ["AAPL"]},
        {"label_id": 2, "url": "https://example.test/b", "gt_tickers": ["MSFT"]},
    ]

    assert validation._select_measurement_labels(
        rows, two_annotator_schema=False
    ) == rows


def test_precisione_per_metodo_usa_le_label_canoniche_e_mostra_l_error_rate():
    labels = [
        _label(1, 101, "a", ["NVO"]),
        _label(2, 102, "a", ["MSFT"]),
    ]
    mappings = [
        {"url": "https://example.test/101", "method": "source_metadata", "ticker": "NVO"},
        {"url": "https://example.test/102", "method": "source_metadata", "ticker": "AAPL"},
        {"url": "https://example.test/102", "method": "org_lookup", "ticker": "MSFT"},
    ]

    assert validation._method_metrics(mappings, labels) == {
        "source_metadata": {"n": 2, "precision": 0.5, "error_rate": 0.5},
        "org_lookup": {"n": 1, "precision": 1.0, "error_rate": 0.0},
    }
