"""Metrics report generator: Markdown + HTML output from a BacktestResult.

Usage:
    result = orchestrator.run(replay, strategy)
    report = MetricsReport.from_backtest_result(result)
    report.save_markdown(Path("reports/metrics.md"))
    report.save_html(Path("reports/metrics.html"))
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.backtest.metrics import performance as perf
from src.backtest.metrics import risk
from src.backtest.metrics.attribution import AttributionResult


@dataclass
class MetricsReport:
    """Bundle of all computed metrics for one backtest run."""

    # Identification
    title: str = "Backtest Metrics Report"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Period
    start_date: str = ""
    end_date: str = ""
    n_periods: int = 0

    # Performance
    total_return: float = 0.0
    annualized_return: float = 0.0
    annualized_volatility: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    omega: float = 0.0

    # Risk
    max_drawdown: float = 0.0
    var_95: float = 0.0
    es_95: float = 0.0
    tail_ratio: float = 0.0
    skewness: float = 0.0
    excess_kurtosis: float = 0.0

    # Attribution (optional)
    attribution: AttributionResult | None = None

    # Raw returns for charting
    _nav_series: pd.Series | None = field(default=None, repr=False)
    _drawdown_series: pd.Series | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ #

    @classmethod
    def from_backtest_result(
        cls,
        result,
        title: str = "Backtest Metrics Report",
        attribution: AttributionResult | None = None,
    ) -> "MetricsReport":
        """Build a MetricsReport from a BacktestResult."""
        returns = result.to_returns_series()
        nav = result.to_nav_series()
        dd_series = risk.drawdown_series(returns)

        start = str(nav.index[0].date()) if not nav.empty else ""
        end = str(nav.index[-1].date()) if not nav.empty else ""
        total_ret = float(nav.iloc[-1] / nav.iloc[0] - 1.0) if len(nav) >= 2 else 0.0

        return cls(
            title=title,
            start_date=start,
            end_date=end,
            n_periods=len(returns),
            total_return=total_ret,
            annualized_return=perf.annualized_return(returns),
            annualized_volatility=perf.annualized_volatility(returns),
            sharpe=perf.sharpe_ratio(returns),
            sortino=perf.sortino_ratio(returns),
            calmar=perf.calmar_ratio(returns),
            omega=perf.omega_ratio(returns),
            max_drawdown=risk.max_drawdown(returns),
            var_95=risk.value_at_risk(returns, cutoff=0.05),
            es_95=risk.expected_shortfall(returns, cutoff=0.05),
            tail_ratio=risk.tail_ratio(returns),
            skewness=risk.skewness(returns),
            excess_kurtosis=risk.excess_kurtosis(returns),
            attribution=attribution,
            _nav_series=nav,
            _drawdown_series=dd_series,
        )

    # ------------------------------------------------------------------ #
    # Markdown output
    # ------------------------------------------------------------------ #

    def to_markdown(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Period:** {self.start_date} → {self.end_date} ({self.n_periods} days)",
            "",
            "## Performance",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Return | {self.total_return:.2%} |",
            f"| Annualised Return | {self.annualized_return:.2%} |",
            f"| Annualised Volatility | {self.annualized_volatility:.2%} |",
            f"| Sharpe Ratio | {self.sharpe:.3f} |",
            f"| Sortino Ratio | {self.sortino:.3f} |",
            f"| Calmar Ratio | {self.calmar:.3f} |",
            f"| Omega Ratio | {self.omega:.3f} |",
            "",
            "## Risk",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Max Drawdown | {self.max_drawdown:.2%} |",
            f"| VaR (95%) | {self.var_95:.2%} |",
            f"| ES (95%) | {self.es_95:.2%} |",
            f"| Tail Ratio | {self.tail_ratio:.3f} |",
            f"| Skewness | {self.skewness:.3f} |",
            f"| Excess Kurtosis | {self.excess_kurtosis:.3f} |",
            "",
        ]
        if self.attribution is not None:
            lines += self._attribution_markdown()
        return "\n".join(lines)

    def _attribution_markdown(self) -> list[str]:
        attr = self.attribution
        rows = [
            "## Strategy Attribution",
            "",
            "| Strategy | Weight | Ann. Return | Ann. Vol | Sharpe | Contrib. Return | Corr. |",
            "|----------|--------|-------------|----------|--------|-----------------|-------|",
        ]
        for s in attr.strategies:
            rows.append(
                f"| {s.name} | {s.weight:.1%} | {s.annualized_return:.2%} | "
                f"{s.annualized_volatility:.2%} | {s.sharpe:.2f} | "
                f"{s.contribution_to_return * 252:.2%} | {s.correlation_to_portfolio:.2f} |"
            )
        rows += [
            "",
            f"**Diversification Ratio:** {attr.diversification_ratio:.3f}",
            "",
        ]
        return rows

    def save_markdown(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ #
    # HTML output
    # ------------------------------------------------------------------ #

    def to_html(self) -> str:
        nav_chart = self._nav_chart_svg()
        dd_chart = self._drawdown_chart_svg()
        attr_section = self._attribution_html() if self.attribution else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(self.title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ color: #1a1a2e; }}
  h2 {{ color: #16213e; border-bottom: 2px solid #e0e0e0; padding-bottom: 4px; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th {{ background: #1a1a2e; color: white; padding: 8px 12px; text-align: left; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #e8e8e8; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }}
  .metric-card {{ background: #f0f4ff; border-radius: 8px; padding: 12px 16px; }}
  .metric-card .label {{ font-size: 0.8rem; color: #555; margin-bottom: 4px; }}
  .metric-card .value {{ font-size: 1.4rem; font-weight: 700; color: #1a1a2e; }}
  .metric-card .value.negative {{ color: #c0392b; }}
  .metric-card .value.positive {{ color: #27ae60; }}
  .chart-container {{ background: #fafafa; border-radius: 8px; padding: 12px; margin: 1rem 0; }}
  .subtitle {{ color: #666; margin-bottom: 1.5rem; font-size: 0.95rem; }}
  svg {{ width: 100%; height: 200px; overflow: visible; }}
</style>
</head>
<body>
<h1>{html.escape(self.title)}</h1>
<p class="subtitle">Period: {self.start_date} → {self.end_date} &nbsp;|&nbsp;
{self.n_periods} trading days &nbsp;|&nbsp;
Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}</p>

<h2>Performance Summary</h2>
<div class="metric-grid">
  {self._metric_card("Total Return", f"{self.total_return:.2%}", self.total_return >= 0)}
  {self._metric_card("Ann. Return", f"{self.annualized_return:.2%}", self.annualized_return >= 0)}
  {self._metric_card("Ann. Volatility", f"{self.annualized_volatility:.2%}", None)}
  {self._metric_card("Sharpe Ratio", f"{self.sharpe:.3f}", self.sharpe >= 0)}
  {self._metric_card("Sortino Ratio", f"{self.sortino:.3f}", self.sortino >= 0)}
  {self._metric_card("Calmar Ratio", f"{self.calmar:.3f}", self.calmar >= 0)}
  {self._metric_card("Max Drawdown", f"{self.max_drawdown:.2%}", self.max_drawdown >= 0)}
  {self._metric_card("VaR 95%", f"{self.var_95:.2%}", self.var_95 >= 0)}
  {self._metric_card("ES 95%", f"{self.es_95:.2%}", self.es_95 >= 0)}
  {self._metric_card("Tail Ratio", f"{self.tail_ratio:.3f}", self.tail_ratio >= 1)}
  {self._metric_card("Skewness", f"{self.skewness:.3f}", self.skewness >= 0)}
  {self._metric_card("Exc. Kurtosis", f"{self.excess_kurtosis:.3f}", None)}
</div>

<h2>NAV Series</h2>
<div class="chart-container">
{nav_chart}
</div>

<h2>Drawdown</h2>
<div class="chart-container">
{dd_chart}
</div>

{attr_section}
</body>
</html>"""

    @staticmethod
    def _metric_card(label: str, value: str, positive: bool | None) -> str:
        css_class = ""
        if positive is True:
            css_class = " positive"
        elif positive is False:
            css_class = " negative"
        return (
            f'<div class="metric-card">'
            f'<div class="label">{html.escape(label)}</div>'
            f'<div class="value{css_class}">{html.escape(value)}</div>'
            f"</div>"
        )

    def _nav_chart_svg(self) -> str:
        if self._nav_series is None or self._nav_series.empty:
            return "<p>No NAV data.</p>"
        return _line_chart_svg(self._nav_series, label="NAV", color="#1a1a2e")

    def _drawdown_chart_svg(self) -> str:
        if self._drawdown_series is None or self._drawdown_series.empty:
            return "<p>No drawdown data.</p>"
        return _line_chart_svg(self._drawdown_series, label="Drawdown", color="#c0392b", fill=True)

    def _attribution_html(self) -> str:
        attr = self.attribution
        rows = ""
        for s in attr.strategies:
            ann_contrib = s.contribution_to_return * 252
            rows += (
                f"<tr><td>{html.escape(s.name)}</td>"
                f"<td>{s.weight:.1%}</td>"
                f"<td>{s.annualized_return:.2%}</td>"
                f"<td>{s.annualized_volatility:.2%}</td>"
                f"<td>{s.sharpe:.2f}</td>"
                f"<td>{ann_contrib:.2%}</td>"
                f"<td>{s.correlation_to_portfolio:.2f}</td></tr>\n"
            )
        return f"""
<h2>Strategy Attribution</h2>
<p>Diversification Ratio: <strong>{attr.diversification_ratio:.3f}</strong></p>
<table>
<tr>
  <th>Strategy</th><th>Weight</th><th>Ann. Return</th><th>Ann. Vol</th>
  <th>Sharpe</th><th>Contrib. Return</th><th>Corr.</th>
</tr>
{rows}
</table>
"""

    def save_html(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_html(), encoding="utf-8")
        return path


# ------------------------------------------------------------------ #
# SVG chart helper
# ------------------------------------------------------------------ #

def _line_chart_svg(
    series: pd.Series,
    label: str = "",
    color: str = "#1a1a2e",
    fill: bool = False,
    width: int = 800,
    height: int = 180,
) -> str:
    """Render a pd.Series as a minimal inline SVG polyline."""
    vals = series.values.astype(float)
    n = len(vals)
    if n == 0:
        return "<p>No data.</p>"

    pad_x, pad_y = 40, 20
    draw_w = width - 2 * pad_x
    draw_h = height - 2 * pad_y

    v_min, v_max = float(vals.min()), float(vals.max())
    v_range = v_max - v_min if v_max != v_min else 1.0

    def _scale_x(i: int) -> float:
        return pad_x + (i / (n - 1)) * draw_w if n > 1 else pad_x + draw_w / 2

    def _scale_y(v: float) -> float:
        return pad_y + draw_h - ((v - v_min) / v_range) * draw_h

    points = " ".join(f"{_scale_x(i):.1f},{_scale_y(v):.1f}" for i, v in enumerate(vals))

    fill_path = ""
    if fill:
        zero_y = _scale_y(0.0)
        fill_path = (
            f'<polygon points="{_scale_x(0):.1f},{zero_y:.1f} {points} '
            f'{_scale_x(n-1):.1f},{zero_y:.1f}" '
            f'fill="{color}" fill-opacity="0.2" stroke="none"/>'
        )

    y_zero = _scale_y(0.0) if v_min < 0 < v_max else None
    zero_line = (
        f'<line x1="{pad_x}" y1="{y_zero:.1f}" x2="{pad_x + draw_w}" '
        f'y2="{y_zero:.1f}" stroke="#aaa" stroke-dasharray="4 3" stroke-width="1"/>'
        if y_zero is not None
        else ""
    )

    # Y-axis labels
    y_labels = (
        f'<text x="{pad_x - 4}" y="{_scale_y(v_max):.1f}" '
        f'text-anchor="end" font-size="9" fill="#777">{v_max:.2f}</text>'
        f'<text x="{pad_x - 4}" y="{_scale_y(v_min):.1f}" '
        f'text-anchor="end" font-size="9" fill="#777">{v_min:.2f}</text>'
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        f"{zero_line}{fill_path}"
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f"{y_labels}"
        f'<text x="{width // 2}" y="{height - 2}" text-anchor="middle" '
        f'font-size="10" fill="#555">{html.escape(label)}</text>'
        f"</svg>"
    )
