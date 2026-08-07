# Trading Algorithms & Software Research Report

**Date:** 2026-07-26  
**Prepared for:** Alembic Trading System  
**Research Scope:** Open-source trading algorithms, bots, and financial software for value-add integration

---

## Executive Summary

This report identifies **30 open-source resources** relevant to Alembic, organized by category and priority. Research focused on:

- Architectural compatibility (offline signal generation, Redis caching)
- Risk management and execution intelligence
- Portfolio optimization
- Alternative data sources beyond existing news pipeline

**Alembic Context:**
- LLM-based Algorithmic Trading System (Alpha Miner paradigm)
- Current strategies: S1 (Multi-Lookback Relative Momentum, 50% allocation), S4 (News-Driven Tactical with LLM ensemble, 10% allocation)
- Broker: Alpaca (USA-only), IBKR migration planned (multi-market)
- Infrastructure: FastAPI + Celery + Redis + PostgreSQL
- Backtesting: Backtrader
- LLM: Ensemble glm-5.2 + gpt-oss via Ollama + FinBERT fallback
- Status: Paper trading live, ~$110K portfolio, 15-min cycle

---

## 1. TRADING STRATEGIES

### 1.1 Mean Reversion / Statistical Arbitrage

#### 1.1.1 Cointrader
**Priority:** HIGH | **Complexity:** Medium

- **GitHub:** https://github.com/MatyDiop/Cointrader
- **Description:** Pairs trading engine with Engle-Granger/Johansen cointegration, dynamic hedge ratio via Kalman filter, walk-forward validation. Includes FDR correction for multiple testing and Streamlit dashboard.
- **Language/Framework:** Python 3.10+, pandas, statsmodels, yfinance
- **Status:** Active (MIT license)
- **Why Useful for Alembic:** Complements S1 (momentum) with market-neutral strategy. Kalman filter for dynamic hedge ratio is superior to static OLS.
- **Integration Complexity:** Medium (requires data pipeline for cointegration screening)
- **Data Required:** Historical daily/intraday prices for pair screening

---

#### 1.1.2 Statistical Arbitrage Engine
**Priority:** HIGH | **Complexity:** Medium

- **GitHub:** https://github.com/Pooja2420/statistical-arbitrage-engine
- **Description:** Complete system with dual cointegration test, Kalman filter, OU half-life filtering (5-60 days), Streamlit dashboard with 4 tabs. Backtest: 14.2% annualized, Sharpe 1.63 (2023-2024 OOS).
- **Language/Framework:** Python 3.11, vectorbt, DuckDB, Plotly
- **Status:** Active, 37 tests passing
- **Why Useful for Alembic:** Modular architecture compatible with Redis caching. Dashboard ready for integration.
- **Integration Complexity:** Medium
- **Data Required:** Historical prices for universe of pairs

---

#### 1.1.3 Bayesian-Optimized Pairs Engine
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/theanh97/Statistical-Arbitrage-Bayesian-Optimized-Kappa-Half-life-Pairs-Trading-Engine
- **Description:** Bayesian optimization (skopt) for Kappa and Half-life parameters. Maximizes Sharpe Ratio. Backtrader integration.
- **Language/Framework:** Python, backtrader, skopt, statsmodels
- **Status:** Active, 45 stars
- **Why Useful for Alembic:** Bayesian optimization could improve entry/exit parameter tuning.
- **Integration Complexity:** Low (if already using Backtrader)
- **Data Required:** Historical prices

---

### 1.2 Volatility Strategies

#### 1.2.1 Options Volatility Trading Strats
**Priority:** HIGH | **Complexity:** High

- **GitHub:** https://github.com/tfrmma/options-volatility-trading-strats
- **Description:** Advanced crypto options strategies (Deribit/Binance): delta-neutral straddles/strangles with Whalley-Wilmott bands, VRP harvesting, dispersion trading, volatility surface trading.
- **Language/Framework:** Python, asyncio
- **Status:** Active (MIT)
- **Why Useful for Alembic:** VRP (Volatility Risk Premium) is a factor decorrelated from momentum. Compatible with IBKR migration (USA options).
- **Integration Complexity:** High (requires options data and IV/RV calculation)
- **Data Required:** Options chain, IV surface, realized volatility

---

#### 1.2.2 Volatility Trading (VRP Harvesting)
**Priority:** MEDIUM | **Complexity:** Medium

- **GitHub:** https://github.com/anthonymakarewicz/volatility-trading
- **Description:** Research and backtesting for equity options. Includes VRP harvesting with regime detection, tail-risk filters (VIX term structure, VVIX), and SPX backtesting engine.
- **Language/Framework:** Python, Jupyter
- **Status:** Active, 23 stars
- **Why Useful for Alembic:** Regime detection for VRP is transferable to crypto/equity.
- **Integration Complexity:** Medium
- **Data Required:** VIX, VVIX, SPX options

---

### 1.3 Machine Learning / Deep Learning

#### 1.3.1 FinRL-Trading
**Priority:** HIGH | **Complexity:** Medium-High

- **GitHub:** https://github.com/AI4Finance-Foundation/FinRL-Trading
- **Description:** Modular AI-native infrastructure for quantitative trading. PPO, DRL, ML stock selection, portfolio allocation. Supports live trading via Alpaca and backtesting with `bt` engine. Paper on arXiv (2603.21330).
- **Language/Framework:** Python, PyTorch, Stable Baselines3
- **Status:** Very active, 3.4K+ stars
- **Why Useful for Alembic:** Similar architecture (Alpaca integration). RL for dynamic allocation could complement LLM ensemble.
- **Integration Complexity:** Medium-High
- **Data Required:** Prices, fundamentals (optional)

---

#### 1.3.2 LSTM-PPO DRL StockTrader
**Priority:** MEDIUM | **Complexity:** Medium

- **GitHub:** https://github.com/MahanVeisi8/LSTMppo-DRL-StockTrader
- **Description:** Combines LSTM + PPO with FinBERT sentiment analysis. Published IEEE ICCKE 2024. Includes drawdown penalty in reward function.
- **Language/Framework:** Python, PyTorch, Transformers
- **Status:** Active (October 2024)
- **Why Useful for Alembic:** FinBERT is already in your stack. LSTM for temporal patterns + RL for execution is a validated pattern.
- **Integration Complexity:** Medium
- **Data Required:** Prices, news for FinBERT

---

#### 1.3.3 Ray-PPO-Transformer-Trader
**Priority:** MEDIUM | **Complexity:** High

- **GitHub:** https://github.com/nssanta/Ray-PPO-Transformer-Trader
- **Description:** Custom Transformer architecture with Ray RLlib for Bitcoin futures. Uses 360-candle lookback, +57% return on validation data with 30x leverage.
- **Language/Framework:** Python, PyTorch, Ray RLlib
- **Status:** Active
- **Why Useful for Alembic:** Transformer for feature extraction is superior to LSTM for long sequences.
- **Integration Complexity:** High (Ray requires dedicated infrastructure)
- **Data Required:** Futures data (crypto or CME)

---

### 1.4 Carry Trade

#### 1.4.1 Crypto Carry Trade Strategies
**Priority:** HIGH | **Complexity:** Low

- **GitHub:** https://github.com/matthias-wyss/crypto-carry-trade-strategies
- **Description:** EPFL Engineering Finance project: delta-neutral carry trade on crypto using funding rates (BTC/ETH), staking (ETH + Lido), Pendle Finance (PT-stETH). Backtest 2019-2024.
- **Language/Framework:** Python, pandas
- **Status:** Active (MIT)
- **Why Useful for Alembic:** Market-neutral strategy decorrelated from momentum. Funding rates are free and predictable data.
- **Integration Complexity:** Low (just reading funding rates from exchanges)
- **Data Required:** Historical funding rates (Binance, OKX, Bybit)

---

#### 1.4.2 Cross-Asset Carry
**Priority:** MEDIUM | **Complexity:** Medium

- **GitHub:** https://github.com/christianmacion26/cross-asset-carry
- **Description:** Multi-asset carry: FX (interest rate differential), Bond (curve slope 10Y-2Y), Commodity (roll yield). Portfolio long/short volatility-weighted.
- **Language/Framework:** Python, Jupyter
- **Status:** Active
- **Why Useful for Alembic:** Useful post-IBKR migration for multi-asset.
- **Integration Complexity:** Medium
- **Data Required:** FX rates, bond yields, futures curves

---

### 1.5 Event-Driven Strategies

#### 1.5.1 Catalyst Detector
**Priority:** HIGH | **Complexity:** Low

- **GitHub:** https://github.com/Harsh-Daga/Catalyst-Detector
- **Description:** Automatic catalyst detection from SEC filings, earnings calls, press releases: M&A, FDA approvals, dividend increases, buybacks, partnerships. Multi-LLM (Groq, Gemini, Claude, Ollama). Telegram alerts.
- **Language/Framework:** Python, multiple LLMs
- **Status:** Active (MIT), 10+ free data sources
- **Why Useful for Alembic:** Extends S4 (news-driven) with structured events. Ollama is already in your stack.
- **Integration Complexity:** Low (API-compatible with existing LLM pipeline)
- **Data Required:** SEC EDGAR, earnings transcripts, press releases (free)

---

#### 1.5.2 Earnings Trade Backtest
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/tradermonty/earnings-trade-backtest
- **Description:** Specialized in earnings-based swing trading (mid/small-cap). 99.7% accuracy on earnings dates (FinancialModelingPrep API). Two-stage filtering, dynamic position sizing.
- **Language/Framework:** Python, Alpaca SDK
- **Status:** Active (MIT), 44+ tests
- **Why Useful for Alembic:** Direct integration with Alpaca (your current broker).
- **Integration Complexity:** Low
- **Data Required:** Earnings calendar, pre/post market prices

---

### 1.6 Multi-Factor Models

#### 1.6.1 OpenFactor
**Priority:** HIGH | **Complexity:** Medium

- **GitHub:** https://github.com/maxthraxx/openfactor
- **Description:** Open-source Barra-style equity style risk model. 25+ factors (Value, Quality, Momentum, Size, Growth, Profitability, Leverage). Risk attribution, tracking error decomposition, semantic factor discovery with LLM.
- **Language/Framework:** Python, CLI + API
- **Status:** Active, production-ready
- **Why Useful for Alembic:** Factor exposure analysis to monitor hidden portfolio risks. LLM for factor discovery is innovative.
- **Integration Complexity:** Medium
- **Data Required:** Prices, fundamentals (market cap, book value, earnings)

---

#### 1.6.2 MultiFactorStockRS
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/amit943c/MultiFactorStockRS
- **Description:** 8 factors (Momentum, Trend, Mean Reversion, Liquidity, Volatility, Fundamental, Quality, Value). Streamlit dashboard with IC analysis, quantile returns, factor decay, regime analysis.
- **Language/Framework:** Python, YAML config, Streamlit, Plotly
- **Status:** Active
- **Why Useful for Alembic:** Robust validation (lookahead bias check, sensitivity sweeps).
- **Integration Complexity:** Low (configurable via YAML)
- **Data Required:** Prices, fundamentals

---

## 2. TRADING BOTS & FRAMEWORKS

### 2.1 Complete Trading Bots

#### 2.1.1 Vibe-Trading
**Priority:** HIGH | **Complexity:** High

- **GitHub:** https://github.com/HKUDS/Vibe-Trading
- **Description:** Most popular open-source AI trading agent (27K+ stars). Multi-agent teams (investment committee, quant desk, risk committee). 88 skills, 462 pre-built alphas. 12 broker connectors (IBKR, Alpaca, OKX, Binance). Shadow Account for trade journal.
- **Language/Framework:** Python, multi-agent
- **Status:** Very active, frequent releases (v0.1.12+)
- **Why Useful for Alembic:** Multi-agent architecture similar to your LLM ensemble. Shadow Account for post-trade analysis is valuable.
- **Integration Complexity:** High (heavy framework, better to extract components)
- **Data Required:** Depends on selected strategies

---

#### 2.1.2 Samvid Trading Core
**Priority:** MEDIUM | **Complexity:** High

- **GitHub:** https://github.com/AshishTalpada/samvid-trading-core
- **Description:** Multi-agent AI for IBKR and MetaTrader 5. 11 specialized agents with consensus-based execution. Institutional risk management (drawdown ladder, consecutive loss tracking). QuestDB for real-time data.
- **Language/Framework:** Python + Rust
- **Status:** Active (MIT)
- **Why Useful for Alembic:** IBKR integration is relevant for migration. Consensus-based execution reduces errors.
- **Integration Complexity:** High (Python+Rust stack)
- **Data Required:** Real-time data from IBKR/MT5

---

#### 2.1.3 MMR (Make Me Rich)
**Priority:** HIGH | **Complexity:** Medium

- **GitHub:** https://github.com/9600dev/mmr
- **Description:** LLM-native platform built on `ib_async` for IBKR. Pipeline Propose → Review → Approve (LLM doesn't trade directly). ATR-inverse position sizing. ZeroMQ, DuckDB. 80+ CLI commands.
- **Language/Framework:** Python, ib_async, ZeroMQ, DuckDB
- **Status:** Active, 123 stars
- **Why Useful for Alembic:** LLM-safe architecture (human-in-the-loop) is similar to your approach. IBKR-ready.
- **Integration Complexity:** Medium (modular, extract position sizing and risk management)
- **Data Required:** Data from IBKR

---

### 2.2 Alternative Backtesting Frameworks

#### 2.2.1 VectorBT
**Priority:** HIGH | **Complexity:** Low

- **GitHub:** https://github.com/polakowo/vectorbt
- **Description:** Vectorized backtesting (NumPy/Numba) with optional Rust engine. 56.9K combos/second (40x faster than backtesting.py, 950x faster than bt). PRO adds portfolio optimization.
- **Language/Framework:** Python, NumPy, Numba, Rust (optional)
- **Status:** Very active, 8.4K+ stars
- **Why Useful for Alembic:** Backtrader is slow (0.11 combos/sec). VectorBT for parameter sweep + Backtrader for final validation is 2024-2025 best practice.
- **Integration Complexity:** Low (similar API, installable alongside Backtrader)
- **Data Required:** Same as Backtrader

---

#### 2.2.2 Backtesting.py
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/heliphix/backtesting.py
- **Description:** Lightweight event-driven framework (NumPy-backed). 1.42 combos/second. Automatic HTML reports with Sharpe, drawdown, equity curves.
- **Language/Framework:** Python, NumPy
- **Status:** Active, AGPL-3.0 license
- **Why Useful for Alembic:** Faster than Backtrader for rapid prototyping.
- **Integration Complexity:** Low
- **Data Required:** Standard pandas DataFrame

---

## 3. RISK MANAGEMENT & EXECUTION

### 3.1 Risk Management Systems

#### 3.1.1 FRTB IMA Risk Monitor
**Priority:** HIGH | **Complexity:** Medium

- **GitHub:** https://github.com/marksguo/frtb-ima-risk-monitor
- **Description:** FRTB-compliant (Fundamental Review of the Trading Book) system. Historical Simulation VaR & Expected Shortfall (97.5%), stress calibration, backtesting (Acerbi-Szekely, Kupiec, Christoffersen). Plotly Dash dashboard with scenario/stress lab. Marginal & Component VaR.
- **Language/Framework:** Python 3.13, yfinance, Dash, PostgreSQL
- **Status:** Active, production-ready
- **Why Useful for Alembic:** Expected Shortfall is required by Basel III. Risk model backtesting is crucial for paper/live trading.
- **Integration Complexity:** Medium
- **Data Required:** Historical prices for simulation

---

#### 3.1.2 Real-Time Risk Engine
**Priority:** MEDIUM | **Complexity:** Medium

- **GitHub:** https://github.com/jrajath94/real-time-risk-engine
- **Description:** GPU-accelerated intraday VaR engine for sub-second risk management. Vectorized Monte Carlo, Expected Shortfall, stress testing.
- **Language/Framework:** Python, NumPy, CUDA (optional)
- **Status:** Active
- **Why Useful for Alembic:** For intraday portfolio monitoring (currently 15-min cycle).
- **Integration Complexity:** Medium (GPU optional)
- **Data Required:** Real-time or delayed prices

---

#### 3.1.3 RiskKit
**Priority:** HIGH | **Complexity:** Low

- **GitHub:** https://github.com/9600dev/mmr/tree/main/riskkit
- **PyPI:** `pip install riskkit-quant`
- **Description:** Modular risk management toolkit. PositionSizer (volatility-adjusted with half-Kelly), DrawdownManager (tiered control), volatility_target_size, inverse_vol_weights (risk parity), kelly_fraction.
- **Language/Framework:** Python, zero runtime dependencies
- **Status:** Active, PyPI package
- **Why Useful for Alembic:** Framework-agnostic (works with Backtrader, vectorbt, FastAPI). Kelly fraction and volatility targeting are best practices.
- **Integration Complexity:** Low (pure library, simple API)
- **Data Required:** ATR or historical volatility

---

### 3.2 Execution Algorithms & Smart Order Routing

#### 3.2.1 Smart Order Router
**Priority:** HIGH | **Complexity:** Medium-High

- **GitHub:** https://github.com/shivangraval50/smart-order-router
- **Description:** Intelligent multi-venue routing (8 markets: NYSE, NASDAQ, BATS, ARCA). 74.3% fill rate improvement, 44.2% latency reduction. Multi-factor scoring (latency, fill rate, fees, liquidity). Live dashboard with Prometheus metrics.
- **Language/Framework:** Python 3.11
- **Status:** Active, production-ready
- **Why Useful for Alembic:** Post-IBKR migration (multi-venue), SOR reduces slippage. Anti-churn logic included.
- **Integration Complexity:** Medium-High
- **Data Required:** Level 2 data from multiple venues

---

#### 3.2.2 Nautilus Trader
**Priority:** HIGH | **Complexity:** High

- **GitHub:** https://github.com/nautechsystems/nautilus_trader
- **Description:** Institutional-grade trading platform with production-grade execution engine. Order state machine, reconciliation logic, anti-churn (in-flight order checks, fill deduplication, retry limits).
- **Language/Framework:** Python + Rust (core)
- **Status:** Very active, production-ready
- **Why Useful for Alembic:** Best-in-class anti-churn logic. Preventing order churn is critical for performance.
- **Integration Complexity:** High (better to extract only execution engine)
- **Data Required:** Real-time data from broker

---

#### 3.2.3 TWAP vs VWAP 2026
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/alicelmre2705/twap-vs-vwap-2026
- **Description:** Comparative analysis of execution costs: TWAP, forecast-VWAP, realized-VWAP. Measures implementation shortfall vs arrival price. Includes max-participation constraints.
- **Language/Framework:** Python, pandas, yfinance
- **Status:** Active (MIT)
- **Why Useful for Alembic:** Implementing VWAP forecast (vs realized) reduces slippage by ~0.0044 USD/share.
- **Integration Complexity:** Low (simple code, extractable)
- **Data Required:** 5-min bars for volume forecasting

---

### 3.3 Position Sizing & Portfolio Optimization

#### 3.3.1 PyPortfolioOpt
**Priority:** HIGH | **Complexity:** Low

- **GitHub:** https://github.com/PyPortfolio/PyPortfolioOpt
- **Description:** Complete portfolio optimization library. Mean-Variance, Black-Litterman, Hierarchical Risk Parity (HRP), covariance shrinkage (Ledoit-Wolf, OAS), Mean-CVaR, Mean-Semivariance.
- **Language/Framework:** Python, pandas, scipy
- **Status:** Very active (v1.6.0, February 2026), JOSS published
- **Why Useful for Alembic:** HRP is superior to Mean-Variance for stability. Black-Litterman for incorporating LLM views.
- **Integration Complexity:** Low (`pip install pyportfolioopt`)
- **Data Required:** Historical returns, covariance matrix

---

#### 3.3.2 Canopy
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/Anagatam/Canopy
- **PyPI:** `pip install canopy-optimizer`
- **Description:** HRP, HERC (Hierarchical Equal Risk Contribution), NCO (Nested Clustered Optimization). 4 covariance estimators, 4 risk measures (Variance, CVaR, CDaR, MAD). Walk-forward backtesting. ISO 8601 audit trails (MiFID II / SEC compliant).
- **Language/Framework:** Python, PyPI package
- **Status:** New (2026), v3.0.2
- **Why Useful for Alembic:** HRP/HERC are more robust than Mean-Variance. Audit trail is useful for compliance.
- **Integration Complexity:** Low
- **Data Required:** Historical returns

---

## 4. ALTERNATIVE DATA & SENTIMENT

### 4.1 Alt Data Alpha Engine
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/Vansh-Coder/alt-data-alpha-engine
- **Description:** Alpha generation from alternative data: financial news, Reddit, SEC filings (8-K). Sentiment analysis with OpenAI. Backtrader integration. Streamlit dashboard with automatic weekly updates.
- **Language/Framework:** Python, OpenAI, Backtrader, Streamlit, GitHub Actions
- **Status:** Active
- **Why Useful for Alembic:** Reddit + SEC filings are free data. GitHub Actions for automatic scraping.
- **Integration Complexity:** Low
- **Data Required:** Reddit API (free), SEC EDGAR (free), news RSS

---

### 4.2 Alternate Alpha Generator
**Priority:** MEDIUM | **Complexity:** Medium

- **GitHub:** https://github.com/poenitens-42/Alternate-Alpha-Generator
- **Description:** Three signals: Reddit/FinBERT sentiment, Finnhub news, satellite imagery (Sentinel-2). Institutional IC/ICIR evaluation. PLTR IC(1d)=+0.352, p<0.01. Lookahead bias controls.
- **Language/Framework:** Python, FinBERT (HuggingFace), Google Earth Engine, PRAW, Finnhub
- **Status:** Active
- **Why Useful for Alembic:** Satellite imagery is unconventional alternative data. IC/ICIR metrics for validation.
- **Integration Complexity:** Medium (Google Earth Engine requires setup)
- **Data Required:** Sentinel-2 (free), Reddit, Finnhub (free tier)

---

### 4.3 Social Arbitrage
**Priority:** MEDIUM | **Complexity:** Low

- **GitHub:** https://github.com/pateljalpan01/social-arbitrage
- **Description:** Exploits latency gap between retail hype (Twitter) and financial news. FinBERT for sentiment quantification. Social-News Latency Arbitrage methodology.
- **Language/Framework:** Python, FinBERT, FinTwitBERT, Playwright, Yahoo Finance
- **Status:** Active
- **Why Useful for Alembic:** Latency arbitrage is compatible with 15-min cycle architecture.
- **Integration Complexity:** Low
- **Data Required:** Twitter/X API, news RSS

---

## SUMMARY BY PRIORITY

### Priority 1: Quick Integration (Low Complexity, High Value)

| Resource | Category | Why |
|----------|----------|-----|
| **RiskKit** | Risk Management | Kelly/vol-targeting position sizing, immediate integration |
| **PyPortfolioOpt** | Portfolio Optimization | HRP + Black-Litterman for dynamic allocation |
| **Crypto Carry Trade** | Strategy | Market-neutral, free data, decorrelated |
| **Catalyst Detector** | Event-Driven | Extends S4 with structured events, Ollama-compatible |
| **VectorBT** | Backtesting | Fast parameter sweep (alongside Backtrader) |

---

### Priority 2: Medium-Term (Medium Complexity, High Value)

| Resource | Category | Why |
|----------|----------|-----|
| **Cointrader / Stat Arb Engine** | Mean Reversion | Complements S1 (momentum) with market-neutral strategy |
| **FRTB IMA Risk Monitor** | Risk Management | VaR/ES with backtesting, dashboard ready |
| **OpenFactor** | Factor Analysis | Factor exposure to monitor hidden risks |
| **Smart Order Router** | Execution | Post-IBKR, reduces slippage multi-venue |
| **FinRL-Trading** | ML/RL | RL for dynamic allocation, Alpaca-compatible |

---

### Priority 3: Long-Term (High Complexity, High Value)

| Resource | Category | Why |
|----------|----------|-----|
| **Nautilus Trader (Execution Engine)** | Execution | Production-grade anti-churn logic |
| **Options Volatility Strategies** | Volatility | VRP harvesting post-IBKR (USA options) |
| **Vibe-Trading (components)** | Multi-Agent | Shadow Account for trade journal analysis |

---

## SPECIFIC RECOMMENDATIONS FOR ALEMBIC

### 1. Dynamic Allocation (Replace 50%/10% Static)
Implement **PyPortfolioOpt with HRP** for allocation between S1 and S4. Black-Litterman to incorporate LLM views as "view" in the model.

### 2. Intraday Risk Management
Integrate **RiskKit** for volatility-adjusted position sizing and **FRTB IMA** for continuous VaR/ES monitoring.

### 3. New Strategy: Crypto Carry Trade
Add market-neutral strategy based on funding rates (crypto). Free data, low correlation with momentum.

### 4. Execution Anti-Churn
Extract anti-churn logic from **Nautilus Trader** to prevent order cancellation/replace loops.

### 5. Hybrid Backtesting
Use **VectorBT** for parameter sweep (fast) + **Backtrader** for final validation (realistic).

---

## ADDITIONAL DATA REQUIRED

| Data Type | Source | Cost | Priority |
|-----------|--------|------|----------|
| Crypto Funding Rates | Binance/OKX/Bybit API | Free | High (Carry) |
| SEC EDGAR 8-K | sec.gov | Free | High (Catalyst) |
| Reddit API (r/stocks, r/wallstreetbets) | PRAW | Free | Medium (Sentiment) |
| Earnings Calendar | FinancialModelingPrep | Free tier | Medium (Event-driven) |
| Options Chain (post-IBKR) | IBKR API | Included | Medium (Volatility) |
| Factor Data (Value, Quality, etc.) | Yahoo Finance / Compustat | Free / Paid | Medium (OpenFactor) |

---

## IMPLEMENTATION ROADMAP

### Phase 1 (Week 1-2): Quick Wins
- [ ] Install RiskKit → position sizing volatility-adjusted
- [ ] Install PyPortfolioOpt → HRP allocation S1/S4
- [ ] Install VectorBT → parameter sweep alongside Backtrader
- [ ] Crypto Carry strategy → funding rates data pipeline

### Phase 2 (Week 3-4): Medium Complexity
- [ ] Catalyst Detector → SEC EDGAR integration
- [ ] FRTB IMA Risk Monitor → VaR/ES dashboard
- [ ] OpenFactor → factor exposure analysis
- [ ] Statistical Arbitrage Engine → pairs screening pipeline

### Phase 3 (Month 2-3): Post-IBKR Migration
- [ ] Smart Order Router → multi-venue execution
- [ ] Options Volatility Strategies → VRP harvesting
- [ ] Nautilus Trader execution engine → anti-churn logic

---

## CONCLUSION

The identified resources cover Alembic's entire stack:
- **Strategies:** Mean reversion, carry, volatility, ML/RL
- **Risk:** VaR/ES, position sizing, factor exposure
- **Execution:** SOR, anti-churn, TWAP/VWAP
- **Portfolio:** HRP, Black-Litterman
- **Data:** Sentiment, alternative data (SEC, Reddit, satellite)

**Low-complexity integrations** (RiskKit, PyPortfolioOpt, Carry Trade) can be implemented immediately. **Medium/high-complexity** (SOR, Nautilus execution, options) should be planned post-IBKR migration.

---

## APPENDIX: QUICK REFERENCE LINKS

### Libraries (pip install)
- `pip install ib_async` — Interactive Brokers API
- `pip install riskkit-quant` — Risk management toolkit
- `pip install pyportfolioopt` — Portfolio optimization
- `pip install vectorbt` — Fast backtesting
- `pip install canopy-optimizer` — HRP/HERC optimization

### GitHub Organizations to Watch
- https://github.com/AI4Finance-Foundation — FinRL, FinGPT
- https://github.com/ib-api-reloaded — ib_async (IBKR)
- https://github.com/PyPortfolio — PyPortfolioOpt
- https://github.com/nautechsystems — Nautilus Trader
- https://github.com/polakowo — VectorBT

### Documentation
- ib_async: https://ib-api-reloaded.github.io/ib_async/
- PyPortfolioOpt: https://pyportfolioopt.readthedocs.io/
- VectorBT: https://vectorbt.dev/
- IBKR API: https://www.interactivebrokers.com/en/trading/ib-api.php

---

*Report generated by autonomous research agent on 2026-07-26*
