"""L'alert del breaker deve partire anche quando il chiamante e' dentro un loop.

Il 2026-09-14 non e' partito: il callback sincrono del breaker viene invocato
mentre `asyncio.run()` sta gia' girando (sentiment.py:1459), quindi un secondo
`asyncio.run()` solleva RuntimeError, la coroutine non viene mai attesa e
l'`except` la declassa a warning. 22 timeout dell'ensemble, zero avvisi.
"""

import asyncio

import pytest

from src.notifications.base import esegui_sincrono


async def _eco(valore, registro):
    registro.append(valore)
    return valore


def test_funziona_quando_non_c_e_nessun_loop():
    registro = []
    assert esegui_sincrono(_eco(7, registro)) == 7
    assert registro == [7]


def test_funziona_quando_un_loop_e_gia_in_esecuzione():
    registro = []

    async def dentro_il_loop():
        # chiamata sincrona dall'interno di una coroutine: e' il caso reale
        return esegui_sincrono(_eco(9, registro))

    assert asyncio.run(dentro_il_loop()) == 9
    assert registro == [9]


def test_un_trasporto_che_si_pianta_non_blocca_il_chiamante():
    async def mai():
        await asyncio.sleep(30)

    with pytest.raises(TimeoutError):
        esegui_sincrono(mai(), timeout=0.2)


def test_l_eccezione_del_trasporto_arriva_al_chiamante():
    async def esplode():
        raise ValueError("telegram giu'")

    with pytest.raises(ValueError):
        esegui_sincrono(esplode())
