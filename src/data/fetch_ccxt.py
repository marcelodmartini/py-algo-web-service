# src/data/fetch_ccxt.py
from __future__ import annotations

import ccxt
import pandas as pd
from typing import Optional

# Mapa de timeframes válidos según exchange. Para Binance basta este set común.
VALID_TIMEFRAMES = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M"
}


def ccxt_download(
    symbol: str,
    exchange_id: str = "binance",
    timeframe: str = "1h",
    limit: int = 1000,
    since_ms: Optional[int] = None,
) -> pd.DataFrame:
    """
    Descarga OHLCV para pares cripto (BTC/USDT).
    Devuelve DataFrame normalizado: ['datetime','open','high','low','close','volume'].
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(
            f"Timeframe '{timeframe}' no soportado. Válidos: {sorted(VALID_TIMEFRAMES)}")

    # Instanciar exchange con CCXT
    klass = getattr(ccxt, exchange_id, None)
    if not klass:
        raise ValueError(f"Exchange '{exchange_id}' no existe en CCXT.")

    exchange = klass({"enableRateLimit": True})

    # Asegurar que el par exista (lanza excepción si no)
    markets = exchange.load_markets()
    if symbol not in markets:
        raise ValueError(
            f"Symbol '{symbol}' no existe en {exchange_id}. ¿Está bien escrito?")

    # Descargar OHLCV
    ohlcv = exchange.fetch_ohlcv(
        symbol=symbol, timeframe=timeframe, since=since_ms, limit=limit)
    if not ohlcv:
        raise RuntimeError(f"Sin datos OHLCV de {symbol} en {exchange_id}.")

    # Formatear DataFrame
    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(
        df["timestamp"], unit="ms", utc=True).dt.tz_convert("UTC")
    df = df[["datetime", "open", "high", "low", "close", "volume"]]

    return df
