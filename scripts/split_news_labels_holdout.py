#!/usr/bin/env python3
"""QX-01 holdout 60/40 split (#54).

Divide il golden label set in train (calibrazione QS-01) / test (validazione)
60/40 per news_log_id, in modo deterministico (seed fisso), e lo persiste nella
tabella news_label_splits (migrazione 046). Non calibrare e validare sullo
stesso split (overfit del label set — spec §5.8, rischio §5.10.5).

Lo split e' per *articolo* (news_log_id): entrambe le righe 2-annotator di uno
stesso articolo finiscono nello stesso split. Idempotente: salta i news_log_id
gia' assegnati. Offline. Run nel container worker:

    docker compose exec worker python scripts/split_news_labels_holdout.py
"""
from __future__ import annotations

import os
import random

import psycopg2

_SEED = 42
_TRAIN_FRACTION = 0.60


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def assign_splits(news_log_ids, seed: int = _SEED,
                  train_fraction: float = _TRAIN_FRACTION) -> dict[int, str]:
    """Assegna ogni news_log_id a 'train' o 'test', deterministico.

    Ordina gli id (ordine di input irrilevante), mescola con seed fisso, i primi
    round(n*train_fraction) sono train, il resto test."""
    ids = sorted(int(i) for i in news_log_ids)
    n = len(ids)
    if n == 0:
        return {}
    rng = random.Random(seed)
    shuffled = list(ids)
    rng.shuffle(shuffled)
    n_train = round(n * train_fraction)
    out: dict[int, str] = {}
    for i, nid in enumerate(shuffled):
        out[nid] = "train" if i < n_train else "test"
    return out


def main() -> int:
    with _conn() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT news_log_id FROM news_labels
                   WHERE news_log_id IS NOT NULL"""
            )
            all_ids = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT news_log_id FROM news_label_splits")
            already = {r[0] for r in cur.fetchall()}

        new_ids = [i for i in all_ids if i not in already]
        if not new_ids:
            print(f"Nessun nuovo news_log_id da assegnare "
                  f"({len(already)} gia' in news_label_splits).")
            conn.rollback()
            return 0

        splits = assign_splits(new_ids)
        with conn.cursor() as cur:
            for nid, split in splits.items():
                cur.execute(
                    """INSERT INTO news_label_splits (news_log_id, split)
                       VALUES (%s, %s)
                       ON CONFLICT (news_log_id) DO NOTHING""",
                    (nid, split),
                )
        conn.commit()

    n_train = sum(1 for v in splits.values() if v == "train")
    n_test = len(splits) - n_train
    print(f"Assegnati {len(splits)} nuovi news_log_id: "
          f"train={n_train} ({n_train/len(splits):.0%}), "
          f"test={n_test} ({n_test/len(splits):.0%}).")
    print(f"Totale in news_label_splits: {len(already) + len(splits)} "
          f"(di {len(all_ids)} articoli con label).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())