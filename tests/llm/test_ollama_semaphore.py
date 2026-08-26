"""#368: il semaforo Ollama deve poter recuperare i token, non solo perderli.

Il pool shadow e' stato trovato a 0 slot su 3 il 2026-08-26, con ogni
acquire() bloccata in attesa di un token che non sarebbe mai arrivato.
"""
import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.llm.client import _OllamaSemaphore


class _FakeRedis:
    """Redis minimale: solo le operazioni che il semaforo usa."""

    def __init__(self, liste=None):
        self.liste = liste or {}
        self.chiusa = False

    def lpush(self, key, val):
        self.liste.setdefault(key, []).insert(0, val)

    def rpush(self, key, val):
        self.liste.setdefault(key, []).append(val)

    def llen(self, key):
        return len(self.liste.get(key, []))

    def blpop(self, key, timeout=None):
        coda = self.liste.get(key, [])
        if coda:
            return (key, coda.pop(0))
        return None

    def eval(self, *a, **k):
        return 0

    def close(self):
        self.chiusa = True


@pytest.mark.asyncio
async def test_cancellazione_durante_l_attesa_non_perde_il_token():
    """Se il task viene cancellato MENTRE il thread e' dentro il BLPOP, il
    token che quel thread estrae dopo deve tornare nel pool.

    E' il meccanismo che ha svuotato il pool shadow: il bounded wait di
    process_news_batch cancella i candidati ancora in coda per uno slot,
    l'await solleva CancelledError, ma il thread dell'executor continua, fa il
    BLPOP e il token non torna piu' indietro. Il try/finally attorno allo
    `yield` non viene mai raggiunto, perche' la cancellazione arriva prima.
    """
    sblocca = threading.Event()
    fake = _FakeRedis({"ollama:sem:test": ["slot"]})

    def _blpop_bloccante(key, timeout=None):
        sblocca.wait(timeout=5)          # il thread resta dentro il BLPOP
        coda = fake.liste.get(key, [])
        return (key, coda.pop(0)) if coda else None

    fake.blpop = _blpop_bloccante
    sem = _OllamaSemaphore(key="ollama:sem:test", slots=1)

    with patch.object(sem, "_connect", return_value=fake):
        async def _usa():
            async with sem.acquire():
                await asyncio.sleep(10)

        task = asyncio.create_task(_usa())
        await asyncio.sleep(0.1)         # il task e' dentro il BLPOP
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        sblocca.set()                    # ora il thread estrae il token
        await asyncio.sleep(0.4)         # lascia girare il ripristino

    assert fake.llen("ollama:sem:test") == 1, (
        "il token estratto dopo la cancellazione non e' tornato nel pool"
    )


def test_recovery_copre_anche_il_pool_shadow():
    """Il pool shadow era escluso dalla recovery: e' il motivo per cui e'
    morto mentre quello live e' rimasto sano."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    redis = MagicMock()
    redis.llen.return_value = 0
    redis.exists.return_value = 1

    _recover_ollama_semaphore_if_leaked(redis)

    chiavi = {c.args for c in redis.delete.call_args_list}
    assert ("ollama:sem", "ollama:sem:init") in chiavi
    assert ("ollama:sem:shadow", "ollama:sem:shadow:init") in chiavi


def test_recovery_ripristina_anche_una_perdita_parziale():
    """Un solo token perso su tre non blocca il pool, ma lo degrada in
    silenzio: a concurrency=1, all'avvio del task nessuno detiene token,
    quindi un ammanco e' una perdita, non un falso positivo."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    redis = MagicMock()
    redis.llen.return_value = 1   # 1 su 3 nel pool shadow
    redis.exists.return_value = 1

    _recover_ollama_semaphore_if_leaked(redis)

    assert redis.delete.called, "perdita parziale lasciata degradare"
