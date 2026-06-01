#!/usr/bin/env python3
"""
Tournament — confronta N modelli AI sullo stesso compito.
Versione semplificata: nessun worktree, nessuna sequenza manuale.

Workflow:
    1. L'utente cambia modello: /model <nome>
    2. L'utente chiede a Claude di fare la review (conversazione normale)
    3. Lo script salva la risposta: python scripts/tournament.py save
    4. Quando finiti tutti i modelli:
       python scripts/tournament.py compare

Comandi:
    save      — salva l'ultima risposta di Claude come review del modello attuale
    status    — mostra quali modelli hanno già una review
    compare   — confronta tutte le review e genera report
    init      — prepara la directory .claude/reviews/
    cleanup   — rimuove tutte le review
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip())

REVIEWS_DIR = REPO_ROOT / ".claude" / "reviews"
STATE_FILE = REPO_ROOT / ".claude" / "tournament_state.json"


def get_current_model():
    """Legge il modello attuale da .claude/last_model (scritto da /model)."""
    # Non c'è un modo diretto; usiamo l'ambiente o chiediamo all'utente
    # Fallback: cerca in .claude/settings o simili
    # Per ora, usiamo un'euristica semplice: se il file .claude/current_model esiste, leggiamo
    model_file = REPO_ROOT / ".claude" / "current_model"
    if model_file.exists():
        return model_file.read_text().strip()
    return None


def save_review():
    """Salva la review corrente nel file del modello."""
    model = get_current_model() or input("Inserisci il nome del modello attuale (es. kimi-k2.6:cloud): ").strip()
    if not model:
        print("Nome modello richiesto.")
        sys.exit(1)

    # Leggi la conversazione corrente da .claude/last_response o simile
    # POICHÉ non possiamo leggere la conversazione di Claude direttamente,
    # questo tool richiede che l'utente abbia già il testo della review pronto.
    # In realtà, l'utente può semplicemente fare la review nella chat e poi dire "salva".
    # Il salvataggio vero sarà fatto manualmente dall'utente copiando la risposta.

    print(f"Per salvare la review di {model}:")
    print(f"1. Copia il testo della review dalla chat")
    print(f"2. Incollalo nel file: .claude/reviews/{model.replace('/', '-').replace(':', '-')}.md")
    print(f"Oppure usa: echo '...' > .claude/reviews/{model.replace('/', '-').replace(':', '-')}.md")


def status():
    """Mostra lo stato delle review raccolte."""
    if not REVIEWS_DIR.exists():
        print("Nessuna review trovata. Esegui 'python scripts/tournament.py init' per iniziare.")
        return

    reviews = list(REVIEWS_DIR.glob("*.md"))
    if not reviews:
        print("Nessuna review salvata ancora.")
        return

    print(f"{'Modello':<35} {'Dimensione':<12} {'Data'}")
    print("-" * 70)
    for r in sorted(reviews):
        stat = r.stat()
        size = f"{stat.st_size} bytes"
        date = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
        print(f"{r.stem:<35} {size:<12} {date}")
    print(f"\nTotale: {len(reviews)} review(s)")


def compare():
    """Confronta tutte le review e genera report."""
    if not REVIEWS_DIR.exists():
        print("Nessuna review trovata.")
        sys.exit(1)

    reviews = sorted(REVIEWS_DIR.glob("*.md"))
    if len(reviews) < 2:
        print(f"Trovate solo {len(reviews)} review. Servono almeno 2 per un confronto.")
        sys.exit(1)

    # Estrai punteggi dai report (assumendo formato standard)
    data = []
    for r in reviews:
        text = r.read_text()
        # Cerca "Punteggio complessivo: X / 10" (con o senza markdown bold)
        match = re.search(r'Punteggio\s+complessivo[:\s*]+(?:\*\*)?(\d+(?:\.\d+)?)(?:\*\*)?\s*/\s*10', text, re.IGNORECASE)
        score = float(match.group(1)) if match else None
        data.append({"model": r.stem, "score": score, "size": r.stat().st_size})

    lines = [
        "# Tournament Comparative Report",
        "",
        f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Review confrontate:** {len(reviews)}",
        "",
        "## Punteggi",
        "",
        "| Modello | Punteggio | Dimensione |",
        "|---|---|---|",
    ]

    for d in data:
        score_str = f"{d['score']:.1f}" if d['score'] is not None else "N/A"
        lines.append(f"| `{d['model']}` | {score_str} | {d['size']} bytes |")

    # Ranking
    scored = [d for d in data if d['score'] is not None]
    if scored:
        ranked = sorted(scored, key=lambda x: x['score'], reverse=True)
        lines.extend([
            "",
            "## Ranking",
            "",
            "| Posizione | Modello | Punteggio |",
            "|---|---|---|",
        ])
        for i, d in enumerate(ranked, 1):
            marker = " 🏆" if i == 1 else ""
            lines.append(f"| {i} | `{d['model']}`{marker} | {d['score']:.1f}/10 |")

        lines.extend([
            "",
            f"**Miglior modello:** `{ranked[0]['model']}` con {ranked[0]['score']:.1f}/10",
        ])

    report_path = REPO_ROOT / "tournament_report.md"
    report_path.write_text("\n".join(lines) + "\n")
    print(f"Report scritto in {report_path.relative_to(REPO_ROOT)}")


def init():
    """Crea la directory per le review."""
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Directory pronta: {REVIEWS_DIR.relative_to(REPO_ROOT)}")
    print("Ora puoi salvare le review dei modelli in questa directory.")
    print("Formato del filename: <modello>.md (es. kimi-k2.6-cloud.md)")


def cleanup():
    """Rimuove tutte le review."""
    if REVIEWS_DIR.exists():
        for f in REVIEWS_DIR.glob("*.md"):
            f.unlink()
        REVIEWS_DIR.rmdir()
        print("Tutte le review rimosse.")
    else:
        print("Nessuna review da rimuovere.")


def main():
    parser = argparse.ArgumentParser(description="Tournament — confronta modelli AI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Prepara directory review")
    sub.add_parser("save", help="Istruzioni per salvare review corrente")
    sub.add_parser("status", help="Mostra review salvate")
    sub.add_parser("compare", help="Confronta review e genera report")
    sub.add_parser("cleanup", help="Rimuove tutte le review")

    args = parser.parse_args()

    if args.cmd == "init":
        init()
    elif args.cmd == "save":
        save_review()
    elif args.cmd == "status":
        status()
    elif args.cmd == "compare":
        compare()
    elif args.cmd == "cleanup":
        cleanup()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
