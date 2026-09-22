"""Test della distillazione deterministica dei log (punto 2, triage locale)."""

from src.triage_log.distillazione import (
    Voce,
    distilla,
    normalizza_riga,
    novita,
    redigi,
    rendi_digest,
    seleziona,
)


def test_due_righe_che_differiscono_solo_per_timestamp_e_id_hanno_lo_stesso_template():
    a = (
        "[2026-09-14 00:00:00,002: INFO/MainProcess] Task src.workers.x.run"
        "[29b674c7-0341-46da-ad5e-65435b87d447] received"
    )
    b = (
        "[2026-09-14 23:11:59,999: INFO/MainProcess] Task src.workers.x.run"
        "[fd10ac97-d6ca-42c0-b573-892105ca82f4] received"
    )
    assert normalizza_riga(a) == normalizza_riga(b)


def test_il_numero_del_fork_pool_worker_non_moltiplica_i_template():
    a = "[2026-09-14 00:00:01,518: WARNING/ForkPoolWorker-3] SPY benchmark fetch failed"
    b = "[2026-09-14 00:00:02,001: WARNING/ForkPoolWorker-11] SPY benchmark fetch failed"
    assert normalizza_riga(a) == normalizza_riga(b)


def test_il_livello_resta_nel_template_perche_distingue_un_errore_da_un_informativa():
    errore = "[2026-09-14 08:09:15,466: ERROR/MainProcess] Process exited"
    info = "[2026-09-14 08:09:15,466: INFO/MainProcess] Process exited"
    assert normalizza_riga(errore) != normalizza_riga(info)
    assert "ERROR" in normalizza_riga(errore)


def test_redigi_maschera_il_token_del_bot_telegram():
    riga = (
        "HTTP Request: GET https://api.telegram.org/bot8611445937:"
        "AAH3WL4LYETGPjX593tFunF_IiOiCtv5Q5c/getUpdates?offset=1 \"HTTP/1.1 200 OK\""
    )
    redatta = redigi(riga)
    assert "AAH3WL4LYETGPjX593tFunF_IiOiCtv5Q5c" not in redatta
    assert "[REDATTO]" in redatta


def test_redigi_maschera_bearer_e_api_key():
    assert "sk-abcdef123456" not in redigi("Authorization: Bearer sk-abcdef123456")
    assert "segretissima" not in redigi('{"api_key": "segretissima"}')


def test_l_esempio_conservato_e_gia_redatto():
    riga = "[2026-09-14 00:00:04,856: INFO/W] GET https://api.telegram.org/bot99:AAsegreto/x"
    (voce,) = distilla([riga])
    assert "AAsegreto" not in voce.esempio


def test_distilla_conta_le_occorrenze_e_tiene_prima_e_ultima():
    righe = [
        "[2026-09-14 00:00:01,000: WARNING/W-1] SPY benchmark fetch failed",
        "[2026-09-14 12:30:02,000: WARNING/W-2] SPY benchmark fetch failed",
        "[2026-09-14 23:59:03,000: WARNING/W-3] SPY benchmark fetch failed",
    ]
    (voce,) = distilla(righe)
    assert voce.conteggio == 3
    assert voce.prima == "00:00:01"
    assert voce.ultima == "23:59:03"
    assert voce.livello == "WARNING"


def test_novita_restituisce_solo_i_template_assenti_dallo_storico():
    oggi = distilla(
        [
            "[2026-09-14 00:00:01,000: ERROR/W-1] cosa mai vista",
            "[2026-09-14 00:00:02,000: INFO/W-1] cosa di tutti i giorni",
        ]
    )
    storico = {v.template for v in distilla(["[2026-09-13 00:00:02,000: INFO/W-9] cosa di tutti i giorni"])}
    nuove = novita(oggi, storico)
    assert [v.esempio for v in nuove] == ["[ERROR/W-N] cosa mai vista"] or "mai vista" in nuove[0].esempio
    assert len(nuove) == 1


def test_seleziona_preferisce_errori_e_novita_alle_righe_rare_quando_il_budget_stringe():
    errore = Voce("t-err", "ERROR", 1, "riga di errore", "00:00:00", "00:00:00")
    nuova = Voce("t-new", "INFO", 40, "riga nuova di oggi", "00:00:00", "23:00:00")
    rara = Voce("t-raro", "INFO", 2, "riga rara ma vecchia", "00:00:00", "00:00:00")
    scelte = seleziona([rara, errore, nuova], storici={"t-raro": 3}, tetto_caratteri=150)
    assert errore in scelte and nuova in scelte
    assert rara not in scelte


def test_seleziona_non_supera_mai_il_tetto_di_caratteri():
    voci = [Voce(f"t{i}", "ERROR", 1, "x" * 200, "00:00:00", "00:00:00") for i in range(50)]
    scelte = seleziona(voci, storici=set(), tetto_caratteri=1000)
    assert len(rendi_digest(scelte)) <= 1000


def test_il_digest_numera_le_voci_in_modo_stabile_e_mostra_il_conteggio():
    voci = [
        Voce("t1", "ERROR", 3, "prima riga", "01:00:00", "02:00:00"),
        Voce("t2", "INFO", 1, "seconda riga", "03:00:00", "03:00:00"),
    ]
    digest = rendi_digest(voci)
    assert "T0001" in digest and "T0002" in digest
    assert "x3" in digest or "3x" in digest or "conteggio=3" in digest
    assert "prima riga" in digest and "seconda riga" in digest


def test_annota_ricorrenza_riporta_in_quanti_giorni_precedenti_il_template_esisteva():
    from src.triage_log.distillazione import annota_ricorrenza

    (voce,) = distilla(["[2026-09-14 00:00:01,000: ERROR/W-1] rotto"])
    (annotata,) = annota_ricorrenza([voce], {voce.template: 6})
    assert annotata.giorni_storico == 6
    assert "gia_visto_in=6g" in rendi_digest([annotata])


def test_un_errore_ricorrente_da_giorni_cede_il_passo_a_una_novita_non_grave():
    grave_vecchio = Voce("t-vecchio", "ERROR", 90, "allarme di ogni giorno", "00:00:00", "23:00:00", 7)
    nuovo_banale = Voce("t-nuovo", "INFO", 1, "riga mai vista", "05:00:00", "05:00:00", 0)
    scelte = seleziona(
        [grave_vecchio, nuovo_banale],
        storici={"t-vecchio": 7},
        tetto_caratteri=10_000,
    )
    assert scelte[0] is nuovo_banale


def test_un_errore_nuovo_resta_davanti_a_tutto():
    grave_nuovo = Voce("t-g", "ERROR", 1, "errore mai visto", "05:00:00", "05:00:00", 0)
    nuovo_banale = Voce("t-n", "INFO", 50, "riga nuova banale", "05:00:00", "06:00:00", 0)
    scelte = seleziona([nuovo_banale, grave_nuovo], storici={}, tetto_caratteri=10_000)
    assert scelte[0] is grave_nuovo


# Issue #619: il numero incollato a una parola (es. "18.6pp") non veniva consumato
# interamente dal pattern \b\d+(?:\.\d+)?\b: il \b finale non puo' cadere fra
# una cifra e una lettera (entrambe caratteri di parola), quindi solo la parte
# intera veniva mascherata e il decimale residuo spezzava i template in varianti.
def test_il_decimale_incollato_a_una_lettera_viene_mascherato_interamente():
    riga = (
        "[2026-09-16 04:11:09,111: ERROR/S1] "
        "DECAY CRITICAL [S1]: Hit rate dropped 18.6pp from 54.0% to 35.4%"
    )
    template = normalizza_riga(riga)
    assert ".6pp" not in template, template
    assert "<N>pp" in template, template


def test_il_decimale_incollato_a_unita_di_misura_viene_mascherato_interamente():
    riga = (
        "[2026-09-16 04:11:09,111: WARNING/W] "
        "elapsed 12.5ms before timeout"
    )
    template = normalizza_riga(riga)
    assert ".5ms" not in template, template
    assert "<N>ms" in template, template


def test_il_decimale_incollato_a_unita_sec_viene_mascherato_interamente():
    riga = "[2026-09-16 04:11:09,111: INFO/W] completed in 3.25sec"
    template = normalizza_riga(riga)
    assert ".25sec" not in template, template
    assert "<N>sec" in template, template


def test_numero_decimale_isolato_continua_a_essere_mascherato():
    # 0.035 e -0.051 sono gia' corretti con la vecchia regex, ma vanno
    # preservati dal fix: la regressione silenziosa e' il rischio principale.
    assert "0.035" not in normalizza_riga("[2026-09-16 04:11:09,111: INFO/W] rate=0.035")
    assert "0.051" not in normalizza_riga("[2026-09-16 04:11:09,111: INFO/W] drift=-0.051")


def test_stesso_allarme_con_decimale_collassa_in_un_unico_template():
    # Lo stesso allarme su due righe, con decimali diversi, deve produrre lo
    # stesso template: e' la condizione che annota_ricorrenza vuole verificare.
    a = (
        "[2026-09-16 04:11:09,111: ERROR/S1] "
        "DECAY CRITICAL [S1]: Hit rate dropped 18.6pp from 54.0% to 35.4%"
    )
    b = (
        "[2026-09-17 04:11:09,111: ERROR/S1] "
        "DECAY CRITICAL [S1]: Hit rate dropped 22.8pp from 52.0% to 29.2%"
    )
    assert normalizza_riga(a) == normalizza_riga(b)
