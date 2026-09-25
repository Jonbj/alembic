#!/usr/bin/env python3
"""Riallinea ``primo_avvistamento`` alla prima occorrenza in findings.json.

Chiamato da ``daily_analysis.sh`` dopo la sessione forense e prima del commit
del ledger: vedi ``normalizza_primo_avvistamento`` in
``src/analysis/dossier/ledger_validator.py``. Riscrive il file solo se cambia
qualcosa, con lo stesso formato (indent 2, UTF-8, a-capo finale).

Uso: scripts/normalizza_primo_avvistamento.py docs/evidence/findings.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.dossier.ledger_validator import normalizza_primo_avvistamento  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    percorso = Path(argv[0])
    findings = json.loads(percorso.read_text(encoding="utf-8"))
    modifiche = normalizza_primo_avvistamento(findings)
    for m in modifiche:
        print(f"primo_avvistamento {m['id']}: {m['da']} -> {m['a']}")
    if modifiche:
        percorso.write_text(
            json.dumps(findings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
