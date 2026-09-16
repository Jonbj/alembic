"""Regressione: l'alert del breaker deve partire anche dentro la pipeline async.

Pre-fix questo test fallisce: il callback girava `asyncio.run()` mentre un loop
era gia' attivo (la pipeline vive dentro `asyncio.run()` a sentiment.py), quindi
la coroutine non veniva mai attesa e l'except la declassava a warning.
"""

import asyncio

from src.workers.sentiment import crea_callback_fallback


class _NotifierFinto:
    def __init__(self):
        self.inviati = []

    async def send_fallback_alert(self, count):
        self.inviati.append(count)
        return True


def test_l_alert_parte_quando_il_callback_e_invocato_dentro_un_loop():
    notifier = _NotifierFinto()
    callback = crea_callback_fallback(lambda: notifier)

    async def pipeline():
        callback(7)  # il breaker scatta da codice sincrono dentro il loop

    asyncio.run(pipeline())
    assert notifier.inviati == [7]


def test_l_alert_parte_anche_senza_loop_attivo():
    notifier = _NotifierFinto()
    crea_callback_fallback(lambda: notifier)(3)
    assert notifier.inviati == [3]


def test_il_notifier_viene_costruito_una_volta_sola():
    costruzioni = []

    def costruisci():
        costruzioni.append(1)
        return _NotifierFinto()

    callback = crea_callback_fallback(costruisci)
    callback(1)
    callback(2)
    assert len(costruzioni) == 1


def test_un_trasporto_rotto_non_propaga_l_eccezione_al_breaker(caplog):
    class _Rotto:
        async def send_fallback_alert(self, count):
            raise RuntimeError("telegram giu'")

    crea_callback_fallback(lambda: _Rotto())(5)
    assert "Fallback breaker alert callback failed" in caplog.text
