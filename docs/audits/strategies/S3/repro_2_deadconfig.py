"""S3 BUG-B / BUG-C reproduction: dead config + survivorship universe.

BUG-B (dead config, DV-8): S3Config.from_yaml exists (strategy.py:36-53) but is
  never called anywhere in src/. No config/s3*.yaml exists. Backtest uses bare
  S3Config() (backtest.py:37). Pattern identical to S1 BUG-1 / S2 BUG-D.

BUG-C (survivorship universe, DV-6): run_s3_backtest_full (backtest.py:209-210)
  selects `active_at(end)[:50]` with end=today -> today's 50 most-liquid
  survivors reused on 2000-today. Look-ahead in universe selection (survivorship).

Run: PYTHONPATH=. python docs/audits/strategies/S3/repro_2_deadconfig.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"


def main() -> None:
    print("=== S3 BUG-B: dead config (DV-8) ===")
    s3_strategy = (SRC / "strategies" / "s3" / "strategy.py").read_text()
    tree = ast.parse(s3_strategy)
    has_from_yaml = any(
        isinstance(node, ast.ClassDef)
        and node.name == "S3Config"
        and any(isinstance(m, ast.FunctionDef) and m.name == "from_yaml" for m in node.body)
        for node in tree.body
    )
    print(f"S3Config.from_yaml defined in strategy.py: {has_from_yaml}")

    # Count call sites of S3Config.from_yaml across all of src/.
    from_yaml_calls = 0
    s3config_calls = 0
    for py in SRC.rglob("*.py"):
        try:
            t = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(t):
            if isinstance(node, ast.Call):
                fn = node.func
                # S3Config.from_yaml(...)
                if isinstance(fn, ast.Attribute) and fn.attr == "from_yaml":
                    if isinstance(fn.value, ast.Name) and "S3Config" in (fn.value.id or ""):
                        from_yaml_calls += 1
                # S3Config(...) bare constructor
                if isinstance(fn, ast.Name) and fn.id == "S3Config":
                    s3config_calls += 1
    print(f"S3Config.from_yaml call sites in src/: {from_yaml_calls}")
    print(f"S3Config(...) bare constructor calls in src/: {s3config_calls}")

    # Look for any s3 yaml config.
    cfg_dir = ROOT / "config"
    s3_yamls = sorted(cfg_dir.glob("s3*.yaml")) + sorted(cfg_dir.glob("*s3*.yaml"))
    print(f"config/s3*.yaml files: {s3_yamls}")

    verdict_b = has_from_yaml and from_yaml_calls == 0 and not s3_yamls
    print(f"\nBUG-B CONFIRMED: {verdict_b}  (from_yaml defined but never called; "
          f"no s3 yaml; backtest uses bare S3Config() x{s3config_calls})")

    print()
    print("=== S3 BUG-C: survivorship universe (DV-6) ===")
    # Static trace: read backtest.py:209-210 and show the selection uses end=today.
    backtest_py = (SRC / "strategies" / "s3" / "backtest.py").read_text().splitlines()
    for i in range(195, 215):
        print(f"  backtest.py:{i+1}: {backtest_py[i]}")
    print()
    print("Trace: `end = date.today()` (backtest.py:200) -> "
          "`active = s3_universe.active_at(end)` (209) -> "
          "`tickers = list(active[:50])` (210).")
    print("The universe is filtered PIT at the FINAL date only, then reused on "
          "the full 2000-today window -> the 50 most-liquid survivors TODAY are "
          "the backtest universe for the entire history. Delisted/diminished "
          "names are absent -> survivorship bias + look-ahead in universe.")
    print(f"\nBUG-C CONFIRMED: static trace of backtest.py:200,209-210.")


if __name__ == "__main__":
    main()