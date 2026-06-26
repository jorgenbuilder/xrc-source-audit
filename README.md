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
Crypto.com  never         -         0.9950       DEAD (no volume in 1600d window)
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

Over ~500 days of overlapping venue data, the gate would have dropped Crypto.com on
236/500 days. The daily median moved at most ~4 bps — one frozen quote at 0.995 barely
shifts a nine-source median when the other eight are trading around 0.999.

## Scope and faithfulness

- Targets the **USDT/USDC stablecoin anchor**, where the dead source lived. Point the
  instrument at `ICP_USDT` etc. to check the crypto path.
- `audit` deep-pages Crypto.com to 1600 days (API caps at 300/request). `backtest`
  uses one request per source; Poloniex's 500-day cap sets the overlap window.
- The `SOURCES` table mirrors XRC's own per-exchange request specs; adding or removing
  a venue is one line.

## License

MIT.
