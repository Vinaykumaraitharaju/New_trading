# Prediction Archive Guide

This system is now designed to stop guessing blindly and start building proof from its own predictions.

The important idea is simple:

1. The scanner makes a pre-trade prediction.
2. The prediction is archived with fixed entry, SL, T1, and T2.
3. Live prices update that archived prediction.
4. The archive marks what really happened.
5. Analytics shows which setup types, symbols, and scanner bands are actually working.

## Where To See It

Open:

```text
/pretrade/archive
```

API:

```text
/api/pretrade/archive
```

The Pre-Trade Scanner page also has an `Archive` link.

## What Gets Archived

Every scanner setup stores a row in `pretrade_predictions`.

Important stored fields:

- `symbol`
- `direction`
- `setup_type`
- `regime`
- `scanner_band`
- `initial_price`
- `entry_trigger`
- `stop_loss`
- `target1`
- `target2`
- `score`
- `target_probability`
- `relative_opportunity`
- `state`
- `result`
- `t1_hit`
- `t2_hit`
- `mfe_points`
- `mae_points`

The first valid levels are frozen. If the scanner refreshes and shows the same symbol/setup/direction again, the archive keeps the original entry, SL, T1, and T2. That prevents moving-target predictions.

## Prediction Lifecycle

### 1. WATCHING

The scanner found a setup, but price has not reached entry yet.

Example:

```text
Symbol: RELIANCE
Direction: BULLISH
Entry: 2948.25
SL: 2928.80
T1: 2972.40
T2: 2996.55
Live price: 2941.10
State: WATCHING
Result: OPEN
```

Meaning:

Price is still below entry. The setup is only being watched.

### 2. ENTERED

Price reaches the entry trigger.

Example:

```text
Entry: 2948.25
Live price: 2949.00
State changes: WATCHING -> ENTERED
```

Now the archive starts judging target and stop outcomes.

### 3. T1 Hit

For bullish setup:

```text
Live price >= T1
```

For bearish setup:

```text
Live price <= T1
```

Example:

```text
Entry: 2948.25
T1: 2972.40
Live price: 2973.00
t1_hit: Yes
State: ENTERED
Result: OPEN
```

Meaning:

The setup reached first target, but it is still open unless T2, SL, or time exit happens.

### 4. T2 Hit

Example:

```text
Entry: 2948.25
T1: 2972.40
T2: 2996.55
Live price: 2997.00
State: CLOSED
Result: T2_HIT
t1_hit: Yes
t2_hit: Yes
```

Meaning:

This was a strong successful prediction.

### 5. SL Hit

Example:

```text
Entry: 2948.25
SL: 2928.80
Live price: 2928.00
State: CLOSED
Result: SL_HIT
```

Meaning:

Prediction failed after entry.

### 6. Missed Entry

If price never reaches entry before expiry:

```text
State: CLOSED
Result: MISSED_ENTRY
```

Meaning:

The scanner saw a possible setup, but it never became tradable.

### 7. Time Exit

If price entered but did not hit T2 or SL before max hold time:

```text
State: CLOSED
Result: TIME_EXIT
```

If T1 was hit first:

```text
State: CLOSED
Result: TIME_EXIT_T1
```

Meaning:

The setup worked partially or stalled.

## Bullish Example

Prediction:

```text
Symbol: TEST
Direction: BULLISH
Live price: 99.50
Entry: 100.00
SL: 98.80
T1: 101.00
T2: 102.00
Band: trade-ready
```

Price movement:

```text
100.10 -> entry triggered
101.20 -> T1 hit
102.20 -> T2 hit
```

Final archive:

```text
State: CLOSED
Result: T2_HIT
T1: Yes
T2: Yes
```

Interpretation:

Good prediction. This setup type and band should gain trust if this repeats across more samples.

## Bearish Example

Prediction:

```text
Symbol: TEST
Direction: BEARISH
Live price: 200.00
Entry: 198.50
SL: 201.20
T1: 196.80
T2: 195.00
Band: near-trigger
```

Price movement:

```text
198.40 -> entry triggered
196.70 -> T1 hit
195.00 -> T2 hit
```

Final archive:

```text
State: CLOSED
Result: T2_HIT
T1: Yes
T2: Yes
```

For bearish trades, lower prices are favorable.

## Failed Example

Prediction:

```text
Symbol: FAIL
Direction: BULLISH
Entry: 50.00
SL: 49.00
T1: 51.00
T2: 52.00
```

Price movement:

```text
50.10 -> entry triggered
48.90 -> SL hit
```

Final archive:

```text
State: CLOSED
Result: SL_HIT
T1: No
T2: No
```

Interpretation:

Bad prediction. If the same setup type repeatedly does this, it should be downgraded or avoided.

## How To Read Archive Metrics

### Total Predictions

All scanner calls archived.

High number means the system is collecting evidence.

### Entered Predictions

How many predictions actually touched entry.

If this is low, triggers are too far or scanner is too early.

### Entry Conversion %

```text
entered_predictions / total_predictions
```

Use this to know if the scanner is finding realistic entry levels.

### T1 Hit Rate

```text
T1 hits / entered predictions
```

Good for measuring whether first target is realistic.

### T2 Hit Rate

```text
T2 hits / entered predictions
```

Good for measuring real follow-through.

### SL Hit Rate

```text
SL hits / entered predictions
```

If this is high, the setup is dangerous or entry confirmation is weak.

## How To Decide If A Setup Is Useful

Use this rough guide after enough samples.

### Good Setup

```text
Entries: 10+
T1 hit rate: 55%+
T2 hit rate: 30%+
SL hit rate: below 35%
```

Meaning:

Can be considered for real trading rules.

### Scalp Only

```text
T1 hit rate: high
T2 hit rate: low
SL hit rate: controlled
```

Meaning:

Book early. Do not expect full follow-through.

### Avoid

```text
SL hit rate: 50%+
T1 hit rate: weak
T2 hit rate: weak
```

Meaning:

Do not promote this setup until conditions are stricter.

### Too Early

```text
Entry conversion: low
Missed entries: high
```

Meaning:

Scanner is finding ideas too early or entry is too far from live price.

## What We Still Need To Make It Better

The archive is the foundation. It needs live market days.

Minimum useful evidence:

```text
5 to 10 full trading days
100+ archived predictions
30+ entered predictions
```

Better evidence:

```text
20 trading days
500+ archived predictions
150+ entered predictions
```

After that, we can tune:

- Which bands deserve promotion.
- Which setup types should be blocked.
- Which symbols behave better.
- Whether T1/T2/SL distances are too large or too small.
- Whether the model is better for bullish or bearish setups.
- Whether scanner output is only useful during certain time windows.

## Practical Daily Workflow

1. Start Kotak live feed.
2. Open `/pre-trade-scanner`.
3. Let it run during market hours.
4. Open `/pretrade/archive`.
5. Watch entries and outcomes build during the day.
6. After market close, check:

```text
Entry Conversion %
T1 Hit Rate
T2 Hit Rate
SL Hit Rate
By Setup table
By Symbol table
```

Do not judge from one trade. Judge from repeated behavior.

## Current Truth

Before this archive, the scanner was mostly a structured watchlist.

After this archive, it becomes measurable.

It will only become a reliable predictor after we collect enough archived outcomes and use those results to tighten the scanner rules.

