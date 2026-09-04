"""Review notturna di una PR aperta sul worker locale (spec 2026-09-03).

Orchestratore: tutto l'impuro vive qui — systemctl, gh, la chiamata HTTP in
streaming, il ledger. La logica sta nei moduli puri di `src/review_locale/`.

Il job non ha alcun potere sul merge: pubblica rilievi e nient'altro. Il modello
e' una lente che esamina, mai un cancello che approva — su PR #472 ha prodotto
undici assoluzioni di cui almeno due false, e false esattamente sui due punti
dove i difetti erano reali.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

import httpx

from src.review_locale.estrazione import costruisci_prompt
from src.review_locale.referto import NON_VALIDO, PUBBLICABILE, SENZA_RILIEVI, prepara
from src.review_locale.rilevatori import e_corsa_condannata, e_loop, misura_ripetizione
from src.review_locale.selezione import STATO_FALLITO, PrCandidata, scegli

log = logging.getLogger("review_notturna")

LEDGER = Path("/home/stefano/llm/notte/ledger.jsonl")
DIAGNOSI = Path("/home/stefano/llm/notte")
UNIT = "llama-server.service"
BASE_URL = "http://127.0.0.1:8080"
MODELLO = "qwen3.8-27b-local"
MAX_TOKENS = 32_768
# 9 ore: piu' del tetto teorico (32.768 token a ~1,1 tok/s), cosi' il limite lo
# pongono i rilevatori e non il client.
TIMEOUT_HTTP = 32_400

# Nel ledger lo stato di un tentativo fallito e' NON_ESAMINATA, distinto dallo
# stato NON_VALIDO che il modulo `referto` usa per il singolo referto: sono due
# cose diverse — un referto invalido e un tentativo che non ha prodotto nulla.
# La stringa vive in un posto solo: `selezione.STATO_FALLITO`, che e' anche cio'
# che `scegli()` conta per il tetto dei tentativi. L'alias resta perche' qui si
# legge meglio nel contesto del ledger.
NON_VALIDO_LEDGER = STATO_FALLITO

INTESTAZIONE_COMMENTO = """## Rilievi da una review sul modello locale

Rilievi non verificati da nessuno, prodotti da un worker locale (Qwen3.8-27B) su questa
PR contro la issue che dichiara di chiudere. Il modello e' affidabile quando trova un
difetto che esiste e inaffidabile quando dichiara corretto cio' che ha guardato, quindi
questi rilievi vanno letti come piste da controllare, non come fatti accertati.

Questo commento non esprime nessun verdetto sul merge.

---

"""


# --- confini esterni ------------------------------------------------------


def avvia_server() -> None:
    subprocess.run(["systemctl", "--user", "start", UNIT], check=True)
    for _ in range(60):
        try:
            if httpx.get(f"{BASE_URL}/health", timeout=5).json().get("status") == "ok":
                return
        except Exception:  # noqa: BLE001 — il server sta ancora salendo
            pass
        time.sleep(5)
    raise RuntimeError("il server locale non ha risposto a /health entro 5 minuti")


def ferma_server() -> None:
    subprocess.run(["systemctl", "--user", "stop", UNIT], check=False)


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def pr_aperte() -> list[PrCandidata]:
    righe = json.loads(_gh("pr", "list", "--state", "open", "--json", "number,headRefOid,createdAt"))
    return [
        PrCandidata(numero=r["number"], sha=r["headRefOid"], creata_il=r["createdAt"])
        for r in righe
    ]


def diff_pr(numero: int) -> str:
    return _gh("pr", "diff", str(numero))


def issue_della_pr(numero: int) -> str:
    """Il corpo della issue che la PR dichiara di chiudere.

    Si legge dal corpo della PR (`Closes #N` / `Part of #N`). Senza issue
    collegata si restituisce il corpo della PR: e' comunque la dichiarazione di
    intenti contro cui giudicare il diff.
    """
    corpo = json.loads(_gh("pr", "view", str(numero), "--json", "body"))["body"] or ""
    for marcatore in ("Closes #", "closes #", "Part of #", "part of #"):
        if marcatore in corpo:
            numero_issue = corpo.split(marcatore, 1)[1].split()[0].strip(".,;:")
            if numero_issue.isdigit():
                return json.loads(
                    _gh("issue", "view", numero_issue, "--json", "body")
                )["body"] or corpo
    return corpo


def pubblica_commento(numero: int, corpo: str) -> None:
    subprocess.run(
        ["gh", "pr", "comment", str(numero), "--body", corpo], check=True
    )


def leggi_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(riga) for riga in LEDGER.read_text().splitlines() if riga.strip()]


def scrivi_ledger(voce: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")


def salva_diagnosi(numero: int, indice: int, reasoning: str) -> None:
    DIAGNOSI.mkdir(parents=True, exist_ok=True)
    (DIAGNOSI / f"ragionamento_pr{numero}_{indice}.txt").write_text(reasoning)


def interroga_modello(prompt: str) -> tuple[str, str, int]:
    """Manda il prompt e restituisce (content, reasoning, token generati).

    Interrompe se i rilevatori riconoscono un loop o una corsa che non puo' piu'
    chiudere. In quel caso `content` e' vuoto e il chiamante non pubblica nulla.
    """
    richiesta = {
        "model": MODELLO,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning_effort": "medium",
        "temperature": 1.0, "top_p": 0.95, "top_k": 20,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "stream": True,
    }
    content: list[str] = []
    reasoning: list[str] = []
    generati = 0
    ultimo_controllo = 0

    with httpx.stream(
        "POST", f"{BASE_URL}/v1/chat/completions",
        json=richiesta,
        headers={"Authorization": "Bearer not-needed"},
        timeout=TIMEOUT_HTTP,
    ) as risposta:
        # Senza questo controllo un 4xx/5xx (crash a meta' generazione, OOM,
        # richiesta malformata) produce silenziosamente ("", "", 0): a valle
        # sembra un JSON non parsabile del modello, non un guasto del server.
        risposta.raise_for_status()
        for riga in risposta.iter_lines():
            if not riga.startswith("data: "):
                continue
            payload = riga[6:].strip()
            if payload == "[DONE]":
                break
            try:
                dato = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for scelta in dato.get("choices") or []:
                delta = scelta.get("delta") or {}
                if delta.get("content"):
                    content.append(delta["content"])
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
            generati += 1

            if generati - ultimo_controllo >= 500:
                ultimo_controllo = generati
                testo = "".join(reasoning)
                misure = misura_ripetizione(testo)
                log.info("token=%d misure=%s", generati, misure)
                if e_loop(misure):
                    log.error("loop rilevato a %d token: interrompo", generati)
                    return "", testo, generati
                if e_corsa_condannata(generati, content_vuoto=not content):
                    log.error("corsa condannata a %d token: interrompo", generati)
                    return "", testo, generati

    return "".join(content), "".join(reasoning), generati


# --- composizione ---------------------------------------------------------


def _corpo_commento(rilievi: Sequence[dict]) -> str:
    pezzi = [INTESTAZIONE_COMMENTO]
    for rilievo in rilievi:
        pezzi.append(
            f"### {rilievo['gravita']} — {rilievo['categoria']}\n\n"
            f"**{rilievo['posizione']}**\n\n"
            f"{rilievo['difetto']}\n\n"
            f"**Scenario:** {rilievo['scenario_di_fallimento']}\n"
        )
        if rilievo.get("mascherato_da"):
            pezzi.append(f"\n**Mascherato da:** {rilievo['mascherato_da']}\n")
        pezzi.append("\n")
    return "".join(pezzi)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pr", type=int, help="esamina questa PR invece di scegliere dal ledger")
    args = ap.parse_args(argv)

    candidate = pr_aperte()
    if args.pr is not None:
        candidate = [pr for pr in candidate if pr.numero == args.pr]
    scelta = scegli(candidate, leggi_ledger())
    if scelta is None:
        log.info("nessuna PR eleggibile: niente da fare")
        return 0

    log.info("PR scelta: #%d (%s)", scelta.numero, scelta.sha[:8])
    prompt = costruisci_prompt(diff_pr(scelta.numero), issue_della_pr(scelta.numero))
    if not prompt:
        scrivi_ledger({
            "pr": scelta.numero, "sha": scelta.sha,
            "stato": NON_VALIDO_LEDGER, "causa": "nessun file di codice nel diff",
            "iniziato": datetime.now().astimezone().isoformat(),
        })
        return 0

    iniziato = datetime.now().astimezone()
    rilievi: list[dict] = []
    stato = SENZA_RILIEVI
    causa = None
    misure = {}
    # `fase` racconta, se si arriva all'`except`, quale confine esterno ha
    # fallito: avvio server, interrogazione di un dato prompt, o pubblicazione
    # del commento. E' l'unica cosa che distingue "il modello ha risposto con
    # JSON rotto" (gestito da `prepara`, sopra) da "systemctl/httpx/gh sono
    # esplosi" (gestito qui).
    fase = "avvio del server"
    try:
        avvia_server()
        for indice, singolo in enumerate(prompt):
            fase = f"interrogazione del modello (prompt {indice + 1}/{len(prompt)})"
            log.info("prompt %d/%d, %d byte", indice + 1, len(prompt), len(singolo))
            content, reasoning, generati = interroga_modello(singolo)
            misure = misura_ripetizione(reasoning)
            salva_diagnosi(scelta.numero, indice, reasoning)
            esito = prepara(content)
            if esito.stato == PUBBLICABILE:
                rilievi.extend(esito.rilievi)
                stato = "ESAMINATA_CON_RILIEVI"
            elif esito.stato == NON_VALIDO and stato == SENZA_RILIEVI:
                stato, causa = NON_VALIDO_LEDGER, esito.causa

        if rilievi:
            stato = "ESAMINATA_CON_RILIEVI"
            fase = "pubblicazione del commento"
            pubblica_commento(scelta.numero, _corpo_commento(rilievi))
        elif stato == SENZA_RILIEVI:
            stato = "ESAMINATA_SENZA_RILIEVI"
    except Exception as exc:
        # Qualunque guasto in un confine esterno (avvio server, HTTP verso il
        # modello, `gh pr comment`) deve comunque lasciare una riga nel ledger
        # — altrimenti `scegli()` non lo conta come tentativo fallito e una PR
        # puo' restare in coda per sempre, o un run di ore che ha davvero
        # trovato rilievi sparisce senza traccia. Il processo esce comunque
        # non-zero: si rilancia, non si inghiotte.
        stato, causa = NON_VALIDO_LEDGER, f"guasto durante {fase}: {exc}"
        raise
    finally:
        ferma_server()
        scrivi_ledger({
            "pr": scelta.numero, "sha": scelta.sha,
            "iniziato": iniziato.isoformat(),
            "concluso": datetime.now().astimezone().isoformat(),
            "stato": stato, "causa": causa,
            "rilievi": len(rilievi),
            "misure_loop": misure,
        })

    log.info("esito: %s (%d rilievi)", stato, len(rilievi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
