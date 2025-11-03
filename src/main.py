# py-algo-web-service/src/main.py
import os
import json
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Query
import yaml
import logging

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
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")  # <- nuevo

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


# ---------- Run-now (background) ----------

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


@app.post("/run-now")
def run_now(background: BackgroundTasks, x_run_token: str | None = Header(default=None),
            symbol: str | None = Query(default=None)):
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    def _job():
        try:
            log.info("== RUN START ==")
            # Si viene query ?symbol=..., generamos un config temporal
            cfg_file = CONFIG_PATH
            if symbol:
                cfg = yaml.safe_load(open(CONFIG_PATH, "r", encoding="utf-8"))
                cfg.setdefault("data", {})
                cfg["data"]["symbol"] = symbol.strip()
                tmp = Path(REPORTS_DIR) / "config-run.yaml"
                tmp.write_text(yaml.safe_dump(
                    cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
                cfg_file = str(tmp)
                log.info(f"Override symbol via query: {symbol} → {cfg_file}")

            from py_algo_starter import run_once
            report_path, public_url = run_once(cfg_file)
            log.info(
                f"run_once OK → report_path={report_path}, public_url={public_url}")
            # fallback para latest.html si no se subió
            if report_path and Path(report_path).exists():
                with open(report_path, "rb") as src, open(_latest_path(), "wb") as dst:
                    dst.write(src.read())
        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"RUN FAILED: {e}\n{tb}")
            _write_html_status("Run error", tb, status=500)

    background.add_task(_job)
    return {"status": "running"}
