"""Rilevatori di loop e di corsa condannata (spec 2026-09-03 §5).

Le soglie sono calibrate su due campioni reali del 2026-09-02: un ragionamento
sano di 23.653 caratteri portava 2 righe ripetute e 1 solo 12-gramma ripetuto.
"""

from src.review_locale.rilevatori import (
    e_corsa_condannata,
    e_loop,
    misura_ripetizione,
)


def test_ragionamento_sano_non_e_loop():
    """Un testo che avanza non produce ripetizione, anche se lungo."""
    testo = "\n".join(
        f"Considero ora il ramo numero {i} della classificazione e valuto "
        f"se la condizione a monte possa produrre questo esito nel caso {i}."
        for i in range(200)
    )

    misure = misura_ripetizione(testo)

    assert misure["dodici_grammi_ripetuti"] == 0
    assert not e_loop(misure)


def test_citazione_ripetuta_non_conta_come_loop():
    """Il campione reale sano ripeteva 2 righe: due citazioni. Non e' un loop."""
    citazione = "NO_RELEVANT_NEWS, LATE_NEWS, ENTITY_ERROR, NO_SIGNAL, WRONG_SIGN, BELOW_GATE"
    testo = "\n".join(
        [citazione]
        + [f"Passo {i}: verifico la condizione sul ramo {i} del funnel v2." for i in range(50)]
        + [citazione]
    )

    misure = misura_ripetizione(testo)

    assert misure["righe_ripetute"] == 1
    assert not e_loop(misure)


def test_loop_vero_e_rilevato():
    """Lo stesso paragrafo ripetuto molte volte supera la soglia."""
    paragrafo = (
        "Devo verificare se il ramo OUT_OF_SCOPE sia raggiungibile oppure no, "
        "quindi torno a controllare la condizione in universo del mover prima "
        "di decidere come proseguire con il prossimo passo del ragionamento."
    )
    testo = "\n".join([paragrafo] * 30)

    misure = misura_ripetizione(testo)

    assert misure["dodici_grammi_ripetuti"] > 10
    assert e_loop(misure)


def test_righe_duplicate_distinte_non_si_mescolano():
    """Due frasi diverse, ciascuna ripetuta ma mai adiacente nel testo
    originale (in mezzo c'e' sempre una riga unica), non devono fondersi in
    un 12-gramma fabbricato al bordo fra l'una e l'altra: quel bordo non e'
    mai comparso nel testo sorgente. Ciascuna frase ha esattamente 12
    parole, quindi presa da sola produce esattamente una finestra interna
    (la riga stessa, per intero): con 6 ripetizioni ciascuna, il suo unico
    12-gramma supera la soglia di conteggio e viene contato una volta. Il
    punto del test resta lo stesso: il totale deve essere tracciabile al
    gramma proprio di A piu' al gramma proprio di B (2 in tutto) e non di
    piu' — un gramma in eccesso rivelerebbe un bordo fabbricato dal join fra
    le righe, che nel testo sorgente non e' mai comparso.
    """
    frase_a = "Il ramo NO_SIGNAL resta plausibile su questo mover quindi proseguo con analisi"
    frase_b = "Controllo ora se ENTITY_ERROR sia coerente col resto ragionamento fin qui svolto"
    righe = []
    for i in range(6):
        righe.append(frase_a)
        righe.append(f"Passo unico numero {i} che non si ripete mai nel testo qui sopra o sotto davvero.")
        righe.append(frase_b)
    testo = "\n".join(righe)

    misure = misura_ripetizione(testo)

    assert misure["dodici_grammi_ripetuti"] == 2
    assert misure["righe_ripetute"] == 10


def test_soglia_loop_e_configurabile():
    testo = "\n".join(
        ["la stessa frase ripetuta molte volte senza mai avanzare di un solo passo del ragionamento vero e proprio"] * 15
    )
    misure = misura_ripetizione(testo)

    assert e_loop(misure, soglia_dodici_grammi=5)
    assert not e_loop(misure, soglia_dodici_grammi=10_000)


def test_corsa_condannata_solo_con_content_vuoto():
    """A 28.000 token di ragionamento senza JSON, il tetto non basta piu'."""
    assert e_corsa_condannata(token_ragionamento=28_000, content_vuoto=True)
    assert not e_corsa_condannata(token_ragionamento=28_000, content_vuoto=False)


def test_corsa_sana_non_e_condannata():
    """Il run riuscito su PR #472: 16.453 token totali, ~14.400 di ragionamento."""
    assert not e_corsa_condannata(token_ragionamento=14_400, content_vuoto=True)


def test_tetto_corsa_condannata_e_configurabile():
    assert e_corsa_condannata(token_ragionamento=1_000, content_vuoto=True, tetto=500)
