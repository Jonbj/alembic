"""S2 audit — repro_2: dead config + dead regime function.

Two static-trace checks (no execution of strategy logic; pure introspection):

1. S2 has NO config loader. Unlike S1/S3 which define `S2Config.from_yaml`,
   S2Config has no `from_yaml` method, there is no `config/s2*.yaml` file, and
   every call site uses `S2Config()` defaults. Editing any "S2 config" yaml
   would be inert; the only way to change S2 params is to edit the dataclass
   defaults in src/strategies/s2/config.py.

2. `apply_regime_scale` (regime.py:44) is imported into strategy.py:43 but NEVER
   CALLED. The regime modulation on the *put quantity* (the function's documented
   purpose) does not happen; the regime scale is applied only to the SPY-equity
   notional via `_target_spy_shares`. The function is dead code.

Run: python docs/audits/strategies/S2/repro_2_deadconfig.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
S2 = ROOT / "src" / "strategies" / "s2"

# ---- Check 1: no from_yaml, no yaml wiring ----
config_src = (S2 / "config.py").read_text()
cfg_tree = ast.parse(config_src)
has_from_yaml = any(
    isinstance(node, ast.FunctionDef) and node.name == "from_yaml"
    for node in ast.walk(cfg_tree)
)
s2_yaml_files = sorted((ROOT / "config").glob("s2*")) + sorted((ROOT / "config").glob("S2*"))

# Confirm the ONLY S2Config constructor uses are bare S2Config() (defaults)
strategy_src = (S2 / "strategy.py").read_text()
backtest_src = (S2 / "backtest.py").read_text()
scheduler_src = (ROOT / "src" / "workers" / "portfolio_scheduler.py").read_text()
bare_calls = sum(
    src.count("S2Config()")
    for src in (strategy_src, backtest_src, scheduler_src)
)
yaml_calls = sum(
    src.count("S2Config.from_yaml") for src in (strategy_src, backtest_src, scheduler_src)
)

print("=== Check 1: S2 config wiring ===")
print(f"S2Config.from_yaml method present?   {has_from_yaml}")
print(f"config/s2*.yaml files?               {[str(p.relative_to(ROOT)) for p in s2_yaml_files] or 'NONE'}")
print(f"call sites of bare S2Config():       {bare_calls}")
print(f"call sites of S2Config.from_yaml():  {yaml_calls}")

# ---- Check 2: apply_regime_scale never called ----
# Parse strategy.py and find any Call whose func is the name 'apply_regime_scale'
strat_tree = ast.parse(strategy_src)
call_sites = []
for node in ast.walk(strat_tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "apply_regime_scale":
            call_sites.append(node.lineno)
# imported at top-level, so the name exists; we count actual invocations.
imported = "apply_regime_scale" in ast.dump(ast.parse(strategy_src))

# Double-check across the whole src tree (the F8 'apply_regime_scale' flag in
# portfolio_scheduler is a config key string, not a call to regime.py's function).
regime_func_calls = []
for py in (ROOT / "src").rglob("*.py"):
    tree = ast.parse(py.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "apply_regime_scale":
                regime_func_calls.append(str(py.relative_to(ROOT)) + f":{node.lineno}")

print("\n=== Check 2: apply_regime_scale call sites ===")
print(f"imported into strategy.py?           {imported}")
print(f"call sites of regime.py's apply_regime_scale across src/: {regime_func_calls or 'NONE'}")

print("\n=== Verdict ===")
c1 = (not has_from_yaml) and (not s2_yaml_files) and (bare_calls > 0) and (yaml_calls == 0)
c2 = imported and (not regime_func_calls)
if c1:
    print("CONFIRMED (1): S2 config is dead — no from_yaml, no yaml file, only bare S2Config() defaults.")
if c2:
    print("CONFIRMED (2): apply_regime_scale is imported but NEVER called — dead code.")
if not (c1 and c2):
    print("One or both checks did not match prediction; inspect above.")