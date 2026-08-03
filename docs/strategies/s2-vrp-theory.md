# S2 - Volatility Risk Premium: revisione teorica ufficiale

**Data della revisione:** 2026-07-15

**Stato:** teoria ufficiale approvata dal PO il 2026-07-15; progettazione funzionale
bloccata dalla feasibility su strumenti, dati e investibilita

**Perimetro:** teoria finanziaria. Sono esclusi codice, segnali, soglie, backtest,
gate quantitativi e risultati interni.

## 1. Executive verdict

**TEORIA VALIDA MA DA RIFORMULARE.** Il variance risk premium (VRP) azionario e un
fenomeno reale e ben documentato, soprattutto sulle opzioni di indice: in media, il
prezzo risk-neutral della varianza futura eccede la sua aspettativa sotto la misura
reale. Non e un arbitraggio ne, per definizione, alpha: e principalmente compensazione
per assicurazione contro crash, salti, correlazione, liquidita e vincoli di capitale.
Il semplice spread VIX-volatilita realizzata e solo una proxy ex post; una short put e
un'esposizione mista, non una replica pura. Il premio e variabile, non monotono nel VIX,
con perdite rare e concentrate e con evidenza recente di compressione dei rendimenti
anomali. La teoria giustifica ulteriore ricerca, ma non autorizza ancora una strategia.

## 2. Perimetro e metodologia

La ricerca e stata svolta in due passaggi separati. Prima e stata prodotta una valutazione
clean-room senza consultare la documentazione Alembic, usando paper peer-reviewed,
working paper di istituzioni riconosciute, Federal Reserve, BIS e metodologie Cboe.
Soltanto dopo sono stati letti i documenti interni elencati nella sezione 11. La copertura
include lavori fondazionali dal 2001 e contributi pubblicati o disponibili fino al
2026; l'evidenza recente e distinta da quella peer-reviewed.

Criteri: definizioni sotto le misure P e Q, qualita metodologica, strumenti realmente
negoziati, costi/capitale, robustezza temporale e possibilita di falsificazione. Sono
esclusi tutti i risultati interni e le sezioni operative dei documenti. I limiti principali
sono la scarsita di serie lunghe di variance swap negoziati, il cambiamento della
microstruttura e l'insufficiente evidenza netta e capital-aware dopo il 2020.

## 3. Definizione indipendente

Siano `t` la data di valutazione, `T` la scadenza e `QV(t,T)` la variazione quadratica
annualizzata dell'underlying nel periodo. Con convenzione **seller-sign**:

`VRP_sell(t,T) = E_t^Q[QV(t,T)] - E_t^P[QV(t,T)]`

`Q` e la misura risk-neutral incorporata nei prezzi; `P` e la distribuzione fisica
condizionale. Un valore positivo remunera in aspettativa il venditore di varianza. Molti
paper adottano il segno opposto, dal punto di vista del compratore: il segno va sempre
dichiarato. La prima componente e approssimabile con un variance swap fair strike o con
una strip model-free di opzioni; la seconda non e osservabile e deve essere stimata ex
ante. La varianza realizzata futura consente soltanto una verifica ex post rumorosa.

| Termine | Definizione rigorosa | Nota pratica |
|---|---|---|
| Volatilita implicita | Parametro inverso di un modello per strike/scadenza, oppure radice di una misura di varianza model-free | Non e `E^P` della volatilita futura |
| Varianza realizzata | Misura ex post della variazione quadratica sullo stesso intervallo | Quella passata non sostituisce l'aspettativa fisica futura |
| Varianza attesa sotto P | Aspettativa condizionale reale di `QV(t,T)` | Non osservabile; dipende dal modello di previsione |
| Varianza sotto Q | Prezzo risk-neutral della varianza futura | Pesa molto gli stati costosi, non e una previsione statistica |
| Variance risk premium | Differenza tra aspettative Q e P della varianza, con segno dichiarato | Definizione normativa del progetto |
| Volatility risk premium | Differenza relativa a un payoff in volatilita o uso pratico generico del VRP | Non e sinonimo matematico: la radice introduce Jensen e vol-of-vol |
| Jump/tail premium | Compenso per salti e stati estremi | Componente distinta ma centrale del VRP azionario |
| Skew premium | Prezzo relativo degli stati downside lungo la superficie | Non prova che le OTM put siano "sovrastimate" |
| Correlation premium | Differenza tra correlazione implicita e realizzata/attesa | Spiega parte del divario indice-single name |
| Dispersion premium | P&L della differenza tra opzioni indice e componenti | Include correlazione, volatilita, salti e frizioni; non e puro VRP |

Usare "VRP" per `IV-RV` e una semplificazione descrittiva accettabile solo se si indicano
orizzonte, segno e carattere ex post. Presentarla come definizione teorica o P&L
direttamente monetizzabile e fuorviante.

## 4. Meccanismo economico

| Meccanismo | Fondamento ed evidenza | Condizioni di indebolimento | Presenza interna / decisione |
|---|---|---|---|
| Domanda di protezione e avversione al crash | Gli investitori pagano payoff convessi negli stati a elevata utilita marginale; put e straddle hanno rendimenti medi bassi per il compratore | Offerta abbondante, rischio percepito basso o protezione sostituita | Presente e valido, ma va espresso come prezzo degli stati, non errore probabilistico |
| Salti, coda e downside | La componente downside e controciclica; eventi rari spiegano parte rilevante dei prezzi | Mercati senza forte asimmetria o con rischio trasferito altrove | Presente ma incompleto: aggiungere jump, gap e rovina |
| Vincoli degli intermediari | Dealer assorbono domanda con rischio non perfettamente copribile; capitale, funding e margini rendono inclinata l'offerta | Bilanci forti, liquidita elevata, nuovi venditori ben capitalizzati | Quasi assente; integrazione necessaria |
| Hedging, modello, vol-of-vol e liquidita | Delta hedging non elimina gamma, salti, surface, basis o liquidita; il premio copre rischio residuo | Mercati profondi e rischi piu replicabili | Assente; integrazione necessaria |
| Correlazione in crisi | L'indice concentra correlazione e downside sistemico, spiegando un premio piu forte che nei singoli titoli | Correlazioni stabili e dispersione liquida | Assente; integrazione necessaria |
| Pressione di domanda sulla surface | La domanda netta modifica livelli e skew dove il rischio non e arbitrabile | Capacita dealer elevata e domanda bilanciata | Solo implicita; riformulare |
| Bias comportamentali | Sovrappeso psicologico dei disastri puo contribuire | Non e identificabile separatamente da preferenze razionali e vincoli | La "crash phobia" interna non e dimostrata e non va assunta |

Le spiegazioni sono complementari. L'evidenza identifica bene prezzo degli stati downside
e limiti di intermediazione, ma non dimostra che il premio derivi principalmente da una
sovrastima irrazionale della probabilita di crash.

## 5. Evidenze empiriche

| Fonte | Anno; campione | Mercato/strumento e definizione | Metodo e risultato | Limiti | Affidabilita |
|---|---|---|---|---|---|
| [Coval-Shumway](https://doi.org/10.1111/0022-1082.00352) | 2001; storico opzioni USA | S&P 500, put/straddle | Rendimenti delle opzioni coerenti con premi per rischio; straddle ATM zero-beta circa -3% settimanale per il compratore | Campione storico e costi/capitale incompleti | Alta, fondazionale |
| [Bakshi-Kapadia](https://doi.org/10.1093/rfs/hhg002) | 2003; SPX | Opzioni delta-hedged | La posizione lunga delta-hedged sottoperforma: premio negativo per il compratore | Delta hedging non isola salti e surface | Alta |
| [Bollen-Whaley](https://doi.org/10.1111/j.1540-6261.2004.00647.x) e [GPP](https://doi.org/10.1093/rfs/hhp005) | 2004/2009 | Index e single-name options | Pressione di domanda e rischio non copribile influenzano IV e skew | Identificazione dipende dal modello | Alta |
| [Carr-Wu](https://doi.org/10.1093/rfs/hhn038) | 2009; 1996-2003 | 5 indici, 35 titoli; variance swap sintetici 30d | Buyer-sign molto negativo sugli indici, meno uniforme sui titoli | Periodo breve, swap sintetici | Alta |
| [Broadie-Chernov-Johannes](https://doi.org/10.1093/rfs/hhp032) | 2009; 1987-2005 | S&P index options | Rendimenti put-write estremi non sono necessariamente anomali con salti e sampling tail | Sensibile al modello dei salti | Alta, falsificante |
| [Santa-Clara-Saretto](https://doi.org/10.1016/j.finmar.2009.01.002) | 2009; 1985-2001 | Strategie su opzioni USA | Margini, bid-ask e margin call riducono rendimento e capacita | Regole di mercato storiche | Alta |
| [Driessen-Maenhout-Vilkov](https://doi.org/10.1111/j.1540-6261.2009.01467.x) | 2009; index/componenti | Dispersion/correlation | Il rischio di correlazione e prezzato; apparente alpha non robusto alle frizioni | Replica complessa | Alta |
| [Bollerslev-Todorov](https://doi.org/10.1111/j.1540-6261.2011.01695.x) | 2011; opzioni e high-frequency | S&P 500; tail variation | Paura di eventi rari e componente jump sono materiali | Stima delle code fragile | Alta |
| [Dew-Becker et al.](https://www.sciencedirect.com/science/article/pii/S0304405X16302161) | 2017; 1996-2014 | Variance swap 1m-10y | E prezzata soprattutto la varianza realizzata inattesa e transitoria; forte dipendenza dalla scadenza | Campione USA | Alta |
| [Londono, Fed](https://www.federalreserve.gov/econres/ifdp/the-variance-risk-premium-around-the-world.htm) | 2015; 2000-2009 | 8 mercati sviluppati | VRP medio positivo; potere predittivo locale non universale, forte ruolo USA | Campione include crisi e mercati limitati | Medio-alta |
| [Bekaert-Engstrom-Ermolov](https://www.nber.org/papers/w27108) | 2023; lungo campione USA | Equity VRP Q-P | Premio positivo, moderatamente persistente, legato alla coda sinistra dei consumi; modelli standard insufficienti | Stima di P model-dependent | Alta |
| [Cheng COVID](https://doi.org/10.1093/rapstu/raaa010) | 2020; feb-apr 2020 | VIX futures | Premi ex ante divengono negativi e i prezzi sottoreagiscono allo shock | Evento singolo; mispricing vs rischio non identificati | Medio-alta |
| [Londono-Samadi, Fed](https://doi.org/10.17016/IFDP.2023.1376) | 2023; incl. 2022-23 | SPX scadenze giornaliere | Premi evento macro molto eterogenei; crescono su alcune release nel 2022-23 | Working paper, micro-orizzonti | Media |
| [Duarte-Jones-Wang](https://doi.org/10.1111/jofi.13365) | 2024; opzioni USA moderne | Rendimenti opzioni e microstruttura | I bias di microstruttura alterano le stime; opzioni liquide conservano rendimenti negativi per il compratore | Scelte di filtri importanti | Alta |
| [Chicago Fed WP 2025-17](https://www.chicagofed.org/publications/working-papers/2025/2025-17) | 2025; SPX 1987-2022, sintetico 1926-2022 | Put returns e alpha | Negli ultimi 15 anni alpha indistinguibile da zero; il secolo sintetico non mostra alpha negativo del compratore | Working paper; opzioni sintetiche | Indicativa ma cruciale |
| [Horenstein-Vasquez-Xiao](https://doi.org/10.1093/rfs/hhaf060) | 2026; opzioni USA | Portafogli delta-hedged | Fattori option-specific, incluso IV-RV e vol-of-vol, non spiegati dai soli fattori azionari | Non prova investibilita netta | Alta, recente |

Conclusione empirica: esistenza media del premio di varianza di indice = **robusta**;
universalita cross-market e stabilita = **indicative, non dimostrate**; alpha netto,
capital-aware e persistente dopo il 2020 = **non dimostrato**. Gli studi recenti non
eliminano il fenomeno, ma indeboliscono la tesi di un'anomalia stabile.

## 6. Misurazione

| Misura | Significato | Uso corretto | Limite principale |
|---|---|---|---|
| `E^Q[QV]-E^P[QV]` | Premio atteso di varianza | Misura teorica primaria | `E^P` non osservabile |
| Variance strike - futura RV | Innovazione ex post del premio | Validazione storica matched-horizon | Rumorosa; realizzo non equivale all'aspettativa |
| `VIX^2` - attesa fisica di varianza 30d | Proxy model-free dell'equity VRP | Buona approssimazione con convenzioni allineate | VIX ha metodologia e settlement specifici |
| `VIX^2` - futura RV 30d | Proxy ex post | Descrittiva/validazione | Overlap, salti, calendario, errore di aspettativa |
| VIX - futura volatilita | Spread in punti vol | Comunicazione descrittiva | Jensen/convessita; non e un payoff lineare |
| VIX / RV passata | Regime relativo | Descrizione, non VRP normativo | Lookback e forward mismatch; P non stimata |
| Rendimento variance swap | Premio investibile piu diretto | P&L di strumento specifico | Mark-to-market, collateral, liquidita e jump |
| Opzione delta-hedged | Premio option-specific | Isolamento parziale | Hedging discreto, gamma, skew, vol-of-vol, costi |
| P&L put-write/straddle | Rendimento di strategia | Test di investibilita successivo | Mescola beta, skew, jump, timing e capitale |
| Intera surface model-free | Q-variance e componenti per tenor/moneyness | Analisi piu completa | Dati e microstruttura complessi |

**Convenzione teorica Alembic.** La misura primaria e in varianza, con segno seller,
underlying e settlement espliciti. Per una misura a 30 giorni si usa lo stesso intervallo
di 30 giorni di calendario su entrambi i lati, includendo close-to-open e giorni non di
negoziazione; timestamp e informazioni disponibili sono fissati a `t`. L'annualizzazione
usa un'unica base coerente e dichiarata. Il lato Q replica scadenza e interpolazione dello
strumento; il lato P e una previsione ex ante. La RV futura matched-window e solo esito ex
post. Le osservazioni non sovrapposte sono preferibili; se si sovrappongono, l'inferenza
deve correggere l'autocorrelazione. Frequenza intraday migliora la misura della variazione
continua ma richiede trattamento separato di overnight, salti e microstruttura.

Il [VIX Cboe](https://cdn.cboe.com/resources/vix/VIX_Methodology.pdf) misura una varianza
risk-neutral costante a 30 giorni di calendario usando una strip di opzioni SPX OTM e
interpolazione per minuti. Non e una previsione P certa. Differenze di varianza,
volatilita, orizzonte, calendario o settlement rendono il confronto distorto.

## 7. Strumenti coerenti

| Strumento | Esposizione/componente | Purezza | Rischi aggiuntivi | Investibilita e limite |
|---|---|---|---|---|
| Variance swap su indice | Varianza realizzata vs strike Q | Alta | Jump, collateral, counterparty, MTM | Teoricamente migliore; accesso OTC limitato |
| Strip replicante / variance futures | Varianza di indice | Alta-media | Discretizzazione, basis, liquidita | Listed/cleared possibile, liquidita da verificare ([Cboe](https://www.cboe.com/tradable-products/sp-500/variance-futures)) |
| Opzioni indice delta-hedged | Volatilita/varianza locale e surface | Media | Gamma, hedge, skew, vol-of-vol, costi | Liquide ma gestione complessa |
| Short straddle/strangle | Short vol con diversa moneyness | Media-bassa | Gamma, jump e perdite non limitate | Accessibile; capitale e tail dominanti |
| Put-writing indice/ETF | Insurance/downside VRP | Bassa-media | Equity beta, skew, gap, early exercise ETF | Investibile ma non puro; cash-secured non elimina la coda |
| Covered call | Call premium piu equity | Bassa | Equity beta, upside truncation | Accessibile, non misura pura del VRP |
| VIX futures | Aspettative Q della futura VIX | Bassa per VRP spot | Roll, basis, convexity, crowding | Liquidi; non replica la varianza SPX realizzata |
| VIX options | Vol-of-vol e coda della VIX | Bassa | Settlement, smile, basis, convexity | Esposizione derivata di secondo ordine |
| Single-name options | Vol/jump idiosincratici | Variabile | Earnings, dividend, borrow, liquidita | Evidenza meno uniforme degli indici |
| Dispersion | Correlazione implicita vs componenti | Media per correlation RP | Vega mismatch, salti, costi multi-leg | Complessa; non puro VRP |
| Term structure/surface | Premi per tenor/skew/correlation | Specifica, non unica | Roll, basis, model e liquidita | Coerente solo con ipotesi componente-specifiche |
| Proxy senza derivati | Equity/liquidity/overnight factors | Molto bassa | Fattori estranei | Non va denominata cattura del VRP senza identificazione |

## 8. Alpha vs risk premium

La classificazione predefinita e **risk premium / alternative beta assicurativa**: il
venditore accetta esposizioni short crash, downside, convexity, liquidita, correlazione e
capacita intermediaria. Un rendimento medio positivo o uno Sharpe elevato non sono alpha,
specialmente con skew negativo e pochi eventi estremi.

L'eventuale alpha e soltanto il residuo, in una fase successiva, dopo costi, collateral e
capitale e dopo aver controllato esposizioni lineari e non lineari a mercato, downside,
salti, liquidita, gamma/vega, skew, vol-of-vol e timing. Una migliore selezione condizionale
potrebbe produrre alpha; l'esistenza del VRP non la dimostra.

### Semplificazioni comuni da vietare

| Affermazione | Giudizio | Condizione/correzione |
|---|---|---|
| "IV e sempre sopra RV" | Errata | La relazione e media e condizionale; puo invertirsi |
| "Il VIX sovrastima la volatilita futura" | Fuorviante | VIX e una misura Q a 30 giorni, non una forecast P omogenea |
| "Vendere volatilita rende stabilmente" | Errata | Le perdite sono concentrate, path-dependent e capital-intensive |
| "Il premio e 3-4 punti" | Campione-specifica | Servono mercato, periodo, tenor e unita; non e una legge |
| "Il premio e un'anomalia" | Non dimostrata | La spiegazione predefinita e compensazione per rischio |
| "Basta vendere opzioni" | Errata | Payoff, strike, hedge, costi e capitale determinano l'esposizione |
| "La diversificazione elimina la coda" | Errata | Crash e correlazione sistemica restano comuni |
| "Sharpe alto prova alpha" | Errata | Skew, kurtosis e fattori non lineari invalidano l'inferenza |
| "Il livello VIX predice il premio" | Plausibile ma non dimostrata | Serve `E^P` e validazione OOS; la relazione non e monotona |
| "IV alta rende conveniente vendere" | Errata | Anche varianza fisica, margini e rischio di overshoot possono essere alti |
| "IV-RV e direttamente monetizzabile" | Errata | Solo un payoff definito genera P&L, con scaling e frizioni |
| "Il premio e costante" | Errata | Varia per regime, tenor, moneyness, mercato e capacita dealer |
| "Si cattura senza rischio estremo" | Errata | Eliminare completamente la coda elimina gran parte del razionale economico |

## 9. Regimi e stabilita

Il premio medio e positivo ma condizionale. Domanda di protezione, downside atteso e
vincoli dealer possono alzare il prezzo Q nei mercati stressati; simultaneamente salgono
varianza fisica, margini e probabilita di perdita. Quindi "VIX alto = vendita conveniente"
non segue dalla teoria. Durante shock improvvisi la RV puo superare quanto prezzato e il
premio ex ante puo ridursi o diventare negativo, come nei VIX futures nel 2020.

In bassa volatilita l'incasso apparente puo essere regolare ma la leva implicita e la
compiacenza accumulano rischio. Nel febbraio 2018 i prodotti short-VIX amplificarono il
deleveraging ([BIS](https://www.bis.org/publ/qtrpdf/r_qt1803t.htm)). In crisi, recessioni,
inflazione o rialzi dei tassi l'effetto dipende da rischio fisico, domanda assicurativa,
liquidita e bilanci: non esiste segno universale. L'evidenza internazionale e piu debole
fuori dagli indici USA. Il recupero puo richiedere anni e pochi eventi possono dominare
la media campionaria.

## 10. Rischi strutturali

| Gravita | Rischio | Natura e mitigabilita |
|---|---|---|
| 1 | Crash, jump, gap e rovina | Inseparabile dal premio assicurativo; limiti di esposizione riducono anche il rendimento atteso, non eliminano il rischio |
| 2 | Short gamma/convexity, skew negativo e kurtosis | Essenziale nelle vendite di opzioni; hedging discreto fallisce nei salti |
| 3 | Margin, funding e liquidazione forzata | Puo rendere insolvente una strategia con payoff finale positivo; collateral e riserva mitigano, con costo |
| 4 | Liquidita, crowding e unwind simultaneo | Spread e market depth peggiorano quando la copertura serve; diversificazione tra venditori non aiuta |
| 5 | Correlation breakdown e rischio sistemico | Indici convergono verso correlazione alta nelle crisi; e parte del premio, non rumore |
| 6 | Vol-of-vol, vega, term structure e surface | Mark-to-market puo perdere senza grande movimento spot; hedge parziale e costoso |
| 7 | Path dependency e rischio di hedging | Frequenza, gap, roll ed early exercise cambiano il P&L; mitigabile solo parzialmente |
| 8 | Basis, settlement e strumento | VIX, SPX, SPY e variance swap non sono intercambiabili |
| 9 | Modello, stima e campione di coda | P non e osservabile e pochi crash dominano; robustezza e scenari sono necessari |
| 10 | Regime e decay/capacita intermediaria | Il premio puo comprimersi o cambiare forma; nessuna persistenza e garantita |

Spesso sono sottostimati margini, MTM prima della scadenza, liquidita endogena,
correlazione e incertezza da pochi crash. Nessuna diversificazione elimina una perdita
sistemica comune; una mitigazione completa della convexity elimina anche gran parte del
premio.

## 11. Critica della documentazione esistente

Documenti esaminati dopo la ricerca indipendente:

- **D1:** `archive/.../01_strategy_design.md`, sezione S2.
- **D2:** `docs/strategies.md`, sezione S2.
- **D3:** `docs/user_guide.md`, sezione S2 e glossario.
- **D4:** `docs/RESEARCH_S2_S3_S7_PRIMARY_LITERATURE_2026-07-15.md`, sezioni 2.1-2.2.
- **D5:** `archive/.../OPUS_QUANT_TRADING_VALIDITY_MEMO_2026-06-18.md`, S2.
- **D6:** `archive/.../FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md`, S2.

Le sezioni su implementazione, parametri, segnali, backtest, risultati e gate sono state
escluse e rinviate alle fasi successive.

| Documento/sezione | Affermazione originale | Giudizio e motivazione | Evidenza | Azione |
|---|---|---|---|---|
| D1/Razionale | IV > RV di 3-4 punti = income strutturale | Corretta ma incompleta e matematicamente imprecisa: campione/orizzonte assenti; vol diversa da varianza; non direttamente monetizzabile | Carr-Wu; Cboe VIX | Riformulare in Q-P variance, senza numero universale |
| D1/Perche | Tail risk e insurance demand | Corretta ma incompleta | Coval-Shumway; Bollerslev-Todorov | Mantenere e integrare intermediari, correlazione, liquidita |
| D1/Perche | Crash phobia = sovrastima cronica dei disastri | Plausibile ma non dimostrata; confonde probabilita e state prices | Bekaert et al.; GPP | Eliminare come fatto; mantenere come ipotesi concorrente |
| D1/Skew | OTM put piu sovrastimate delle ATM | Economicamente debole: prezzo elevato non prova mispricing | Broadie et al.; Driessen et al. | Sostituire con premio downside/skew |
| D1/Persistenza | "Fattore piu persistente" | Non supportata e non aggiornata | Chicago Fed 2025 | Eliminare |
| D1/ETF | AUM di PUTW/JEPI/JEPQ prova il VRP | Irrilevante/promozionale; prodotti non puri | Metodologie prodotto | Eliminare come evidenza |
| D1/Regime | Vendere in stress e molto profittevole se si sopravvive | Fuorviante e non monotono | Cheng 2019/2020 | Riformulare come ipotesi condizionale |
| D1/Misura | `VIX/RV20 passata - 1` stima il VRP | Matematicamente imprecisa | Cboe VIX; definizione Q-P | Declassare a indicatore descrittivo |
| D1/Rischi | "gap up" e gennaio 2018 | Errata: una short put teme gap down; Volmageddon fu febbraio 2018 | BIS 2018 | Correggere |
| D2/Razionale | Short put o long SPY overnight catturano lo stesso edge | Contraddetta dalla teoria: il proxy equity non replica varianza | Carr-Wu; payoff replication | Eliminare equivalenza |
| D3/Guida | Il venditore incassa un premio assicurativo | Semplificazione utile ma incompleta | Letteratura option returns | Mantenere con avvertenza su MTM/coda |
| D3/Gate | Sotto-performance stress accettata per natura assicurativa | Appartiene a fase successiva e puo normalizzare rischio non sostenibile | Santa-Clara-Saretto | Rimuovere dalla teoria; valutare in governance |
| D4/2.1 | Esistenza premio, non alpha; short put mescola rischi | Corretta e utile | Ampio allineamento esterno | Mantenere |
| D4/2.2 | VRP "piu universale"; cresce in stress | Ambigua/eccessiva; evidenza cross-market e monotonicita deboli | Londono; Cheng | Riformulare |
| D4/Bibliografia | DOI Santa-Clara-Saretto `.02.002` | Riferimento errato | DOI ufficiale `.01.002` | Correggere |
| D5/S2 | Strategia negativa invalida il VRP | Errore di livello: invalida strategia/utilita, non il fenomeno | Definizione fenomeno vs P&L | Separare teoria e strumento |
| D6/S2 | VIX term slope e piu pulita e meno tail-heavy | Plausibile ma non dimostrata; aggiunge roll/basis/crowding | Cheng; BIS 2018 | Non adottare senza ipotesi separata |

## 12. Gap analysis

| Tema | Ricerca indipendente | Documentazione | Gap / gravita | Decisione di merge |
|---|---|---|---|---|
| Definizione | `E^Q[QV]-E^P[QV]`, seller-sign | IV-RV generico | Bloccante | Adottare definizione Q-P |
| Vol vs varianza | Distinte per Jensen/vol-of-vol | Intercambiabili | Sostanziale | Varianza normativa; vol solo descrittiva |
| Q vs P | Differenza di misure | Non esplicitata | Bloccante | Introdurre entrambe |
| Origine | Insurance + stati downside + intermediari | Insurance/crash phobia | Sostanziale | Integrare; declassare bias comportamentale |
| Rischi remunerati | Crash, jump, correlation, liquidity, funding, vol-of-vol | Prevalentemente tail | Sostanziale | Ampliare |
| Alpha/risk premium | Alternative beta assicurativa di default | "edge"/fattore | Bloccante | Vietare presunzione di alpha |
| Strumenti | Variance exposure piu pura; put mista | Short put e proxy equity | Bloccante | Separare fenomeno, replica e strategia |
| Investibilita | Costi, MTM, capitale e accesso sono essenziali | Parzialmente presenti | Sostanziale | Integrare nella teoria |
| Orizzonte | Forward matched-horizon/calendar | VIX vs RV passata | Bloccante | Convenzione unica ex ante/ex post |
| Stabilita | Media positiva, condizionale e non universale | 3-4 punti strutturali | Sostanziale | Rimuovere costante universale |
| Regime | Non monotono | Stress = premio piu ricco | Sostanziale | Formulare ipotesi falsificabile |
| Costi/capitale | Determinano rendimento investibile | Presenti come dettaglio tecnico | Rilevante | Elevarli a requisito economico |
| Hedging | Trasforma ma non elimina rischi | Poco trattato | Rilevante | Integrare |
| Tail risk | Inseparabile; pochi eventi dominano | Riconosciuto | Allineamento parziale | Mantenere e rafforzare rovina/margini |
| Limiti | Post-2020, cross-market, P non osservabile | Quasi assenti | Sostanziale | Esplicitare incertezza |
| Falsificabilita | Dieci ipotesi separate | Narrazione generale | Bloccante | Adottare sezione 16 |

## 13. Elementi da mantenere, correggere, integrare o eliminare

**Da mantenere:** domanda assicurativa, compensazione per coda, skew negativo e perdite
concentrate; distinzione D4 tra premio e alpha; avvertenze D4 su costi, margini e sampling
dei crash. Sono coerenti con la letteratura e utili agli stakeholder.

**Da correggere:** IV-RV in Q-P variance; "3-4 punti" in stima campione-specifica;
stress premium in relazione non monotona; "gap up/gennaio 2018" in gap down/febbraio
2018; DOI Santa-Clara-Saretto in `.01.002`; guida utente da incasso a compensazione
attesa con rischio MTM.

**Da integrare:** segno del premio, Jensen, physical expectation, orizzonte/calendario,
intermediari, correlazione, vol-of-vol, liquidita/funding, differenza indice-single name,
decay recente, distinzione fenomeno/P&L e ipotesi falsificabili.

**Da eliminare dalla teoria:** equivalenza con long SPY overnight, persistenza assoluta,
AUM come prova, OTM put "sovrastimate" come fatto, alpha presunto, profittabilita
automatica con VIX elevato e regole/segnali/gate operativi. Questi ultimi, quando utili,
vanno valutati solo nelle fasi successive.

## 14. Registro delle decisioni di merge

| ID | Tema | Prima | Formulazione adottata / origine | Motivo e supporto | Impatto |
|---|---|---|---|---|---|
| M01 | Definizione | IV-RV | Q-P expected variance, seller-sign / ricerca esterna | Coerenza matematica; Carr-Wu | Cambia metrica normativa |
| M02 | Terminologia | VRP=Variance RP | Concetti distinti, uso pratico dichiarato / nuova formulazione | Jensen e payoff diversi | Impone glossario |
| M03 | Razionale | Crash phobia | Insurance + tail + intermediari; bias solo ipotesi / merge di entrambe | Evidenza piu identificabile | Evita behavioral story unica |
| M04 | Alpha | Structural edge | Risk premium/alternative beta di default / ricerca esterna | Broadie; Bekaert; Chicago Fed | Alpha richiede test residuo |
| M05 | Strumento | Short put/proxy equivalenti | Gerarchia per purezza / ricerca esterna | Payoff e rischi differenti | Richiede decisione strumento |
| M06 | Misura | VIX/RV20 | Forecast P matched-horizon; RV futura ex post / ricerca esterna | Orizzonte e misure coerenti | Blocca proxy come prova |
| M07 | Stabilita | 3-4 punti | Time-varying e sample-specific / ricerca esterna | Evidenza internazionale/recente | Vietate costanti universali |
| M08 | Regime | Stress sempre ricco | Relazione non monotona / merge di entrambe | Cheng 2019/2020 | Regime diventa ipotesi |
| M09 | Coda | Rischio noto | Include margin, liquidity, ruin, correlation / merge di entrambe | Santa-Clara; BIS | Capitale entra nell'investibilita |
| M10 | Evidence | ETF/AUM | Paper, dati e metodologie trasparenti / ricerca esterna | AUM non prova rendimento | Alza standard bibliografico |
| M11 | Universalita | VRP universale | Forte su equity index, non universale / ricerca esterna | Carr-Wu; Londono | Restringe dominio |
| M12 | Separazione fasi | Teoria + regole + gate | Teoria autonoma; operativita rinviata / nuova formulazione | Falsificabilita e governance | Evita confirmation bias |

## 15. Teoria definitiva consolidata

### Definizione e natura

Nel progetto Alembic il **variance risk premium azionario**, con convenzione seller-sign,
e la differenza tra il prezzo risk-neutral della varianza futura di un underlying su un
orizzonte definito e l'aspettativa condizionale della stessa varianza sotto la misura
reale. Il premio e positivo quando, in aspettativa, chi vende varianza riceve compensazione
per detenere rischi costosi negli stati avversi. La misura Q non e una previsione P e la
realizzazione futura non e l'aspettativa ex ante.

"Volatility risk premium" resta il nome funzionale S2, ma non e sinonimo matematico
perfetto di variance risk premium. Payoff lineari in volatilita, differenze tra radici di
varianza e implied volatility di una singola opzione incorporano convexity, Jensen,
vol-of-vol, strike e scadenza. Ogni uso pratico del termine deve dichiarare la misura.

### Fondamento ed evidenza

Il premio puo esistere perche investitori avversi al rischio domandano protezione convessa
contro crash, salti e correlazione elevata; intermediari e venditori richiedono compenso
per rischio non perfettamente copribile, capitale, funding, modello e liquidita. La
pressione di domanda sulla superficie puo rafforzarlo. Una distorsione comportamentale
puo contribuire, ma non e necessaria ne dimostrata come causa dominante.

L'esistenza media del seller-sign VRP e robusta per opzioni liquide su grandi indici
azionari USA. Il premio e meno uniforme su singoli titoli e mercati internazionali, varia
per scadenza e componente downside/upside, e non dimostra un alpha persistente. Evidenza
recente indica che i rendimenti anomali delle put possono essersi compressi; l'equilibrio
tra domanda di protezione e capacita intermediaria cambia nel tempo.

### Misura e strumenti

La misura concettuale primaria e `E^Q[QV]-E^P[QV]` con stesso underlying, payoff,
settlement, intervallo e annualizzazione. Un variance strike o una strip model-free
approssima Q; P richiede una previsione condizionale. Il confronto con RV futura e una
verifica ex post. VIX-RV in punti vol e descrittivo; VIX/RV passata non e la definizione
del premio. Il P&L di una strategia e un oggetto distinto.

Variance swap o replica model-free di indice sono l'esposizione teoricamente piu diretta.
Opzioni delta-hedged sono approssimazioni con rischi residui. Put-writing, straddle,
covered call, VIX futures/options, dispersion e strategie di term structure catturano
componenti diverse e aggiungono beta, skew, jump, roll, basis, correlation o vol-of-vol.
Una proxy azionaria senza derivati non puo essere chiamata esposizione al VRP senza una
identificazione empirica separata.

### Rendimento, validita e fallimento

Il rendimento atteso e innanzitutto un premio assicurativo sistematico, non alpha. La
teoria e valida quando esiste domanda per protezione e il prezzo Q degli stati di alta
varianza eccede la loro aspettativa P abbastanza da compensare costi, capitale e rischio
di rovina. Il fenomeno puo restare positivo mentre una specifica strategia perde, e una
strategia puo guadagnare per beta o timing senza catturare il fenomeno.

La tesi operativa fallisce se il differenziale Q-P non e persistente sul mercato e
orizzonte scelti, se costi/capitale assorbono il premio, se il rendimento e spiegato da
altri fattori, o se il rischio di coda rende l'utilita economica inaccettabile. VIX alto,
IV sopra RV passata e premio incassato non sono da soli condizioni sufficienti.

### Rischi, limiti e implicazioni

I rischi inseparabili sono crash/jump, short convexity/gamma, skew negativo, correlazione
e concentrazione temporale delle perdite. Funding, margini, liquidita, unwind, vol-of-vol,
surface, basis, hedging, stima e regime possono trasformare un premio statistico in un
investimento non sostenibile. Mitigarli riduce anche parte del rendimento; non possono
essere dichiarati eliminati tramite sola diversificazione o collateralizzazione.

Restano incerti la dimensione futura netta, il decay recente, la trasferibilita fuori da
SPX, la migliore stima P e la capacita richiesta nei crash. La progettazione futura deve
quindi scegliere esplicitamente mercato e componente, separare fenomeno da strumento,
misurare ex ante ed ex post con orizzonti coerenti, e trattare costi, margini e tail risk
come requisiti economici. Questa teoria non prescrive segnali, soglie o regole di trading.

## 16. Ipotesi falsificabili

| ID | Ipotesi e fondamento | Evidenza di supporto / falsificazione | Confondenti, dati, orizzonte | Fonte |
|---|---|---|---|---|
| H1 | Su indici liquidi `E^Q[QV] > E^P[QV]` in media, per domanda assicurativa | Supporto: differenza positiva e significativa; falsifica: non positiva robustamente | Modello P, overlap; strip/variance strike e RV, matched tenor | ricerca esterna |
| H2 | Il premio persiste ma varia nel tempo | Supporto: media positiva in sottoperiodi; falsifica: dipende da un solo episodio/decennio | Break strutturali; lungo campione | nuova formulazione derivante dal merge |
| H3 | Un'esposizione diretta conserva rendimento netto economicamente positivo | Supporto: P&L dopo spread, hedge, collateral, capitale; falsifica: netto non positivo | Selection bias, funding; quote eseguibili | nuova formulazione derivante dal merge |
| H4 | Il premio non e stabile in tutti i regimi | Supporto: differenze condizionali; falsifica: coefficienti invarianti con potenza adeguata | Endogeneita regime; campione multi-crisi | ricerca esterna |
| H5 | La remunerazione e legata a downside/jump/tail | Supporto: premio concentrato in componenti downside e perdite di coda; falsifica: nessuna relazione | Stima jump, rare events; surface e intraday | entrambe |
| H6 | La diversificazione ordinaria non elimina il tail risk sistemico | Supporto: correlazioni/perdite convergono in crisi; falsifica: ES migliora stabilmente senza perdere premio | Esposizioni nascoste; mercati/componenti | nuova formulazione derivante dal merge |
| H7 | Livello VIX o IV/RV passata non predicono monotonamente il premio futuro | Supporto: relazione instabile/non monotona; falsifica: previsione monotona robusta OOS | Regime, horizon; VIX, forecast P, P&L | ricerca esterna |
| H8 | Il premio e piu forte/omogeneo su indici che su single names | Supporto: differenziale cross-section; falsifica: stesso premio dopo controlli | Earnings, liquidita; index e component options | ricerca esterna |
| H9 | Strumenti diversi generano premi e rischi non equivalenti | Supporto: decomposizioni P&L divergenti; falsifica: esposizioni replicate dopo controlli | Basis/roll/hedging; options, VIX, variance | nuova formulazione derivante dal merge |
| H10 | Il rendimento non e alpha dopo fattori non lineari e costi | Supporto: intercetta nulla; falsifica: residuo positivo robusto dopo tail/liquidity/convexity | Fattori incompleti, data mining; P&L e factor data | entrambe |

Nessuna ipotesi contiene parametri operativi. H1-H2 verificano il fenomeno; H3-H10
determinano investibilita, rischio e classificazione.

## 17. Questioni ancora aperte

- Quale dominio e obiettivo di business: varianza SPX, assicurazione downside SPY o altra
  componente? La letteratura non rende questi oggetti equivalenti.
- Quale disponibilita reale di strumenti, capitale, margini e dati e compatibile con
  Alembic? E una decisione di business/investibilita, non teorica.
- Quanto del premio resta netto nel periodo recente e dopo shock non presenti nel campione?
- Quale modello/ensemble per `E^P[QV]` e sufficientemente robusto senza data mining?
- Quale quota del rendimento deriva da jump, correlation, liquidity e intermediary risk?
- Il decay recente e strutturale, ciclico o dipendente dalla microstruttura?
- Quale perdita di coda e tempo di recupero sono accettabili per il prodotto?
- La progettazione funzionale dovra definire payoff e benchmark; la validazione quantitativa
  dovra risolvere H1-H10. Nessuna di queste risposte puo essere dedotta da un backtest proxy.

## 18. Prerequisiti per la fase successiva

Questa checklist e un gate analitico del documento, non un tracker di stato della roadmap.

| Requisito | Stato | Evidenza disponibile | Attivita necessaria | Blocco |
|---|---|---|---|---|
| Definizione Q-P e segno condivisi | soddisfatto | Sezioni 3 e 15; approvazione PO 2026-07-15 | Nessuna | Risolto |
| Terminologia varianza/volatilita coerente | soddisfatto | Glossario consolidato; approvazione PO | Adozione nei futuri documenti | Risolto |
| Ipotesi falsificabili | soddisfatto | H1-H10 | Approvare per la validazione | Alto |
| Rischi strutturali espliciti | soddisfatto | Sezione 10 | Definire risk appetite in fase business | Alto |
| Distinzione premio/alpha | soddisfatto | Sezione 8; classificazione PO come alternative beta | Nessuna | Risolto |
| Perimetro strumenti coerenti | soddisfatto teoricamente | SPX 30d; listed/cleared; sezione 7 | Feasibility di variance futures e replica SPX | Bloccante per il design |
| Evidenza empirica aggiornata | parzialmente soddisfatto | Sezione 5 | Quantificare il periodo recente nella fase empirica | Alto |
| Convenzione di misura/orizzonte | soddisfatto | Sezione 6 | Tradurla in data requirements, non ancora in codice | Alto |
| Investibilita netta/capitale | non valutabile | Letteratura esterna | Studio successivo su accesso, costi e margini | Bloccante per strategia, non per design |
| Versione teorica consolidata | soddisfatto | Questo documento approvato dal PO | Nessuna | Risolto |
| Registro differenze | soddisfatto | Sezioni 11-14 | Nessuna attivita teorica ulteriore | Basso |
| Decisione di business/risk appetite | soddisfatto teoricamente | Registro PO nella sezione 19 | Verifica di fattibilita economica | Bloccante per il design |

## 19. Gate teorico

**CONDITIONAL PASS - procedere solo dopo ulteriori verifiche teoriche o documentali.**

Prima della progettazione funzionale devono essere approvati: (1) definizione seller-sign
Q-P in varianza; (2) classificazione come risk premium e non alpha presunto; (3) H1-H10;
(4) scelta business del primo dominio tra esposizione diretta alla varianza e premio
downside con opzioni; (5) accettazione esplicita che tail risk, margini e liquidita sono
parte economica del payoff. L'output da approvare e la sezione 15, con il registro M01-M12.
L'approvazione documentale e le decisioni teoriche sono state completate dal PO il
2026-07-15. Resta un blocco di investibilita: prima del design funzionale deve esistere
una feasibility `GO` su strumenti listed, accesso IBKR, liquidita, dati, payoff
defined-loss e rispetto dei limiti di rischio. Non e richiesto ne ammesso usare un
risultato di backtest interno come sostituto di tale verifica.

### Registro delle decisioni PO del 2026-07-15

- S2 studia il **variance risk premium di indice**, con SPX e 30 giorni di calendario
  come dominio iniziale.
- Definizione normativa approvata: `E^Q[QV] - E^P[QV]`, seller-sign. La misura del
  fenomeno, la verifica ex post e il P&L investibile restano oggetti separati.
- Classificazione approvata: alternative beta assicurativa/risk premium, non alpha per
  definizione. Crash, jump, convexity, correlazione, liquidita e capitale sono rischi
  inseparabili.
- Perimetro investibile limitato a strumenti listed/cleared accessibili tramite broker;
  OTC escluso dal deployment. Candidati: Cboe variance futures, replica SPX e, come
  approssimazione secondaria, portafogli SPX delta-hedged.
- Obiettivo primario: rendimento assoluto netto e capital-adjusted. L'income non e un
  obiettivo. Benchmark sistematico e overlay condizionale sono due livelli separati.
- Sleeve ring-fenced; perdita massima contrattuale pari al 2% del NAV Alembic; margine
  stressato non oltre il 50% del capitale della sleeve. Il candidato investibile deve
  avere perdita finita per costruzione; il benchmark short variance puro resta teorico.
- Se nessuno strumento soddisfa contemporaneamente purezza, liquidita e perdita limitata,
  la decisione e `NO-GO`: nessuna sostituzione con proxy economicamente diverse.
- IBKR e la venue primaria da verificare. Dati professionali possono essere acquistati
  soltanto dopo confronto vendor e nuova approvazione del budget. La misura economica
  primaria e pre-tax; la fiscalita italiana costituisce un gate separato.
- Campione minimo: dati SPX negoziati dal 1996 al presente, con 2008, febbraio 2018,
  marzo 2020 e 2022 obbligatori; 1987 come stress ricostruito separato; sottoperiodi
  pre/post 2010 e pre/post 2020.
- Metriche e soglie devono essere preregistrate. Sharpe e rendimento medio non bastano;
  servono tail, drawdown/recovery, margini, rovina, concentrazione, sottoperiodi e costi.
- Overlay iniziale limitato a variabili direttamente connesse al VRP. LLM, sentiment e
  filtri news sono esclusi. Eventi macro restano nel benchmark e sono analizzati come
  sottocampioni. La stima P deve essere robusta a piu forecast.
- Sono richiesti gate standalone e incrementale sul portafoglio. Allocazione derivata dal
  budget di perdita, non dal precedente 30%. Promozione: offline, shadow, IBKR paper,
  review umana, eventuale live minimo; nessuna promozione automatica.
- Prossimo deliverable autorizzato: feasibility study senza codice e senza acquisti.
  H1-H10 e M01-M12 sono approvati.

## Domande finali obbligatorie

1. **Il fenomeno e reale?** Si, soprattutto come variance risk premium medio su indici azionari liquidi; non e universale ne stabile.
2. **Definizione corretta?** `E^Q[QV]-E^P[QV]`, seller-sign, su stesso payoff e orizzonte.
3. **VRP vs variance RP?** Il primo e spesso usato genericamente; rigorosamente un payoff in volatilita non coincide con uno in varianza per Jensen e vol-of-vol.
4. **IV-RV basta?** No. E al massimo una proxy ex post con orizzonti e convenzioni allineati.
5. **Volatilita o varianza?** Varianza per la definizione e replica teorica; volatilita per comunicazione o payoff specifici.
6. **Alpha o compensazione?** Di default compensazione per rischi sistematici/alternative beta assicurativa.
7. **Rischi remunerati?** Crash, salti, downside, convexity, correlazione, liquidita, funding, hedging, modello e capacita intermediaria.
8. **Strumenti piu coerenti?** Variance swap/replica model-free di indice; poi opzioni indice delta-hedged. Short put e VIX products sono esposizioni miste.
9. **Stabile tra mercati/regimi?** No. L'evidenza e piu forte sugli indici USA e varia per regime, scadenza e componente.
10. **Sopravvive a costi, hedging e code?** Esiste evidenza storica, ma non prova generale e aggiornata di rendimento netto capital-aware; e una questione bloccante da testare.
11. **Parti interne corrette?** Insurance demand, tail compensation, skew negativo, costi/margini e distinzione premio-alpha in D4.
12. **Parti incomplete/errate?** IV-RV come definizione, 3-4 punti universali, stress monotono, persistenza assoluta, equivalenza long-SPY/short-put e OTM put come mispricing.
13. **Contributi interni da mantenere?** Linguaggio assicurativo, enfasi sulla sopravvivenza, costi reali e necessita di separare short put da alpha.
14. **Differenze principali?** Misura Q-P, varianza vs volatilita, strumenti, intermediari/correlazione, instabilita e recente decay mancavano internamente.
15. **Come risolte?** Con M01-M12, privilegiando rigore, evidenza replicabile e formulazioni falsificabili; i contributi interni validi sono confluiti nel merge.
16. **Valore aggiunto reale?** Si: definizione normativa, gerarchia delle misure/strumenti, limiti recenti, rischi completi e dieci ipotesi testabili.
17. **Assunzioni vietate?** IV=aspettativa P; VRP=IV-RV passata; premio=alpha; VIX alto=vendita conveniente; collateral=assenza di coda; proxy equity=VRP; spread costante.
18. **Ipotesi da testare prima del design?** H1-H10, con priorita a esistenza matched-horizon, investibilita netta, tail linkage e non-equivalenza degli strumenti.
19. **Punti incerti?** Premio netto recente, dominio ottimale, stima P, decay, capacita nei crash e risk appetite.
20. **Autorizza la progettazione?** Solo condizionatamente all'approvazione dei cinque punti del gate e alla scelta del dominio business.

## Sintesi in pochi minuti

Il VRP non e semplicemente "VIX meno volatilita realizzata". La formulazione corretta
confronta il prezzo risk-neutral della **varianza futura** con la sua aspettativa sotto la
distribuzione reale, sullo stesso orizzonte. E un premio assicurativo documentato, piu
robusto sulle opzioni di indice, che remunera soprattutto crash, salti, correlazione,
convexity, liquidita e capitale. Per questo non e alpha per definizione.

La documentazione Alembic aveva colto assicurazione e tail risk, ma trasformava troppo
rapidamente il fenomeno in una short put, in uno spread fisso di 3-4 punti e perfino in
una proxy long-SPY. Queste equivalenze sono eliminate. Variance exposure, short put,
VIX futures e dispersion sono strumenti differenti con rischi differenti.

La teoria merita investimento di ricerca, non ancora capitale o sviluppo operativo. Il
passaggio successivo e condizionato all'approvazione della teoria, alla scelta esplicita
del payoff/mercato e all'accettazione che costi, margini e perdite di coda sono parte del
premio. Poi H1-H10 dovranno distinguere premio statistico, rendimento investibile e
eventuale alpha residuo.
