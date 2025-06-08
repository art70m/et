import ccxt
import pandas as pd
from datetime import datetime
import time

# ===== اتصال به CoinEx Futures (فقط برای اجرا) =====
coinex = ccxt.coinex({
    'apiKey': '93CD9AC0AAC04CB397C6BC423FF0E2D1',
    'secret': '66CD478B4E0C701942B6AB1219536588A1752CCB4BE39093',
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})
coinex_symbol = 'ETH/USDT:USDT'
leverage = 8

# ===== اتصال به LBank برای دریافت داده =====
lbank = ccxt.lbank({'enableRateLimit': True})
lbank_symbol = 'ETH/USDT'
timeframe = '1m'

# ===== تنظیمات استراتژی =====
min_sl_percent = 0.003
min_tp_percent = 0.01
usdt_balance_to_use = None

position = None
entry_price = None
sl = None
tp = None
trade_in_current_trend = False
last_trend = None

def calculate_vwma(df, length):
    s = df.tail(length)
    return (s['close'] * s['volume']).sum() / s['volume'].sum() if len(s) == length and s['volume'].sum() else None

def fetch_ohlcv():
    o = lbank.fetch_ohlcv(lbank_symbol, timeframe, limit=700)
    return pd.DataFrame(o, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def get_usdt_balance():
    bal = coinex.fetch_balance()
    return float(bal['total']['USDT']) if 'USDT' in bal['total'] else 0.0

def place_market(side, amount):
    return coinex.create_market_order(coinex_symbol, side, amount)

# تنظیم اهرم در CoinEx
coinex.load_markets()
coinex.set_margin_mode('cross', coinex_symbol, {'leverage': leverage})

print("🚀 استراتژی اجرا شد (داده از LBank، معامله در CoinEx)")

while True:
    df = fetch_ohlcv()
    price = df['close'].iloc[-1]
    balance = get_usdt_balance()
    if usdt_balance_to_use is None:
        usdt_balance_to_use = balance

    print(f"\n[{datetime.now()}] قیمت: {price:.2f} | موجودی: {balance:.2f} | استفاده‌شده: {usdt_balance_to_use:.2f}")

    vwma_666 = calculate_vwma(df, 666)
    vwma_177 = calculate_vwma(df, 177)
    if not vwma_666 or not vwma_177:
        print("⏳ در حال جمع‌آوری داده از LBank...")
        time.sleep(60)
        continue

    upper = vwma_177 * 1.0018
    lower = vwma_177 * 0.9982
    trend = 'bullish' if lower > vwma_666 else 'bearish' if upper < vwma_666 else 'neutral'
    print(f"🔍 روند: {trend.upper()} | VWMA666: {vwma_666:.2f}, VWMA177: {vwma_177:.2f}")

    if trend != last_trend:
        trade_in_current_trend = False
        last_trend = trend

    if not position and trend in ['bullish', 'bearish'] and not trade_in_current_trend:
        recent = df.tail(20)
        entry, stop, take, side = None, None, None, None

        if trend == 'bullish':
            lowest = recent['low'].min()
            entry = lowest + 0.618 * (price - lowest)
            stop = lowest
            take = entry * (1 + min_tp_percent)
            if (entry - stop) / entry >= min_sl_percent:
                side = 'buy'
        else:
            highest = recent['high'].max()
            entry = highest - 0.618 * (highest - price)
            stop = highest
            take = entry * (1 - min_tp_percent)
            if (stop - entry) / entry >= min_sl_percent:
                side = 'sell'

        if side and entry:
            amount = round((usdt_balance_to_use * leverage) / entry, 4)
            min_amt = coinex.market(coinex_symbol)['limits']['amount']['min']
            if amount >= min_amt:
                print(f"⚠️ شرایط ورود → {trend.upper()} — قیمت: {entry:.2f}, حجم: {amount}")
                o = place_market(side, amount)
                print(f"✅ سفارش {side.upper()} ثبت شد:", o)
                position = trend
                entry_price = entry
                sl = stop
                tp = take
                trade_in_current_trend = True

    if position:
        current = price
        should_exit = (
            (position == 'bullish' and (current >= tp or current <= sl)) or
            (position == 'bearish' and (current <= tp or current >= sl))
        )
        if should_exit:
            exit_side = 'sell' if position == 'bullish' else 'buy'
            o = place_market(exit_side, amount)
            print(f"💥 خروج از {position.upper()} — قیمت: {current:.2f}", o)
            position = None

    time.sleep(60)
