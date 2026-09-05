"""Filtro del diff e costruzione dei prompt per il modello locale.

Modulo puro: riceve il testo del diff e il corpo della issue, non chiama `gh`.

Il filtro non e' un dettaglio di efficienza, e' cio' che rende esaminabili le PR
di questo repo. PR #477 porta +69.343 righe di cui 58.339 sono un dossier JSON
generato: senza filtro sarebbe trenta volte oltre il contesto del modello e
verrebbe saltata, con il filtro il codice vero (~2.000 righe) ci sta comodo.

I test sono esclusi dal diff dato al modello: il compito e' giudicare il codice
contro la issue, e i test consumano contesto senza aggiungere ipotesi.
"""

from __future__ import annotations

import re


ESTENSIONI_CODICE = (".py", ".sh", ".sql")

# 35 KB: il run riuscito su PR #472 aveva un prompt da 42 KB comprensivo di
# issue e schema, quindi il diff sotto i 35 KB tiene il caso normale in un
# prompt unico.
TETTO_BYTE = 35_000

# Limite noto: per un file rinominato cattura il percorso pre-rename (a/), quindi
# _e_codice classifica sul nome vecchio. Un file spostato da tests/ a produzione
# viene scartato per errore, uno spostato da produzione a tests/ viene incluso per
# errore. Un percorso quotato da git (spazi o non-ASCII, es. "a/foo bar.py") non
# soddisfa affatto la regex e il blocco non viene riconosciuto come inizio file.
_INIZIO_FILE = re.compile(r"^diff --git a/(\S+) b/\S+", re.MULTILINE)

_INTESTAZIONE = """Sei un ingegnere senior che fa la review di una pull request su un sistema di
trading in Python. Ricevi il testo della issue che la PR dichiara di chiudere e il
diff del codice di produzione (i file di test sono esclusi). NON hai accesso al
repository: usa soltanto cio' che segue.

Il tuo compito **NON e' approvare**. Il tuo compito e' trovare i difetti. Se non
trovi nulla di concreto dillo, ma non inventare rilievi per riempire lo spazio:
ogni rilievo deve essere qualcosa su cui un manutentore agirebbe.

Cerca in particolare, in ordine di gravita':
1. RAMI IRRAGGIUNGIBILI: codice o categorie che la logica a monte non puo' mai
   produrre (e i test che li esercitano con input impossibili).
2. CLASSIFICAZIONI SBAGLIATE: un caso che finisce nella categoria di un altro,
   per una condizione troppo larga o troppo stretta.
3. EVIDENZE FALSE: un campo che afferma un fatto che non e' stato osservato.
4. DOPPI CONTEGGI o predicati riscritti due volte che possono divergere.
5. NON DETERMINISMO: valori letti a run time invece che dallo stato del giorno
   analizzato.
6. SCARTI FRA CIO' CHE LA ISSUE CHIEDE E CIO' CHE IL DIFF FA, incluse le
   contraddizioni fra un commento o una docstring e il codice che descrive.

Alcuni difetti si mascherano a vicenda: un ramo che svuota una popolazione rende
irraggiungibili i difetti a valle. Se te ne accorgi, dillo in `mascherato_da`.
"""

_SCHEMA = """
## COSA DEVI PRODURRE

Rispondi con UN SOLO oggetto JSON valido, senza testo prima o dopo:

{
  "rilievi": [
    {
      "gravita": "<ALTA|MEDIA|BASSA>",
      "categoria": "<ramo_irraggiungibile|classificazione_sbagliata|evidenza_falsa|doppio_conteggio|non_determinismo|scarto_dalla_issue>",
      "posizione": "<file:riga come compare nel diff>",
      "difetto": "<una frase: cosa e' sbagliato>",
      "scenario_di_fallimento": "<input o stato concreto -> risultato sbagliato. Uno scenario, non una preoccupazione generica>",
      "mascherato_da": "<il rilievo che oggi lo rende irraggiungibile, oppure null>"
    }
  ],
  "verificato_e_scartato": ["<cose che hai controllato e che ti sembrano corrette>"],
  "criteri_issue": [
    {"criterio": "<il criterio di accettazione, copiato>", "esito": "<SODDISFATTO|NON_SODDISFATTO|PARZIALE>", "perche": "<una frase>"}
  ],
  "informazioni_mancanti": ["<cio' che ti servirebbe e non hai>"],
  "confidenza": <numero fra 0 e 1>
}
"""


def file_toccati(diff: str) -> list[str]:
    """I percorsi che il diff modifica, nell'ordine in cui compaiono."""
    return _INIZIO_FILE.findall(diff)


def _blocchi(diff: str) -> list[tuple[str, str]]:
    """Il diff spezzato in (percorso, testo del blocco)."""
    posizioni = [(m.group(1), m.start()) for m in _INIZIO_FILE.finditer(diff)]
    risultato = []
    for indice, (percorso, inizio) in enumerate(posizioni):
        fine = posizioni[indice + 1][1] if indice + 1 < len(posizioni) else len(diff)
        risultato.append((percorso, diff[inizio:fine]))
    return risultato


def _e_codice(percorso: str) -> bool:
    if percorso.startswith("tests/") or "/tests/" in percorso:
        return False
    return percorso.endswith(ESTENSIONI_CODICE)


def filtra_diff(diff: str) -> str:
    """Il diff ridotto ai soli file di codice di produzione."""
    return "".join(testo for percorso, testo in _blocchi(diff) if _e_codice(percorso))


def _prompt(diff: str, issue: str) -> str:
    return (
        f"{_INTESTAZIONE}\n"
        f"## ISSUE COLLEGATA\n\n{issue}\n\n"
        f"## DIFF DEL CODICE DI PRODUZIONE\n\n{diff}\n"
        f"{_SCHEMA}"
    )


def _impacchetta(blocchi: list[tuple[str, str]], tetto_byte: int) -> list[str]:
    """Raggruppa i blocchi (nell'ordine del diff) in buffer di testo.

    Bin-packing greedy: il file successivo entra nel buffer corrente se ci
    sta, altrimenti apre un nuovo buffer. Un file da solo gia' sopra il tetto
    diventa comunque un buffer proprio (non lo spezziamo), ma non impedisce
    ai file successivi di raggrupparsi fra loro.

    Non ordiniamo per dimensione: l'ordine del diff tiene il contesto di
    review vicino alla struttura naturale della PR. Il prezzo e' che file
    piccoli ma sparsi fra file grandi (come su PR #477) non collassano nel
    minor numero di prompt possibile — e' un compromesso deliberato, non un
    limite da correggere ordinando.
    """
    gruppi: list[str] = []
    buffer = ""
    for _, testo in blocchi:
        if not buffer:
            buffer = testo
        elif len(buffer) + len(testo) <= tetto_byte:
            buffer += testo
        else:
            gruppi.append(buffer)
            buffer = testo
    if buffer:
        gruppi.append(buffer)
    return gruppi


def costruisci_prompt(diff: str, issue: str, tetto_byte: int = TETTO_BYTE) -> list[str]:
    """Uno o piu' prompt pronti da mandare al modello.

    Sotto il tetto: un prompt unico, che conserva la visione d'insieme. Sopra,
    bin-packing greedy nell'ordine del diff: i file piccoli condividono un
    prompt finche' ci stanno, un file da solo sopra il tetto occupa un prompt
    tutto suo senza bloccare l'impacchettamento degli altri (PR #477: 14 file,
    i sei piu' piccoli sommavano meno di 15 KB e finivano comunque in sei
    prompt separati).
    """
    blocchi = [(percorso, testo) for percorso, testo in _blocchi(diff) if _e_codice(percorso)]
    if not blocchi:
        return []

    return [_prompt(testo, issue) for testo in _impacchetta(blocchi, tetto_byte)]
