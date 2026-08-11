#!/usr/bin/env python3
"""Information Coefficient di S4: il segnale di sentiment predice i rendimenti?

Ricalcola OGNI VOLTA l'intera serie e riscrive docs/evidence/s4_ic.json. E'
idempotente per costruzione: non accumula stato, quindi non puo' divergere da
quello che il DB dice oggi. Sola lettura sul database.

Autonomo di proposito: non tocca il cron del report alpha-miss, che e' script di
produzione ed e' congelato fino alla verifica del primo commit automatico del
ledger (vedi #171, #174). Il collegamento al report arrivera' con #174.

METODO — la scelta che decide la validita' del numero.
Ci sono piu' segnali per lo stesso simbolo nello stesso giorno, e condividono lo
stesso forward return: trattarli come indipendenti gonfia la significativita' di
circa un ordine di grandezza. Quindi si riduce a UNA osservazione per
simbolo-giorno, tenendo l'ULTIMO segnale del giorno — che e' esattamente quello
che il ranker usa in produzione — e si calcola lo Spearman cross-sectional giorno
per giorno, mediando poi sui giorni.

Uso:
    uv run python scripts/compute_s4_ic.py
"""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import spearmanr

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT = PROJECT_DIR / "docs" / "evidence" / "s4_ic.json"
# Soglia del kill criterion di S4 (#180): registrata dall'operatore in YAML,
# letta a ogni run. Se il file manca o e' vuoto l'esito e' NO_CRITERION.
CRITERION_FILE = PROJECT_DIR / "config" / "s4_kill_criterion.yaml"
# Stato della notifica one-shot al raggiungimento della soglia. Idempotente:
# scriviamo qui l'ultimo esito che e' stato notificato, cosi' lo stesso esito
# ripetuto giorno dopo giorno non genera spam su Telegram.
NOTIFY_FILE = PROJECT_DIR / "docs" / "evidence" / "s4_ic_notification.json"
MIN_SIMBOLI_GIORNO = 5  # sotto, la correlazione cross-sectional e' rumore puro

QUERY = """SELECT date_trunc('day', generated_at)::date, symbol, score, fallback_used,
       forward_return, forward_return_3d, forward_return_5d
FROM sentiment_signals
WHERE forward_return IS NOT NULL
ORDER BY generated_at;"""


def _leggi_segnali() -> dict:
    """Una osservazione per (giorno, simbolo): l'ultimo segnale, come il ranker."""
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", QUERY],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:200]}")

    ultimo: dict[tuple[str, str], dict] = {}
    for riga in res.stdout.strip().split("\n"):
        if not riga.strip():
            continue
        p = riga.split("|")
        if p[4] == "":
            continue
        ultimo[(p[0], p[1])] = {
            "score": float(p[2]),
            "fallback": p[3] == "t",
            1: float(p[4]),
            3: float(p[5]) if p[5] else None,
            5: float(p[6]) if p[6] else None,
        }
    return ultimo


def _serie_ic(per_giorno: dict, filtro, orizzonte: int) -> list[tuple[str, float, int]]:
    """IC cross-sectional per ogni giorno con abbastanza simboli."""
    out = []
    for giorno, righe in sorted(per_giorno.items()):
        sel = [r for r in righe if filtro(r) and r[orizzonte] is not None]
        if len(sel) < MIN_SIMBOLI_GIORNO:
            continue
        scores = [r["score"] for r in sel]
        fwd = [r[orizzonte] for r in sel]
        if len(set(scores)) < 2 or len(set(fwd)) < 2:
            continue  # serie costante: la correlazione non e' definita
        ic = spearmanr(scores, fwd).correlation
        if ic is not None and not math.isnan(ic):
            out.append((giorno, float(ic), len(sel)))
    return out


def _sintesi(serie: list[tuple[str, float, int]]) -> dict:
    """Media, dispersione e t sulla serie giornaliera degli IC.

    Il t si calcola sui GIORNI, non sulle osservazioni: e' il giorno l'unita'
    indipendente, non il singolo segnale.
    """
    n = len(serie)
    if n < 3:
        return {"giorni": n, "ic_medio": None, "dev_std": None, "t_stat": None,
                "significativo_a_3": False}
    valori = [ic for _, ic, _ in serie]
    media = statistics.mean(valori)
    dev = statistics.stdev(valori)
    if dev == 0:
        return {"giorni": n, "ic_medio": media, "dev_std": 0.0, "t_stat": None,
                "significativo_a_3": False}
    t = media / (dev / math.sqrt(n))
    return {
        "giorni": n,
        "ic_medio": media,
        "dev_std": dev,
        "t_stat": t,
        "significativo_a_3": abs(t) >= 3.0,
        "ic_rilevabile_a_t3": 3.0 * dev / math.sqrt(n),
    }


def _tg_send(testo: str) -> bool:
    """Invia un messaggio Telegram. Silenzioso se le credenziali mancano.

    La stessa logica di soppressione usata da daily_alpha_miss_analysis.sh:
    il cron della notifica non deve MAI bloccare la generazione dell'artefatto,
    quindi se Telegram non risponde si prosegue e si segnala su stderr.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[tg_send] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID non settati: skip", file=__import__("sys").stderr)
        return False
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"https://api.telegram.org/bot{token}/sendMessage",
             "-d", f"chat_id={chat}", "-d", f"text={testo}"],
            check=False, capture_output=True, timeout=10,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - la notifica non deve mai rompere il run
        print(f"[tg_send] fallita: {exc}", file=__import__("sys").stderr)
        return False


def _leggi_criterio() -> dict | None:
    """Legge la soglia registrata dall'operatore in config/s4_kill_criterion.yaml.

    Ritorna None se il file manca o non ha i campi minimi: in quel caso l'esito
    sara' NO_CRITERION e l'osservazione prosegue senza decisione.
    """
    if not CRITERION_FILE.exists():
        return None
    try:
        # PyYAML e' gia' una dipendenza del progetto (usato da alpha_miner_dossier.py).
        import yaml
        raw = yaml.safe_load(CRITERION_FILE.read_text())
    except Exception:  # noqa: BLE001 - file illeggibile = come assente
        return None
    if not isinstance(raw, dict):
        return None
    min_giorni = raw.get("min_giorni")
    if not isinstance(min_giorni, int) or min_giorni <= 0:
        return None
    significativo_a_t = float(raw.get("significativo_a_t", 3.0))
    max_ic = raw.get("max_ic_rilevabile_a_t")
    return {
        "min_giorni": min_giorni,
        "significativo_a_t": significativo_a_t,
        "max_ic_rilevabile_a_t": float(max_ic) if max_ic is not None else None,
    }


def _esito(sintesi: dict) -> dict:
    """Calcola l'esito rispetto al kill criterion (#180).

    Quattro stati, in ordine di priorita':
    - NO_CRITERION: soglia non ancora registrata
    - INSUFFICIENT_N: campione sotto la soglia, anche se il segnale e' forte
    - FAIL: campione sufficiente E IC significativamente negativo
    - PASS: campione sufficiente E IC significativamente positivo

    L'ordine conta: INSUFFICIENT_N batte PASS/FAIL per costruzione, perche' una
    decisione con campione insufficiente NON e' una decisione. Questa e' la
    asimmetria che la issue definisce ("se il criterio non e' ancora registrato
    l'esito e' NO_CRITERION e la cosa si vede").
    """
    criterio = _leggi_criterio()
    blocco = sintesi.get("tutti", {}).get("1g", {})
    n_corrente = blocco.get("giorni")
    ic_medio = blocco.get("ic_medio")
    t_stat = blocco.get("t_stat")

    if criterio is None:
        return {
            "criterio_registrato": False,
            "esito": "NO_CRITERION",
            "soglia": None,
            "n_corrente": n_corrente,
            "n_richiesto": None,
            "ic_medio": ic_medio,
            "t_stat": t_stat,
        }

    n_richiesto = criterio["min_giorni"]
    soglia_signif = criterio["significativo_a_t"]

    if n_corrente is None or n_corrente < n_richiesto:
        return {
            "criterio_registrato": True,
            "esito": "INSUFFICIENT_N",
            "soglia": None,
            "n_corrente": n_corrente,
            "n_richiesto": n_richiesto,
            "ic_medio": ic_medio,
            "t_stat": t_stat,
        }

    # Campione sufficiente: la decisione dipende dal segno del t.
    if t_stat is None or ic_medio is None:
        # n >= soglia ma il t non e' calcolabile (dev_std = 0 o n < 3): caso
        # degenere, trattato come non-decisionale.
        return {
            "criterio_registrato": True,
            "esito": "INSUFFICIENT_N",
            "soglia": None,
            "n_corrente": n_corrente,
            "n_richiesto": n_richiesto,
            "ic_medio": ic_medio,
            "t_stat": t_stat,
        }

    if t_stat <= -soglia_signif:
        esito = "FAIL"
    elif t_stat >= soglia_signif:
        esito = "PASS"
    else:
        # n >= soglia ma |t| < soglia_signif: il campione basta in teoria ma
        # il segnale non e' ancora significativo — l'esito onesto e'
        # "non-decisionale", non "PASS per default".
        return {
            "criterio_registrato": True,
            "esito": "INSUFFICIENT_N",
            "soglia": soglia_signif,
            "n_corrente": n_corrente,
            "n_richiesto": n_richiesto,
            "ic_medio": ic_medio,
            "t_stat": t_stat,
        }

    return {
        "criterio_registrato": True,
        "esito": esito,
        "soglia": soglia_signif,
        "n_corrente": n_corrente,
        "n_richiesto": n_richiesto,
        "ic_medio": ic_medio,
        "t_stat": t_stat,
    }


def _gestisci_notifica(esito: dict) -> bool:
    """Notifica one-shot al raggiungimento di PASS/FAIL.

    Ritorna True se la notifica e' stata inviata O aggiornata. NO_CRITERION e
    INSUFFICIENT_N non sono mai notificati — il freeze vuole silenzio
    sull'osservazione, non rumore.

    Idempotenza: scriviamo l'ultimo esito notificato in NOTIFY_FILE; se il run
    successivo produce lo stesso esito, non ritriggera. Se l'esito cambia
    (FAIL -> PASS o viceversa), retriggera una volta.
    """
    stato = esito.get("esito")
    if stato not in ("PASS", "FAIL"):
        return False

    # Leggi l'ultimo stato notificato (se esiste).
    precedente: dict | None = None
    if NOTIFY_FILE.exists():
        try:
            precedente = json.loads(NOTIFY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            precedente = None

    if precedente and precedente.get("esito") == stato:
        return False

    # Componi il messaggio: solo i campi del criterio, niente prosa.
    righe = [
        f"S4 IC — kill criterion raggiunto",
        f"esito: {stato}",
        f"n_corrente: {esito.get('n_corrente')}",
        f"n_richiesto: {esito.get('n_richiesto')}",
        f"ic_medio: {esito.get('ic_medio')}",
        f"t_stat: {esito.get('t_stat')}",
        "decisione operativa del PO — questo messaggio e' solo il via",
    ]
    testo = "\n".join(str(r) for r in righe)
    inviato = _tg_send(testo)

    # Persisti lo stato notificato SOLO se l'invio e' andato: cosi' un
    # fallimento di Telegram non viene mascherato da "gia' notificato ieri".
    if inviato:
        NOTIFY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = NOTIFY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(
            {"esito": stato, "notificato_il": datetime.now(timezone.utc).isoformat()},
            indent=2,
        ))
        tmp.replace(NOTIFY_FILE)
        return True
    return False


def main() -> int:
    ultimo = _leggi_segnali()
    if not ultimo:
        raise SystemExit("Nessun segnale con forward_return: niente da calcolare.")

    per_giorno: dict[str, list[dict]] = defaultdict(list)
    for (giorno, _sym), v in ultimo.items():
        per_giorno[giorno].append(v)

    sottoinsiemi = {
        "tutti": lambda r: True,
        "ensemble": lambda r: not r["fallback"],
        "fallback": lambda r: r["fallback"],
        "alta_convinzione_0.30": lambda r: abs(r["score"]) >= 0.30,
    }

    risultato: dict = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "metodo": (
            "una osservazione per simbolo-giorno (ultimo segnale, come il ranker); "
            "Spearman cross-sectional giornaliero; t calcolato sui giorni"
        ),
        "osservazioni_simbolo_giorno": len(ultimo),
        "giorni_totali": len(per_giorno),
        "sintesi": {},
        "serie_giornaliera_1g": [],
    }

    for nome, filtro in sottoinsiemi.items():
        risultato["sintesi"][nome] = {
            f"{o}g": _sintesi(_serie_ic(per_giorno, filtro, o)) for o in (1, 3, 5)
        }

    risultato["serie_giornaliera_1g"] = [
        {"giorno": g, "ic": ic, "n_simboli": n}
        for g, ic, n in _serie_ic(per_giorno, lambda r: True, 1)
    ]

    # Confronto col kill criterion (#180): scritto DENTRO l'artefatto cosi' il
    # confronto non e' mai "a memoria" di chi guarda il file.
    risultato["criterio"] = _esito(risultato["sintesi"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(risultato, indent=2, ensure_ascii=False))
    tmp.replace(OUT)  # atomica: mai un file mezzo scritto

    # Notifica one-shot: idempotente, non rompe mai il run.
    _gestisci_notifica(risultato["criterio"])

    print(f"Scritto: {OUT}")
    print(f"\n{len(ultimo)} osservazioni simbolo-giorno su {len(per_giorno)} giorni\n")
    print(f"{'sottoinsieme':24} {'oriz':5} {'giorni':>6} {'IC medio':>9} {'t':>6} {'sign.':>6}")
    for nome in sottoinsiemi:
        for o in (1, 3, 5):
            s = risultato["sintesi"][nome][f"{o}g"]
            if s["ic_medio"] is None:
                continue
            t = s["t_stat"]
            print(f"{nome:24} {o}g{'':3} {s['giorni']:>6} {s['ic_medio']:>+9.4f} "
                  f"{t:>+6.2f} {'SI' if s['significativo_a_3'] else 'no':>6}")

    tutti_1g = risultato["sintesi"]["tutti"]["1g"]
    if tutti_1g.get("ic_rilevabile_a_t3"):
        print(f"\nCon {tutti_1g['giorni']} giorni rileviamo solo |IC| > "
              f"{tutti_1g['ic_rilevabile_a_t3']:.4f}. L'IC tipico di un segnale")
        print("azionario in letteratura e' 0.02-0.05: se il campione non basta,")
        print("l'esito e' 'non rilevabile', NON 'assente'.")

    # Esito del kill criterion: scritto anche in stdout perche' la consultazione
    # umana del file non richieda di aprire JSON.
    cr = risultato["criterio"]
    print(f"\nKill criterion: {cr['esito']}  "
          f"(n={cr['n_corrente']}, n_richiesto={cr['n_richiesto']}, "
          f"soglia={cr['soglia']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
