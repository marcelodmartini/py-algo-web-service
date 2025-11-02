
import os
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Algo Reports Web Service")

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
