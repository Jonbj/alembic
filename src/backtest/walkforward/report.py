"""Walk-forward HTML report generator."""
from __future__ import annotations

import html as _html
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.backtest.walkforward.runner import WalkForwardResult


class WalkForwardHTMLReport:
    """Generate a self-contained HTML report from a WalkForwardResult."""

    def generate(self, result: WalkForwardResult, title: str = "Walk-Forward Report") -> str:
        """Return HTML string for the given walk-forward result."""
        agg = result.aggregate_metrics
        per_window = agg.get("per_window", [])

        body_parts = [
            self._summary_section(agg, result.config),
            self._windows_table(per_window),
        ]

        oos_nav = agg.get("oos_nav_series")
        if isinstance(oos_nav, pd.Series) and len(oos_nav) > 1:
            body_parts.append(self._nav_chart(oos_nav))

        return self._wrap_html(title, "\n".join(body_parts))

    def save(
        self,
        result: WalkForwardResult,
        path: Path | str,
        title: str = "Walk-Forward Report",
    ) -> Path:
        """Generate HTML report and write to file. Returns the path."""
        html_str = self.generate(result, title)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_str, encoding="utf-8")
        return path

    # --- private helpers ---

    def _summary_section(self, agg: dict, cfg) -> str:
        metrics = [
            ("IS window (days)", getattr(cfg, "in_sample_days", "–")),
            ("OOS window (days)", getattr(cfg, "out_of_sample_days", "–")),
            ("Step (days)", getattr(cfg, "step_days", "–")),
            ("Windows", agg.get("n_windows", "–")),
            ("Valid windows", agg.get("n_valid_windows", "–")),
            ("Mean Sharpe", _fmt(agg.get("mean_sharpe"))),
            ("Median Sharpe", _fmt(agg.get("median_sharpe"))),
            ("Std Sharpe", _fmt(agg.get("std_sharpe"))),
            ("Mean Ann. Return", _pct(agg.get("mean_annualized_return"))),
            ("Mean Max DD", _pct(agg.get("mean_max_drawdown"))),
            ("Worst Drawdown", _pct(agg.get("worst_drawdown"))),
            ("% Windows Positive", _pct(agg.get("pct_windows_positive"))),
        ]
        rows = "".join(
            f"<tr><td>{_html.escape(str(label))}</td>"
            f"<td><strong>{_html.escape(str(value))}</strong></td></tr>"
            for label, value in metrics
        )
        return f"""
<section>
  <h2>Aggregate Metrics</h2>
  <table class="summary">
    <thead><tr><th>Metric</th><th>Value</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""

    def _windows_table(self, per_window: list[dict]) -> str:
        if not per_window:
            return "<section><h2>Per-Window Results</h2><p>No valid windows.</p></section>"

        headers = ["#", "OOS Start", "OOS End", "Days", "Ann. Return", "Sharpe", "Max DD", "Calmar"]
        header_html = "".join(f"<th>{_html.escape(c)}</th>" for c in headers)

        rows = []
        for w in per_window:
            ann_ret = w.get("annualized_return") or 0.0
            css = "positive" if ann_ret > 0 else "negative"
            rows.append(
                f'<tr class="{css}">'
                f"<td>{w.get('window_idx', '–')}</td>"
                f"<td>{w.get('oos_start', '–')}</td>"
                f"<td>{w.get('oos_end', '–')}</td>"
                f"<td>{w.get('n_days', '–')}</td>"
                f"<td>{_pct(w.get('annualized_return'))}</td>"
                f"<td>{_fmt(w.get('sharpe'))}</td>"
                f"<td>{_pct(w.get('max_drawdown'))}</td>"
                f"<td>{_fmt(w.get('calmar'))}</td>"
                "</tr>"
            )

        return f"""
<section>
  <h2>Per-Window Results</h2>
  <table class="windows">
    <thead><tr>{header_html}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>"""

    def _nav_chart(self, oos_nav: pd.Series) -> str:
        """Render concatenated OOS NAV as an inline SVG line chart."""
        w, h = 820, 320
        pad = {"l": 70, "r": 25, "t": 20, "b": 45}
        plot_w = w - pad["l"] - pad["r"]
        plot_h = h - pad["t"] - pad["b"]

        n = len(oos_nav)
        nav_min = float(oos_nav.min())
        nav_max = float(oos_nav.max())
        nav_range = nav_max - nav_min or 1.0

        pts = []
        for i, v in enumerate(oos_nav):
            x = pad["l"] + i / max(n - 1, 1) * plot_w
            y = pad["t"] + (1.0 - (float(v) - nav_min) / nav_range) * plot_h
            pts.append(f"{x:.1f},{y:.1f}")
        polyline = " ".join(pts)

        # Y-axis: 5 tick marks
        y_ticks: list[str] = []
        for i in range(5):
            frac = i / 4
            val = nav_min + frac * nav_range
            cy = pad["t"] + (1.0 - frac) * plot_h
            y_ticks.append(
                f'<line x1="{pad["l"]}" y1="{cy:.1f}" x2="{pad["l"] + plot_w}" y2="{cy:.1f}"'
                f' stroke="#eee" />'
                f'<text x="{pad["l"] - 6}" y="{cy + 4:.1f}" text-anchor="end"'
                f' font-size="11" fill="#555">{val:,.0f}</text>'
            )

        # X-axis: 3 date labels
        idx = oos_nav.index
        x_labels: list[str] = []
        for frac, tidx in [(0, 0), (0.5, n // 2), (1.0, n - 1)]:
            cx = pad["l"] + frac * plot_w
            ts = idx[tidx]
            label = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
            x_labels.append(
                f'<text x="{cx:.1f}" y="{pad["t"] + plot_h + 18}" text-anchor="middle"'
                f' font-size="11" fill="#555">{label}</text>'
            )

        return f"""
<section>
  <h2>OOS NAV Series</h2>
  <svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">
    {''.join(y_ticks)}
    {''.join(x_labels)}
    <polyline points="{polyline}" fill="none" stroke="#1a7abf" stroke-width="2" stroke-linejoin="round"/>
    <rect x="{pad['l']}" y="{pad['t']}" width="{plot_w}" height="{plot_h}"
          fill="none" stroke="#ccc"/>
  </svg>
</section>"""

    def _wrap_html(self, title: str, body: str) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #222; max-width: 1100px; }}
    h1 {{ border-bottom: 2px solid #1a7abf; padding-bottom: .5rem; }}
    h2 {{ color: #1a7abf; margin-top: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #ddd; padding: .45rem .7rem; text-align: left; white-space: nowrap; }}
    th {{ background: #f5f5f5; font-weight: 600; }}
    tr.positive td:nth-child(5) {{ color: #1a7a3a; font-weight: 600; }}
    tr.negative td:nth-child(5) {{ color: #c0392b; font-weight: 600; }}
    table.summary {{ max-width: 420px; }}
    section {{ margin-bottom: 2.5rem; }}
    footer {{ color: #999; font-size: .82rem; margin-top: 3rem; border-top: 1px solid #eee; padding-top: .5rem; }}
    p.meta {{ color: #777; font-size: .9rem; margin: 0 0 1rem; }}
  </style>
</head>
<body>
  <h1>{_html.escape(title)}</h1>
  <p class="meta">Generated: {now}</p>
  {body}
  <footer>Alembic Backtest Framework — Walk-Forward Report</footer>
</body>
</html>"""


def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{float(v):.4f}"


def _pct(v) -> str:
    if v is None:
        return "–"
    return f"{float(v) * 100:.2f}%"
