# Reaction Alpha

An Indian-equities research workspace: live Kotak observations, immutable timed
forecasts, separate paper-trade execution, and prospective learning comparisons.
No model in this project guarantees direction, target timing, or profit.

## Daily workflow

1. Open Scanner and check feed status and the full date of the last verified trade.
2. Choose today's IST window: 09:20, 09:40, then every 20 minutes through 15:20.
3. Developing candidates are provisional, not trade-ready calls. Only the next
   window gets a rolling-price preview; later windows remain scheduled.
4. At publication, up to five qualifying candidates get fixed entry, stop, T1,
   T2, source evidence, strategy version and stable ID. Empty batches are valid.
5. Open "Why these levels?" for the formula, evidence gaps and recorded timeline.
6. Use History for archived forecasts. A forecast is not a paper trade or fill.

T1 normally expires after 10 minutes and T2 after 20. Both stop at 15:30 IST.
There is no new 15:30 entry batch. Dates outside the supported calendar are not
guessed. Published deadlines are evaluation windows, not estimated arrival times.

## Implemented Evidence

NSE EQ mover discovery is separate from the small live trading subscription.
During supported open sessions a background worker scans batches of up to 20
instruments from the authenticated Kotak NSE cash master with a five-second
pause. Only same-session, dated quotes with valid high/low/previous close count.
The current session high or low may show a threshold that the latest price no
longer meets. These retrospective discoveries are not forecast wins, fills, or
timestamped first touches. Coverage and errors are shown alongside results.

**Daily +/-4% study:** Scanner lists the first verified touch of each boundary
against the stock's same-session reference close, even if the move reverses.
Coverage is the monitored live feed, not the entire exchange. First observed
already beyond the boundary is reported, not credited as a forecast. Fresh NIFTY
comparison and available timestamped SEC filing metadata are context, not a
causal news model. Indian company news coverage is not comprehensive.

On first observation inside the band, freeze a shadow forecast for the first
observed boundary through session close. Group by starting half-hour and starting
move (below -1%, within 1%, above +1%, inclusive at the outer boundaries).
Use the most frequent label from the preceding 180 days only after 30 measured
examples across five sessions; abstain on ties. Include neither-touch controls
only with no observed gap over 45 seconds and coverage into the final 15 seconds.
Unobserved gaps are not negative examples. Selective coverage and survivorship
can bias results; compare prospective predictions to always-neither before
considering promotion. Stored locally in the persistent paper database.

History > Performance now includes a Direction scorecard across archived sessions,
separated by source. New live forecasts freeze NIFTY and stock five-minute
continuation baselines when timestamped coverage is available. Each uses a
neutral band of +/-0.2%. The existing 30-minute trial measures stock movement
from its first eligible post-publication trade, independently of entry. Only
measured pairs that disagree count toward scanner vs baseline wins. This is
prospective evaluation, not model training or a cost-adjusted trading return.

Each new timed edition archives the equity subscription count, usable five-minute
quotes, qualified setups, published picks, and first exclusion reason per omitted
symbol. Zero verified observations means none reached the edition evaluator, not
necessarily that the exchange saw no trades. Historical reasons are not backfilled.

Scanner labels market direction from the three index changes versus previous
close. At least two fresh indices must agree for Bullish/Bearish. Conflicting
readings remain visible. This describes the indices, not the cause of the move
or the performance of every stock; it does not change stock entry rules.

| Input | How it is used | Limitation |
| --- | --- | --- |
| Timestamped Kotak prices | Range, pressure, breakout entry and barrier observations | Feed gaps make outcomes unresolved |
| Bid/ask spread | Reject narrow/noisy ranges; minimum risk distance | Not a complete order book or executable fill |
| Five-minute NIFTY move | Reject strongly opposing published setups | Missing benchmark is not positive confirmation |
| Earlier same-slot/direction outcomes | Frozen counts and experimental shadow rank | Small samples are not calibrated probabilities |
| ECB daily FX, Fed release, optional SEC filings | Dated external context | Not real-time Indian company sentiment |

T1 = one risk unit; T2 = two risk units. Risk is max(half the observed five-minute
range, four spreads, INR 0.05). Levels are research barriers, not exchange-rounded
orders. We have not demonstrated that this rule beats a baseline after costs.

## Learning Without Forgetting

- The existing direction-experience store and timed-edition ledger are distinct.
- Timed editions are persisted in the configured paper SQLite database. Git pulls
  do not erase this file. EC2 persistence depends on retaining its EBS volume and
  database path; backups remain necessary.
- Optional Turso synchronization covers the existing direction experience store,
  **not** the timed-edition ledger. Do not assume it backs up all app history.
- The Learning ledger evaluates the last 90 days of earlier sessions for the
  same rule version. Today's outcomes cannot train today's published decisions.
- Entered trades, never-entered calls and insufficient data are reported separately.
- Historical time-to-T1 uses successful entries only and is labelled survivor-only,
  not a forecast ETA. Wilson intervals show sampling uncertainty, not next-trade odds.
- Original and shadow top picks are compared prospectively. No automatic promotion
  or threshold tuning to fill empty categories is allowed.

## Improvement Contract

Before changing a rule: record its hypothesis, required inputs, version, evaluation
period, baseline, failure cases and rollback criteria here. Keep original outcomes.
Use chronological holdouts and transaction costs before any promotion. Never train
on revised announcements or prices that were unavailable at the decision time.

| Hypothesis | Required evidence | Current state / next test |
| --- | --- | --- |
| Price-pressure breakout adds value | Prospective live observations, entry-first outcomes | Collect and compare with simple breakout and market baselines |
| Past outcomes improve ranking | Paired original/shadow decisions across unseen sessions | Shadow only; no proven improvement |
| Oil shocks have company-specific effects | Dated event, actual oil move, company exposure, price already moved | Not implemented; verify free source permission and timestamp history first |
| Rate surprises affect bank/subsector returns | Expected vs actual decision, yields, bank exposure | Not implemented; a hike alone is not a universal bearish signal |
| Earnings surprise predicts continuation | Original filing timestamp, actual vs expectations, guidance, prior price move | Not implemented; profit growth alone is insufficient |
| Fast rallies reverse after exhaustion | Prospective spread, volume, failed continuation, market regime | Research hypothesis; do not automatically fade every rise |

No unsupported news input contributes a fabricated score. No 10/10 positivity or
guaranteed 5-7% move is shown. A catalyst can already be priced in. Good news and a
good entry are different questions.

## Change Log / Evidence Register

### 2026-11-18 - Upcoming windows and transparent evidence

- Replaced the stale last-edition default with today's server-dated schedule.
- Added next-window provisional candidates, frozen rationale and stable archive links.
- Extended publication through 15:20 with session-close deadlines.
- Added transition timelines and explicit restart/disconnect evidence gaps.
- Added prior-session evaluation, conditional entry statistics, uncertainty, and
  paired baseline/shadow totals. This is measurement, not proven improvement.
- Preserved scanner, inline broker login, paper trading, and original API fields.
- New UI assets are scoped to the timed-research section; no new navigation page.

## Verification

```powershell
.\.venv-kotak-verify\Scripts\python.exe -m pytest tests -q
.\.venv-kotak-verify\Scripts\python.exe tests/edition_browser.py
```

The browser test uses deterministic fixtures, not a live broker connection.
See [timed research details](docs/workspace/timed-editions.md) for source policies
and [workspace documentation](docs/workspace/README.md) for the existing app.

Local verification on 2026-11-18: 93 Python tests passed; desktop/mobile timed
research checks and the existing workspace browser regression passed. Screenshots
in `docs/workspace/screenshots/` use synthetic acceptance-test fixtures, not live
market results. The statistical interval assumes independent binomial observations;
correlated stocks/sessions can make real uncertainty wider.

## Next Highest-Value Work

1. Collect uninterrupted observations and expose per-slot coverage before judging
   prediction quality. Investigate unresolved calls before adding indicators.
2. Build cost-aware, chronological baseline comparisons using saved observations.
3. Validate a permitted Indian corporate-announcement source and historical
   timestamps. Preserve raw evidence and distinguish expected from surprise data.
4. Add event-impact models only in shadow mode, with visible supporting and
   opposing evidence, then evaluate unseen sessions before changing ranking.
5. Remove a rule only after its replacement passes regression tests and improves
   predefined held-out metrics. Maintain a rollback and the old strategy's records.
