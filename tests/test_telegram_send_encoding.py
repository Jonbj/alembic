"""Il canale di allerta Telegram non deve poter perdere messaggi in silenzio.

`curl` NON codifica i valori passati con `-d`: ogni `&` nel testo spezza il form
e tronca il campo in quel punto. Il `sed` che rende sicuro l'HTML *produce* `&`
(`&amp;`, `&lt;`, `&gt;`), quindi bastava un `<` nella coda dell'output di un
agente perche' il `<pre>` arrivasse senza tag di chiusura e Telegram rifiutasse
l'intero messaggio con `400 can't parse entities` — con la risposta scartata in
/dev/null, quindi senza che nessuno se ne accorgesse.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# `-d campo=` o `-d "campo="` sui campi di sendMessage: la forma non codificata.
_D_NON_CODIFICATO = re.compile(r'(?<!-)\B-d "?(chat_id|parse_mode|text)=')


def _mittenti_telegram() -> list[Path]:
    trovati = [
        p
        for p in sorted((ROOT / "scripts").iterdir())
        if p.is_file() and "api.telegram.org" in p.read_text(errors="ignore")
    ]
    assert trovati, "nessun mittente Telegram trovato: il test non sta guardando nulla"
    return trovati


def test_nessuno_script_invia_a_telegram_con_d_non_codificato():
    colpevoli = {
        p.name: sorted({m.group(1) for m in _D_NON_CODIFICATO.finditer(p.read_text())})
        for p in _mittenti_telegram()
    }
    colpevoli = {nome: campi for nome, campi in colpevoli.items() if campi}

    assert not colpevoli, (
        "questi script passano campi di sendMessage con `-d` invece di "
        f"`--data-urlencode`: {colpevoli}. Ogni `&` nel testo tronca il messaggio."
    )


def test_curl_con_d_tronca_al_primo_ampersand_mentre_urlencode_no():
    """La ragione del test sopra, verificata contro curl vero invece che assunta."""
    testo = "prima &amp; dopo"

    def _campo_text(args: list[str]) -> str:
        # `--trace-ascii` mostrerebbe il corpo; piu' semplice: curl parla con se
        # stesso via `file://`? No — si ispeziona il corpo con `-o /dev/null -w`
        # non basta. Si usa `--libcurl` che stampa i campi come li ha capiti.
        out = subprocess.run(
            ["curl", "-s", "--libcurl", "/dev/stdout", "-o", "/dev/null",
             "--connect-timeout", "1", *args, "http://127.0.0.1:9"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout

    con_d = _campo_text(["-d", f"text={testo}"])
    con_enc = _campo_text(["--data-urlencode", f"text={testo}"])

    # Con -d il corpo resta letterale: l'`&` e' un separatore di campi.
    assert "text=prima &amp; dopo" in con_d or "prima &amp; dopo" in con_d
    # Con --data-urlencode l'`&` diventa %26 e non puo' piu' spezzare il form.
    assert "%26" in con_enc, con_enc
    assert "&amp;" not in con_enc.split("POSTFIELDS")[-1]
