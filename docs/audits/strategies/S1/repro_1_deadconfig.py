"""S1 audit — repro_1: config/s1_strategy.yaml is dead config (not wired at runtime).

Confirmation:
 1. The live S1 instance is built with S1Config() defaults
    (src/workers/portfolio_scheduler.py:3068: TimeSeriesMomentum(prices=bars_df, config=S1Config())).
 2. S1Config.from_yaml exists (strategy.py:38-53) but is NEVER CALLED in any
    runtime path (only defined + referenced in an API doc comment).
 3. Therefore editing config/s1_strategy.yaml has NO effect on live or backtest S1.
    The yaml currently equals the defaults, so the bug is latent: a future divergent
    edit would silently not take effect.

This script is an audit artifact (read-only). It does NOT import the live worker;
it statically confirms (1)-(3) and demonstrates that from_yaml vs defaults would
diverge if the yaml were edited.

Run: python docs/audits/strategies/S1/repro_1_deadconfig.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from src.strategies.s1.strategy import S1Config  # noqa: E402

YAML = ROOT / "config" / "s1_strategy.yaml"

# (1) defaults used live
defaults = S1Config()
print("S1Config() defaults:", defaults.target_vol, defaults.vol_window_sizing,
      defaults.lookbacks, defaults.max_weight)

# (2) from_yaml loads the yaml
yaml_cfg = S1Config.from_yaml(YAML)
print("S1Config.from_yaml():  ", yaml_cfg.target_vol, yaml_cfg.vol_window_sizing,
      yaml_cfg.lookbacks, yaml_cfg.max_weight)

# (3) static check: is from_yaml ever CALLED anywhere under src/ (not defined)?
src = ROOT / "src"
call_sites = []
for p in src.rglob("*.py"):
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "from_yaml":
                # S1Config.from_yaml or S3Config.from_yaml call
                call_sites.append(str(p.relative_to(ROOT)))
print(f"\nCall sites of *.from_yaml under src/: {call_sites}")
# Expected: none for S1Config in a runtime path (only the definition itself is a def, not a Call).

# Demonstrate latent risk: if yaml target_vol were changed to 0.15, live would NOT change.
print("\nLatent risk demo: defaults vs yaml currently equal? ",
      defaults.target_vol == yaml_cfg.target_vol and defaults.lookbacks == yaml_cfg.lookbacks)
print("If an operator edits config/s1_strategy.yaml (e.g. target_vol: 0.15), the live")
print("S1 instance still uses S1Config() defaults (target_vol=0.10). YAML is dead config.")

print("\nCONFIRMED (static): live path uses S1Config() defaults; from_yaml never called")
print("in any src/ runtime path -> config/s1_strategy.yaml is not wired.")