# xrc-source-audit

A tiny, dependency-free script that audits the exchange price sources behind the
Internet Computer **Exchange Rate Canister** (XRC, `uf6dk-hyaaa-aaaaq-qaaaq-cai`,
repo [`dfinity/exchange-rate-canister`](https://github.com/dfinity/exchange-rate-canister)).

## Why

XRC reads each exchange candle's **open** as the rate and **never looks at volume**.
A delisted market that forward-fills a flat, zero-volume candle is therefore ingested
as a live quote, indistinguishable from a real trade.

That is not hypothetical. Crypto.com's `USDT_USDC` pair (one of XRC's stablecoin
sources for anchoring USDT to USD) has had **zero volume since 2022-10-31**, frozen at
open `0.995`, and was still counted as a healthy source for ~3.5 years until proposal
#142566 removed it by hand.

This script hits the **same public endpoints XRC uses** (reconstructed from the
canister source) and checks whether any source is dead or stale, and what a simple
zero-volume gate would have changed.

## Usage

```
python3 xrc_audit.py             # per source: the last day it actually traded
python3 xrc_audit.py --backtest  # USDT/USDC median, with vs without a zero-volume gate
```

Python 3 stdlib only. No install, no keys.

### `audit` — source liveness

```
source      last traded   days ago  recent open  status
Coinbase    2026-06-26    0         0.9988       live
KuCoin      2026-06-26    0         0.9989       live
...
Crypto.com  never         -         0.9950       DEAD (no volume in 300d window)
```

### `--backtest` — would a zero-volume gate have mattered?

Reconstructs the cross-venue USDT/USDC daily median two ways: with every source
(what XRC does) and after dropping any zero-volume candle (the gate). XRC's stored
rate is a deterministic median over these candles, so this faithfully reproduces the
gate's effect.

```
USDT/USDC daily median, 500 days 2025-02-11..2026-06-26, 9 sources
zero-volume gate changes the rate on 236/500 days; sources it drops: ['Crypto.com']
|median shift| from the gate: median 0.00 bps, max 4.02 bps
```

The takeaway is deliberately honest: the gate is **correct and free** (it only ever
drops verifiably dead data), but its effect on the published rate is **small**,
because the median's outlier-robustness already isolates a *single* dead source. The
gate's real value is insurance against **correlated staleness** (several thin sources
freezing at once, which a median cannot absorb) and against the same effect at the
**minute** granularity XRC actually reads. See the writeup linked below for the full
multi-year and depeg-window analysis.

## Scope and faithfulness

- Targets the **USDT/USDC stablecoin anchor**, where the dead source lived. Point the
  instrument at `ICP_USDT` etc. to check the crypto path.
- One request per source, no paging, so the window is whatever each venue returns by
  default (months to years). For the paged multi-year reconstruction and the March
  2023 USDC-depeg case, see the writeup.
- The `SOURCES` table mirrors XRC's own per-exchange request specs; adding or removing
  a venue is one line.

## License

MIT.
