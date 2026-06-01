-- migrations/010_add_adr_tickers.sql
-- Add international ADRs listed on NYSE/Nasdaq (Alpaca-compatible).
--
-- Selection criteria:
--   1. Listed on NYSE or Nasdaq (not OTC) → executable via Alpaca
--   2. High GDELT English-language news volume (company name reliably extracted)
--   3. Event-driven price moves that justify LLM signal attention
--
-- European:
--   SAP    – Largest European software company; enterprise IT/AI spending articles
--   SHEL   – Shell: LNG/oil-transition news, geopolitical energy stories
--   BP     – British Petroleum: oil/climate/energy-transition cycle
--   AZN    – AstraZeneca: drug-pipeline and clinical-trial news volume
--   UBS    – UBS Group: European banking stress, Credit Suisse acquisition aftermath
--   DB     – Deutsche Bank: European banking/macro stress indicator
--   ERIC   – Ericsson: 5G equipment, Huawei-alternative geopolitical stories
--   NOK    – Nokia: 5G infrastructure, telecom-vendor contract news
--
-- Asian:
--   BABA   – Alibaba: China e-commerce/cloud/regulatory; very high GDELT volume
--   BIDU   – Baidu: China AI/autonomous-driving; LLM competitor news
--   JD     – JD.com: China retail/logistics; supply-chain and consumer articles
--   TM     – Toyota: EV transition, hydrogen, largest automaker by volume
--   SONY   – Sony Group: gaming (PlayStation), image sensors, entertainment
--
-- Emerging markets / Other:
--   INFY   – Infosys: Indian IT outsourcing; frequently cited in offshoring articles
--   RIO    – Rio Tinto: metals/mining; China demand and commodity-cycle news
--   VALE   – Vale: iron-ore/nickel; Brazil macro and EV-battery materials
--   PBR    – Petrobras: Brazil oil; political risk and energy-policy news

INSERT INTO ticker_lookup (company_name, aliases, ticker, source) VALUES
  -- European
  ('SAP SE',
   ARRAY['SAP','SAP AG','SAP America'],
   'SAP',  'adr'),

  ('Shell plc',
   ARRAY['Shell','Royal Dutch Shell','Shell Energy'],
   'SHEL', 'adr'),

  ('BP plc',
   ARRAY['BP','British Petroleum','BP p.l.c.'],
   'BP',   'adr'),

  ('AstraZeneca plc',
   ARRAY['AstraZeneca','AZ','AstraZeneca PLC'],
   'AZN',  'adr'),

  ('UBS Group AG',
   ARRAY['UBS','UBS AG','UBS Group'],
   'UBS',  'adr'),

  ('Deutsche Bank AG',
   ARRAY['Deutsche Bank','Deutsche Bank AG'],
   'DB',   'adr'),

  ('Telefonaktiebolaget LM Ericsson',
   ARRAY['Ericsson','LM Ericsson','Ericsson AB'],
   'ERIC', 'adr'),

  ('Nokia Corporation',
   ARRAY['Nokia','Nokia Corp','Nokia Networks'],
   'NOK',  'adr'),

  -- Asian
  ('Alibaba Group Holding Limited',
   ARRAY['Alibaba','Alibaba Group','Taobao','Tmall','Alipay'],
   'BABA', 'adr'),

  ('Baidu Inc',
   ARRAY['Baidu','Baidu Inc','Baidu AI Cloud'],
   'BIDU', 'adr'),

  ('JD.com Inc',
   ARRAY['JD.com','JD','Jingdong','JD Logistics'],
   'JD',   'adr'),

  ('Toyota Motor Corporation',
   ARRAY['Toyota','Toyota Motor','Toyota Motor Corp'],
   'TM',   'adr'),

  ('Sony Group Corporation',
   ARRAY['Sony','Sony Group','Sony Corporation','Sony Corp','PlayStation'],
   'SONY', 'adr'),

  -- Emerging markets / Other
  ('Infosys Limited',
   ARRAY['Infosys','Infosys Ltd','Infosys BPM'],
   'INFY', 'adr'),

  ('Rio Tinto plc',
   ARRAY['Rio Tinto','Rio Tinto Group','Rio Tinto plc'],
   'RIO',  'adr'),

  ('Vale SA',
   ARRAY['Vale','Vale S.A.','Vale SA'],
   'VALE', 'adr'),

  ('Petroleo Brasileiro SA',
   ARRAY['Petrobras','Petróleo Brasileiro','Petróleo Brasileiro S.A.'],
   'PBR',  'adr')

ON CONFLICT (lower(company_name), ticker) DO NOTHING;
