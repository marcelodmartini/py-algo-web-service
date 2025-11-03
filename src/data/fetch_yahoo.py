# src/data/fetch_yahoo.py
from __future__ import annotations

import yfinance as yf
import pandas as pd
from typing import Optional

INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}

# Periodo sugerido por intervalo:
DEFAULT_PERIOD_BY_INTERVAL = {
    # Intradía
    "1m": "7d",
    "2m": "7d",
    "5m": "30d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "730d",
    "1h": "730d",
    # Diarios/semanales/mensuales
    "1d": "max",
    "1wk": "max",
    "1mo": "max",
}


def yahoo_download(
    symbol: str,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Descarga OHLCV de Yahoo Finance con manejo de límites intradía.
    - Para intervalos intradía, ignora start/end y usa period recomendado.
    - Fallback: si intradía vacío, baja diario 1 año para no romper el flujo.
    """
    interval = interval.lower()
    period = DEFAULT_PERIOD_BY_INTERVAL.get(interval, "max")

    if interval in INTRADAY_INTERVALS:
        df = yf.download(
            symbol,
            interval=interval,
            period=period,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    else:
        if start or end:
            df = yf.download(
                symbol,
                interval=interval,
                start=start,
                end=end,
                progress=False,
                auto_adjust=True,
                threads=False,
            )
        else:
            df = yf.download(
                symbol,
                interval=interval,
                period=period,
                progress=False,
                auto_adjust=True,
                threads=False,
            )

    # Fallback si vacío en intradía → diario 1 año
    if df is None or df.empty:
        if interval in INTRADAY_INTERVALS:
            df = yf.download(
                symbol,
                interval="1d",
                period="1y",
                progress=False,
                auto_adjust=True,
                threads=False,
            )

    if df is None or df.empty:
        raise RuntimeError(f"No data found for {symbol} on Yahoo Finance.")

    df = df.rename(columns=str.lower).reset_index()

    # normalizar columnas esperadas
    # ['datetime','open','high','low','close','adj close','volume']
    if "date" in df.columns and "datetime" not in df.columns:
        df = df.rename(columns={"date": "datetime"})
    if "adj close" in df.columns and "close" not in df.columns:
        df["close"] = df["adj close"]

    # Asegurar tipos mínimos
    needed = ["datetime", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in df.columns:
            # crear columna vacía si faltara algo, para no romper pipelines
            df[col] = pd.NA

    return df[needed]
