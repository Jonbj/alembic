"""S3 BUG-D reproduction: milestone_c_pass uses a trivial threshold.

backtest.py:97  milestone_c_pass = (0.0 <= oos_sharpe <= 1.0) and gate_report.overall_passed

The milestone-C acceptance condition requires only that OOS Sharpe lies in
[0.0, 1.0]. A Sharpe of exactly 0.0 (zero alpha, zero risk-adjusted return) is
accepted by the first conjunct. This makes the "milestone" gate non-informative:
it cannot reject a strategy that does literally nothing.

Additionally, the reported summary.json shows gate 1 (significance) and gate 2
(walk-forward) PASS with min_sharpe=0.0 -> the same trivial-threshold pattern at
the sub-gate level.

This is a logic/gate bug: the acceptance range starts at 0.0 instead of a
positive minimum (the design intent of milestone C per config/strategies.yaml
note is an OOS Sharpe in an "expected range [0.4, 0.6]" per the code comment at
backtest.py:96, but the implementation checks [0.0, 1.0]).

Run: PYTHONPATH=. python docs/audits/strategies/S3/repro_3_trivial_gate.py
"""


def milestone_c(oos_sharpe: float, overall_passed: bool) -> bool:
    # Mirror of backtest.py:97
    return (0.0 <= oos_sharpe <= 1.0) and overall_passed


def main() -> None:
    print("=== S3 BUG-D: trivial milestone_c threshold ===")
    print("backtest.py:97: milestone_c_pass = (0.0 <= oos_sharpe <= 1.0) and overall_passed")
    print()
    # Even if we pretend overall_passed is True, a zero-alpha strategy passes.
    cases = [
        (0.0, True, "zero alpha (does nothing)"),
        (0.001, True, "epsilon positive"),
        (0.148, True, "actual S3 OOS Sharpe"),
        (-0.5, True, "negative Sharpe (destroying value)"),
        (0.5, False, "decent Sharpe but a sub-gate failed"),
    ]
    for sharpe, passed, desc in cases:
        result = milestone_c(sharpe, passed)
        print(f"  oos_sharpe={sharpe:+.3f}  overall_passed={passed!s:5}  -> milestone_c={result!s:5}  ({desc})")
    print()
    print("CONFIRMED: oos_sharpe=0.0 with overall_passed=True yields milestone_c=True.")
    print("A strategy with zero risk-adjusted return is accepted -> the gate is "
          "non-informative; it cannot reject a no-op strategy. The code comment "
          "(backtest.py:96) says 'expected range [0.4, 0.6]' but the code checks "
          "[0.0, 1.0] -> implementation diverges from its own documented intent.")
    print()
    print("Note: in the actual S3 summary.json, overall_passed is False (gates "
          "3/5 fail) so milestone_c_pass is False regardless. The bug is latent: "
          "if gates 3/5 ever pass, a zero-alpha strategy would be promoted.")


if __name__ == "__main__":
    main()