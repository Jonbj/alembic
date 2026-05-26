-- migrations/009_expand_ticker_lookup.sql
-- Add 14 high-alpha symbols missing from the original S&P 500 seed.
--
-- Selection rationale (each symbol must pass two tests):
--   1. GDELT news volume: company name appears frequently in financial news
--      → GDELT GKG can map org_name → ticker via ticker_lookup
--   2. Trading alpha: event-driven price moves justify execution worker attention
--
-- Symbols added and why:
--   AMD    – Direct NVDA rival; every AI chip story mentions both. Highest
--            missed-alpha candidate: GDELT would have produced AMD signals but
--            the watchlist discarded them.
--   TSM    – TSMC manufactures chips for NVDA/AMD/AAPL; appears in every
--            supply-chain and export-control article.
--   LLY    – Eli Lilly: top-5 S&P 500 by market cap; GLP-1/Ozempic news cycle
--            drives sustained directional moves.
--   MU     – Micron: memory chips are the bottleneck for AI data centres;
--            earnings/supply cycle = strong event-driven signals.
--   ASML   – Semiconductor equipment monopoly; export-control headlines
--            (US/Netherlands/China) generate sharp moves.
--   ARM    – Arm Holdings: licenses chip architecture to nearly every SoC
--            vendor; IPO 2023, high news volume, AI narrative.
--   AMAT   – Applied Materials: largest US semiconductor equipment maker;
--            correlated with ASML/MU news cycles.
--   PLTR   – Palantir: government AI contracts generate event-driven spikes;
--            GDELT picks up DoD/intelligence-agency stories.
--   NOW    – ServiceNow: enterprise AI automation; frequently cited alongside
--            MSFT/GOOGL in CIO spending surveys.
--   SNOW   – Snowflake: cloud data platform; appears in AI/cloud spending
--            analyst reports picked up by GDELT.
--   PANW   – Palo Alto Networks: cybersecurity incidents name vendors directly
--            → reliable GDELT org-name extraction.
--   LLY duplicate guard → NVO (Novo Nordisk): GLP-1 direct competitor to LLY;
--            "Ozempic"/"semaglutide" stories always mention both.
--   XLE    – Energy Select Sector SPDR: oil/gas macro signals from GDELT
--            (OPEC, geopolitical) need a tradeable energy proxy.
--   XLV    – Health Care Select Sector SPDR: broad pharma/biotech macro proxy.
--   SOXX   – iShares Semiconductor ETF: captures semiconductor sector momentum
--            when individual ticker attribution is ambiguous.

INSERT INTO ticker_lookup (company_name, aliases, ticker, source) VALUES
  ('Advanced Micro Devices Inc',         ARRAY['Advanced Micro Devices','AMD Inc'],                                         'AMD',  'sp500'),
  ('Taiwan Semiconductor Manufacturing', ARRAY['TSMC','Taiwan Semiconductor Manufacturing Company','Taiwan Semiconductor'], 'TSM',  'sp500'),
  ('Eli Lilly and Company',              ARRAY['Eli Lilly','Lilly'],                                                        'LLY',  'sp500'),
  ('Micron Technology Inc',              ARRAY['Micron Technology','Micron'],                                               'MU',   'sp500'),
  ('ASML Holding NV',                    ARRAY['ASML','ASML Holding'],                                                      'ASML', 'sp500'),
  ('Arm Holdings plc',                   ARRAY['ARM Holdings','Arm Limited','ARM'],                                         'ARM',  'sp500'),
  ('Applied Materials Inc',              ARRAY['Applied Materials'],                                                        'AMAT', 'sp500'),
  ('Palantir Technologies Inc',          ARRAY['Palantir Technologies','Palantir'],                                         'PLTR', 'sp500'),
  ('ServiceNow Inc',                     ARRAY['ServiceNow'],                                                               'NOW',  'sp500'),
  ('Snowflake Inc',                      ARRAY['Snowflake'],                                                                'SNOW', 'sp500'),
  ('Palo Alto Networks Inc',             ARRAY['Palo Alto Networks'],                                                       'PANW', 'sp500'),
  ('Novo Nordisk AS',                    ARRAY['Novo Nordisk','Novo Nordisk A/S','Ozempic'],                                'NVO',  'sp500'),
  ('Energy Select Sector SPDR Fund',     ARRAY[]::text[],                                                                   'XLE',  'etf'),
  ('Health Care Select Sector SPDR Fund',ARRAY[]::text[],                                                                   'XLV',  'etf'),
  ('iShares Semiconductor ETF',          ARRAY['SOXX'],                                                                     'SOXX', 'etf')
ON CONFLICT (lower(company_name), ticker) DO NOTHING;
