# S4 — ricerca sulle strategie di uscita (analisi GLM-5.2)

> Data cutoff: 2026-08-14. Fonti primarie verificate via risoluzione DOI / arXiv / siti autore.
> Livello di accesso dichiarato per ogni voce in bibliografia (full-text / abstract). I dettagli
> numerici di tabelle/figure letti solo tramite riepilogo secondario sono marcati `snippet`.
> 02/03/04 sono usati come **evidenza e contesto**, non come conclusioni da confermare: il candidato
> D+2 (04) è trattato come ipotesi falsificabile.

---

## 1. Executive verdict

**Policy raccomandata: E1 modificata.** Mantenere il **time-stop primario alla chiusura di D+2**, affiancato da (i) un **contro-segnale ridisegnato come falsificazione della tesi** — posteriore aggregato sulla validità del segnale d'ingresso con requisito di persistenza (≥2 cicli) e **una sola soglia pre-registrata ex ante**, non fittata sul campione storico — e (ii) un **catastrophe stop largo** uguale al `d_hard` broker esistente (12–20%, già abilitato di default). **Chiudere due divergenze codice/config prima del batch shadow**: la soglia del contro-segnale (codice −0,20 / ops −0,35 / pre-reg −0,30) e l'estensione del clock DAILY a S4 (`_REBALANCE_CLOCK_STRATEGIES={"S1"}` oggi esclude S4). Confronto confirmatorio: **E1-mod vs E5 (time+catastrophe, senza contro-segnale) vs E0 (baseline)**, gate congiunto R1–R4, test di selezione **Hansen SPA_c**, ~213 sedute pulite o `INCONCLUSIVE`.

**Confidenza.** Moderata sul *processo* e sull'elemento time-stop (la fonte più trasferibile, Lopez-Lira–Tang, è LLM-based e mostra prevedibilità su ~2 giorni); bassa sul contro-segnale *come implementato* (soglia puntuale, senza persistenza, soglia divergente); strutturalmente limitata sul *magnitude* dell'edge, perché S4 è long-only e gran parte del drift documentato (negativo, lento) è sulla gamba short inaccessibile.

**Verdetto su D+2: `MODIFY`** (§9). Lo scheletro è corretto e allineato alla letteratura di validazione; la carne sul contro-segnale e due divergenze codice/config lo rendono non eseguibile come dichiarato.

> Le 10 domande (§6) sono indirizzate inline: **Q1** §2 · **Q2** §3,§9 · **Q3** §4,§9 · **Q4** §4,§9 · **Q5** §4 · **Q6** §4 · **Q7** §4,§5 · **Q8** §6,§8 · **Q9** §4 · **Q10** §1,§9.

---

## 2. As-is audit — rami di uscita correnti

Mappa ricostruita dal codice (`EVIDENZA ALEMBIC`, riferimenti `file:line`) e dai documenti 02/04. Distinguo **codice corrente** / **config-runtime effettivo** / **evidenza storica** / **decisione futura** dove c'è conflitto.

### 2.1 I cinque eventi del §0 confusi in un solo ramo

`EVIDENZA ALEMBIC`: il ranker non emette HOLD/SELL; produce target weights. Il portfolio orchestrator vende integralmente quando il simbolo scompare dal target aggregato. Questo realizza, senza distinguerli, i cinque eventi del prompt §0:

| evento §0 | meccanismo che lo realizza oggi | statuto |
|---|---|---|
| 1 tesi smentita | contro-segnale `score < soglia` (force-sell) | **razionale ma mal specificato** |
| 2 segnale scaduto/non ripetuto | `max_signal_age` 4h + FIX-D riammissione + `expired` | semantica ambigua |
| 3 altro titolo occupa lo slot | rank turnover → peso zero | razionale ma non etichettato come replacement |
| 4 dato filtrato/perso | `below_entry_gate`, `entry_freshness_filtered`, `fallback_filtered` | difetto di pipeline travestito da exit |
| — non mappato | `unknown` (STALE_PRESERVED riammesso ma peso zero) | **difetto di osservabilità** |

**(Q1)** La policy corrente è in parte un effetto collaterale del ranker: i rami 3 (replacement) e 4 (difetto pipeline) non sono exit economiche. Sono razionali il ramo 1 (contro-segnale) e il time-exit implicito (freshness); sono difetti di semantica/osservabilità i rami 2-ambiguo e `unknown`. L'exit classification (`exit_classification.py:62-69`) mappa `FRESH→whipsaw`, `STALE_PRESERVED→unknown`, `STALE_DROPPED→expired`: la ragione `unknown` dichiara esplicitamente che il meccanismo che ha azzerato il peso **non è noto** — un'ammissione onesta, ma significa che una frazione non trascurabile di uscite non è interpretabile economicamente.

### 2.2 Clock e freshness

`EVIDENZA ALEMBIC`:
- `max_signal_age_hours = 4` wall-clock (`src/strategies/s4/config.py:39`), confronto `generated_at` vs `now_utc` (`portfolio_scheduler.py:967-968`). Oggi è **driver d'uscita** (segnale oltre 4h → può cadere dal target → SELL).
- Ciclo portafoglio ogni 15 min.
- `min-hold` 90 min (`trading.yaml:154`); isteresi `exit_persistence_cycles: 2` (`:160`); stop e reversal **bypassano** entrambi (`yaml:159`, `scheduler:1637-1638`).
- `anti-whipsaw` S4 disponibile ma **disabilitato** (`s4_anti_whipsaw_damping_enabled: false`, `trading.yaml:223`; `confirm_cycles: 2`, `:224`). Se attivato si **somma** all'isteresi generica (~4 cicli/~60 min) e non la sostituisce.
- **Clock DAILY non applicato a S4**: `_REBALANCE_CLOCK_STRATEGIES = frozenset({"S1"})` (`portfolio_scheduler.py:413`) → S4 escluso; l'istanza viene ricreata e il target ricalcolato intraday a ogni ciclo.

> **Divergenza (finding, non risolta per supposizione).** 04 §2 dichiara «`rebalance_frequency` DAILY **applicata** (S4 entra in `_REBALANCE_CLOCK_STRATEGIES`)». Il **codice corrente** non lo fa: è una **decisione futura** non ancora implementata. Eseguire lo shadow sul codice attuale significa misurare un clock 15-min, non DAILY. `NON DECIDIBILE` se il deploy runtime abbia già la patch: da verificare su env/log broker prima del batch.

### 2.3 Contro-segnale (la divergenza centrale)

`EVIDENZA ALEMBIC`:
- Default codice: `score < -0,20` (`src/config.py:267-271`, env `SENTIMENT_REVERSAL_EXIT_THRESHOLD`, **non in `trading.yaml`**). Freschezza max 60 min (`config.py:275-279`). Fallback FinBERT **esclusi** (`scheduler:4226-4227`). Cooldown re-entry 2h.
- Documento operativo: `-0,35`. Pre-registrazione 04: `<= -0,30`.

> **Divergenza (finding).** Tre valori: codice −0,20 / ops −0,35 / pre-reg −0,30. È la **stessa classe di errore E1/E3** per cui 04 ritira #179 («il criterio dichiarato ≠ quello misurato»): lo shadow eseguito sul default codice uscirebbe a −0,20, non a −0,30. **Da chiudere prima del batch shadow** impostando esplicitamente un solo valore (config/runtime), e registrandolo. `NON DECIDIBILE` quale sia quello effettivamente deployato: verificare env e log ordini.

### 2.4 Stop, take-profit, risk di portafoglio

`EVIDENZA ALEMBIC`:
- **Stop sintetico disabilitato**: `risk.stop_loss = 0.0` (`trading.yaml:182`, mode `fixed`). Il gate FIX-C (`scheduler:1385`) ritorna `{}` quando `stop_loss<=0`. Il candidato vol-scaled S4 (`k=2.0, floor=0.03, cap=0.08`) è `stop_shadow_enabled: true` ma **solo loggato, non applicato**.
- **`d_hard` broker GTC abilitato di default**: `ALPACA_FRACTIONAL_STOP_ENABLED` default `true` (`config.py:234-236`), promosso da shadow a enforcement reale il 2026-07-16 (#62/#63). Banda 12–20% (`trading.yaml:202-206`: `multiplier=1.5`, `sigma_multiple=5.0`, `floor_pct=0.12`, `cap_pct=0.20`). Calcolo `clip(max(1.5·d_init, 5.0·σ_eff), 0.12, 0.20)` (`stop_policy.py:252-265`). Floor di azioni intere GTC (`fractional_stop_orders.py:69-71`); **residuo sotto 1 azione non protetto**. Gamba SL della bracket usa `d_hard` (`scheduler:3998-4009`).
- **Take-profit +6%**: `ALPACA_TAKE_PROFIT_PCT=0.06` (`config.py:223-225`), bracket `enabled` default true. Gating: `if ALPACA_BRACKET_ENABLED and price>0 and not is_fractionable` (`scheduler:3995`) → **solo BUY non-fractionable** ricevono TP/SL broker. Le posizioni fractionable **non ricevono** né TP né SL broker.
- Alert perdita non protetta 15% (non è un ordine).
- **Risk di portafoglio, non per-trade**: VIX≥40 / ΔVIX≥30% = hard breaker (`drift.py:177`) → blocca auto-apply dei pesi ensemble + alert critico; **non** blocca nuovi ingressi S4, **non** liquida. Drawdown 5% (`trading.yaml:166`) → kill-switch 18h (`scheduler:2155-2169`) → blocca nuovi ingressi + cancella pending; **non** vende posizioni esistenti. `regime_mult` ×0,2 a VIX≥40 (riduzione sizing).

> **Divergenza (finding).** Il commento YAML descrive `d_hard` come «shadow telemetry». Il **codice corrente** lo ha promosso a stop broker GTC reale (default `true`, #62/#63). Il commento è **stale**. `NON DECIDIBILE` la copertura reale runtime: verificare ordini broker e residui non protetti. `d_hard` è largo (12–20%) e coerente con la teoria dello stop ritardato/largo (§3): è da conservare come catastrophe stop, non da restringere.

### 2.5 Failure mode

`EVIDENZA ALEMBIC` (02 §2.4): nelle 9 sedute 2026-08-06→08-12, 8 round trip perdenti su 9 (netto −89,12 $), **nessuna** uscita da contro-segnale (`below_entry_gate` ×4, `unknown`/QS-07/FIX-D ×3, `expired` ×1, `whipsaw` ×1). Tenuta mediana 1h45; 6/9 uscite a 1h45 o 4h15 = scadenze del software, non dell'alpha. Segnali sovrascrivibili (ultimo articolo vince); errori di entity resolution; ingressi tardivi (64° percentile mediano del range, 70–84% del movimento già fatto al primo segnale); ~metà watchlist senza articoli in una giornata.

---

## 3. Literature evidence table

Una riga per fonte primaria. Trasferibilità distingue long-short vs long-only (la maggior parte delle fonti è long-short: **non si trasferisce automaticamente alla gamba long**). **Correzioni bibliografiche** rilevate e verificate: Chan 2003, Tetlock 2011, Tetlock 2008, Jiang 2021 (terzo autore), Cederburg 2020 (autori/titolo), DeMiguel 2024 (3 autori), Bajgrowicz–Scaillet 2012 (titolo), Broadie–Glasserman–Kou (forma esatta), Vaicenavicius (titolo), Mei–DeMiguel–Nogales (titolo), DeMiguel–Garlappi–Nogales–Uppal 2009 (quarto autore). Dettagli in §10.

### 3.1 Decadimento dell'informazione da news (famiglia 1, 2)

| fonte | universo / lato | uscita misurata | effetto | trasferibilità S4 |
|---|---|---|---|---|
| **Lopez-Lira & Tang 2023** (arXiv:2304.07619) | USA, long-short, **LLM (ChatGPT)**, 134k headline ott21–dic23 | rendimento t…t+4 | prevedibilità su ~2 giorni (38 bps a t=0 + 20 bps a t+1; **t+2/t+3/t+4 non significativi**); Sharpe declina 6,54→2,33 nel tempo `snippet` | **ALTA** — unica fonte LLM-based, la più vicina a S4; **long-short** (legge long-only parziale) |
| **Heston & Sinha 2016/17** (FEDS 2016-048; FAJ 73(3):67–83, DOI 10.2469/faj.v73.n3.3) | >900k news, long-short | orizzonte daily vs weekly | «daily news predicts stock returns for only 1 to 2 days»; positive incorporate ~1 sett, negative fino a un trimestre `abstract` | **ALTA** per l'orizzonte; **long-short** (la coda negativa è short-leg) |
| **Tetlock 2008** (*More Than Words*, JF 63(3):1437–1467, DOI 10.1111/j.1540-6261.2008.01362.x) | S&P500, firm-specific, long-short | underreaction 1 giorno a negative words | prevedibilità **massima per news che focalizzano sui fondamentali**; sotto-reazione «breve» (~1 giorno) `abstract` | **ALTA** — diretto su news fundamental long-only; supporta orizzonte corto |
| **Jiang, Li, Wang 2021** (JFE 141(2):573–599, DOI 10.1016/j.jfineco.2021.04.003; 3° aut. **Haitao Wang**) | USA, high-freq, long-short, holding **5 giorni** | drift post-news in **continuazione** | «drift in the same direction… without reversals»; spread cumulativo cresce oltre D+2 (working paper) `abstract+snippet` | **MEDIA** — drift in continuazione suggerisce che D+2 **lascia alpha** nei giorni 3–5 su news fresca; **long-short** |
| **Tetlock 2011** (*All the News That's Fit to **Reprint***, RFS 24(5):1481–1512, DOI 10.1093/rfs/hhq141) | stale news, long-short | reversal t+2→t+5 | giorno di news stale **predice negativamente** la settimana successiva; investitori retail `abstract` | **MEDIA-ALTA** — su segnale stale D+2 è **già troppo lungo** (reversale inizia a t+2) |
| **Tetlock 2007** (JF 62(3):1139–1168, DOI 10.1111/j.1540-6261.2007.01232.x) | WSJ editoriale, **mercato**, daily | reversione entro la settimana | pessimismo → pressione D+1 poi reversione a fondamentali `abstract` | **BASSA-MEDIA** — sentiment editoriale di mercato, non fundamental long-only |
| **Chan 2003** (*Stock Price Reaction to News and No-News*, JFE 70(2):223–260, DOI 10.1016/S0304-405X(03)00146-6) | headline, **mensile**, long-short | drift post-news mensile | drift dopo bad news; reversal dopo shock senza news; titoli piccoli/illiquidi `abstract` | **BASSA** per D+2 (orizzonte mensile); principio qualitativo: news genuine→drift |
| **Boudoukh et al. 2019** (RFS 32(3):992–1033, DOI 10.1093/rfs/hhy083) | firm-specific news | vol overnight vs intraday | news spiega 49,6% vol idiosincratica overnight vs 12,4% intraday `abstract` | **MEDIA** — incorporazione concentrata overnight: timing di entry/exit e misura dei rendimenti |
| **Aksoy-Yurdagul et al. 2026** (Econ. Letters 260(C), DOI 10.1016/j.econlet.2025.112803) | RavenPack, 2000–23 | orizzonte discrimina continuation vs reversal | sentiment momentum breve → rendimenti anomali positivi; persistenza lunga → reversali `abstract` | **MEDIA** — l'orizzonte **decide** se si ha continuation o reversal |
| **Glasserman, Li, Mamaysky 2023** (JFQA 60(1):258–294, DOI 10.1017/S0022109023001369) | replica Tetlock 2008 | variazione temporale underreaction | underreaction **dimezzata** 1996-2000 vs 2015-18 `abstract` | **MEDIA** — base empirica dell'underreaction **in erosione** |
| **PEAD-decay** (Martineau 2021; Griffin et al. 2026, JAAF DOI 10.1177/0148558X261439734) | post-earnings | declino drift | PEAD ~azzerato post-2017; causa = declino persistenza SUE `snippet` | **MEDIA** — limita la fiducia in drift long-horizon da news |

**Sintesi (Q2).** `[EVIDENZA ESTERNA]` La fonte più trasferibile (Lopez-Lira–Tang, LLM-based) mostra edge su ~2 giorni (signal-day + t+1), non oltre; Heston-Sinha 1–2 giorni; Tetlock 2008 ~1 giorno. **D+2 è dentro la finestra, al suo margine conservativo.** L'edge è **asimmetrico e fragile**: news fresca fondamentale drifta in continuazione oltre D+2 (Jiang, 5 giorni) → D+2 può **lasciare alpha**; news stale reverte da t+2 (Tetlock 2011) → D+2 può essere **troppo lungo**; l'underreaction è **in erosione** (Glasserman dimezzato, PEAD-decay). **Trasferibilità long-only parziale**: la coda lunga (negativa, lenta) è short-leg; S4 cattura solo l'incorporazione positiva rapida (1–2 giorni). `INFERENZA`: questo **supporta un orizzonto corto** (D+1/D+2) ma **cappa strutturalmente** l'edge di S4 sotto quanto suggerito dalla letteratura long-short.

### 3.2 Stop, trailing, barriere (famiglie 4, 5)

| fonte | risultato | trasferibilità S4 |
|---|---|---|
| **Kaminski & Lo** (SSRN 968338) | sotto random walk lo stop riduce sempre il rendimento atteso; aggiunge valore solo con momentum (ρ ≥ Sharpe); costi erodono | **MEDIA** — S4 ha momentum (drift news) → stop può aggiungere valore; stop **largo/ritardato** > stretto/immediato |
| **Lo & Remorov 2017** (Fin. Mkts 26:3-35, DOI 10.1016/j.finmar.2017.02.003) | stop stretti su azioni USA sottoperformano dopo costi salvo autocorr. ≥ ~10%; stop ritardati > immediati | **MEDIA** — giustifica il `d_hard` largo 12–20%; boccia la riproposizione dello stop 2% (consistente col replay Alembic) |
| **Broadie, Glasserman, Kou 1997** (Math. Finance 7(2):107-133, DOI 10.1111/1467-9965.00035) | monitoring discreto vs continuo: misclassifica hit di `exp(±β·σ·√Δt)`, **β≈0,5826** | **MEDIA** — S4 monitora a 15-min + close D+2 (discreto); bias piccolo a 15-min, alto al close puntuale |
| **López de Prado 2018** (JPM 44(6):120-133, DOI 10.3905/jpm.2018.44.6.120) | **Triple Barrier**: stop/TP/time sono **congiunti**, non indipendenti; etichetta quale barriera tocca prima; purging+embargo anti-leakage | **ALTA** — il design «time primario + contro + stop come eccezioni» è un'**approssimazione di ordinamento**, non un first-passage congiunto |
| **Leung & Li 2015** (IJTAF 18(3), DOI 10.1142/S021902491550020X) | stop più alto → TP ottimo più basso; le barriere si contendono lo stesso trade | **MEDIA** — ottimizzare stop/TP/time separatamente è subottimale |
| **Leung & Zhang 2017** (arXiv:1701.03960) | trailing stop: optimal stopping su OU | **BASSA** — mean-reversion (pairs), non news-momentum |
| **Dai, Marshall, Nguyen, Visaltanachoti 2021** (Int. Rev. Finance 21(4):1334-1352, DOI 10.1111/irfi.12328) | trailing stop riduce rischio sotto regime-switching `abstract` | **MEDIA** — contesto regime; non primeggia sul long-only news |
| **Veiga & Shelton 2024** (SSRN 4947910 / Risk.net) | 4 esiti mutuamente esclusi (stop/TP/offset/liquidazione) closed-form; le probabilità **non sono indipendenti** | **MEDIA** — il modello competing-risks per barriere congiunte |

**(Q5)** Il replay Alembic che boccia lo stop 2% (245 trade, `no_protective` > stop fisso 2% e vol-scaled nel suo OOS) **consente** di concludere che uno stop stretto su rumore, su questa miscela di strategie, non aiuta — coerente con Kaminski-Lo/Lo-Remorov sotto random-walk-like. **Non** consente di concludere che ogni stop è inutile: non testa stop larghi di catastrofe, trailing post-MFE, né stop condizionati al regime. Il `d_hard` 12–20% esistente è **al di fuori** di ciò che il replay ha bocciato.

### 3.3 Regime, signal-exit, optimal stopping (famiglie 3, 6, 7, 8, 10)

| fonte | risultato | trasferibilità S4 |
|---|---|---|
| **Moreira & Muir 2017** (JF 72(4):1611-1644, DOI 10.1111/jofi.12513) | vol-managed MKT: Sharpe +25%, alpha 4,86%; vol persiste, **non** predice rendimenti → de-risking di portafoglio | **MEDIA** — il gate VIX è de-risking **di portafoglio** (già presente), non un exit per-trade |
| **Barroso & Santa-Clara 2015** (JFE 116(1):111-120, DOI 10.1016/j.jfineco.2014.11.010) | target-vol momentum: Sharpe 0,53→0,97, kurtosi 18,2→2,7, maxDD −96,7%→−45,2% | **MEDIA** — vol-targeting riduce coda; per-trade debole |
| **Cederburg, O'Doherty, Wang, Yan 2020** (JFE 138(1):95-117, DOI 10.1016/j.jfineco.2020.04.015) | 103 strategie: managed vince 53/103 (coin flip); solo 8 significative; 72/103 underperform OOS su CER `abstract` | **MEDIA** — vol-managed **per-trade è debole/instabile OOS**; conferma: regime = portafoglio |
| **DeMiguel, Martín-Utrera, Uppal 2024** (JF 79(6):3859-3891, DOI 10.1111/jofi.13395; **3 autori**) | multifactor condizionale: +13% Sharpe OOS netto; prezzo di rischio ↓ con vol `abstract` | **MEDIA** — condizionale al regime; fattoriale, non per-trade |
| **Bajgrowicz & Scaillet 2012** (JFE 106(3):473-491, DOI 10.1016/j.jfineco.2012.06.001) | FDR + persistenza + costi su DJIA 1897-2011: valore economico annullato; impossibile selezionare ex-ante il futuro migliore `abstract` | **ALTA** — l'ex-post tuning della soglia del contro-segnale è una **falsa scoperta** |
| **Brock, Lakonishok, LeBaron 1992** (JF 47(5):1731-1764, DOI 10.1111/j.1540-6261.1992.tb04681.x) | MA/range-break DJIA 1897-1986: buy>sell | **BASSA** — tecnico, non news; contesto per data-snooping |
| **Ekström & Vaicenavicius 2016** (SIAM JFM 7(1):357-381, arXiv:1509.00686) | liquidation sotto drift incognito: exit = **primo passaggio della media posteriore del drift sotto frontiera monotona**; fino a ~10-15% vs naive binaria `full-text` | **ALTA** — l'uscita di S4 è «è decaduto l'edge?»; la regola ottima dipende dal **credo posteriore aggiornato**, non dal P&L realizzato |
| **Vaicenavicius 2020** (Appl. Math. Optim. 81:757-784, DOI 10.1007/s00245-018-9518-5, arXiv:1701.08579) | optimal stopping 4D (tempo, media posteriore, *effective learning time*, stato vol); frontiera **crescente nella volatilità** → esce **più tardi** in high-vol `full-text` | **ALTA** — la soglia di uscita deve essere **state-dependent**: banda più larga in regimi high-VIX (apprendimento più lento, più rumore) |
| **Gârleanu & Pedersen 2013** (JF 68(6):2309-2340, DOI 10.1111/jofi.12080) | «aim in front of target» + trade parziale verso aim; Markowitz net −9,84 vs dynamic net 0,58 (~20% > statico) `full-text` | **MEDIA** — de-risking graduale qualitativamente supportato; **quantitativamente inapplicabile** (costi quadrat. impact) |
| **Collin-Dufresne, Daniel, Sağlam 2020** (JFE 136(2):379-406, DOI 10.1016/j.jfineco.2019.09.011) | modellare price-impact è economicamente significativo **solo per AUM ≳ 100M $**; per portafogli piccoli la strategia myopic è quasi ottima `abstract+snippet` | **ALTA** — **S4 non ha capacity exit**: impatto ~0; resta spread/fee fisso |
| **Davis & Norman 1990** (MOR 15(4):676-713, DOI 10.1287/moor.15.4.676) | no-trade wedge; ottimo = local times al bordo; wedge → Merton line per costi→0 `abstract` | **BASSA-MEDIA** — origine del concetto di banda; cuneo nello spazio (bank,stock), non (rank,score) |
| **Mei, DeMiguel, Nogales 2016** (JBF 69:108-120, DOI 10.1016/j.jbankfin.2016.04.002; titolo "*Multiple Risky Assets*") | costi proporzionali → no-trade parallelepipedo + **buy-and-hold** ottimo; perdita da miopia 60,5% / da ignorare costi 49,3% (caso base ~1B $) `full-text` | **MEDIA** — buy-and-hold supporta slot-sticky; **i numeri 49-60% sono per investitori grandi, non S4** |
| **Guasoni & Muhle-Karbe** (arXiv:1207.7330) | banda no-trade semi-ampiezza `μ/(γσ²) ± […]^(1/3)·ε^(1/3)`; welfare loss `O(ε^(2/3))`; banda «sorprendentemente larga» ma **piccolo valore di sintonizzarla** `full-text` | **MEDIA** — isteresi qualitativamente giustificata; la sintonia fine ha poco valore economico |
| **DeMiguel, Garlappi, Nogales, Uppal 2009** (Mgmt Sci 55(5):798-812, DOI 10.1287/mnsc.1080.0986; 4° aut. **Garlappi**) | norm-constrained: Sharpe ↑ ma turnover ↑; non modella costi | **BASSA** — contesto: migliorare Sharpe senza guardare turnover ↑ costi netti |

**(Q4)** `[EVIDENZA ESTERNA]` L'evidenza per l'uscita su contro-segnale è la **falsificazione della tesi**, non un P&L stop. La regola teoricamente fondata (Ekström-Vaicenavicius, Vaicenavicius 2020) è: esci quando il **credo posteriore aggiornato sulla validità del segnale d'ingresso** scende sotto una frontiera, con **persistenza** — non quando un singolo score rumoroso supera una soglia puntuale. Il contro-segnale **deve usare lo stesso modello dell'ingresso** (evita look-ahead da un secondo modello tarato ex post), soglia **asimmetrica e più stretta** dell'ingresso (i costi rendono l'overtrading autodistruttivo), e la soglia **pre-registrata ex ante**, non fittata sul campione (Bajgrowicz-Scaillet). `IPOTESI`: aggregare i segnali successivi in un posteriore (Wonham/filtering-like) con persistenza ≥2 osservazioni.

**(Q9)** Strategie consolidate **non adottate** e realmente trasferibili: (a) **no-trade band state-dependent** sul VIX (Vaicenavicius 2020) — la banda di non-uscita si allarga in high-vol; (b) **de-risking guidato dal credo** (Ekström-Vaicenavicius) — alternativa al full-close binario; (c) **triple-barrier con purging** (López de Prado) — per confrontare exit in CV senza leakage. **Non trasferibili**: trailing su OU mean-reversion (Leung-Zhang), capacity exit (Collin-Dufresne: S4 << 100M $), vol-managed per-trade (Cederburg).

### 3.4 Validazione (famiglia 9)

| fonte | risultato | trasferibilità S4 |
|---|---|---|
| **White 2000** (Econometrica 68(5):1097-1126, DOI 10.1111/1468-0262.00152) | BRC: S&P500, 3654 modelli; naive p 0,0036 → BRC p 0,2040; data snooping `abstract` | **ALTA** — la selezione del «migliore» exit è data snooping |
| **Hansen 2005** (JBES 23(4):365-380, DOI 10.1198/073500105000000063) | **SPA_c** (studentizzato + recentering condizionale); BRC asintoticamente biasato, policy inferiori erodono la potenza a zero `abstract` | **ALTA** — **usare SPA_c, non BRC puro** (exit policy con varianze eterogenee) |
| **Sullivan, Timmermann, White 1999** (JF 54(5):1647-1691, DOI 10.1111/0022-1082.00163) | 7846 regole DJIA 1897-1996; OOS 1987-96 miglior regola NON batte benchmark (p≈0,12) `abstract` | **ALTA** — edge in-sample non persiste OOS; serve walk-forward |
| **Bailey & López de Prado 2014** (JPM 40(5):94-107, DOI 10.3905/jpm.2014.40.5.094) | DSR/MinTRL: SR 0,95 → ~3 anni daily per rifiutare H₀; correzione per N trial `abstract` | **MEDIA-ALTA** — bound conservativo per lunghezza minima track-record OOS |
| **Bailey, Borwein, López de Prado, Zhu 2017** (JCF 20(4):39-69, DOI 10.21314/JCF.2016.322) | PBO/CSCV: prob che il vincitore IS sia pessimo OOS; su rumore PBO≈0,5; **non distingue «nessun edge» da «tutte simili»** `full-text` | **MEDIA** — diagnostico, non obiettivo di ottimizzazione; richiede disclosure di tutti i trial |
| **Romano & Wolf 2005** (Econometrica 73(4):1237-1282, DOI 10.1111/j.1468-0262.2005.00615.x) | stepwise: più potente del BRC; identifica tutte le policy con edge, non solo la prima `abstract` | **ALTA** — se un cluster di exit ha edge reale |
| **Harvey, Liu, Zhu 2016** (RFS 29(1):5-68, DOI 10.1093/rfs/hhv059) | 316 fattori; nuovo fattore oggi richiede **t > 3,0** (non 2,0); BHY/FDR come alternativa `full-text` | **MEDIA** — principio: più test = soglia più alta per la «migliore» exit |
| **Ding & Sun 2023** (J. Asset Mgmt 24(1):1-15, DOI 10.1057/s41260-022-00295-9) | `IR = IC̄/√(σ²_IC + σ²_e/N)`; per **IC=0,05** servono ~20 periodi cross-sectionali (N~1000) per t>2; **N ∝ 1/IC²** `full-text` | **ALTA** — power analysis: per IC=0,05 pochi decenni di ticker S4 → servono **mesi** per policy |
| **Hjalmarsson 2008** (Fin. Res. Letters 5(2):104-117, DOI 10.1016/j.frl.2007.12.005) | overlapping: t-stat / **√q** (q=orizzonte); NW HAC gravemente biased downward su orizzonti lunghi `full-text` | **ALTA** — forward return D+2/D+3/D+5 sovrapposti: correggere per √q |
| **Britten-Jones, Neuberger, Nolte 2011** (JBFA 38(5-6):657-683, DOI 10.1111/j.1468-5957.2011.02244.x) | trasformazione dei regressori → regression overlapping equivalente non-overlapping; meglio di NW in campioni finiti `full-text` | **ALTA** — alternativa robusta a NW |
| **Conley, Gonçalves, Hansen 2018** (J. Acct. Res. 56(4):1139-1203, DOI 10.1111/1475-679X.12219) | cluster bootstrap per **giorno/evento** (non per trade); block length = orizzonte `abstract` | **ALTA** — trade stesso giorno/stesso ticker NON indipendenti |
| **López de Prado 2018** (JPM 44(6):120-133, DOI 10.3905/jpm.2018.44.6.120) | triple-barrier (competing-risks labeling) + meta-labeling + purging/embargo + CPCV `full-text` | **ALTA** — barriere congiunte, anti-leakage CV |

---

## 4. Strategy catalog (E0–E9)

Per ogni policy: razionale, vantaggi, failure mode, complessità, trial cost, **condizione di falsificazione**.

**E0 — uscita corrente a target weight zero** `[EVIDENZA ALEMBIC]`. Baseline as-is. Razionale: nessuno (è il comportamento emergente). Failure: confonde 5 eventi (§2.1); `unknown` non interpretabile; tenuta 1h45 = proprietà del software. Complessità 0, trial cost 0. *Falsificazione*: è sempre il benchmark; non si «falsifica», si batte.

**E1 — D+2 time-stop + contro-segnale + catastrophe stop** (candidata 04) `[IPOTESI/INFERENZA]`. Razionale: time-stop primario allineato alla decadenza 1–2g (Lopez-Lira-Tang, Heston-Sinha); contro-segnale falsifica la tesi; catastrophe stop largo protegge la coda. Vantaggi: parsimoniosa, un solo orizzonte primario, congelabile. Failure: (i) contro-segnale a soglia puntuale senza persistenza → overtrading su rumore (Davis-Norman, Guasoni-Muhle-Karbe); (ii) soglia divergente −0,20/−0,30/−0,35 → lo shadow non misura ciò che 04 dichiara; (iii) clock DAILY non applicato a S4 → shadow misura clock 15-min; (iv) barriere trattate come eccezioni ordinate, non first-passage congiunto (López de Prado, Leung-Li). Complessità media, trial cost 1. *Falsificazione*: al gate congiunto su n pulito, E1 non batte E5 (time+catastrophe senza contro) su excess return netto, oppure il contro-segnale genera false-stop rate > beneficio.

**E1-mod — E1 con contro-segnale posteriore+persistenza e banda no-trade** (raccomandata) `[INFERENZA]`. Come E1, ma: (a) contro-segnale = posteriore aggregato sulla validità della tesi (Ekström-Vaicenavicius), persistenza ≥2 cicli, **una sola soglia pre-registrata ex ante** (Bajgrowicz-Scaillet); (b) banda no-trade state-dependent sul VIX, più larga in high-vol (Vaicenavicius 2020); (c) soglia e clock DAILY chiusi prima del batch. Vantaggi: risolve le due divergenze codice/config; allinea il contro-segnale alla teoria dell'optimal stopping; riduce overtrading. Failure: complessità del posteriore (ma approssimabile con una media mobile dello score con banda, senza un modello bayesiano completo); richiede pre-registrazione della soglia scelta senza peeking. Complessità media-alta, trial cost 1 (sostituisce E1). *Falsificazione*: E1-mod non batte E5 sul gate, oppure il posteriore non è stimabile con abbastanza osservazioni per ticker (news sparse → posteriore dominato dal prior).

**E2 — D+1 e D+3** `[DIAGNOSTICA]`. Razionale: mappare la term structure. `[EVIDENZA ESTERNA]` La fonte più trasferibile (Lopez-Lira-Tang) mostra edge concentrato su signal-day+t+1, non oltre → D+1 potrebbe catturare lo stesso edge con meno esposizione; D+3 è fuori finestra. Failure: **non sono due nuovi vincitori da scegliere ex post** (prompt §4) — sono diagnostici; usarli per scegliere dopo aver visto i risultati = falsa scoperta (STW 1999). Complessità bassa, trial cost 2 (diagnostici, non confirmatori). *Falsificazione*: non si «promuove» E2; si usa per fissare l'unico orizzonte confirmatorio (già D+2) o, se la diagnostica è univoca e pre-registrata, per giustificare un cambio a D+1 **prima** del segmento confirmatorio.

**E3 — counter-signal only con massimo holding dichiarato** `[DIAGNOSTICA]`. Razionale: isola il valore del time-stop. Se E3 (senza time-stop) ≈ E1, il time-stop non aggiunge. `[EVIDENZA ESTERNA]` Il time-stop è l'elemento più supportato (decadenza 1–2g), quindi mi attendo E1 > E3; ma è il controllo che lo dimostra. Failure: senza time-stop, le posizioni possono trascinarsse oltre la finestra di edge. Complessità bassa, trial cost 1 (diagnostica). *Falsificazione*: come E1; diagnostica per la domanda «il time-stop guadagna il suo posto?».

**E4 — time-stop + uscita su segnale aggregato/decaduto** `[DIAGNOSTICA]`. Razionale: separa l'exit design dal churn dell'ultimo articolo (l'ultimo articolo vince oggi → uscite su rumore). `[EVIDENZA ALEMBIC]` Segnali frequenti sullo stesso ticker si sovrascrivono. Aggregare (es. media/decadimento dei segnali del giorno) riduce il noise exit. Failure: l'aggregazione introduce look-ahead se usa articoli non point-in-time; definire l'aggregazione ex ante è non banale. Complessità media, trial cost 1 (diagnostica). *Falsificazione*: E4 non batte E1-mod, oppure l'aggregazione non è ricostruibile point-in-time.

**E5 — time-stop + wide catastrophe stop, senza contro-segnale** `[CANDIDATA confirmatoria]`. Razionale: il massimo parsimonioso che conserva l'elemento più supportato (time-stop D+2) + la protezione di coda teoricamente giustificata (stop largo, Kaminski-Lo/Lo-Remorov) **senza** il contro-segnale — che è l'elemento meno supportato come implementato. `[EVIDENZA ESTERNA]` Sotto random-walk-like, rimuovere un trigger rumoroso può solo aiutare. Vantaggi: isola il valore del contro-segnale (E1-mod vs E5); se E1-mod ≈ E5, il contro-segnale non guadagna il suo posto e va scartato. Failure: perde le uscite su vero contro-segnale informativo. Complessità bassa, trial cost 1. *Falsificazione*: E5 batte E1-mod → il contro-segnale è noise; E1-mod batte E5 in modo robusto (paired, gate) → il contro-segnale guadagna il suo posto.

**E6 — trailing attivato solo dopo MFE predefinita** `[RESPINTA in confirmatorio, diagnostica opzionale]`. Razionale: proteggere i vincitori senza troncarli subito. `[EVIDENZA ESTERNA]` In news-momentum long-only, **pochi grandi vincitori pagano la strategia** (asimmetria della coda destra); trailing/TP fissi rischiano di troncare proprio quelli (prompt §3.5; Lopez-Lira-Tang mostra cattura necessaria su ~2 giorni). Failure: trailing post-MFE su orizzonti corti (1–2g) ha poco spazio per manifestare MFE prima del time-stop; attivarlo tardi ≈ non si attiva. Complessità media, trial cost 1. *Falsificazione*: E6 tronca più vincitori di quanti protegga → skewness netta peggiore di E1-mod a pari return. `(Q6)` Non c'è evidenza robusta per TP/trailing in news-momentum long-only a orizzonte 1–2g; il rischio di troncare la coda destra è reale. Respinta dal confirmatorio.

**E7 — policy event-type/segno-specifica** `[RESPINTA per numerosità]`. Razionale: la letteratura distingue positive/negative, fundamental/editorial, scheduled/unscheduled (Tetlock 2008, Heston-Sinha). `(Q7)` Una policy condizionata è teoricamente attraente ma **richiede numerosità che S4 non ha** (Ding-Sun: N ∝ 1/IC² per cella; con poche decine di ticker e IC 0,05, ogni sottogruppo è non decidibile). Failure: overfitting per sottogruppo (Harvey-Liu-Zhu: più test = soglia più alta). Complessità alta, trial cost alto (moltiplica le celle). *Falsificazione*: già falsificata ex ante dalla power analysis — `INCONCLUSIVE` garantito. Respinta.

**E8 — replacement exit basata su costo-opportunità** `[DIAGNOSTICA/RESPINTA come exit separata]`. Razionale: vendi perché un nuovo candidato ha edge atteso superiore (families 8). `[EVIDENZA ESTERNA]` Collin-Dufresne-Daniel-Sağlam 2020: per AUM << 100M $ la strategia myopic è quasi ottima e **non esiste capacity exit**; S4 non muove i prezzi. `(Q8)` Il replacement **va separato** dalla falsificazione della tesi (GP separa target portfolio da trading policy): sostituire A con B sul rank **non è** smentire la tesi di A. Nel design, il replacement è già il ramo 3 (rank turnover) di §2.1; tenerlo separato dal contro-segnale è corretto. Failure: mascherare il replacement come «exit di tesi» confonde le metriche. Complessità bassa (già presente), trial cost 0. *Falsificazione*: non serve una policy separata; serve **etichettare** il replacement come tale nei reason code (oggi è `below_entry_gate`/`unknown`). Diagnostica di osservabilità, non exit candidata.

**E9 — de-risking parziale / posterior expected-edge exit** `[DIAGNOSTICA]`. Razionale: alternativa al full-close binario; aggiusta parzialmente verso il target perché il credo sull'edge è incerto (Ekström-Vaicenavicius; GP «trade partially»). `[EVIDENZA ESTERNA]` La giustificazione quantitativa di GP (costi quadrat. impact) è **inapplicabile** a S4 (Collin-Dufresne); la giustificazione corretta è l'**incertezza sul credo** (Vaicenavicius). Vantaggi: teoricamente la famiglia più fondata per S4. Failure: complessità implementativa (poster stato-dipendente); per size ~2% il de-risking graduale ha poco spazio (slot fissi, non frazionabili in step continui); con slot 1/5 fissi, il «parziale» è 0 o 1 slot. Complessità alta, trial cost 1. *Falsificazione*: E9 non è implementabile in modo pulito su slot discreti fissi → E1-mod (full-close + banda) è la sua approssimazione trattabile. Diagnostica: se l'infrastruttura permite sizing continuo in futuro, E9 diventa la candidata di seconda generazione; oggi `NON DECIDIBILE` e non prioritaria.

**(Q3)** Il **semplice silenzio della fonte** non deve mai chiudere una posizione di per sé. `[EVIDENZA ESTERNA]` Il silenzio non è informazione nuova che smentisce la tesi; è assenza di informazione. `INFERENZA`: il silenzio può giustificare un **time-stop** (l'orizzonte dell'edge è terminato, clock wall/market coerente con la decadenza 1–2g), non un thesis-exit. `[EVIDENZA ALEMBIC]` FIX-D tenta proprio di trattare il silenzio come «non-uscita» riammettendo il vecchio positivo; ma poi il peso va a zero lo stesso via `unknown` → il silenzio diventa economicamente un SELL senza smentita. La correzione è: il silenzio **non genera** exit; l'exit la genera solo il time-stop (o un contro-segnale esplicito). Il clock deve essere **market-time/orizzonte-della-tesi**, non un artefatto del ciclo 15-min.

---

## 5. Shortlist

**Confirmatorio (3):**
1. **E0** — baseline as-is (target weight zero). Sempre presente.
2. **E1-mod** — D+2 time-stop + contro-segnale posteriore+persistenza (soglia unica pre-reg.) + catastrophe stop `d_hard` 12–20%. **Primaria.**
3. **E5** — D+2 time-stop + catastrophe stop, **senza contro-segnale**. Controllo parsimonioso: isola il valore del contro-segnale.

Il confronto chiave è **E1-mod vs E5** (il contro-segnale guadagna il suo posto?) e **entrambi vs E0** (l'exit design batte il behaviour emergente?). `(Q7)` Policy unica parsimoniosa scelta su numerosità: la condizionata E7 è respinta ex ante dalla power analysis.

**Diagnostico (non confirmatorio):** E2 (term structure D+1/D+3 — per *fissare* o eventualmente spostare l'orizzonte primario **prima** del segmento confirmatorio, mai per scegliere ex post), E3 (isola il time-stop), E4 (aggregato anti-churn), E9 (de-risking posteriore — teoria migliore, complessità non prioritaria).

**Respinto:** E6 (trailing/TP tronca la coda destra a orizzonte corto), E7 (numerità insufficiente), E8 (non esiste capacity exit per S4; è un problema di etichettatura dei reason code, non di policy).

---

## 6. Empirical protocol

Confronto **a ingressi congelati**: tutte le exit candidate ricevono gli stessi trade/intenti di ingresso, timestamp, sizing, prezzi eseguibili, collisioni S1, cost model. Il risultato deriva solo dall'uscita.

### 6.1 Ledger (§5.1)

`EVIDENZA ALEMBIC` + `IPOTESI`: event ledger point-in-time con `signal_id`, articolo/evento, ticker risolto, source, published/ingested/generated/decision time; score/confidence/modello/fallback/novelty e appartenenza reale articolo↔ticker; entry intent, fill eseguibile, size, collisione S1, costi/spread; barre intraday+daily con corporate actions (`adjustment="all"`, #192); MAE, MFE, tempo a MAE/MFE, gap overnight, vol e liquidità all'ingresso; ogni condizione di uscita candidata e prezzo eseguibile; post-exit drift a 1h/close/D+1/D+2/D+3/D+5; motivo di censura/dato mancante. **Nessun look-ahead**: novelty score, validazione ticker, event type calcolati post-trade non entrano senza versione point-in-time disponibile allora.

### 6.2 Prezzi e costi (§5.1, 04 §3)

`EVIDENZA ALEMBIC` (04): iniziale = fill shadow al primo prezzo RTH eseguibile dopo il decision timestamp, in assenza chiusura della barra 15-min successiva; finale = close D+2 total return con corporate actions. **Riportare separatamente** IC da prezzo-segnale e IC da prezzo eseguibile (la differenza = slippage strutturale, non nascosto nei costi espliciti). Costi conservativi: spread/fee realistici + slippage (l'ingresso tardivo suggerisce slippage > costi espliciti). `[EVIDENZA ESTERNA]` Collin-Dufresne: l'impatto di mercato è **trascurabile** per S4 — non modellarlo (sarebbe ottimistico al contrario: ingenera una complessità inutile).

### 6.3 Metriche (§5.2)

Rendimento, rischio, utilità economica **separati** (prompt §7). Minimo: P&L netto ed excess return vs E0 e benchmark equal-weight watchlist; paired trade-level delta sugli stessi ingressi; turnover, costi, slippage, capitale-giorni; expectancy, mediana, hit rate, profit factor, payoff win/loss; vol, downside deviation, VaR/ES con cautela, maxDD, drawdown duration; **skewness e contributo coda destra** (quanti grandi vincitori troncati — critico per E6); **false-stop rate** (uscita in perdita seguita da recupero entro l'orizzonte della tesi); giveback da MFE e perdita evitata vs MAE; diagnostica per event type/segno/ora/gap/liquidità/source/regime (**non** licenza per scegliere il sottogruppo migliore); overlap e valore incrementale vs S1.

### 6.4 Inferenza e anti-overfitting (§5.3) `[EVIDENZA ESTERNA]`

- **Test di selezione: Hansen SPA_c** (studentizzato + recentering condizionale), **non** BRC puro di White — il BRC è asintoticamente biasato e le exit policy chiaramente inferiori erodono la potenza a zero (Hansen 2005). SPA_c gestisce varianze eterogenee (stop tight = alta var, time-barrier larga = bassa). Complementare: Romano-Wolf stepwise se si vuole identificare tutte le exit con edge reale; DSR/MinTRL come bound conservativo per lunghezza minima track-record OOS; PBO/CSCV come **diagnostico** (non distingue «nessun edge» da «tutte le exit simili», e richiede disclosure di tutti i trial).
- **Bootstrap a blocchi per giorno/evento**, non per trade (Conley-Gonçalves-Hansen 2018): articoli sullo stesso evento/ticker-giorno **non** sono indipendenti. Block length = orizzonte (exit-horizon) per preservare l'overlap.
- **Forward return sovrapposti**: correggere il t-stat per **√q** (Hjalmarsson 2008, q = orizzonte) o usare la trasformazione di Britten-Jones-Neuberger-Nolte (2011); NW/HAC da solo è gravemente biased downward su orizzonti lunghi relativi al campione.
- **Competing risks**: un trade che esce per contro-segnale/stop/time non va trattato come se le altre barriere fossero indipendenti (Leung-Li 2015; Veiga-Shelton 2024; triple-barrier di López de Prado etichetta quale barra vince prima, ma **non modella** le dipendenze — per l'inferenza stimare le cause-specific hazard congiuntamente). Riportare quale barriera ha vinto prima (i reason code lo fanno già).
- **Multiple testing**: contare e pubblicare **tutti** i trial, incluse le analisi già viste dal team (i 4 modelli precedenti, il consolidamento, il replay 245-trade). L'universo effettivo è grande → l'onere statistico è alto (Harvey-Liu-Zhu: t > 3,0 per dichiarare significativa la «migliore» dopo la ricerca).
- **Term structure** `{1h,4h,close,D+1,D+2,D+3,D+5}` solo esplorativa una tantum: il risultato **fissa** la singola ipotesi confirmatoria su dati forward mai letti; il segmento esplorativo **non** diventa OOS per rinomina (STW 1999).
- **Edge cases**: delisting/halt → censura al tempo dell'evento, prezzo eseguibile realisticamente = ultimo trade o `NON DECIDIBILE`; overnight gap → riportare separato; partial fill → size effettiva; market close → nessun fill dopo close, slittamento a D+1; missing bar → censura, non interpolazione; corporate action → `adjustment="all"` (#192).

### 6.5 Power analysis (§5.3) `[EVIDENZA ESTERNA + ALEMBIC]`

`[EVIDENZA ESTERNA]` Ding-Sun 2023: `IR = IC̄/√(σ²_IC + σ²_e/N)`, e per IC = 0,05 servono ~20 periodi cross-sectionali (N ~1000) per t > 2; **N ∝ 1/IC²** — dimezzare l'IC quadruplica i periodi. `[EVIDENZA ALEMBIC]` 04 §4 fissa ~213 sedute pulite su `(3 × 0,243 / 0,05)²` con la dev. std. giornaliera ensemble osservata. `INFERENZA`: se l'IC vero è ~0,015 (l'ensemble puro decontaminato vale oggi +0,0149, 04 §1), n balzona a ~(3×0,243/0,015)² ≈ 2360 sedute (~11 anni) → il test **non passerà mai**, che è l'esito corretto (kill/redesign, 04 §5). La power analysis **va rifatta sulla varianza post-fix** e sul numero effettivo di nomi/giorno prima di congelare il conteggio; può solo **aumentare**. Sotto la soglia di potenza → `INCONCLUSIVE`, non «negativo».

### 6.6 Gate (§5.4)

`EVIDENZA ALEMBIC` (04 §5 R1–R4, congiuntivo) + integrazione:
1. **R1 Integrità**: ≥95% lifecycle ricostruibile end-to-end; `expired`+`unknown` < 5%; nessuna divergenza materiale dichiarata↔applicata (incluse le due di §2).
2. **R2 Alpha**: sulla popolazione tradabile, orizzonte D+2: IC medio ≥ +0,05; t-NW ≥ 3; segno non contraddetto a 1 e 3 sedute.
3. **R3 Economia**: portafoglio shadow batte benchmark equal-weight watchlist con limite inferiore unilaterale al 95% dell'excess return > 0, dopo fill eseguibili e costi conservativi.
4. **R4 Indipendenza**: overlap intenti con S1 ≤ 50% (#181/#182); oltre, dimostrare valore incrementale.
5. **(aggiunta)** Rischio di coda non peggiore oltre tolleranza predefinita (VaR/ES, maxDD); stabilità direzionale per sottoperiodo e regime **senza** usare gli split per ottimizzare ex post; correzione per le policy provate (SPA_c).

---

## 7. Pre-registration draft

**Una sola ipotesi primaria.** E1-mod (D+2 time-stop + contro-segnale posteriore+persistenza, soglia unica pre-reg., banda no-trade state-VIX + catastrophe stop `d_hard` 12–20%) produce excess return netto paired superiore a E0 **e** a E5 sul segmento pulito post-fix, superando il gate congiunto R1–R4.

**Benchmark**: E0 (behaviour as-is); E5 (time+catastrophe senza contro-segnale); equal-weight watchlist (R3).

**Metrica primaria**: excess return netto paired E1-mod vs E0 alla chiusura di D+2, su prezzi eseguibili, dopo costi conservativi. Metrica secondaria confermatoria: IC medio a D+2 (R2) — le due insieme (rendimento + relazione segnale-rendimento) sono l'unica evidenza che regge (04 §5).

**Gate**: R1–R4 congiuntivo (§6.6). **In particolare per il contro-segnale**: E1-mod deve battere E5 in modo robusto (paired, SPA_c) — altrimenti il contro-segnale è scartato e si adotta E5.

**Sample start**: batch atomico post-fix (fix correttezza dato #243/#244 + shadow end-to-end E1-mod + chiusura delle due divergenze §2: soglia contro-segnale impostata esplicitamente a un solo valore; S4 aggiunto a `_REBALANCE_CLOCK_STRATEGIES`). `n = 0` parte col batch atomico successivo se i fix non sono tutti pronti (04 §8).

**Stopping rule**: ~213 sedute pulite (power analysis post-fix da rifare, solo ↑). Review 28/09 = **tecnica/diagnostica**, non verdetto (04 §4). Decisione confirmatoria solo al superamento congiunto R1–R4.

**Invalidazione / restart del campione**:
- Qualsiasi errore di implementazione che può aver alterato le osservazioni (lifecycle, fill, collisioni, clock, time-stop, reason code) **azzera e riavvia** il campione confirmatorio (04 §8.4).
- **Ri-fit della soglia del contro-segnale dopo aver visto i risultati shadow** = riavvio (Bajgrowicz-Scaillet: ex-post tuning = falsa scoperta).
- Cambio di popolazione a monte (#243/#244) → **non concatenare** pre-fix con post-fix (04 §7).
- Esito negativo a n = 213 (IC economicamente nullo o performance netta non positiva) → **kill o redesign**, non shadow indefinito (04 §5).

**Cosa NON conta** (pre-registrato, 04 §6): le 9 chiusure della settimana peggiore; il controfattuale «compra all'apertura» (usa info futura); la t = −4,96 sull'ora 14 UTC (coorte legacy); il confronto S4 vs S1 realizzato (P&L non omogenei, #210); P&L settimanale in qualunque direzione.

---

## 8. Unknowns and data requests

`NON DECIDIBILE` / dati mancanti:

1. **Soglia del contro-segnale effettivamente deployata**. Codice −0,20 (default), ops −0,35, pre-reg −0,30. `[EVIDENZA ALEMBIC]` Servono env di produzione + log ordini broker per determinare quale valore gira. **Azione**: verificare prima del batch; impostarne esplicitamente uno; registrarlo.
2. **Clock DAILY applicato a S4 nel runtime**. Codice corrente esclude S4 (`_REBALANCE_CLOCK_STRATEGIES={"S1"}`); 04 lo dichiara come decisione futura. `[EVIDENZA ALEMBIC]` Verificare se il deploy ha la patch. **Azione**: se no, implementarla prima del batch (altrimenti lo shadow misura un clock 15-min).
3. **`d_hard` copertura reale e residui non protetti**. Commento YAML stale («shadow telemetry»); codice lo ha promosso a GTC reale. `[EVIDENZA ALEMBIC]` Verificare ordini broker + residui <1 azione non protetti per posizioni fractionable. **Azione**: misurare la frazione di posizioni senza SL/TP broker (fractionable) e separarle dal confronto (l'exit dipende oggi dalla frazionabilità, §2.4 — non è una tesi S4 omogenea).
4. **IC vero di S4**. L'ensemble puro decontaminato vale +0,0149 oggi (04 §1); l'1g ensemble∩|score|≥0,30 vale +0,1372 su 23 giorni (t 1,75, non significativo). `[EVIDENZA ALEMBIC]` `NON DECIDIBILE` se l'IC vero sia ≥ 0,05 o ~0,015 — la power analysis e l'esito stesso dipendono da questo. **Azione**: la shadow deve misurarlo su dati puliti post-fix; non presumere.
5. **Stabilità della term structure**. 04 §1 (E4): la forma si capovolge al variare di `MIN_SIMBOLI_GIORNO`; la monotonia si è dissolta in 4 giorni. `[EVIDENZA ALEMBIC]` `NON DECIDIBILE` la vera scadenza. **Azione**: fissare `MIN_SIMBOLI_GIORNO = 5` ex ante (04 §3) e non riaprirlo.
6. **Timing d'ingresso**. 64° percentile mediano del range, 70–84% del movimento già fatto al primo segnale. `[EVIDENZA ALEMBIC]` `NON DECIDIBILE` quanto edge residuo sia catturabile dall'uscita (l'ingresso è congelato per disciplina, 04 §2). `(Q8)` **L'exit non può risolvere il problema a monte** (ultimo articolo, resolver ticker, timing tardivo): vanno misurati e separati, non assorbiti nella metrica di exit. **Azione**: riportare entry-percentile e prezzo-segnale vs prezzo-eseguibile come variabili separate; il confronto exit è valido solo a parità di ingressi.
7. **Posteriore del contro-segnale stimabile**. News sparse (~metà watchlist senza articoli/giorno) → il posteriore aggregato può essere dominato dal prior. `IPOTESI`: approssimare con media mobile dello score + banda (no modello bayesiano completo) e pre-registrare la larghezza della banda. `NON DECIDIBILE` senza misurare la densità di segnali per ticker-giorno.
8. **Qualità non osservabile**. «Post-fix» ≠ «corretto»: serve verifica su campione etichettato (QX-01, #30/#54). `[EVIDENZA ALEMBIC]` **Azione**: non promuovere senza verifica su golden set.

---

## 9. Challenge to the existing D+2 decision

### Argomento migliore A FAVORE di D+2

`[EVIDENZA ESTERNA]` La fonte **più trasferibile** a S4 — Lopez-Lira & Tang (2023), LLM-based — mostra prevedibilità su ~2 giorni e nulla oltre; Heston-Sinha confermano 1–2 giorni; Tetlock 2008 ~1 giorno. D+2 è **dentro** la finestra documentata, al suo margine conservativo (meno esposto al rumore di D+1, meno oltre-edge di D+3). `[EVIDENZA ALEMBIC]` Il **processo** di 04 è allineato alla letteratura di validazione: un solo orizzonte primario congelato, shadow end-to-end, gate congiunto, ~213 sedute o `INCONCLUSIVE`, «28/09 non è verdetto», niente decisioni su P&L settimanale. Questo protegge dal multiple testing meglio del quadro di gran parte della pratica. Il catastrophe stop `d_hard` 12–20% è largo e coerente con la teoria dello stop ritardato (Kaminski-Lo, Lo-Remorov).

### Argomento migliore CONTRO D+2

`(a)` `[EVIDENZA ESTERNA]` La stessa fonte più trasferibile mostra edge concentrato su **signal-day + t+1** (38 bps a t=0, 20 bps a t+1, poi nulla). `[EVIDENZA ALEMBIC]` S4 entra tardi (70–84% del movimento già fatto) → consuma quasi tutto signal-day → il capturabile è essenzialmente **t+1**. Un time-stop alla **chiusura di D+2** tiene un giorno (t+2) oltre l'edge: D+1 potrebbe catturare lo stesso alpha con meno esposizione e meno falso-stop. D+2 non è sbagliato, ma **non è nettamente favorito** su D+1 dalla fonte più rilevante.

`(b)` `[EVIDENZA ALEMBIC]` Il **contro-segnale è mal specificato**: soglia puntuale (−0,20/−0,30/−0,35 divergente), senza persistenza, senza posteriore. `[EVIDENZA ESTERNA]` La teoria dell'optimal stopping (Ekström-Vaicenavicius, Vaicenavicius 2020) dice che l'uscita dipende dal **credo posteriore aggiornato sull'edge**, non da un singolo score; e la soglia deve essere **state-dependent** (più larga in high-VIX). Una soglia puntuale su rumore, senza banda no-trade, overtrade (Davis-Norman, Guasoni-Muhle-Karbe). Inoltre, **fittare la soglia ex post è una falsa scopenza** (Bajgrowicz-Scaillet).

`(c)` `[EVIDENZA ALEMBIC]` **Due divergenze codice/config** fanno sì che lo shadow eseguito sul codice attuale **non misuri ciò che 04 dichiara**: contro-segnale a −0,20 (non −0,30) e clock 15-min (non DAILY). È la **stessa classe E1/E3** per cui 04 ritira #179. Non è un dettaglio: invalida il confronto se non chiusa prima del batch.

`(d)` `[EVIDENZA ESTERNA]` **Trasferibilità long-only parziale** cappa strutturalmente l'edge: la coda lunga (negativa, lenta) è short-leg; la base empirica è **in erosione** (Glasserman dimezzato, PEAD-decay, Sharpe Lopez-Lira-Tang in calo 6,54→2,33). Qualunque orizzonte scelto su decadenza storica può essere già stale.

### Verdetto: `MODIFY`

**KEEP** lo scheletro: time-stop primario alla chiusura di D+2 + protocollo confirmatorio (shadow end-to-end, gate R1–R4, ~213 sedute o `INCONCLUSIVE`, niente verdict sul P&L settimanale). È corretto e allineato alla letteratura di validazione.

**MODIFY**:
1. **Contro-segnale**: ridisegnare come falsificazione della tesi — posteriore aggregato + persistenza ≥2 cicli + **una sola soglia pre-registrata ex ante** + banda no-trade state-dependent sul VIX (E1-mod). In alternativa minima, se il posteriore non è stimabile: congelare **una** soglia scelta senza peeking e riattivare l'isteresi 2-cicli sul percorso del contro-segnale (oggi disabilitata per S4).
2. **Chiudere le due divergenze prima del batch**: impostare esplicitamente la soglia del contro-segnale (un solo valore, registrato); aggiungere S4 a `_REBALANCE_CLOCK_STRATEGIES` per applicare DAILY. Verificare env/log broker, non presumere.
3. **Trattare D+1 come diagnostica pre-registrata** (E2): se la term structure pulita mostra edge concentrato a t+1 e S4 entra tardi, **spostare l'orizzonte primario a D+1 prima del segmento confirmatorio** — non dopo. D+2 resta la scelta conservativa di default; D+1 è il candidato legittimo se i dati lo indicano senza peeking.
4. **Separare** il replacement (rank turnover, ramo 3) dalla falsificazione della tesi nei reason code (E8); non mascherare il primo come exit di tesi.
5. **Usare Hansen SPA_c** come test di selezione (non BRC puro) e correggere i forward return sovrapposti per √q (Hjalmarsson); bootstrap per giorno/evento.

`(Q10)` **Raccomandazione finale**: E1-mod in shadow end-to-end, confronto confirmatorio vs E5 ed E0, gate congiunto R1–R4, SPA_c, ~213 sedute o `INCONCLUSIVE`. **Osservazione concreta che la falsificherebbe**: sul segmento pulito post-fix, E1-mod **non batte E5** in modo robusto (paired, SPA_c) su excess return netto → il contro-segnale non guadagna il suo posto e va scartato (si adotta E5). Oppure: l'IC vero decontaminato risulta ~0,015 (non ≥ 0,05) sostenuto → a n = 213 il test è `INCONCLUSIVE`/negativo → kill o redesign di S4, non shadow indefinito.

---

## 10. Bibliography

DOI/URL diretti + accesso (full-text / abstract). **Correzioni verificate** segnalate con §. Fonti agent-only verificate via risoluzione DOI ma non lette in full-text da me dichiarate `abstract`.

**News decay / sentiment**
- Lopez-Lira, A., Tang, F. (2023). *Can ChatGPT Forecast Stock Price Movements?* arXiv:2304.07619 / SSRN 4412788. `abstract` (HTML arXiv letto). — fonte LLM più trasferibile.
- Heston, S.L., Sinha, N.R. (2017). *News versus Sentiment: Predicting Stock Returns from News Stories.* Financial Analysts Journal 73(3):67–83, DOI 10.2469/faj.v73.n3.3 (FEDS 2016-048, DOI 10.17016/FEDS.2016.048). `abstract`.
- Tetlock, P.C. (2007). *Giving Content to Investor Sentiment.* JF 62(3):1139–1168, DOI 10.1111/j.1540-6261.2007.01232.x. `abstract`.
- Tetlock, P.C., Saar-Tsechansky, M., Macskassy, S. (2008). **§**titolo corretto: *More Than Words: Quantifying Language to Measure Firms' Fundamentals.* JF 63(3):1437–1467, DOI 10.1111/j.1540-6261.2008.01362.x. `abstract`.
- Tetlock, P.C. (2011). **§**titolo corretto: *All the News That's Fit to **Reprint**: Do Investors React to Stale Information?* RFS 24(5):1481–1512, DOI 10.1093/rfs/hhq141. `abstract`.
- Chan, W.S. (2003). **§**titolo corretto: *Stock Price Reaction to News and No-News: Drift and Reversal after Headlines.* JFE 70(2):223–260, DOI 10.1016/S0304-405X(03)00146-6. `abstract`.
- Jiang, H., Li, S.Z., Wang, H. (2021). *Pervasive Underreaction: Evidence from High-Frequency Data.* JFE 141(2):573–599, DOI 10.1016/j.jfineco.2021.04.003. `abstract+snippet`. **§**3° autore Haitao Wang.
- Boudoukh, J., Feldman, R., Kogan, S., Richardson, M. (2019). *Information, Trading, and Volatility: Evidence from Firm-Specific News.* RFS 32(3):992–1033, DOI 10.1093/rfs/hhy083. `abstract`.
- Aksoy-Yurdagul, N., Buchner, M., Zareei, M. (2026). *The persistence of news sentiment…* Economics Letters 260(C), DOI 10.1016/j.econlet.2025.112803. `abstract`.
- Glasserman, P., Li, J., Mamaysky, H. (2023). *Time Variation in the News–Returns Relationship.* JFQA 60(1):258–294, DOI 10.1017/S0022109023001369. `abstract`.
- Martineau, C. (2021). *Rest in Peace Post-Earnings Announcement Drift.* `snippet` (DOI non verificato indip. in questa sessione).
- Griffin (Kettell), McInnis, Zhao (2026). *Explaining the Decline of PEAD…* JAAF, DOI 10.1177/0148558X261439734. `snippet`.
- Boyarchenko, N., Larsen, T., Whelan, L. (2023). *The Overnight Drift.* RFS 36(9):3502–3547, DOI 10.1093/rfs/hhad020. `snippet`.
- Pénasse, J. (2022). *Understanding Alpha Decay.* Management Science, DOI 10.1287/mnsc.2022.4353. `snippet`.

**Stop / trailing / barriere**
- Kaminski, K., Lo, A.W. *When Do Stop-Loss Rules Stop Losses?* SSRN 968338. `abstract`.
- Lo, A.W., Remorov, A. (2017). *Stop-loss Strategies with Serial Correlation, Regime Switching, and Transaction Costs.* Financial Markets 26:3–35, DOI 10.1016/j.finmar.2017.02.003. `abstract`.
- Broadie, M., Glasserman, P., Kou, S. (1997). *A Continuity Correction for Discrete Barrier Options.* Mathematical Finance 7(2):107–133, DOI 10.1111/1467-9965.00035. `abstract`. **§**correzione `exp(±βσ√Δt)`, β≈0,5826.
- Leung, T., Li, X. (2015). *Optimal Mean Reversion Trading: With Transaction Costs and Stop-Loss Exit.* IJTAF 18(3), DOI 10.1142/S021902491550020X. `abstract`.
- Leung, T., Zhang, H. (2017). *Optimal Trading with a Trailing Stop.* arXiv:1701.03960. `abstract`.
- Dai, M., Marshall, B., Nguyen, N., Visaltanachoti, N. (2021). *Risk Reduction Using Trailing Stop-Loss Rules.* **§**venue corretto: International Review of Finance 21(4):1334–1352, DOI 10.1111/irfi.12328. `abstract`.

**Regime / vol-managed**
- Moreira, A., Muir, T. (2017). *Volatility-Managed Portfolios.* JF 72(4):1611–1644, DOI 10.1111/jofi.12513. `abstract`.
- Barroso, P., Santa-Clara, P. (2015). *Momentum has its moments.* JFE 116(1):111–120, DOI 10.1016/j.jfineco.2014.11.010. `abstract`.
- Cederburg, J., O'Doherty, B., Wang, F., Yan, X. (2020). **§**autori/titolo corretti: *On the Performance of Volatility-Managed Portfolios.* JFE 138(1):95–117, DOI 10.1016/j.jfineco.2020.04.015. `abstract`.
- DeMiguel, V., Martín-Utrera, A., Uppal, R. (2024). *Multifactor Portfolio Construction…* JF 79(6):3859–3891, DOI 10.1111/jofi.13395. `abstract`. **§**3 autori (non Nogales).
- Bajgrowicz, P., Scaillet, O. (2012). **§**titolo corretto: *Technical trading revisited: False discoveries, persistence tests, and transaction costs.* JFE 106(3):473–491, DOI 10.1016/j.jfineco.2012.06.001. `abstract`.
- Brock, W., Lakonishok, J., LeBaron, B. (1992). *Simple Technical Trading Rules and the Stochastic Properties…* JF 47(5):1731–1764, DOI 10.1111/j.1540-6261.1992.tb04681.x. `abstract`.

**Optimal stopping / no-trade / capacity**
- Ekström, E., Vaicenavicius, J. (2016). *Optimal liquidation of an asset under drift uncertainty.* SIAM JFM 7(1):357–381, arXiv:1509.00686. `full-text`.
- Vaicenavicius, J. (2020). **§**titolo corretto: *Asset liquidation under drift uncertainty and regime-switching volatility.* Appl. Math. Optim. 81:757–784, DOI 10.1007/s00245-018-9518-5, arXiv:1701.08579. `full-text`.
- Gârleanu, N., Pedersen, L.H. (2013). *Dynamic Trading with Predictable Returns and Transaction Costs.* JF 68(6):2309–2340, DOI 10.1111/jofi.12080. `full-text` (PDF autore).
- Gârleanu, N., Pedersen, L.H. (2016). *Dynamic Portfolio Choice with Frictions.* JET 165:487–516, DOI 10.1016/j.jet.2016.06.001. `abstract`.
- Davis, M.H.A., Norman, A.R. (1990). *Portfolio Selection with Transaction Costs.* MOR 15(4):676–713, DOI 10.1287/moor.15.4.676. `abstract`.
- Mei, X., DeMiguel, V., Nogales, F.J. (2016). **§**titolo corretto: *Multiperiod portfolio optimization with multiple risky assets and general transaction costs.* JBF 69:108–120, DOI 10.1016/j.jbankfin.2016.04.002. `full-text` (LBS open).
- Collin-Dufresne, P., Daniel, K., Sağlam, M. (2020). *Liquidity Regimes and Optimal Dynamic Asset Allocation.* JFE 136(2):379–406, DOI 10.1016/j.jfineco.2019.09.011. `abstract+snippet`.
- Guasoni, P., Muhle-Karbe, J. *Portfolio Choice with Transaction Costs: a User's Guide.* arXiv:1207.7330. `full-text`.
- DeMiguel, V., Garlappi, L., Nogales, F.J., Uppal, R. (2009). **§**4° autore Garlappi (non Wang): *A Generalized Approach to Portfolio Optimization…* Mgmt Sci 55(5):798–812, DOI 10.1287/mnsc.1080.0986. `abstract`.

**Validazione**
- White, H. (2000). *A Reality Check for Data Snooping.* Econometrica 68(5):1097–1126, DOI 10.1111/1468-0262.00152. `abstract`.
- Hansen, P.R. (2005). *A Test for Superior Predictive Ability.* JBES 23(4):365–380, DOI 10.1198/073500105000000063. `abstract`.
- Sullivan, R., Timmermann, A., White, H. (1999). *Data-Snooping, Technical Trading Rule Performance, and the Bootstrap.* JF 54(5):1647–1691, DOI 10.1111/0022-1082.00163. `abstract`.
- Bailey, D.H., López de Prado, M. (2014). *The Deflated Sharpe Ratio…* JPM 40(5):94–107, DOI 10.3905/jpm.2014.40.5.094. `abstract`.
- Bailey, D.H., Borwein, J.M., López de Prado, M., Zhu, Q.J. (2017). *The Probability of Backtest Overfitting.* JCF 20(4):39–69, DOI 10.21314/JCF.2016.322. `full-text`.
- Romano, J.P., Wolf, M. (2005). *Stepwise Multiple Testing as Formalized Data Snooping.* Econometrica 73(4):1237–1282, DOI 10.1111/j.1468-0262.2005.00615.x. `abstract`.
- Harvey, C.R., Liu, Y., Zhu, H. (2016). *…and the Cross-Section of Expected Returns.* RFS 29(1):5–68, DOI 10.1093/rfs/hhv059. `full-text`.
- Ding, Z., Sun, Y. (2023). *The statistics of time varying cross-sectional information coefficients.* J. Asset Mgmt 24(1):1–15, DOI 10.1057/s41260-022-00295-9. `full-text`.
- Hjalmarsson, E. (2008). *Interpreting long-horizon estimates in predictive regressions.* Fin. Res. Letters 5(2):104–117, DOI 10.1016/j.frl.2007.12.005. `full-text`.
- Britten-Jones, M., Neuberger, A., Nolte, I. (2011). *Improved Inference in Regression with Overlapping Observations.* JBFA 38(5-6):657–683, DOI 10.1111/j.1468-5957.2011.02244.x. `full-text`.
- Conley, T., Gonçalves, S., Hansen, C. (2018). *Inference with Dependent Data in Accounting and Finance Applications.* J. Acct. Res. 56(4):1139–1203, DOI 10.1111/1475-679X.12219. `abstract`.
- López de Prado, M. (2018). *The 10 Reasons Most Machine Learning Funds Fail.* JPM 44(6):120–133, DOI 10.3905/jpm.2018.44.6.120. `full-text`.
- Veiga, C., Shelton, D. (2024). *Market-Maker Hard Exit Thresholds Strategy.* SSRN 4947910 / Risk.net. `abstract`.

**Alembic (codice/docs)**
- `src/strategies/s4/config.py` (max_signal_age, prefilters); `src/config.py:223-271,234-236` (TP +6%, contro-segnale −0,20, d_hard); `config/trading.yaml:154,160,166,182,202-206,223-224,315` (min-hold, isteresi, DD, stop_loss, d_hard band, anti-whipsaw, gate); `src/workers/portfolio_scheduler.py:413,714-736,3995,4226-4227` (clock, FIX-D, bracket gating, fallback exclusion); `src/portfolio/exit_classification.py:62-69` (reason map); `src/strategies/s4/stop_policy.py:252-265`, `fractional_stop_orders.py:69-71`; `src/workers/drift.py:177` (VIX breaker). `EVIDENZA ALEMBIC`.
- 04_PREREGISTRAZIONE_D2.md (protocollo, R1–R4, ~213 sedute); 03_DECISIONE_PRECEDENTE_CONSOLIDATA.md; 02_ANALISI_PRELIMINARE_LETTERATURA.md; `docs/evidence/s4_ic.json`, `s4_ic_2x2.json`.

---

*Fine analisi GLM-5.2. Tutte le proposte hanno una condizione di falsificazione (§4, §7, §9). Le divergenze codice/config/runtime sono registrate come finding, non risolte per supposizione (§2, §8).*
