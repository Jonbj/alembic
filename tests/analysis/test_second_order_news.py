"""#408 — classificazione deterministica delle notizie di secondo ordine."""

import pytest

from src.analysis.second_order_news import CompanyIdentity, SecondOrderDetector


COMPANIES = [
    CompanyIdentity("ADBE", "Adobe Inc", ("Adobe Systems",)),
    CompanyIdentity("AVGO", "Broadcom Inc", ("Broadcom Corporation",)),
    CompanyIdentity("INTC", "Intel Corporation", ("Intel Corp",)),
    CompanyIdentity("NOW", "ServiceNow Inc", ("ServiceNow",)),
    CompanyIdentity("CRM", "Salesforce Inc", ("Salesforce.com Inc",)),
    CompanyIdentity("NVDA", "NVIDIA Corporation", ("NVIDIA Corp",)),
    CompanyIdentity("MA", "Mastercard Inc", ("Mastercard International",)),
    CompanyIdentity("V", "Visa Inc", ("Visa International",)),
]


@pytest.mark.parametrize(
    ("ticker", "title", "third_party"),
    [
        (
            "ADBE",
            "Adobe stock is trading higher Thursday following quarterly earnings results from Salesforce",
            "CRM",
        ),
        (
            "AVGO",
            "Broadcom stock rises nearly 2% premarket following strong NVIDIA earnings",
            "NVDA",
        ),
        (
            "INTC",
            "Intel stock is surging Thursday following Nvidia's strong Q2",
            "NVDA",
        ),
        (
            "NOW",
            "Shares of ServiceNow are trading higher following a blockbuster Q2 from Salesforce",
            "CRM",
        ),
    ],
)
def test_rileva_i_quattro_seed_reali_della_issue(ticker, title, third_party):
    match = SecondOrderDetector(COMPANIES).classify(ticker, title)

    assert match is not None
    assert match.category == "second_order"
    assert match.connector == "following"
    assert match.third_party_ticker == third_party


def test_senza_connettore_non_classifica_un_titolo_sullemittente():
    match = SecondOrderDetector(COMPANIES).classify(
        "MA", "Why Is Mastercard Stock Surging on Monday?"
    )

    assert match is None


def test_senza_autoreferenza_non_confonde_il_fanout_con_secondo_ordine():
    match = SecondOrderDetector(COMPANIES).classify(
        "V", "Why Is Mastercard Stock Surging on Monday?"
    )

    assert match is None


def test_dopo_il_connettore_serve_unaltra_societa_nota():
    match = SecondOrderDetector(COMPANIES).classify(
        "V", "Visa Stock Climbs After Trump Buys Millions in Stock"
    )

    assert match is None


def test_la_stessa_societa_dopo_il_connettore_non_e_una_terza_parte():
    match = SecondOrderDetector(COMPANIES).classify(
        "CRM", "Salesforce stock rises following Salesforce's own earnings beat"
    )

    assert match is None


def test_connettori_e_nomi_rispettano_i_confini_di_parola():
    detector = SecondOrderDetector(COMPANIES)

    assert detector.classify(
        "V", "Visa stock rises in the aftermath of Salesforce earnings"
    ) is None
    assert detector.classify(
        "V", "Visa stock rises after NVIDIAware launches a product"
    ) is None


def test_ticker_assente_dalla_lookup_resta_non_classificato():
    assert SecondOrderDetector(COMPANIES).classify(
        "UNKNOWN", "Unknown stock rises following Salesforce earnings"
    ) is None
