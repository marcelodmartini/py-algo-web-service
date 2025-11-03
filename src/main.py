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
@app.post("/run-now")
def run_now(background: BackgroundTasks, x_run_token: str | None = Header(default=None)):
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    def _job():
        try:
            # Log contexto
            log.info("== RUN START ==")
            log.info(f"CWD: {Path.cwd()}")
            log.info(f"REPORTS_DIR: {REPORTS_DIR}")
            log.info(
                f"CONFIG_PATH: {CONFIG_PATH} (exists={Path(CONFIG_PATH).exists()})")

            # Validar config
            if not Path(CONFIG_PATH).exists():
                msg = f"No se encontró el archivo de configuración: {CONFIG_PATH}"
                log.error(msg)
                _write_html_status("Run error", msg, status=500)
                return

            # Ejecutar pipeline
            from py_algo_starter import run_once  # type: ignore
            log.info("Importado py_algo_starter.run_once OK, ejecutando...")

            report_path, public_url = run_once(CONFIG_PATH)
            log.info(
                f"run_once() retornó report_path={report_path}, public_url={public_url}")

            # Si por alguna razón no se subió, intentamos setear latest con lo que haya
            if report_path and Path(report_path).exists():
                latest_path = _latest_path()
                try:
                    with open(report_path, "rb") as src, open(latest_path, "wb") as dst:
                        dst.write(src.read())
                    log.info(f"Actualizado latest.html desde {report_path}")
                except Exception as e:
                    log.warning(
                        f"No se pudo actualizar latest desde report_path: {e}")

            log.info("== RUN END OK ==")

        except Exception as e:
            # Dump stack trace a latest.html para verlo en el iframe
            tb = traceback.format_exc()
            log.error(f"RUN FAILED: {e}\n{tb}")
            _write_html_status("Run error", tb, status=500)

    background.add_task(_job)
    stamp = datetime.utcnow().isoformat()
    return {"status": "running", "started_at": stamp, "hint": "Revisá /list o el iframe en /"}
