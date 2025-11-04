# -*- coding: utf-8 -*-
from __future__ import annotations
from report_builder import build_report_html, save_report_files
from py_algo_starter.indicators import compute_signals
from py_algo_starter.fetch_data import fetch_and_validate
import matplotlib.pyplot as plt
import os
import io
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from datetime import datetime
import matplotlib
matplotlib.use("Agg")

# Evitar warnings de Arial
plt.rcParams["font.family"] = "DejaVu Sans"

REPORTS_DIR = os.environ.get("REPORTS_DIR", "/var/data/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# --- Starter lib ---


app = FastAPI()


def _now_str():
    return datetime.now().strftime("%Y%m%d-%H%M")


@app.get("/", response_class=HTMLResponse)
def root():
    return "<h3>py-algo-web-service OK</h3>"


@app.post("/run-now")
async def run_now(request: Request):
    data = dict(await request.form())
    raw_symbols = data.get("symbol") or data.get(
        "symbols") or data.get("tickers") or ""
    raw_symbols = raw_symbols.strip() or (await request.body()).decode("utf-8")
    if not raw_symbols:
        return JSONResponse({"error": "missing symbol"}, status_code=400)
    # permitir "AAPL,SPY"
    symbols = [s.strip() for s in raw_symbols.replace(
        "\n", ",").split(",") if s.strip()]
    if not symbols:
        return JSONResponse({"error": "no symbols parsed"}, status_code=400)

    interval = data.get("interval", "1h")
    start = data.get("start", None)
    end = data.get("end", None)

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    per_symbol = []

    for sym in symbols:
        try:
            df = fetch_and_validate(
                sym, interval=interval, start=start, end=end)
            if df.empty:
                per_symbol.append({
                    "symbol": sym,
                    "error": "No hay datos (YF vacío). Revisá el ticker o el período para 1h."
                })
                continue

            sig = compute_signals(df)
            # Guardar un gráfico simple precio + EMA20/50 y marcar R1/R2/S1/S2 en el último día
            fig, ax = plt.subplots(figsize=(10, 4))
            sig["close"].plot(ax=ax, lw=1.2, label="Close")
            sig["EMA20"].plot(ax=ax, lw=1.0, label="EMA20")
            sig["EMA50"].plot(ax=ax, lw=1.0, label="EMA50")

            # Líneas horizontales pivots del último valor
            last = sig.dropna().iloc[-1]
            for lvl, color in [("S2", "#888888"), ("S1", "#888888"), ("P", "#666666"),
                               ("R1", "#888888"), ("R2", "#888888")]:
                ax.axhline(last[lvl], linestyle="--", alpha=0.6)

            ax.set_title(f"{sym} — Close/EMA & Pivots")
            ax.legend(loc="best")
            ax.grid(True, alpha=0.15)

            png_name = f"chart-{ts}-{sym}.png"
            png_path = os.path.join(REPORTS_DIR, png_name)
            fig.savefig(png_path, bbox_inches="tight")
            plt.close(fig)

            # Resumen de conclusiones (última vela)
            concl = {
                "symbol": sym,
                "traffic": last["TRAFFIC"],
                "entry": _fmt(last.get("ENTRY_PRICE")),
                "exit": _fmt(last.get("EXIT_PRICE")),
                "stop": _fmt(last.get("STOP_LOSS")),
                "r1": _fmt(last.get("R1")),
                "r2": _fmt(last.get("R2")),
                "s1": _fmt(last.get("S1")),
                "s2": _fmt(last.get("S2")),
                "rsi": _fmt(last.get("RSI14")),
                "ema20": _fmt(last.get("EMA20")),
                "ema50": _fmt(last.get("EMA50")),
                "atr": _fmt(last.get("ATR14")),
                "conclusion_text": str(last.get("CONCLUSION", "")),
                "chart_png": png_name
            }
            per_symbol.append(concl)

        except Exception as e:
            per_symbol.append({"symbol": sym, "error": repr(e)})

    # Construir HTML por símbolo y master report
    html, report_fname = build_report_html(per_symbol, ts)
    saved_html, latest_html = save_report_files(
        html, report_fname, REPORTS_DIR)

    return JSONResponse({
        "ok": True,
        "report": os.path.basename(saved_html),
        "latest": os.path.basename(latest_html),
        "symbols": per_symbol
    })


def _fmt(x):
    try:
        if x is None or (isinstance(x, float) and (np.isnan(x))):
            return "-"
    except Exception:
        pass
    if isinstance(x, (int, float)):
        return f"{x:.2f}"
    return str(x)


@app.get("/reports/latest.html", response_class=HTMLResponse)
def serve_latest():
    latest = os.path.join(REPORTS_DIR, "latest.html")
    if not os.path.exists(latest):
        return HTMLResponse("<h4>No hay latest.html</h4>", status_code=404)
    with open(latest, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/reports/{name}", response_class=HTMLResponse)
def serve_report(name: str):
    path = os.path.join(REPORTS_DIR, name)
    if not os.path.exists(path):
        return HTMLResponse("<h4>Reporte no encontrado</h4>", status_code=404)
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
