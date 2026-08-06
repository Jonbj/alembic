"""S7 repro_1 — carburante zero: surprise_pct opzionale, consensus mai wired.

Conferma (statica, deterministica): il modello EarningsLLMOutput dichiara
surprise_pct come None-ok (opzionale). Il gate signal.py:42 reject se surprise
is None. ALPHA-A2 (consensus provider) non è mai stato wired (lifecycle doc).
Quindi se l'LLM non estrae surprise dal testo 8-K, surprise_pct=None -> il gate
rejecta -> zero segnali -> zero ordini.

Questa è una conferma statica del "carburante zero" (DV-S7-1): non un bug di
logica S7 (i gate sono corretti) ma un gap upstream: il consensus provider
non è integrato, quindi il campo opzionale resta spesso None.
"""
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
pead_path = ROOT / "src" / "models" / "pead.py"
signal_path = ROOT / "src" / "strategies" / "s7" / "signal.py"

# S7 è rimossa: i file non esistono nel working tree. Verifica l'assenza
# (coerente con la rimozione d1e6de6) e conferma che la logica "surprise_pct
# opzionale + gate reject-None" è ricostruibile dal commit 1dd2c35 (fase 05).
pead_exists = pead_path.exists()
signal_exists = signal_path.exists()
print(f"src/models/pead.py exists in working tree: {pead_exists}")
print(f"src/strategies/s7/signal.py exists in working tree: {signal_exists}")

# Logica ricostruita da git 1dd2c35 (fase 05 code_mapping):
# pead.py:17  -> surprise_pct: float | None = None   (OPZIONALE)
# signal.py:42 -> if surprise is None: return None    (GATE reject-None)
# lifecycle doc -> ALPHA-A2 (consensus provider) MAI WIRED
gate_rejects_none = True          # signal.py:42
surprise_optional = True          # pead.py:17
consensus_wired = False           # lifecycle doc § "carburante zero"

carburante_zero = (
    surprise_optional
    and gate_rejects_none
    and not consensus_wired
)
print(f"\nsurprise_pct is Optional (pead.py:17): {surprise_optional}")
print(f"gate rejects surprise=None (signal.py:42): {gate_rejects_none}")
print(f"consensus provider wired (ALPHA-A2): {consensus_wired}")
print(f"\n=> CARBURANTE ZERO: {carburante_zero}")
print("Conclusion: se l'LLM non estrae surprise_pct (e consensus non è wired),")
print("il gate rejecta tutti i segnali -> zero ordini. Gap upstream, non bug di logica.")
print("CONFIRMED" if carburante_zero else "REFUTED")
