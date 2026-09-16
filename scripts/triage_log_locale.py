#!/usr/bin/env python3
"""Triage notturno dei log di container sul modello locale (2026-09-14).

Orchestratore: tutto l'impuro vive qui — systemd, disco, la chiamata HTTP. La
logica sta nei moduli puri di `src/triage_log/`.

Il mestiere e' quello per cui la macchina locale e' adatta e nessun'altra parte
del sistema copre: legge molto (i 9 MB al giorno di log che nessuno apre),
scrive poco (una manciata di reperti), e ogni reperto deve **citare una riga
vera**, riscontrata meccanicamente prima di arrivare all'operatore.

Il job non ha alcun potere: non spegne, non riavvia, non apre issue. Pubblica
reperti citati e nient'altro. `SENZA_REPERTI` non significa che la giornata sia
sana: significa che questa lente non ha trovato niente.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import requests

# Il recupero del JSON troncato e' gia' scritto e testato per i nodi S4: si riusa
# quello, non se ne scrive un secondo.
from scripts.s4_cluster_literature import parse_json
from src.triage_log.distillazione import annota_ricorrenza, distilla, rendi_digest, seleziona
from src.triage_log.referto import SENZA_REPERTI, recupera_troncato, verifica

log = logging.getLogger("triage_log")

BASE_URL = "http://127.0.0.1:8080"
MODELLO = "qwen3.8-27b-local"
UNIT = "llama-server.service"
# Il tetto e' aritmetica, non gusto: a ~121 token/s di prefill, 60.000 caratteri
# sono circa due minuti di lettura. Sopra, il job smette di chiudere in una notte.
TETTO_CARATTERI = 60_000
# Un referto su ~320 template ha gia' sfondato i 3.000 token una volta, perdendo
# 41 minuti di generazione. Il tetto costa tempo, non contesto: si tiene largo.
MAX_TOKENS = 6_000
TIMEOUT_HTTP = 4 * 60 * 60

SISTEMA = """Sei un lettore di log di produzione, non un assistente.
Ricevi un distillato: una riga per template di log, con quante volte e' comparso oggi.
Ogni riga porta `gia_visto_in=Ng`: in quanti dei giorni precedenti quel template esisteva gia'.
`gia_visto_in=0g` e' una novita' di oggi ed e' cio' che interessa di piu'; un template presente
da giorni e' sfondo, va segnalato solo se il suo conteggio o il suo orario cambiano in modo
significativo, e in quel caso va detto che e' ricorrente.
Cerchi anomalie operative: errori nuovi, fallimenti ripetuti, task che spariscono,
timeout, retry, code che crescono, sequenze che non tornano.
Un solo evento produce un solo reperto: se lo stesso guasto compare su piu' metriche, strategie
o worker, scrivi un reperto unico e cita la riga piu' rappresentativa.
Rispondi con un solo oggetto JSON.
Ogni reperto deve citare TESTUALMENTE la riga di esempio del template su cui si pronuncia:
la citazione viene riscontrata a macchina e un reperto con citazione inesatta viene buttato.
Non dichiarare sano cio' che non hai trovato anomalo: cio' che non e' un reperto non va scritto.
Se non trovi nulla, restituisci una lista vuota."""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "referto_triage",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reperti": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "template_id": {"type": "string"},
                            "gravita": {"type": "string", "enum": ["ALTA", "MEDIA", "BASSA"]},
                            "anomalia": {"type": "string"},
                            "citazione": {"type": "string"},
                            "perche_anomalo": {"type": "string"},
                            "cosa_controllare": {"type": "string"},
                        },
                        "required": [
                            "template_id",
                            "gravita",
                            "anomalia",
                            "citazione",
                            "perche_anomalo",
                            "cosa_controllare",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["reperti"],
            "additionalProperties": False,
        },
    },
}


def righe_del_giorno(cartella: Path, giorno: date) -> tuple[list[str], list[str]]:
    """Righe dei container per quel giorno, e i nomi dei file letti."""
    righe: list[str] = []
    letti: list[str] = []
    for percorso in sorted(cartella.glob(f"*-{giorno.isoformat()}.log")):
        righe.extend(percorso.read_text(errors="replace").splitlines())
        letti.append(percorso.name)
    return righe, letti


def template_storici(cartella: Path, giorno: date, giorni: int) -> dict[str, int]:
    """Template dei giorni precedenti, con in quanti giorni ciascuno e' comparso."""
    storici: dict[str, int] = {}
    for scarto in range(1, giorni + 1):
        righe, _ = righe_del_giorno(cartella, giorno - timedelta(days=scarto))
        for voce in distilla(righe):
            storici[voce.template] = storici.get(voce.template, 0) + 1
    return storici


def interroga(digest: str, giorno: date, out_dir: Path) -> dict:
    """Una sola chiamata al server locale, con schema JSON vincolato.

    La risposta grezza viene scritta su disco **prima** di essere interpretata: a
    1,4 token/s un referto sono decine di minuti, e un parsing fallito non deve
    poterli cancellare. Il recupero di un JSON troncato e' delegato a
    `parse_json`, che chiude i container mancanti e salva i reperti completi.
    """
    payload = {
        "model": MODELLO,
        "messages": [
            {"role": "system", "content": SISTEMA},
            {
                "role": "user",
                "content": (
                    f"GIORNO: {giorno.isoformat()}\n\n"
                    "DISTILLATO (un template per riga: id, conteggio, prima->ultima, esempio):\n<<<\n"
                    f"{digest}\n>>>"
                ),
            },
        ],
        "temperature": 0.0,
        "top_p": 0.9,
        "max_tokens": MAX_TOKENS,
        "stream": False,
        "response_format": SCHEMA,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    risposta = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer not-needed"},
        timeout=TIMEOUT_HTTP,
    )
    if not risposta.ok:
        raise RuntimeError(f"HTTP {risposta.status_code}: {risposta.text[:500]}")
    contenuto = risposta.json()["choices"][0]["message"].get("content", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"risposta_grezza_{giorno.isoformat()}.json").write_text(contenuto)
    # Il cancello a citazione lega i `template_id` al digest esatto che e' stato
    # inviato: riusare la risposta con una selezione diversa produrrebbe un
    # referto silenziosamente sbagliato. Il digest si conserva accanto.
    (out_dir / f"digest_usato_{giorno.isoformat()}.txt").write_text(digest)
    try:
        return parse_json(contenuto)
    except (json.JSONDecodeError, ValueError):
        salvato = recupera_troncato(contenuto)
        if salvato is None:
            raise
        log.warning("risposta troncata: recuperati i reperti completi, l'ultimo e' perso")
        referto = parse_json(salvato)
        referto["troncata"] = True
        return referto


def _ricorrenza(reperto: dict, scelte: list) -> int:
    """Da quanti giorni esiste il template citato dal reperto (0 = novita')."""
    try:
        posizione = int(reperto["template_id"][1:])
    except (KeyError, ValueError, TypeError):
        return 0
    if 1 <= posizione <= len(scelte):
        return scelte[posizione - 1].giorni_storico
    return 0


def numera(esito, scelte: list) -> list[dict]:
    """Assegna un id stabile a ogni reperto e vi attacca la ricorrenza.

    L'id serve a una cosa sola, ed e' la ragione per cui esiste: poter scrivere
    piu' tardi se quel reperto era vero o falso. Senza disposizione la precisione
    di questo job resta un aneddoto, che e' esattamente cio' che ha reso inutile
    la review notturna delle PR.
    """
    numerati = []
    for indice, reperto in enumerate(esito.reperti, 1):
        numerati.append(
            {**reperto, "id": f"R{indice:02d}", "gia_visto_in_giorni": _ricorrenza(reperto, scelte)}
        )
    return numerati


def rendi_referto(giorno: date, numerati: list[dict], esito, scelte, n_template, letti, totale_righe) -> str:
    """Il digest che legge l'operatore: le novita' prima, lo sfondo dopo."""
    nuovi = [r for r in numerati if r["gia_visto_in_giorni"] == 0]
    ricorrenti = [r for r in numerati if r["gia_visto_in_giorni"] > 0]
    righe = [
        f"# Triage log — {giorno.isoformat()}",
        "",
        f"File letti: {', '.join(letti) or 'nessuno'} ({totale_righe} righe, "
        f"{n_template} template distinti, {len(scelte)} passati al modello).",
        "",
        "Reperti prodotti dal modello locale e **riscontrati a macchina**: ogni citazione "
        "esiste nel log del giorno e appartiene al template citato. Nessun reperto non "
        "significa giornata sana, significa che questa lente non ha trovato niente.",
        "",
        f"Disposizione: `python -m scripts.triage_disponi --giorno {giorno.isoformat()} "
        "--id R01 --esito confermato|falso|gia_noto`.",
        "",
    ]
    if esito.stato == SENZA_REPERTI:
        righe.append("**SENZA_REPERTI.**")
    for titolo, gruppo in (("Novita' di oggi", nuovi), ("Gia' visti nei giorni scorsi", ricorrenti)):
        if not gruppo:
            continue
        righe += [f"## {titolo} ({len(gruppo)})", ""]
        for reperto in gruppo:
            eta = (
                "novita'"
                if reperto["gia_visto_in_giorni"] == 0
                else f"ricorrente da {reperto['gia_visto_in_giorni']} giorni"
            )
            righe += [
                f"### {reperto['id']} — {reperto['gravita']} — {reperto['anomalia']}",
                "",
                f"```\n{reperto['citazione']}\n```",
                "",
                f"**Perche' anomalo:** {reperto['perche_anomalo']} _({eta})_",
                f"**Cosa controllare:** {reperto['cosa_controllare']}",
                "",
            ]
    if esito.scartati:
        righe += [
            "---",
            f"{len(esito.scartati)} reperti scartati dal cancello: "
            + ", ".join(sorted({m for s in esito.scartati for m in s["motivi"]})),
            "",
        ]
    return "\n".join(righe)


def avvisa(numerati: list[dict], giorno: date) -> bool:
    """Manda su Telegram i soli reperti nuovi ALTA/MEDIA, o niente.

    Un referto che resta su disco non viene letto: e' il difetto che ha reso
    inutile la review notturna delle PR, 79 rilievi pubblicati e nove commenti
    su dieci senza risposta.
    """
    import asyncio

    from src.notifications.telegram import TelegramNotifier

    degni = [
        r for r in numerati if r["gia_visto_in_giorni"] == 0 and r["gravita"] in ("ALTA", "MEDIA")
    ]
    if not degni:
        log.info("niente da avvisare: nessun reperto nuovo ALTA/MEDIA")
        return False
    testo = "\n".join(
        [f"<b>Triage log {giorno.isoformat()}</b> — {len(degni)} reperti nuovi", ""]
        + [f"{r['id']} [{r['gravita']}] {r['anomalia'][:180]}" for r in degni]
        + ["", f"Referto: logs/triage/triage_{giorno.isoformat()}.md"]
    )
    return asyncio.run(TelegramNotifier().send_alert(testo, level="warning"))


def main() -> int:
    """Distilla un giorno di log, interroga il modello, riscontra, scrive."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--giorno", default=date.today().isoformat())
    parser.add_argument("--log-dir", type=Path, default=Path("logs/containers"))
    parser.add_argument("--out-dir", type=Path, default=Path("logs/triage"))
    parser.add_argument("--storico-giorni", type=int, default=7)
    parser.add_argument("--tetto-caratteri", type=int, default=TETTO_CARATTERI)
    parser.add_argument(
        "--gestisci-server",
        action="store_true",
        help="Avvia e ferma llama-server.service attorno alla chiamata",
    )
    parser.add_argument("--solo-distillato", action="store_true", help="Non interroga il modello")
    parser.add_argument(
        "--notifica", action="store_true", help="Manda su Telegram i reperti nuovi ALTA/MEDIA"
    )
    parser.add_argument(
        "--riusa-grezza",
        action="store_true",
        help="Rilegge la risposta gia' salvata invece di interrogare il modello",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    giorno = date.fromisoformat(args.giorno)
    righe, letti = righe_del_giorno(args.log_dir, giorno)
    if not righe:
        log.error("nessun log per %s in %s", giorno, args.log_dir)
        return 1
    voci = annota_ricorrenza(
        distilla(righe), template_storici(args.log_dir, giorno, args.storico_giorni)
    )
    storici = {voce.template: voce.giorni_storico for voce in voci if voce.giorni_storico}
    scelte = seleziona(voci, storici, args.tetto_caratteri)
    digest = rendi_digest(scelte)
    log.info(
        "%d righe -> %d template -> %d nel prompt (%d caratteri)",
        len(righe),
        len(voci),
        len(scelte),
        len(digest),
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"distillato_{giorno.isoformat()}.txt").write_text(digest)
    if args.solo_distillato:
        return 0

    if args.gestisci_server:
        subprocess.run(["systemctl", "--user", "start", UNIT], check=True)
        for _ in range(60):
            try:
                if requests.get(f"{BASE_URL}/health", timeout=5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(10)
    inizio = time.time()
    grezza = args.out_dir / f"risposta_grezza_{giorno.isoformat()}.json"
    digest_usato = args.out_dir / f"digest_usato_{giorno.isoformat()}.txt"
    if args.riusa_grezza and grezza.exists():
        if not digest_usato.exists() or digest_usato.read_text() != digest:
            log.error(
                "il digest di oggi non coincide con quello inviato al modello: "
                "i template_id della risposta salvata puntano ad altre righe. "
                "Rilancia senza --riusa-grezza."
            )
            return 2
        # Il referto costa un'ora di generazione: ricomporlo da una risposta gia'
        # ottenuta non deve richiedere di rifarla.
        log.info("riuso la risposta grezza del %s", giorno)
        referto = parse_json(grezza.read_text())
        esito = verifica(referto.get("reperti", []), scelte, righe)
        numerati = numera(esito, scelte)
        percorso = args.out_dir / f"triage_{giorno.isoformat()}.md"
        percorso.write_text(
            rendi_referto(giorno, numerati, esito, scelte, len(voci), letti, len(righe))
        )
        print(percorso)
        return 0
    try:
        referto = interroga(digest, giorno, args.out_dir)
        esito = verifica(referto.get("reperti", []), scelte, righe)
    finally:
        if args.gestisci_server:
            subprocess.run(["systemctl", "--user", "stop", UNIT], check=False)
    durata = round(time.time() - inizio, 1)
    log.info("esito: %s (%d reperti, %d scartati) in %ss", esito.stato, len(esito.reperti), len(esito.scartati), durata)

    numerati = numera(esito, scelte)
    percorso = args.out_dir / f"triage_{giorno.isoformat()}.md"
    percorso.write_text(
        rendi_referto(giorno, numerati, esito, scelte, len(voci), letti, len(righe))
    )
    with (args.out_dir / "reperti.jsonl").open("a") as fh:
        for reperto in numerati:
            fh.write(json.dumps({"giorno": giorno.isoformat(), **reperto}) + "\n")
    if args.notifica:
        try:
            log.info("avviso Telegram inviato: %s", avvisa(numerati, giorno))
        except Exception as exc:  # l'avviso non deve mai far perdere il referto
            log.error("avviso Telegram fallito: %r", exc)
    with (args.out_dir / "ledger.jsonl").open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "giorno": giorno.isoformat(),
                    "righe": len(righe),
                    "template": len(voci),
                    "nel_prompt": len(scelte),
                    "stato": esito.stato,
                    "reperti": len(esito.reperti),
                    "scartati": [s["motivi"] for s in esito.scartati],
                    "secondi": durata,
                    "modello": MODELLO,
                }
            )
            + "\n"
        )
    print(percorso)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
