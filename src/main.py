# py-algo-web-service/src/main.py
import os
import re
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks, Request, Body, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

from pydantic import BaseModel
import yaml

# ---------- Modelos ----------


class BatchReq(BaseModel):
    symbols: List[str]  # e.g. ["AAPL","SPY","BTC","BTC/USDT","ETH"]


# ---------- Logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("algo-web")

# ---------- Config & paths ----------
REPORTS_DIR = os.environ.get("REPORTS_DIR", "/var/data/reports")
UPLOAD_TOKEN = os.environ.get("UPLOAD_TOKEN", "")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")  # <- tu config base

os.makedirs(REPORTS_DIR, exist_ok=True)

app = FastAPI(title="Algo Reports Web Service")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
templates = Jinja2Templates(directory="templates")


def _latest_path() -> str:
    return os.path.join(REPORTS_DIR, "latest.html")


def _write_html_status(title: str, pre: str, status: int = 200):
    """Escribe un HTML simple como último reporte (útil para errores/estado)."""
    html = f"<h1>{title}</h1><pre>{pre}</pre>"
    path = _latest_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return HTMLResponse(html, status_code=status)


# ---------- Normalización de símbolos ----------
YAHOO_DEFAULTS = {"BTC": "BTC-USD"}  # atajos útiles

INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
# Periodo recomendado para intradía (mitiga límites de Yahoo)
DEFAULT_PERIOD_BY_INTERVAL = {
    "1m": "7d",
    "2m": "7d",
    "5m": "30d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "730d",
    "1h": "730d",
}


def normalize_symbols(items: List[str]) -> List[str]:
    """
    - Limpia separadores visuales (coma, pipe, espacio y ' / ' suelto).
    - Mantiene slash válido de pares cripto (BTC/USDT).
    - Uppercase, aplica alias (BTC -> BTC-USD).
    - De-dup.
    """
    out: List[str] = []
    seen = set()

    # Re-split defensivo si llega algo tipo "AAPL / SPY / BTC"
    exploded: List[str] = []
    for s in items:
        s = (s or "").strip()
        if not s:
            continue

        # Si hay barras pero NO parece par cripto con formato X/Y, re-split
        if "/" in s and not re.search(r"^[A-Z0-9\-]+/[A-Z0-9\-]+$", s.upper()):
            parts = [p.strip() for p in s.split("/") if p.strip()]
            exploded.extend(parts)
        else:
            exploded.append(s)

    # Normalizar cada token
    for s in exploded:
        # split adicional por coma, pipe o espacios
        for tok in re.split(r"[,\|\s]+", s):
            tok = tok.strip().upper()
            if not tok:
                continue
            tok = YAHOO_DEFAULTS.get(tok, tok)  # alias
            if tok not in seen:
                seen.add(tok)
                out.append(tok)

    return out


def _build_temp_cfg_for_symbol(sym: str, base_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clona el config base y ajusta:
      - data.symbol = sym
      - Si el intervalo es intradía, usar 'period' recomendado y remover start/end
        (mitiga 'No data found' por pedir demasiado histórico intradía en Yahoo).
    """
    cfg = json.loads(json.dumps(base_cfg))  # deep copy simple
    data = cfg.setdefault("data", {})
    data["symbol"] = sym.strip()

    interval = str(data.get("interval") or data.get("timeframe") or "").lower()
    if interval in INTRADAY_INTERVALS:
        # Preferir period vs start/end para yfinance intradía
        data["period"] = DEFAULT_PERIOD_BY_INTERVAL.get(interval, "60d")
        # Remover start/end si existen
        data.pop("start", None)
        data.pop("end", None)

    # Alias útil por si alguien carga 'BTC' en config directamente:
    if data.get("source", "").lower() in ("yahoo", "yfinance"):
        if data.get("symbol", "").upper() == "BTC":
            data["symbol"] = "BTC-USD"

    return cfg


def _render_batch_index(stamp: str, link_names: List[str]) -> str:
    items = "\n".join(
        [f'<li><a href="/reports/{name}" target="_blank">{name}</a></li>' for name in link_names])
    return f"<h1>Batch {stamp}</h1><ul>{items}</ul><p><a href='/'>Volver</a></p>"


# ---------- Pages ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/latest", response_class=HTMLResponse)
def latest():
    if not os.path.exists(_latest_path()):
        return HTMLResponse("<h1>No hay reporte aún</h1>", status_code=404)
    with open(_latest_path(), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/list", response_class=HTMLResponse)
def list_reports():
    files = sorted([f for f in os.listdir(REPORTS_DIR)
                   if f.endswith(".html")], reverse=True)
    if not files:
        return HTMLResponse("<h1>No hay reportes generados todavía</h1>", status_code=404)
    items = "\n".join(
        [f'<li><a href="/reports/{f}" target="_blank">{f}</a></li>' for f in files])
    html = f"<h1>Reportes disponibles</h1><ul>{items}</ul><p><a href='/'>Volver</a></p>"
    return HTMLResponse(html)


# ---------- Debug / Health ----------
@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"


@app.get("/debug-env", response_class=PlainTextResponse)
def debug_env():
    info = {
        "cwd": str(Path.cwd()),
        "exists_config": Path(CONFIG_PATH).exists(),
        "config_path": str(Path(CONFIG_PATH).resolve()),
        "reports_dir": REPORTS_DIR,
        "env_keys": sorted([k for k in os.environ.keys() if k in
                            ("PYTHON_VERSION", "TZ", "REPORTS_DIR", "UPLOAD_TOKEN", "WEB_SERVICE_BASE_URL", "PYTHONPATH", "CONFIG_PATH")]),
    }
    return json.dumps(info, indent=2)


# ---------- Upload endpoint ----------
@app.post("/upload-report")
async def upload_report(file: UploadFile = File(...), x_upload_token: str | None = Header(default=None)):
    token = UPLOAD_TOKEN
    if not token or x_upload_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    content = await file.read()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    hist_path = os.path.join(REPORTS_DIR, f"report-{stamp}.html")
    latest_path = _latest_path()

    for path in (hist_path, latest_path):
        with open(path, "wb") as f:
            f.write(content)

    log.info(f"[UPLOAD] Guardado {hist_path} y actualizado latest.html")
    return {"ok": True, "filename": os.path.basename(hist_path), "url": f"/reports/{os.path.basename(hist_path)}"}


# ---------- Persistencia de símbolo único ----------
@app.post("/set-symbol")
def set_symbol(symbol: str):
    """Persiste símbolo en config.yaml."""
    cfg_path = Path(CONFIG_PATH)
    data = yaml.safe_load(cfg_path.read_text(
        encoding="utf-8")) if cfg_path.exists() else {}
    data.setdefault("data", {})
    data["data"]["symbol"] = symbol.strip()
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False,
                        allow_unicode=True), encoding="utf-8")
    return {"ok": True, "symbol": symbol}


# ---------- Run batch (protegido por token) ----------
@app.post("/run-batch")
def run_batch(req: BatchReq, background: BackgroundTasks, x_run_token: str | None = Header(default=None)):
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    def _job():
        try:
            from py_algo_starter import run_once  # type: ignore
            stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
            links: List[str] = []

            base_cfg = {}
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                base_cfg = yaml.safe_load(f) or {}

            for raw_sym in req.symbols:
                for sym in normalize_symbols([raw_sym]):
                    cfg_obj = _build_temp_cfg_for_symbol(sym, base_cfg)
                    tmp_cfg_path = os.path.join(
                        REPORTS_DIR, f"cfg-{stamp}-{sym.replace('/', '_').replace('-', '_')}.yaml")
                    with open(tmp_cfg_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(
                            cfg_obj, f, sort_keys=False, allow_unicode=True)

                    # Ejecutar
                    report_path, public_url = run_once(tmp_cfg_path)

                    # Renombrar con sufijo de símbolo para no pisar
                    if report_path and os.path.exists(report_path):
                        out_name = f"report-{stamp}-{sym.replace('/', '_').replace('-', '_')}.html"
                        out_path = os.path.join(REPORTS_DIR, out_name)
                        with open(report_path, "rb") as src, open(out_path, "wb") as dst:
                            dst.write(src.read())
                        links.append(out_name)

            # Construir índice batch
            if links:
                batch_html = _render_batch_index(stamp, links)
                batch_name = f"batch-{stamp}.html"
                batch_path = os.path.join(REPORTS_DIR, batch_name)
                with open(batch_path, "w", encoding="utf-8") as f:
                    f.write(batch_html)
                # actualizar latest.html al índice batch
                with open(batch_path, "rb") as src, open(_latest_path(), "wb") as dst:
                    dst.write(src.read())

        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"[RUN-BATCH] Error: {e}\n{tb}")
            _write_html_status("Run-batch error", tb, status=500)

    background.add_task(_job)
    return {"status": "running", "count": len(req.symbols)}


# ---------- Run-now (público) ----------
@app.api_route("/run-now", methods=["GET", "POST"])
def run_now(
    symbol: Optional[str] = Query(
        default=None, description="Símbolos separados por coma: AAPL,SPY,BTC-USD,BTC/USDT"),
    symbols: Optional[List[str]] = Query(
        default=None, description="?symbols=AAPL&symbols=SPY ..."),
    background: BackgroundTasks = None,
):
    """
    Llama a /run-now sin token.
    Acepta:
      - /run-now?symbol=AAPL,SPY,BTC-USD,BTC/USDT
      - /run-now?symbols=AAPL&symbols=SPY&symbols=BTC-USD&symbols=BTC/USDT
    Dispara un job en background que corre cada símbolo y arma un índice batch.
    """
    collected: List[str] = []
    if symbols:
        collected.extend(symbols)
    if symbol:
        collected.append(symbol)

    norm = normalize_symbols(collected)
    if not norm:
        return {"ok": False, "detail": "No se recibieron símbolos válidos."}

    def _job():
        try:
            from py_algo_starter import run_once  # type: ignore
            stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
            links: List[str] = []

            base_cfg = {}
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                base_cfg = yaml.safe_load(f) or {}

            for sym in norm:
                cfg_obj = _build_temp_cfg_for_symbol(sym, base_cfg)
                tmp_cfg_path = os.path.join(
                    REPORTS_DIR, f"cfg-{stamp}-{sym.replace('/', '_').replace('-', '_')}.yaml")
                with open(tmp_cfg_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(cfg_obj, f, sort_keys=False,
                                   allow_unicode=True)

                # Ejecutar
                report_path, public_url = run_once(tmp_cfg_path)

                # Guardar por símbolo
                if report_path and os.path.exists(report_path):
                    out_name = f"report-{stamp}-{sym.replace('/', '_').replace('-', '_')}.html"
                    out_path = os.path.join(REPORTS_DIR, out_name)
                    with open(report_path, "rb") as src, open(out_path, "wb") as dst:
                        dst.write(src.read())
                    links.append(out_name)

            # Índice batch y latest.html
            if links:
                batch_html = _render_batch_index(stamp, links)
                batch_name = f"batch-{stamp}.html"
                batch_path = os.path.join(REPORTS_DIR, batch_name)
                with open(batch_path, "w", encoding="utf-8") as f:
                    f.write(batch_html)
                with open(batch_path, "rb") as src, open(_latest_path(), "wb") as dst:
                    dst.write(src.read())

        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"[RUN-NOW] Error: {e}\n{tb}")
            _write_html_status("Run-now error", tb, status=500)

    background.add_task(_job)
    return {"ok": True, "status": "running", "count": len(norm), "symbols": norm}


@app.post("/run-now-json")
def run_now_json(payload: Dict[str, Any] = Body(...), background: BackgroundTasks = None):
    """
    POST JSON:
      { "symbols": ["AAPL","SPY","BTC-USD","BTC/USDT"] }
    """
    items = payload.get("symbols", [])
    if not isinstance(items, list):
        return {"ok": False, "detail": "El campo 'symbols' debe ser una lista."}

    norm = normalize_symbols(items)
    if not norm:
        return {"ok": False, "detail": "No se recibieron símbolos válidos."}

    def _job():
        try:
            from py_algo_starter import run_once  # type: ignore
            stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
            links: List[str] = []

            base_cfg = {}
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                base_cfg = yaml.safe_load(f) or {}

            for sym in norm:
                cfg_obj = _build_temp_cfg_for_symbol(sym, base_cfg)
                tmp_cfg_path = os.path.join(
                    REPORTS_DIR, f"cfg-{stamp}-{sym.replace('/', '_').replace('-', '_')}.yaml")
                with open(tmp_cfg_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(cfg_obj, f, sort_keys=False,
                                   allow_unicode=True)

                report_path, public_url = run_once(tmp_cfg_path)

                if report_path and os.path.exists(report_path):
                    out_name = f"report-{stamp}-{sym.replace('/', '_').replace('-', '_')}.html"
                    out_path = os.path.join(REPORTS_DIR, out_name)
                    with open(report_path, "rb") as src, open(out_path, "wb") as dst:
                        dst.write(src.read())
                    links.append(out_name)

            if links:
                batch_html = _render_batch_index(stamp, links)
                batch_name = f"batch-{stamp}.html"
                batch_path = os.path.join(REPORTS_DIR, batch_name)
                with open(batch_path, "w", encoding="utf-8") as f:
                    f.write(batch_html)
                with open(batch_path, "rb") as src, open(_latest_path(), "wb") as dst:
                    dst.write(src.read())

        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"[RUN-NOW-JSON] Error: {e}\n{tb}")
            _write_html_status("Run-now JSON error", tb, status=500)

    background.add_task(_job)
    return {"ok": True, "status": "running", "count": len(norm), "symbols": norm}
