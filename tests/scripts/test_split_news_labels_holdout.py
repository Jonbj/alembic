"""Test delle funzioni pure del holdout split 60/40 (#54).

Assegnamento deterministico (seed fisso) dei news_log_id a train/test,
~60/40, riproducibile. Pura computazione; la persistenza in news_label_splits
e' testata a parte su DB.
"""

from __future__ import annotations

import scripts.split_news_labels_holdout as holdout


def test_assign_is_deterministic_same_seed():
    ids = list(range(1, 101))
    a = holdout.assign_splits(ids, seed=42)
    b = holdout.assign_splits(ids, seed=42)
    assert a == b


def test_assign_ratio_is_about_60_40():
    ids = list(range(1, 101))   # 100 articoli
    split = holdout.assign_splits(ids, seed=42, train_fraction=0.6)
    train = sum(1 for v in split.values() if v == "train")
    test = sum(1 for v in split.values() if v == "test")
    assert train + test == 100
    assert train == 60           # round(100 * 0.6)
    assert test == 40


def test_assign_covers_every_id_exactly_once():
    ids = [7, 3, 21, 99, 5, 12, 44, 1, 8, 100]
    split = holdout.assign_splits(ids, seed=1)
    assert set(split.keys()) == set(ids)
    assert all(v in ("train", "test") for v in split.values())


def test_assign_is_stable_under_input_order():
    # L'ordine di input non cambia il risultato (ordina internamente).
    ids_sorted = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    ids_shuffled = [10, 3, 7, 1, 5, 9, 4, 8, 2, 6]
    assert holdout.assign_splits(ids_sorted, seed=7) == holdout.assign_splits(ids_shuffled, seed=7)


def test_different_seeds_can_differ():
    ids = list(range(1, 101))
    a = holdout.assign_splits(ids, seed=42)
    b = holdout.assign_splits(ids, seed=7)
    # seed diverso → quasi sicuramente assegnamenti diversi (almeno uno).
    assert a != b