"""Test delle funzioni pure dello script inter-annotator agreement (#54).

Cohen's kappa (direction, 3-classi) e ticker (confronto di insiemi, 4-classi),
detection dei disaccordi per l'adjudication workflow. Pura computazione, niente
DB: la lettura delle righe labeled e' testata a parte via mock.
"""

from __future__ import annotations

import scripts.inter_annotator_agreement as iaa

DIRECTIONS = ("positive", "negative", "neutral")


# ---------------------------------------------------------------- Cohen's kappa

def test_kappa_perfect_agreement_is_one():
    assert iaa.cohens_kappa(
        ["positive", "negative", "neutral", "positive"],
        ["positive", "negative", "neutral", "positive"],
        DIRECTIONS,
    ) == 1.0


def test_kappa_pure_chance_is_zero():
    # Due annotatori indipendenti su 2 categorie con 50/50 marginali → kappa ~ 0.
    a = ["positive", "positive", "negative", "negative"]
    b = ["positive", "negative", "positive", "negative"]
    k = iaa.cohens_kappa(a, b, DIRECTIONS)
    assert k is not None and abs(k) < 1e-9


def test_kappa_classic_textbook_value():
    # Esempio canonico di Cohen (1960): k = 0.406 per i 2 annotatori su 2 classi.
    # A: P P P P M M M M ; B: P P P M P M M M  (P=0..3 agree su 8? vedi calcolo)
    a = ["P", "P", "P", "P", "M", "M", "M", "M"]
    b = ["P", "P", "P", "M", "P", "M", "M", "M"]
    k = iaa.cohens_kappa(a, b, ("P", "M"))
    # po = 6/8 = 0.75; pe = (0.5*0.5)+(0.5*0.5) = 0.5; k = (0.75-0.5)/(1-0.5) = 0.5
    assert k is not None and abs(k - 0.5) < 1e-9


def test_kappa_no_variance_returns_none():
    # Tutti d'accordo sulla stessa classe → pe = 1 → kappa indefinito.
    assert iaa.cohens_kappa(
        ["neutral", "neutral", "neutral"],
        ["neutral", "neutral", "neutral"],
        DIRECTIONS,
    ) is None


def test_kappa_empty_returns_none():
    assert iaa.cohens_kappa([], [], DIRECTIONS) is None


# ----------------------------------------------------------------- ticker kappa

def test_ticker_category_classification():
    # Relazione simmetrica fra i due insiemi (per la worklist di adjudication).
    assert iaa.ticker_category({"AAPL"}, {"AAPL"}) == "match"
    assert iaa.ticker_category({"AAPL", "MSFT"}, {"AAPL", "MSFT"}) == "match"
    assert iaa.ticker_category({"AAPL", "MSFT"}, {"AAPL"}) == "overlap"
    assert iaa.ticker_category({"AAPL"}, {"MSFT"}) == "disjoint"
    assert iaa.ticker_category(set(), set()) == "both_empty"
    assert iaa.ticker_category(set(), {"AAPL"}) == "disjoint"  # one empty != both empty


def test_ticker_kappa_binary_units_over_global_universe():
    # Cohen's kappa su presenza/assenza di ogni ticker dell'universo: e' la
    # maniera standard per annotazioni set-valued. Universo globale cosi'
    # l'assenza e' informativa (non solo l'unione per-item).
    sets_a = [{"AAPL"}, {"MSFT"}, {"AAPL", "MSFT"}, {"AAPL"}]
    sets_b = [{"AAPL"}, {"MSFT"}, {"AAPL", "MSFT"}, {"MSFT"}]
    k = iaa.ticker_kappa(sets_a, sets_b)
    # 6 su 8 unit (item,ticker) d'accordo, pe~0.53 → kappa ≈ 0.47 (in (0,1)).
    assert k is not None and 0.0 < k < 1.0


def test_ticker_kappa_perfect_match_is_one():
    sets = [{"AAPL"}, {"MSFT"}, set(), {"TSLA"}]
    k = iaa.ticker_kappa(sets, sets)
    assert k == 1.0


# ------------------------------------------------------------- disagreements

def test_disagreements_flags_direction_and_ticker_mismatch():
    items = [
        {"news_log_id": 1, "dir": ("positive", "positive"),
         "tickers": ({"AAPL"}, {"AAPL"})},            # d'accordo
        {"news_log_id": 2, "dir": ("positive", "negative"),
         "tickers": ({"AAPL"}, {"AAPL"})},            # disaccordo direzione
        {"news_log_id": 3, "dir": ("neutral", "neutral"),
         "tickers": ({"AAPL"}, {"MSFT"})},           # disaccordo ticker
    ]
    dis = iaa.disagreements(items)
    assert {d["news_log_id"] for d in dis} == {2, 3}


def test_disagreements_empty_when_all_agree():
    items = [
        {"news_log_id": 1, "dir": ("positive", "positive"),
         "tickers": ({"AAPL"}, {"AAPL"})},
        {"news_log_id": 2, "dir": ("neutral", "neutral"),
         "tickers": (set(), set())},
    ]
    assert iaa.disagreements(items) == []