#!/usr/bin/env python3
"""Audit the price sources behind the IC Exchange Rate Canister (XRC).

XRC reads each exchange candle's OPEN as the rate and never looks at volume, so a
delisted market that forward-fills a flat, zero-volume candle is ingested as a live
quote. Crypto.com's USDT_USDC did exactly this: frozen at open 0.995 with zero
volume since 2022-10-31, yet still counted as a healthy source for years.

    python xrc_audit.py             # liveness: per source, the last day it actually traded
    python xrc_audit.py --backtest  # USDT/USDC median, with vs without a zero-volume gate

Targets the USDT/USDC stablecoin anchor (where the dead source lived). It hits the
same public endpoints XRC uses, reconstructed from dfinity/exchange-rate-canister.
Stdlib only, no paging: one request per source (months to years, depending on venue).
The rate XRC stores is a deterministic median over these candles, so the backtest
faithfully reconstructs what a zero-volume gate would have changed.
"""
import json, sys, time, urllib.request, statistics, datetime

DAY = 86400


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    return json.load(urllib.request.urlopen(req, timeout=40))


def day(ts_seconds):
    return datetime.datetime.utcfromtimestamp(ts_seconds).strftime("%Y-%m-%d")


# One row per XRC stablecoin source. `url(daily)` builds the exact request; `rows`
# yields (unix_seconds, open, base_volume) with the pair oriented to USDT priced in
# USDC (venues quoted USDC/USDT are inverted inline, so every source is comparable).
SOURCES = {
    "Coinbase": dict(
        url=lambda d: f"https://api.exchange.coinbase.com/products/USDT-USDC/candles?granularity={DAY if d else 60}",
        rows=lambda j: ((int(c[0]), float(c[3]), float(c[5])) for c in j)),
    "KuCoin": dict(
        url=lambda d: f"https://api.kucoin.com/api/v1/market/candles?symbol=USDC-USDT&type={'1day' if d else '1min'}",
        rows=lambda j: ((int(c[0]), 1 / float(c[1]), float(c[5])) for c in j["data"])),
    "OKX": dict(
        url=lambda d: f"https://www.okx.com/api/v5/market/history-candles?instId=USDC-USDT&bar={'1D' if d else '1m'}",
        rows=lambda j: ((int(c[0]) // 1000, 1 / float(c[1]), float(c[5])) for c in j["data"])),
    "Gate.io": dict(
        url=lambda d: f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair=USDC_USDT&interval={'1d' if d else '1m'}",
        rows=lambda j: ((int(c[0]), 1 / float(c[5]), float(c[6])) for c in j)),
    "MEXC": dict(
        url=lambda d: f"https://api.mexc.com/api/v3/klines?symbol=USDCUSDT&interval={'1d' if d else '1m'}&limit=1000",
        rows=lambda j: ((int(c[0]) // 1000, 1 / float(c[1]), float(c[5])) for c in j)),
    "Poloniex": dict(
        url=lambda d: f"https://api.poloniex.com/markets/USDT_USDC/candles?interval={'DAY_1' if d else 'MINUTE_1'}&limit=500",
        rows=lambda j: ((int(c[12]) // 1000, float(c[2]), float(c[5])) for c in j)),
    "Bitget": dict(
        url=lambda d: f"https://api.bitget.com/api/v2/spot/market/history-candles?symbol=USDCUSDT&granularity={'1day' if d else '1min'}&limit=200&endTime={int(time.time() * 1000)}",
        rows=lambda j: ((int(c[0]) // 1000, 1 / float(c[1]), float(c[5])) for c in j["data"])),
    "Digifinex": dict(
        url=lambda d: f"https://openapi.digifinex.com/v3/kline?symbol=USDC_USDT&period={'1D' if d else '1'}",
        rows=lambda j: ((int(c[0]), 1 / float(c[5]), float(c[1])) for c in j["data"])),
    "Crypto.com": dict(
        url=lambda d: f"https://api.crypto.com/exchange/v1/public/get-candlestick?instrument_name=USDT_USDC&timeframe={'1D' if d else '1m'}&count=300",
        rows=lambda j: ((int(c["t"]) // 1000, float(c["o"]), float(c["v"])) for c in j["result"]["data"])),
}


def daily(source):
    """{date: (open_usdt_in_usdc, volume)} from one daily request."""
    return {day(ts): (price, vol) for ts, price, vol in source["rows"](fetch(source["url"](True)))}


def audit():
    today = day(time.time())
    print(f"{'source':<12}{'last traded':<14}{'days ago':<10}{'recent open':<13}status")
    for name, src in SOURCES.items():
        try:
            d = daily(src)
            traded = sorted(k for k, (p, v) in d.items() if v > 0)
            recent = d[max(d)][0]
            if not traded:
                print(f"{name:<12}{'never':<14}{'-':<10}{recent:<13.4f}DEAD (no volume in {len(d)}d window)")
                continue
            ago = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(traded[-1])).days
            status = "live" if ago <= 3 else f"STALE ({ago}d, zero volume)"  # 3d grace: some history endpoints lag the forming candle
            print(f"{name:<12}{traded[-1]:<14}{ago:<10}{recent:<13.4f}{status}")
        except Exception as e:
            print(f"{name:<12}error: {e}")


def backtest():
    data = {}
    for name, src in SOURCES.items():
        try:
            data[name] = daily(src)
        except Exception as e:
            print(f"skipping {name}: {e}")
    days = sorted(set().union(*data.values()))
    fired, deltas, dropped = 0, [], set()
    for d in days:
        quotes = [(p, v, n) for n, m in data.items() if d in m for (p, v) in [m[d]] if p > 0]
        live = [p for p, v, n in quotes if v > 0]
        if len(quotes) < 3 or len(live) < 2:
            continue
        ungated = statistics.median([p for p, v, n in quotes])
        gated = statistics.median(live)
        if ungated != gated:
            fired += 1
            dropped |= {n for p, v, n in quotes if v == 0}
        deltas.append(abs(gated - ungated) * 1e4)  # basis points
    n = len(deltas)
    print(f"USDT/USDC daily median, {n} days {days[0]}..{days[-1]}, {len(SOURCES)} sources")
    print(f"zero-volume gate changes the rate on {fired}/{n} days; sources it drops: {sorted(dropped)}")
    print(f"|median shift| from the gate: median {statistics.median(deltas):.2f} bps, max {max(deltas):.2f} bps")


if __name__ == "__main__":
    backtest() if "--backtest" in sys.argv else audit()
