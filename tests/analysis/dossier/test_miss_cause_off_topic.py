"""OFF_TOPIC: distinguere «notizia generica» da «notizia su un'altra azienda» (#244).

Metà delle righe scorate (405 su 816 nelle 5 sedute 2026-08-06 → 08-12) nasce da
articoli taggati a 2+ ticker: liste, rassegne, 13F. Oggi finiscono tutte in
THIN_NEUTRAL insieme agli articoli che *parlano* del titolo ma non dicono nulla.

Sono due diagnosi opposte con due rimedi opposti:
  - THIN_NEUTRAL → esiste copertura sul titolo ed è poco informativa
                   ⇒ il sentiment editoriale non ha alpha
  - OFF_TOPIC    → non esiste copertura sul titolo, stiamo scorando pezzi su altri
                   ⇒ è un difetto della pipeline

La domanda di uscita n.1 della carta si falsifica sulla distribuzione delle cause,
e con NO_NEWS a 22 contro THIN_NEUTRAL a 19 il criterio si decide su un margine di 3.

Seam sotto test: `classify_miss_candidate`, modulo puro, nessun I/O.
"""
from src.analysis.dossier.miss_cause import (
    CAUSE_ORDER,
    classify_miss_candidate,
    count_by_cause,
    classify_miss_candidates,
)

# Un punteggio sotto la soglia thin di default (0.05): è ciò che un articolo su
# un'altra azienda produce correttamente quando viene scorato sotto questo ticker.
THIN = 0.004


def candidato(*, news_count: int, news_fanout: int | None = None, score: float = THIN) -> dict:
    c: dict = {
        "symbol": "SPCX",
        "return": -0.0393,
        "news_count": news_count,
        "segnali": [{"ora": "15:15", "score": score, "fallback": False}],
        "in_portafoglio": False,
    }
    if news_fanout is not None:
        c["news_fanout"] = news_fanout
    return c


class TestOffTopicSostituisceThinNeutral:
    def test_tutta_la_copertura_da_articoli_su_terzi_e_off_topic(self):
        """Caso reale: SPCX il 08-11, mover −3,93%, 6 righe e nessuna parla di SPCX
        (tre su Rocket Lab, una su Tesla, una su SpaceX/AST, una lista generica)."""
        assert classify_miss_candidate(candidato(news_count=6, news_fanout=6)) == "OFF_TOPIC"

    def test_copertura_tutta_sul_titolo_resta_thin_neutral(self):
        assert classify_miss_candidate(candidato(news_count=6, news_fanout=0)) == "THIN_NEUTRAL"

    def test_copertura_mista_resta_thin_neutral(self):
        """Se almeno una riga parla davvero del titolo, la copertura esiste: il
        giudizio «poco informativa» è legittimo e non va riclassificato."""
        assert classify_miss_candidate(candidato(news_count=6, news_fanout=5)) == "THIN_NEUTRAL"


class TestNonInvadeLeAltreCause:
    def test_senza_news_resta_no_news_anche_se_il_campo_e_presente(self):
        assert classify_miss_candidate(candidato(news_count=0, news_fanout=0)) == "NO_NEWS"

    def test_sopra_la_soglia_thin_resta_below_gate(self):
        """Un articolo su terzi che produce un punteggio vero è un problema diverso
        e più grave: non va nascosto dentro OFF_TOPIC."""
        c = candidato(news_count=4, news_fanout=4, score=0.20)
        assert classify_miss_candidate(c) == "BELOW_GATE"

    def test_sopra_il_gate_resta_non_classificato(self):
        c = candidato(news_count=4, news_fanout=4, score=0.55)
        assert classify_miss_candidate(c) == "NON_CLASSIFICATO"


class TestRetrocompatibilita:
    def test_candidato_senza_il_campo_si_comporta_come_prima(self):
        """I dossier già scritti non hanno news_fanout: devono continuare a
        classificarsi identici, altrimenti il ricalcolo storico non è confrontabile."""
        assert classify_miss_candidate(candidato(news_count=6)) == "THIN_NEUTRAL"


class TestAggregati:
    def test_off_topic_e_una_causa_del_fenomeno_e_sta_in_cause_order(self):
        assert "OFF_TOPIC" in CAUSE_ORDER

    def test_i_due_bucket_sono_contati_separatamente(self):
        classificati = classify_miss_candidates(
            [
                candidato(news_count=6, news_fanout=6),
                candidato(news_count=6, news_fanout=6),
                candidato(news_count=6, news_fanout=0),
            ]
        )
        conteggi = count_by_cause(classificati)
        assert conteggi["OFF_TOPIC"] == 2
        assert conteggi["THIN_NEUTRAL"] == 1
