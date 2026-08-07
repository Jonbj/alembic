"""Osservazione del destino del segnale S4 → exit_mechanism (#184).

L'etichetta deve descrivere cosa il pipeline ha FATTO al segnale, non cosa
l'orologio suggerisce. Questi test fissano il vocabolario e la mappa.
"""
import pytest

from src.portfolio.exit_classification import (
    BELOW_ENTRY_GATE,
    ENTRY_FRESHNESS_FILTERED,
    FALLBACK_FILTERED,
    FRESH,
    MECHANISM_UNKNOWN,
    STALE_DROPPED,
    STALE_PRESERVED,
    describe_disposition,
    mechanism_for_disposition,
)


class TestMechanismForDisposition:
    def test_stale_dropped_is_expired(self):
        """L'unico caso in cui "expired" è un fatto osservato: scartato per età."""
        assert mechanism_for_disposition(STALE_DROPPED) == "expired"

    def test_stale_preserved_is_never_expired(self):
        """#184: un segnale ri-ammesso da FIX-D non è stato scartato per scadenza."""
        assert mechanism_for_disposition(STALE_PRESERVED) == MECHANISM_UNKNOWN

    def test_fresh_is_whipsaw(self):
        """Semantica #60 invariata: segnale fresco arrivato al motore, peso 0."""
        assert mechanism_for_disposition(FRESH) == "whipsaw"

    def test_filtered_dispositions_keep_their_own_name(self):
        assert mechanism_for_disposition(FALLBACK_FILTERED) == "fallback_filtered"
        assert mechanism_for_disposition(BELOW_ENTRY_GATE) == "below_entry_gate"
        assert (
            mechanism_for_disposition(ENTRY_FRESHNESS_FILTERED)
            == "entry_freshness_filtered"
        )

    def test_no_observation_is_unknown(self):
        """Nessuna osservazione registrata → il classificatore deve dirlo."""
        assert mechanism_for_disposition(None) == MECHANISM_UNKNOWN

    def test_unrecognised_disposition_is_unknown(self):
        assert mechanism_for_disposition("qualcosa_di_nuovo") == MECHANISM_UNKNOWN

    @pytest.mark.parametrize(
        "disposition",
        [FRESH, STALE_PRESERVED, STALE_DROPPED, FALLBACK_FILTERED,
         ENTRY_FRESHNESS_FILTERED, BELOW_ENTRY_GATE],
    )
    def test_mechanism_fits_the_db_column(self, disposition):
        """execution_decisions.exit_mechanism è VARCHAR(32) (migration 039)."""
        assert len(mechanism_for_disposition(disposition)) <= 32


class TestDescribeDisposition:
    def test_every_disposition_has_a_description(self):
        for disposition in (FRESH, STALE_PRESERVED, STALE_DROPPED,
                            FALLBACK_FILTERED, ENTRY_FRESHNESS_FILTERED,
                            BELOW_ENTRY_GATE):
            assert describe_disposition(disposition).strip()

    def test_preserved_description_mentions_fix_d(self):
        assert "FIX-D" in describe_disposition(STALE_PRESERVED)

    def test_no_observation_description_says_so(self):
        assert describe_disposition(None).strip()
