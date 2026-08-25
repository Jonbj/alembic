"""#286 — rendere i finding falsificabili e sintetizzabili.

Il ledger primario (``findings.json``) e' congelato e read-only: si costruiscono
VISTE PARALLELE che arricchiscono ogni finding con i campi di falsificabilita'
(giorni distinti, giorni esposti, non-occorrenze, evidenza contraria, distanza
da soglia, classe/dimensione, meccanismo, strategia, prova decisiva,
contamination, relazione finding->causa) e uno stato di falsificazione
(supported / contradicted / not_exposed), piu' una SYNTHESIS e un weekly rollup
deterministici. Nessuna cancellazione, fusione distruttiva o modifica
retroattiva del ledger primario: tutto e' derivato e rigenerabile.

Il modulo e' puro: riceve findings (read-only), il ledger delle occorrenze,
un dizionario dei segmenti per giorno (per i denominatori di esposizione) e
opzionali annotazioni parallele dell'operatore; restituisce dict, niente I/O.
"""

from __future__ import annotations

import datetime as dt

from src.analysis.dossier import falsifiability as F


# ---------------------------------------------------------------------------
# Fixture: findings minimali coerenti con la carta.
# ---------------------------------------------------------------------------


def _finding(
    fid="F-001",
    *,
    confidenza="congetturale",
    occorrenze=None,
    costo_cumulato_usd=None,
    occorrenze_non_stimate=0,
    primo_avvistamento="2026-07-31",
    stato="aperto",
):
    return {
        "id": fid,
        "titolo": "titolo",
        "tipo": "osservazione",
        "confidenza": confidenza,
        "primo_avvistamento": primo_avvistamento,
        "occorrenze": occorrenze if occorrenze is not None else [],
        "costo_cumulato_usd": costo_cumulato_usd,
        "stato": stato,
        "issue": None,
        "occorrenze_non_stimate": occorrenze_non_stimate,
    }


def _occ(data, costo_usd=None, nota="...", fonte="R"):
    return {"data": data, "costo_usd": costo_usd, "nota": nota, "fonte": fonte}


WINDOW = (dt.date(2026, 7, 31), dt.date(2026, 9, 28))


# ---------------------------------------------------------------------------
# AC1: il 31/07 e' escluso dai conteggi della finestra come da carta.
# ---------------------------------------------------------------------------


def test_giorni_distinti_esclude_il_31_luglio_secondo_la_carta():
    # La carta (nota sulla riga del 2026-07-31): le occorrenze datate 31/07 non
    # contano verso le soglie di ricorrenza ne' verso i costi cumulati.
    findings = {
        "findings": [
            _finding(
                "F-001",
                confidenza="congetturale",
                occorrenze=[
                    _occ("2026-07-31", costo_usd=500.0),  # PRIMA della finestra
                    _occ("2026-08-03", costo_usd=100.0),
                    _occ("2026-08-04", costo_usd=200.0),
                    _occ("2026-08-05", costo_usd=300.0),
                ],
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    # 3 giorni distinti in finestra (il 31/07 e' escluso), non 4.
    assert f["giorni_distinti"] == 3
    # il costo del 31/07 non entra nel cumulato in finestra.
    assert f["costo_cumulato_in_finestra_usd"] == 600.0


def test_giorni_distinti_conta_solo_date_distinte():
    findings = {
        "findings": [
            _finding(
                occorrenze=[
                    _occ("2026-08-03", costo_usd=10.0),
                    _occ("2026-08-03", costo_usd=20.0),  # stesso giorno
                    _occ("2026-08-04", costo_usd=30.0),
                ],
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    assert views["findings"][0]["giorni_distinti"] == 2


# ---------------------------------------------------------------------------
# distanza da soglia: quanto il finding dista dall'attraversare la soglia
# della sua confidenza, secondo la carta.
# ---------------------------------------------------------------------------


def test_distanza_soglia_congetturale_richiede_costo_e_giorni():
    # congetturale: >= $1000 E >= 10 giorni distinti (carta).
    findings = {
        "findings": [
            _finding(
                confidenza="congetturale",
                occorrenze=[_occ(f"2026-08-{d:02d}", costo_usd=100.0) for d in range(3, 8)]
                + [_occ(f"2026-08-{d:02d}", costo_usd=100.0) for d in range(10, 14)],
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    # 9 giorni distinti (< 10) e $900 cumulati (< $1000): sotto soglia su
    # entrambi gli assi.
    assert f["giorni_distinti"] == 9
    assert f["costo_cumulato_in_finestra_usd"] == 900.0
    assert f["oltre_soglia"] is False
    # distanza: quanto manca al raggiungimento su ciascun asse.
    assert f["distanza_soglia"]["costo_usd"] == 100.0  # 900 -> 1000
    assert f["distanza_soglia"]["giorni"] == 1  # 9 -> 10


def test_distanza_soglia_misurata_solo_costo():
    # misurata: >= $100 cumulati, ricorrenza irrilevante (carta).
    findings = {
        "findings": [
            _finding(confidenza="misurata", occorrenze=[_occ("2026-08-03", costo_usd=40.0)])
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    assert f["oltre_soglia"] is False
    assert f["distanza_soglia"]["costo_usd"] == 60.0  # 40 -> 100
    # misurata non ha soglia di giorni.
    assert f["distanza_soglia"]["giorni"] is None


def test_oltre_soglia_attribuita_richiede_entrambi_gli_assi():
    # attribuita: >= $250 E >= 5 giorni distinti.
    findings = {
        "findings": [
            _finding(
                confidenza="attribuita",
                occorrenze=[_occ(f"2026-08-{d:02d}", costo_usd=100.0) for d in range(3, 8)],
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    # 5 giorni e $500: oltre soglia su entrambi gli assi.
    assert f["giorni_distinti"] == 5
    assert f["costo_cumulato_in_finestra_usd"] == 500.0
    assert f["oltre_soglia"] is True


def test_oltre_soglia_non_stimata_richiede_solo_giorni():
    # occorrenze_non_stimate: >= 15 giorni distinti, costo irrilevante (carta).
    occorrenze = [_occ(f"2026-08-{d:02d}", costo_usd=None) for d in range(3, 18)]
    findings = {
        "findings": [
            _finding(
                confidenza="congetturale",
                occorrenze=occorrenze,
                occorrenze_non_stimate=15,
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    # 15 giorni non stimati: oltre soglia per ricorrenza.
    assert f["giorni_distinti"] == 15
    assert f["oltre_soglia"] is True


# ---------------------------------------------------------------------------
# classe/dimensione: categoria di magnitudo del costo cumulato in finestra.
# ---------------------------------------------------------------------------


def test_classe_dimensione_categorizza_il_costo_cumulato():
    findings = {
        "findings": [
            _finding(
                confidenza="misurata",
                occorrenze=[_occ("2026-08-03", costo_usd=40.0)],  # < $100
            ),
            _finding(
                "F-002",
                confidenza="misurata",
                occorrenze=[_occ("2026-08-03", costo_usd=150.0)],  # $100-$250
            ),
            _finding(
                "F-003",
                confidenza="attribuita",
                occorrenze=[_occ("2026-08-03", costo_usd=500.0)],  # $250-$1000
            ),
            _finding(
                "F-004",
                confidenza="congetturale",
                occorrenze=[_occ("2026-08-03", costo_usd=1500.0)],  # > $1000
            ),
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    by_id = {f["id"]: f for f in views["findings"]}
    assert by_id["F-001"]["dimensione"] == "sotto_100"
    assert by_id["F-002"]["dimensione"] == "100_250"
    assert by_id["F-003"]["dimensione"] == "250_1000"
    assert by_id["F-004"]["dimensione"] == "oltre_1000"

# ---------------------------------------------------------------------------
# AC2: ogni finding puo' registrare supported/contradicted/not-exposed e una
# prova decisiva read-only (dalle annotazioni parallele).
# ---------------------------------------------------------------------------


def test_stato_falsificazione_default_not_exposed_onesto():
    # senza annotazioni, lo stato e' not_exposed: non dichiariamo falso cio' che
    # non e' stato esposto a una prova decisiva.
    findings = {"findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]}
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    assert f["stato_falsificazione"] == "not_exposed"
    assert f["prova_decisiva"] is None
    assert f["meccanismo"] is None
    assert f["strategia"] is None
    assert f["relazione_finding_causa"] is None


def test_stato_falsificazione_supported_da_annotazioni():
    findings = {"findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]}
    annotations = {
        "F-001": {
            "stato_falsificazione": "supported",
            "prova_decisiva": "su 20 giorni NO_NEWS, 18 hanno avuto miss: soglia superata",
            "meccanismo": "NO_NEWS",
            "strategia": "S4",
            "relazione_finding_causa": "NO_NEWS",
        }
    }
    views = F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)
    f = views["findings"][0]
    assert f["stato_falsificazione"] == "supported"
    assert f["prova_decisiva"] is not None
    assert f["meccanismo"] == "NO_NEWS"
    assert f["strategia"] == "S4"
    assert f["relazione_finding_causa"] == "NO_NEWS"


def test_stato_falsificazione_contradicted_da_annotazioni():
    findings = {"findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]}
    annotations = {
        "F-001": {
            "stato_falsificazione": "contradicted",
            "prova_decisiva": "controllo: i ticker NO_NEWS guadagnano quanto gli altri",
        }
    }
    views = F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)
    assert views["findings"][0]["stato_falsificazione"] == "contradicted"


def test_stato_falsificazione_non_ammesso_ricade_su_not_exposed():
    findings = {"findings": [_finding()]}
    annotations = {"F-001": {"stato_falsificazione": "confuted"}}  # refuso
    views = F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)
    assert views["findings"][0]["stato_falsificazione"] == "not_exposed"


# ---------------------------------------------------------------------------
# esposizione: giorni_esposti / non_occorrenze / evidenza_contraria sono
# meccanici SOLO se e' nota la relazione finding->causa.
# ---------------------------------------------------------------------------


def test_esposizione_nulla_senza_relazione_finding_causa():
    # senza relazione_finding_causa, i denominatori sono nulli con missingness:
    # non si confonde un finding non testato con uno senza contro-evidenza.
    findings = {"findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]}
    views = F.build_falsifiability_views(
        findings,
        window=WINDOW,
        segments_by_day={"2026-08-03": {"NO_NEWS"}},
    )
    f = views["findings"][0]
    assert f["giorni_esposti"] is None
    assert f["non_occorrenze"] is None
    assert f["evidenza_contraria"] is None
    assert f["missingness"] == ["relazione_finding_causa_non_nota"]


def test_esposizione_calcolata_con_relazione_finding_causa():
    # F-001 e' legato a NO_NEWS. NO_NEWS appare 4 giorni in finestra; F-001 ha
    # occorrenza solo su 3. 1 non-occorrenza = 1 giorno di evidenza contraria.
    findings = {
        "findings": [
            _finding(
                occorrenze=[
                    _occ("2026-08-03", costo_usd=10.0),
                    _occ("2026-08-04", costo_usd=10.0),
                    _occ("2026-08-06", costo_usd=10.0),
                ],
            )
        ]
    }
    segments_by_day = {
        "2026-08-03": {"NO_NEWS", "BELOW_GATE"},
        "2026-08-04": {"NO_NEWS"},
        "2026-08-05": {"NO_NEWS"},  # causa presente, finding non registrato
        "2026-08-06": {"NO_NEWS"},
    }
    annotations = {"F-001": {"relazione_finding_causa": "NO_NEWS"}}
    views = F.build_falsifiability_views(
        findings, window=WINDOW, annotations=annotations, segments_by_day=segments_by_day
    )
    f = views["findings"][0]
    assert f["giorni_esposti"] == 4
    assert f["non_occorrenze"] == 1
    assert f["evidenza_contraria"] == ["2026-08-05"]
    assert f["missingness"] == []


def test_esposizione_esclude_il_31_luglio():
    # la causa presente il 31/07 non conta come giorno esposto (carta).
    findings = {
        "findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]
    }
    segments_by_day = {
        "2026-07-31": {"NO_NEWS"},  # escluso
        "2026-08-03": {"NO_NEWS"},
    }
    annotations = {"F-001": {"relazione_finding_causa": "NO_NEWS"}}
    views = F.build_falsifiability_views(
        findings, window=WINDOW, annotations=annotations, segments_by_day=segments_by_day
    )
    f = views["findings"][0]
    assert f["giorni_esposti"] == 1
    assert f["evidenza_contraria"] == []


# ---------------------------------------------------------------------------
# AC3: contamination flags propagano alle metriche dipendenti.
# ---------------------------------------------------------------------------


def _views_con_doppio_finding(contamination_f1=None, contamination_f2=None):
    findings = {
        "findings": [
            _finding(
                "F-001",
                confidenza="misurata",
                occorrenze=[_occ("2026-08-03", costo_usd=200.0)],
            ),
            _finding(
                "F-002",
                confidenza="misurata",
                occorrenze=[_occ("2026-08-04", costo_usd=80.0)],
            ),
        ]
    }
    annotations = {}
    if contamination_f1 is not None:
        annotations["F-001"] = {"contamination": contamination_f1}
    if contamination_f2 is not None:
        annotations["F-002"] = {"contamination": contamination_f2}
    return F.build_falsifiability_views(
        findings, window=WINDOW, annotations=annotations
    )


def test_contamination_flag_da_annotazioni_appare_nella_vista():
    views = _views_con_doppio_finding(contamination_f1="attribution")
    f1 = next(f for f in views["findings"] if f["id"] == "F-001")
    assert f1["contamination"] == "attribution"
    f2 = next(f for f in views["findings"] if f["id"] == "F-002")
    assert f2["contamination"] is None


def test_contamination_propaga_alle_metriche_dipendenti_somma_costi():
    # F-001 (contaminato, $200) + F-002 (pulito, $80). La somma "pulita" esclude
    # il costo del finding contaminato; la metrica "costo cumulato totale" e'
    # marcata come contaminata da F-001.
    views = _views_con_doppio_finding(contamination_f1="attribution")
    summary = F.build_contamination_summary(views)
    assert summary["costo_pulito_usd"] == 80.0
    assert summary["costo_contaminato_usd"] == 200.0
    assert "F-001" in summary["propagazione"]["costo_cumulato_totale_usd"]


def test_contamination_mancante_lascia_le_metriche_pulite():
    views = _views_con_doppio_finding()
    summary = F.build_contamination_summary(views)
    assert summary["costo_pulito_usd"] == 280.0
    assert summary["costo_contaminato_usd"] == 0.0
    assert summary["findings_contaminati"] == []


def test_contamination_propaga_al_contatore_oltre_soglia():
    # F-001 oltre soglia ($200 misurata >= $100) ma contaminato: il conteggio
    # "n. findings oltre soglia" va separato in pulito/contaminato.
    views = _views_con_doppio_finding(contamination_f1="attribution")
    summary = F.build_contamination_summary(views)
    assert summary["oltre_soglia_pulito"] == 0  # F-002 ($80) sotto soglia
    assert summary["oltre_soglia_contaminato"] == 1  # F-001 oltre soglia ma contaminato


def test_contamination_multipli_tipi_sono_una_lista():
    views = _views_con_doppio_finding(contamination_f1=["attribution", "segno"])
    summary = F.build_contamination_summary(views)
    fc = next(f for f in summary["findings_contaminati"] if f["id"] == "F-001")
    assert fc["contamination"] == ["attribution", "segno"]


# ---------------------------------------------------------------------------
# Validator: prova decisiva obbligatoria con un verdetto e read-only.
# ---------------------------------------------------------------------------


def _views_con_stato(stato, prova=None):
    findings = {"findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]}
    annotations = {"F-001": {"stato_falsificazione": stato}}
    if prova is not None:
        annotations["F-001"]["prova_decisiva"] = prova
    return F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)


def test_validator_accetta_not_exposed_senza_prova_decisiva():
    views = _views_con_stato("not_exposed")
    res = F.validate_falsifiability(views)
    assert res["ok"], res["errors"]


def test_validator_richiede_prova_decisiva_con_verdetto_supported():
    views = _views_con_stato("supported", prova=None)
    res = F.validate_falsifiability(views)
    assert not res["ok"]
    assert any("prova_decisiva" in e for e in res["errors"])


def test_validator_richiede_prova_decisiva_con_verdetto_contradicted():
    views = _views_con_stato("contradicted", prova=None)
    res = F.validate_falsifiability(views)
    assert not res["ok"]


def test_validator_accetta_verdetto_con_prova_decisiva():
    views = _views_con_stato("supported", prova="test X conferma")
    res = F.validate_falsifiability(views)
    assert res["ok"], res["errors"]


def test_validator_prova_decisiva_e_read_only_immutabile():
    # la prova decisiva, una volta registrata, non si retro-aggiorna: e' un
    # fatto registrato, non un parametro di taratura. Se l'annotazione
    # precedente aveva una prova e ora e' diversa (o manca), e' un errore.
    views = _views_con_stato("supported", prova="prova B nuova")
    previous = {"F-001": {"prova_decisiva": "prova A originale"}}
    res = F.validate_falsifiability(views, previous_annotations=previous)
    assert not res["ok"]
    assert any("prova_decisiva" in e and "read-only" in e for e in res["errors"])


def test_validator_prova_decisiva_stabile_passa():
    views = _views_con_stato("supported", prova="prova A originale")
    previous = {"F-001": {"prova_decisiva": "prova A originale"}}
    res = F.validate_falsifiability(views, previous_annotations=previous)
    assert res["ok"], res["errors"]


def test_validator_ammette_solo_stati_conosciuti():
    # stato non ammesso ricade su not_exposed nella vista, ma se un'annotazione
    # grezza arriva col campo invalido il validator lo segnala.
    findings = {"findings": [_finding()]}
    annotations = {"F-001": {"stato_falsificazione": "inconclusive"}}
    views = F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)
    res = F.validate_falsifiability(views, annotations=annotations)
    assert not res["ok"]
    assert any("stato_falsificazione" in e for e in res["errors"])


# ---------------------------------------------------------------------------
# Status events: snapshot di falsificabilita' parallelo per finding.
# ---------------------------------------------------------------------------


def test_status_events_snapshot_per_finding_con_stato_falsificazione():
    findings = {
        "findings": [
            _finding("F-001", occorrenze=[_occ("2026-08-03", costo_usd=10.0)]),
            _finding("F-002", occorrenze=[_occ("2026-08-04", costo_usd=10.0)]),
        ]
    }
    annotations = {
        "F-001": {"stato_falsificazione": "supported", "prova_decisiva": "p"},
        "F-002": {"stato_falsificazione": "contradicted", "prova_decisiva": "q"},
    }
    views = F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)
    events = F.build_status_events_falsifiability(views)
    by_id = {e["finding_id"]: e for e in events}
    assert all(e["kind"] == "falsifiability_snapshot" for e in events)
    assert by_id["F-001"]["stato_falsificazione"] == "supported"
    assert by_id["F-001"]["oltre_soglia"] is False
    assert by_id["F-002"]["stato_falsificazione"] == "contradicted"
    # la contaminazione fa parte dello snapshot (tracciabilita' dello stato).
    assert "contamination" in by_id["F-001"]


# ---------------------------------------------------------------------------
# AC4: SYNTHESIS deterministica — solo cambi, soglie, P&L economico,
# integrita' dati.
# ---------------------------------------------------------------------------


def _views_due_findings():
    findings = {
        "findings": [
            _finding(
                "F-001",
                confidenza="misurata",
                occorrenze=[_occ("2026-08-03", costo_usd=150.0)],  # oltre soglia
            ),
            _finding(
                "F-002",
                confidenza="misurata",
                occorrenze=[_occ("2026-08-03", costo_usd=40.0)],  # sotto soglia
            ),
        ]
    }
    return F.build_falsifiability_views(findings, window=WINDOW)


def test_synthesis_sezione_soglie_mostra_stato_soglia_di_ogni_finding():
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    syn = F.build_synthesis(views, cont)
    soglie = {s["finding_id"]: s for s in syn["soglie"]}
    assert soglie["F-001"]["oltre_soglia"] is True
    assert soglie["F-002"]["oltre_soglia"] is False
    # la distanza da soglia e' riportata (quanto manca / quanto supera).
    assert soglie["F-002"]["distanza_soglia"]["costo_usd"] == 60.0


def test_synthesis_sezione_cambi_senza_precedente_tutto_nuovo():
    # primo digest: ogni finding e' nuovo (nessun precedente).
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    syn = F.build_synthesis(views, cont)
    nuovi = {c["finding_id"] for c in syn["cambi"] if c["campo"] == "nuovo"}
    assert nuovi == {"F-001", "F-002"}


def test_synthesis_sezione_cambi_mostra_solo_cio_che_cambia():
    # previous digest: F-001 era oltre_soglia false (sotto), ora true. F-002
    # invariata. Il digest mostra SOLO il cambio di F-001, non rumore su F-002.
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    previous = {
        "findings": [
            {"id": "F-001", "oltre_soglia": False, "stato_falsificazione": "not_exposed",
             "contamination": None, "giorni_distinti": 1, "costo_cumulato_in_finestra_usd": 40.0},
            {"id": "F-002", "oltre_soglia": False, "stato_falsificazione": "not_exposed",
             "contamination": None, "giorni_distinti": 1, "costo_cumulato_in_finestra_usd": 40.0},
        ]
    }
    syn = F.build_synthesis(views, cont, previous_digest=previous)
    cambi_f1 = [c for c in syn["cambi"] if c["finding_id"] == "F-001"]
    cambi_f2 = [c for c in syn["cambi"] if c["finding_id"] == "F-002"]
    # F-001 e' passata oltre soglia e il costo e' cresciuto: 2 cambi.
    campi_f1 = {c["campo"] for c in cambi_f1}
    assert "oltre_soglia" in campi_f1
    assert "costo_cumulato_in_finestra_usd" in campi_f1
    # F-002 invariata: nessun cambio.
    assert cambi_f2 == []


def test_synthesis_sezione_cambi_mostra_transizione_di_stato_falsificazione():
    findings = {"findings": [_finding(occorrenze=[_occ("2026-08-03", costo_usd=10.0)])]}
    annotations = {"F-001": {"stato_falsificazione": "supported", "prova_decisiva": "p"}}
    views = F.build_falsifiability_views(findings, window=WINDOW, annotations=annotations)
    cont = F.build_contamination_summary(views)
    previous = {
        "findings": [
            {"id": "F-001", "oltre_soglia": False, "stato_falsificazione": "not_exposed",
             "contamination": None, "giorni_distinti": 1, "costo_cumulato_in_finestra_usd": 10.0},
        ]
    }
    syn = F.build_synthesis(views, cont, previous_digest=previous)
    trans = [c for c in syn["cambi"] if c["campo"] == "stato_falsificazione"]
    assert trans and trans[0]["da"] == "not_exposed" and trans[0]["a"] == "supported"


def test_synthesis_sezione_pnl_economico_passato_tramite_input():
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    pnl = {"S1": -2.81, "S4": 13.03, "BOOK": 10.22, "missingness": {"S4": 0}}
    syn = F.build_synthesis(views, cont, economic_pnl=pnl)
    assert syn["pnl_economico"] == pnl


def test_synthesis_sezione_pnl_economico_null_se_non_fornito():
    views = _views_due_findings()
    syn = F.build_synthesis(views, F.build_contamination_summary(views))
    assert syn["pnl_economico"] is None


def test_synthesis_sezione_integrita_dati_passata_tramite_input():
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    integrity = {"ok": True, "n_errori": 0, "n_warning": 1, "warning": ["x"]}
    syn = F.build_synthesis(views, cont, integrity=integrity)
    assert syn["integrita"]["ok"] is True
    assert syn["integrita"]["n_warning"] == 1


# ---------------------------------------------------------------------------
# weekly rollup deterministico.
# ---------------------------------------------------------------------------


def test_weekly_rollup_e_un_digest_con_scope_weekly():
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    roll = F.build_weekly_rollup(views, cont, settimana="2026-W33")
    assert roll["scope"]["tipo"] == "weekly"
    assert roll["scope"]["settimana"] == "2026-W33"
    # ha le stesse 4 sezioni del synthesis.
    for k in ("cambi", "soglie", "pnl_economico", "integrita"):
        assert k in roll


def test_synthesis_mostra_solo_le_quattro_sezioni_dell_acceptance_criterion():
    # Regressione review #286 (criterio 1): l'AC dichiara SOLO cambi, soglie,
    # P&L economico e integrita'. Il contamination_summary e' gia' esposto
    # top-level dall'orchestratore (scripts/build_longitudinal_panels.py) —
    # una sua copia annidata nel digest non e' dichiarata e viola l'AC.
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    syn = F.build_synthesis(views, cont)
    sezioni = set(syn) - {"schema_version", "scope"}
    assert sezioni == {"cambi", "soglie", "pnl_economico", "integrita"}


def test_weekly_rollup_mostra_solo_le_quattro_sezioni_dell_acceptance_criterion():
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    roll = F.build_weekly_rollup(views, cont, settimana="2026-W33")
    sezioni = set(roll) - {"schema_version", "scope"}
    assert sezioni == {"cambi", "soglie", "pnl_economico", "integrita"}


def test_weekly_rollup_con_precedente_mostra_cambi_della_settimana():
    views = _views_due_findings()
    cont = F.build_contamination_summary(views)
    previous = {
        "findings": [
            {"id": "F-001", "oltre_soglia": False, "stato_falsificazione": "not_exposed",
             "contamination": None, "giorni_distinti": 1, "costo_cumulato_in_finestra_usd": 40.0},
            {"id": "F-002", "oltre_soglia": False, "stato_falsificazione": "not_exposed",
             "contamination": None, "giorni_distinti": 1, "costo_cumulato_in_finestra_usd": 40.0},
        ]
    }
    roll = F.build_weekly_rollup(
        views, cont, settimana="2026-W33", previous_digest=previous
    )
    campi = {(c["finding_id"], c["campo"]) for c in roll["cambi"]}
    assert ("F-001", "oltre_soglia") in campi


# ---------------------------------------------------------------------------
# Soglia: il percorso "non stimato" (>= 15 giorni) e' un FALLBACK OR per i
# finding senza costo stimabile, non un override. Un finding con costo
# stimabile va valutato dalla soglia della sua confidenza; i giorni non
# stimati sono contesto, non la via principale.
# ---------------------------------------------------------------------------


def test_finding_con_costo_stimabile_valutato_dalla_soglia_di_confidenza():
    # congetturale con $1500 (>= $1000) e 12 giorni (>= 10): oltre soglia via
    # confidenza, anche se un'occorrenza e' non stimata. Il fallback ricorrenza
    # NON deve sostituire la via del costo.
    findings = {
        "findings": [
            _finding(
                confidenza="congetturale",
                occorrenze=[_occ(f"2026-08-{d:02d}", costo_usd=150.0) for d in range(3, 15)]
                + [_occ("2026-08-15", costo_usd=None)],  # 1 giorno non stimato
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    assert f["giorni_distinti"] == 13
    assert f["costo_cumulato_in_finestra_usd"] == 1800.0
    assert f["oltre_soglia"] is True  # via confidenza, non via ricorrenza


def test_finding_senza_costo_usa_il_fallback_ricorrenza():
    # congetturale con tutti costi null: la via del costo non scatta (0 < 1000),
    # ma >= 15 giorni non stimati la fa entrare in roadmap per ricorrenza.
    findings = {
        "findings": [
            _finding(
                confidenza="congetturale",
                occorrenze=[_occ(f"2026-08-{d:02d}", costo_usd=None) for d in range(3, 18)],
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    assert f["costo_cumulato_in_finestra_usd"] == 0.0
    assert f["oltre_soglia"] is True  # via ricorrenza (15 giorni non stimati)
    assert f["distanza_soglia"]["ricorrenza_giorni"] == 0  # a soglia


def test_finding_sotto_soglia_su_entrambe_le_vie():
    # congetturale: $800 (< $1000) e 8 giorni (>= 10? no), 3 non stimati (< 15):
    # sotto soglia su entrambe le vie.
    findings = {
        "findings": [
            _finding(
                confidenza="congetturale",
                occorrenze=[_occ(f"2026-08-{d:02d}", costo_usd=100.0) for d in range(3, 11)]
                + [_occ(f"2026-08-{d:02d}", costo_usd=None) for d in range(11, 14)],
            )
        ]
    }
    views = F.build_falsifiability_views(findings, window=WINDOW)
    f = views["findings"][0]
    assert f["giorni_distinti"] == 11  # 8 stimati + 3 non stimati
    assert f["costo_cumulato_in_finestra_usd"] == 800.0
    assert f["oltre_soglia"] is False
    assert f["distanza_soglia"]["costo_usd"] == 200.0  # 800 -> 1000
    assert f["distanza_soglia"]["giorni"] == -1  # 11 - 10 = supera (negativo)
    assert f["distanza_soglia"]["ricorrenza_giorni"] == 12  # 3 -> 15
