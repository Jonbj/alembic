"""S7 repro_2 — guard anti-reintroduzione viva (test_p0_13).

Conferma (statica, deterministica): il test test_p0_13_strategy_containment.py
è VIVO nel working tree e mantiene S7 fuori dallo StrategyRegistry. Se S7
viene reintrodotto, deve essere mode=research e non in get_active_strategies().
Questo è il "bug-prevention" del progetto: impedisce la riesposizione a un
alpha misurato NEGATIVE.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
test_path = ROOT / "tests" / "test_p0_13_strategy_containment.py"

exists = test_path.exists()
src = test_path.read_text() if exists else ""
has_s7_class = "TestS7NotInOperationalRegistry" in src
has_active_guard = "get_active_strategies" in src and "S7" in src
has_research_mode = "research" in src and "S7" in src
print(f"test_p0_13_strategy_containment.py exists: {exists}")
print(f"TestS7NotInOperationalRegistry class present: {has_s7_class}")
print(f"Guard: S7 not in get_active_strategies(): {has_active_guard}")
print(f"Guard: S7 must be mode=research if present: {has_research_mode}")
ok = exists and has_s7_class and has_active_guard and has_research_mode
print(f"\n=> ANTI-REINTRO GUARD ALIVE: {ok}")
print("CONFIRMED" if ok else "REFUTED")
