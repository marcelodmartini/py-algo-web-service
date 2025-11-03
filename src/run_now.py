# src/run_now.py
from typing import List, Dict, Any
import re

from src.data.fetch_yahoo import yahoo_download
from src.data.fetch_ccxt import ccxt_download

# Alias útiles para Yahoo
YAHOO_DEFAULTS = {
    "BTC": "BTC-USD",
}

INTRADAY_DEFAULT_INTERVAL = "1h"   # podés cambiarlo a "1d" si querés diario
CCXT_DEFAULT_EXCHANGE = "binance"
CCXT_DEFAULT_TIMEFRAME = "1h"
CCXT_DEFAULT_LIMIT = 5000


def normalize_symbols(items: List[str]) -> List[str]:
    """
    - Limpia separadores visuales.
    - Mantiene slash de pares cripto (BTC/USDT).
    - Uppercase para tickers/pares.
    - Mapea atajos (BTC -> BTC-USD).
    - Dedup.
    """
    out: List[str] = []
    seen = set()

    # Paso 1: re-split defensivo si llegó "AAPL / SPY / BTC"
    exploded: List[str] = []
    for s in items:
        s = (s or "").strip()
        if not s:
            continue

        # Si hay barras pero NO parece par cripto (no "X/Y" típico), re-split
        if "/" in s and not re.search(r"^[A-Z0-9\-]+/[A-Z0-9\-]+$", s.upper()):
            parts = [p.strip() for p in s.split("/") if p.strip()]
            exploded.extend(parts)
        else:
            exploded.append(s)

    # Paso 2: normalización
    for s in exploded:
        s = s.strip().upper()

        # Si es atajo de Yahoo
        if s in YAHOO_DEFAULTS:
            s = YAHOO_DEFAULTS[s]

        # Dedup
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    return out


def run_for_symbol_list(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Orquestador: decide si cada símbolo va a Yahoo (AAPL, SPY, BTC-USD)
    o a CCXT (BTC/USDT) y devuelve resultados básicos.
    """
    results: List[Dict[str, Any]] = []

    for s in symbols:
        try:
            # Par cripto → CCXT
            if "/" in s:
                df = ccxt_download(
                    symbol=s,
                    exchange_id=CCXT_DEFAULT_EXCHANGE,
                    timeframe=CCXT_DEFAULT_TIMEFRAME,
                    limit=CCXT_DEFAULT_LIMIT,
                )
            else:
                # Ticker Yahoo → yfinance
                df = yahoo_download(
                    symbol=s, interval=INTRADAY_DEFAULT_INTERVAL)

            # Acá iría tu pipeline de indicadores, backtest y reporte.
            # Para mantenerlo genérico, retornamos lo básico.
            results.append(
                {
                    "symbol": s,
                    "ok": True,
                    "rows": int(len(df)),
                    "first_ts": df["datetime"].iloc[0].isoformat() if len(df) > 0 else None,
                    "last_ts": df["datetime"].iloc[-1].isoformat() if len(df) > 0 else None,
                }
            )
        except Exception as e:
            results.append({"symbol": s, "ok": False, "error": str(e)})

    return results
