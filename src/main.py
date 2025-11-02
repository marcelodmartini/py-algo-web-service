import os
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Importa la API pública del starter (instalado vía requirements.txt)
from py_algo_starter.run_backtest import run_once

app = FastAPI(title="Algo Reports Web Service")
UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "")
REPORTS_DIR = os.environ.get("REPORTS_DIR", "/var/data/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")


def _latest_path():
    return os.path.join(REPORTS_DIR, "latest.html")


@app.get("/", response_class=HTMLResponse)
def index():
    # Página con botón
    btn = f"""
    <h1>Algo Reports</h1>
    <p><a href="/list" target="_blank">Ver reportes</a></p>
    <button id="run">Run now</button>
    <pre id="out"></pre>
    <script>
    const out = document.getElementById('out');
    document.getElementById('run').onclick = async () => {{
      out.textContent = 'Running...';
      try {{
        const res = await fetch('/run-now', {{
          method: 'POST',
          headers: {{ 'X-Run-Token': '{UPLOAD_TOKEN}' }}
        }});
        const data = await res.json();
        out.textContent = JSON.stringify(data, null, 2);
      }} catch (e) {{
        out.textContent = 'Error: ' + e;
      }}
    }};
    </script>
    """
    if not os.path.exists(_latest_path()):
        return HTMLResponse(btn + "<h2>No hay reporte aún</h2>")
    with open(_latest_path(), "r", encoding="utf-8") as f:
        return HTMLResponse(btn + f.read())


@app.get("/list", response_class=HTMLResponse)
def list_reports():
    files = sorted([f for f in os.listdir(REPORTS_DIR) if f.endswith(".html")], reverse=True)
    if not files:
        return HTMLResponse("<h1>No hay reportes generados todavía</h1>", status_code=404)
    html = ["<h1>Reportes disponibles</h1><ul>"]
    for f in files:
        html.append(f'<li><a href="/reports/{f}" target="_blank">{f}</a></li>')
    html.append("</ul><p><a href='/'>Volver</a></p>")
    return HTMLResponse("\n".join(html))


def _auth_ok(authorization: str | None, x_upload_token: str | None) -> bool:
    if not UPLOAD_TOKEN:
        return False
    if authorization and authorization.strip() == f"Bearer {UPLOAD_TOKEN}":
        return True
    if x_upload_token and x_upload_token.strip() == UPLOAD_TOKEN:
        return True
    return False


@app.post("/upload-report")
async def upload_report(
    file: UploadFile = File(...),
    authorization: str | None = Header(None),
    x_upload_token: str | None = Header(None),
):
    if not _auth_ok(authorization, x_upload_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    content = await file.read()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    hist_path = os.path.join(REPORTS_DIR, f"report-{stamp}.html")
    latest_path = _latest_path()

    for path in (hist_path, latest_path):
        with open(path, "wb") as f:
            f.write(content)

    return {
        "ok": True,
        "saved": [f"/reports/{os.path.basename(hist_path)}", "/"],
        "filename": os.path.basename(hist_path),
        "url": f"/reports/{os.path.basename(hist_path)}"
    }


@app.post("/run-now")
def run_now(background: BackgroundTasks, x_run_token: str = Header(None)):
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    os.makedirs(REPORTS_DIR, exist_ok=True)

    def _job():
        try:
            _report_path, _public_url = run_once("config.yaml")
        except Exception as e:
            with open(os.path.join(REPORTS_DIR, "last_error.txt"), "w") as f:
                f.write(str(e))

    background.add_task(_job)
    stamp = datetime.utcnow().isoformat()
    return {"status": "running", "hint": "abrí /list o /", "started_at": stamp}
