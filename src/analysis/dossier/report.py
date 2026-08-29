"""Blocco deterministico del book nei report alpha-miss.

La prosa del report resta libera di interpretare la giornata, ma non e' una
fonte affidabile per enumerare i trade. Questo modulo rende ingressi e chiusure
direttamente dal dossier e incorpora un manifest verificabile nello stesso
blocco Markdown.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

INIZIO_BLOCCO = "<!-- alpha-miss-book:start -->"
FINE_BLOCCO = "<!-- alpha-miss-book:end -->"
PREFISSO_MANIFEST = "<!-- alpha-miss-book-manifest: "

_INTESTAZIONE_SEZIONE_QUATTRO = re.compile(r"^## 4\.[^\n]*\n", re.MULTILINE)
_SEZIONE_QUATTRO = re.compile(
    r"^## 4\.[\s\S]*?(?=^## (?:[5-9]|[1-9][0-9])\.|\Z)", re.MULTILINE
)
_BLOCCO = re.compile(
    re.escape(INIZIO_BLOCCO) + r"[\s\S]*?" + re.escape(FINE_BLOCCO)
)
_MANIFEST = re.compile(
    re.escape(PREFISSO_MANIFEST) + r"(\{[^\n]*\}) -->"
)


class ReportReconciliationError(ValueError):
    """Il report non consente una riconciliazione deterministica sicura."""


def _escape_markdown(value: Any) -> str:
    return str(value).replace("|", r"\|").replace("\n", " ")


def _numero(value: Any, decimali: int) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{decimali}f}"


def _prezzo(value: Any) -> str:
    numero = _numero(value, 4)
    return numero if numero == "—" else f"${numero}"


def _pnl(value: Any) -> str:
    if value is None:
        return "—"
    numero = float(value)
    segno = "+" if numero >= 0 else "−"
    return f"{segno}${abs(numero):.2f}"


def _qualita_ingresso(ingresso: Mapping[str, Any]) -> str:
    percentile = ingresso.get("entry_percentile")
    if percentile is None:
        parti = ["percentile non disponibile"]
    else:
        parti = [f"percentile {float(percentile):.2%}"]
    if ingresso.get("denominatore_degenere"):
        parti.append("denominatore intraday degenere: quota non interpretabile")
    else:
        parti.append("denominatore intraday valido")
    return "; ".join(parti)


def _simboli(
    righe: Sequence[Mapping[str, Any]],
) -> list[str]:
    return [str(riga["symbol"]) for riga in righe]


def _manifest(dossier: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": 1,
        "ingressi": _simboli(dossier.get("ingressi", [])),
        "chiusure": _simboli(dossier.get("chiusure", [])),
    }


def _rendi_blocco(dossier: Mapping[str, Any]) -> str:
    manifest = json.dumps(_manifest(dossier), ensure_ascii=True, separators=(",", ":"))
    righe = [
        INIZIO_BLOCCO,
        f"{PREFISSO_MANIFEST}{manifest} -->",
        "",
        "Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.",
        "",
        "| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for ingresso in dossier.get("ingressi", []):
        righe.append(
            "| IN | {symbol} | {strategia} | {ora} | {prezzo} | {qty} | — | {qualita} |".format(
                symbol=_escape_markdown(ingresso["symbol"]),
                strategia=_escape_markdown(ingresso.get("strategia", "—")),
                ora=_escape_markdown(ingresso.get("ora_utc", "—")),
                prezzo=_prezzo(ingresso.get("entry_price")),
                qty=_numero(ingresso.get("qty"), 4),
                qualita=_escape_markdown(_qualita_ingresso(ingresso)),
            )
        )
    for chiusura in dossier.get("chiusure", []):
        righe.append(
            "| OUT | {symbol} | {strategia} | — | {prezzo} | {qty} | {pnl} | {motivo} |".format(
                symbol=_escape_markdown(chiusura["symbol"]),
                strategia=_escape_markdown(chiusura.get("strategia", "—")),
                prezzo=_prezzo(chiusura.get("exit_price")),
                qty=_numero(chiusura.get("qty"), 4),
                pnl=_pnl(chiusura.get("pnl_net")),
                motivo=_escape_markdown(chiusura.get("exit_reason") or "non disponibile"),
            )
        )
    righe.extend([FINE_BLOCCO, ""])
    return "\n".join(righe)


def riconcilia_attivita_book(report: str, dossier: Mapping[str, Any]) -> str:
    """Inserisce o aggiorna il blocco del book nella sezione 4 del report."""
    intestazione = _INTESTAZIONE_SEZIONE_QUATTRO.search(report)
    if intestazione is None:
        raise ReportReconciliationError("sezione 4 del report non trovata")

    inizi = report.count(INIZIO_BLOCCO)
    fini = report.count(FINE_BLOCCO)
    if inizi != fini or inizi > 1:
        raise ReportReconciliationError("marcatori del blocco book incompleti o duplicati")

    blocco = _rendi_blocco(dossier)
    if inizi == 1:
        riconciliato = _BLOCCO.sub(blocco.rstrip(), report, count=1)
    else:
        riconciliato = report[: intestazione.end()] + "\n" + blocco + report[intestazione.end() :]

    if not verifica_riconciliazione(riconciliato, dossier):
        raise ReportReconciliationError("il blocco generato non riconcilia col dossier")
    return riconciliato


def verifica_riconciliazione(report: str, dossier: Mapping[str, Any]) -> bool:
    """Verifica manifest e righe IN/OUT, inclusi ordine e duplicati."""
    sezione_match = _SEZIONE_QUATTRO.search(report)
    if sezione_match is None:
        return False
    sezione = sezione_match.group(0)
    blocchi = _BLOCCO.findall(sezione)
    if len(blocchi) != 1:
        return False
    blocco = blocchi[0]

    manifest_match = _MANIFEST.search(blocco)
    if manifest_match is None:
        return False
    try:
        manifest = json.loads(manifest_match.group(1))
    except json.JSONDecodeError:
        return False
    if manifest != _manifest(dossier):
        return False

    righe_book: dict[str, list[list[str]]] = {"IN": [], "OUT": []}
    for riga in blocco.splitlines():
        celle = [cella.strip() for cella in riga.strip().strip("|").split("|")]
        if celle and celle[0] in righe_book:
            righe_book[celle[0]].append(celle)

    ingressi = list(dossier.get("ingressi", []))
    chiusure = list(dossier.get("chiusure", []))
    if [riga[1] for riga in righe_book["IN"]] != _simboli(ingressi):
        return False
    if [riga[1] for riga in righe_book["OUT"]] != _simboli(chiusure):
        return False
    if any(
        ingresso.get("denominatore_degenere")
        and "denominatore intraday degenere: quota non interpretabile" not in riga[-1]
        for ingresso, riga in zip(ingressi, righe_book["IN"], strict=True)
    ):
        return False
    return True
