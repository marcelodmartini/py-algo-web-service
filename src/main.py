import os
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

REPORTS_DIR = os.environ.get("REPORTS_DIR", "/var/data/reports")
UPLOAD_TOKEN = os.environ.get("UPLOAD_TOKEN", "")
os.makedirs(REPORTS_DIR, exist_ok=True)

app = FastAPI(title="Algo Reports Web Service")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
templates = Jinja2Templates(directory="templates")


def _latest_path():
    return os.path.join(REPORTS_DIR, "latest.html")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Always render the dashboard (iframe attempts / which maps to latest.html via below handler as fallback)
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
    return {"ok": True, "filename": os.path.basename(hist_path), "url": f"/reports/{os.path.basename(hist_path)}"}


@app.post("/run-now")
def run_now(background: BackgroundTasks, x_run_token: str | None = Header(default=None)):
    # Reuse same token for simplicity
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    def _job():
        # Try to import the package and run
        try:
            from py_algo_starter import run_once  # type: ignore
            report_path, public_url = run_once("config.yaml")
            # If public_url is not present, the upload step inside run_once may be disabled; fallback is serving file
        except Exception as e:
            # Write a small HTML log for visibility
            msg = f"<h1>Run error</h1><pre>{e}</pre>"
            path = _latest_path()
            with open(path, "w", encoding="utf-8") as f:
                f.write(msg)

    background.add_task(_job)
    stamp = datetime.utcnow().isoformat()
    return {"status": "running", "started_at": stamp, "hint": "Revisá /list o el iframe en /"}
