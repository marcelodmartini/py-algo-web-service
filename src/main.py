
import os
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Algo Reports Web Service")
UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "")
REPORTS_DIR = os.environ.get("REPORTS_DIR", "/var/data/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")


def _latest_path():
    return os.path.join(REPORTS_DIR, "latest.html")


@app.get("/", response_class=HTMLResponse)
def index():
    if not os.path.exists(_latest_path()):
        return HTMLResponse("<h1>No hay reporte aún</h1>", status_code=404)
    with open(_latest_path(), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/list", response_class=HTMLResponse)
def list_reports():
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith(".html")],
        reverse=True
    )
    if not files:
        return HTMLResponse("<h1>No hay reportes generados todavía</h1>", status_code=404)

    html = ["<h1>Reportes disponibles</h1><ul>"]
    for f in files:
        html.append(f'<li><a href="/reports/{f}" target="_blank">{f}</a></li>')
    html.append("</ul><p><a href='/'>Ver último reporte</a></p>")
    return HTMLResponse("\n".join(html))


@app.post("/upload-report")
async def upload_report(file: UploadFile = File(...), authorization: str | None = Header(None)):
    token = os.environ.get("UPLOAD_TOKEN")
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    content = await file.read()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    hist_path = os.path.join(REPORTS_DIR, f"report-{stamp}.html")
    latest_path = _latest_path()

    for path in (hist_path, latest_path):
        with open(path, "wb") as f:
            f.write(content)

    return {"ok": True, "saved": [f"/reports/{os.path.basename(hist_path)}", "/"]}


@app.post("/run-now")
def run_now(background: BackgroundTasks, x_run_token: str = Header(None)):
    # seguridad simple reutilizando UPLOAD_TOKEN
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    os.makedirs(REPORTS_DIR, exist_ok=True)

    def _job():
        from src.run_backtest import run_once   # import diferido
        # usa el mismo config del starter
        _, url = run_once("config.yaml")
        # si no se pudo subir, al menos queda el archivo en REPORTS_DIR

    background.add_task(_job)
    # devolvemos una pista inmediata
    stamp = datetime.utcnow().isoformat()
    return {"status": "running", "hint": "check /list or open the latest /report/report.html", "started_at": stamp}
