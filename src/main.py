import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# IMPORT diferido dentro del background job para que el import falle menos en cold start,
# pero lo dejamos acá para que mypy no se enoje si lo querés mover.
# from py_algo_starter.src.run_backtest import run_once  # NO: lo importamos dentro del job.

app = FastAPI(title="Algo Reports Web Service")

UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "")
REPORTS_DIR = os.environ.get("REPORTS_DIR", "/var/data/reports")
WEB_BASE = os.environ.get("WEB_BASE", "").rstrip("/")  # opcional

Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")


def _latest_path() -> str:
    return os.path.join(REPORTS_DIR, "latest.html")


@app.get("/", response_class=HTMLResponse)
def index():
    # Home simple con botón "Run now"
    has_report = os.path.exists(_latest_path())
    last_link = "/reports/latest.html" if has_report else "#"
    last_txt = "Ver último reporte" if has_report else "Sin reporte aún"

    html = f"""
    <html>
      <head>
        <meta charset="utf-8"/>
        <title>Algo Reports</title>
        <style>
          body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; padding: 24px; }}
          .btn {{ padding: 10px 16px; border-radius: 8px; border: 1px solid #444; background: #111; color: #fff; cursor:pointer; }}
          .row {{ display:flex; gap:12px; align-items:center; }}
          input[type="password"] {{ padding:10px; border-radius:8px; border:1px solid #ccc; width:320px; }}
          a {{ color:#0af; }}
        </style>
      </head>
      <body>
        <h1>Algo Reports</h1>
        <p><a href="/list" target="_blank">Listar reportes</a> · <a href="{last_link}" target="_blank">{last_txt}</a></p>
        <hr/>
        <h2>Ejecutar ahora</h2>
        <form id="runForm" onsubmit="return false;">
          <div class="row">
            <input type="password" id="token" placeholder="Upload token" />
            <button class="btn" onclick="runNow()">Run now</button>
          </div>
        </form>
        <p id="msg"></p>

        <script>
        async function runNow() {{
          const token = document.getElementById('token').value;
          document.getElementById('msg').innerText = 'Ejecutando...';
          try {{
            const res = await fetch('/run-now', {{
              method: 'POST',
              headers: {{ 'X-Run-Token': token }}
            }});
            const data = await res.json();
            if (res.ok) {{
              document.getElementById('msg').innerText = 'OK: ' + (data.hint || 'running');
            }} else {{
              document.getElementById('msg').innerText = 'Error: ' + (data.detail || JSON.stringify(data));
            }}
          }} catch (e) {{
            document.getElementById('msg').innerText = 'Error de red: ' + e;
          }}
        }}
        </script>
      </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/list", response_class=HTMLResponse)
def list_reports():
    files = sorted([f for f in os.listdir(REPORTS_DIR)
                   if f.endswith(".html")], reverse=True)
    if not files:
        return HTMLResponse("<h1>No hay reportes generados todavía</h1>", status_code=404)

    lis = "\n".join(
        f'<li><a href="/reports/{f}" target="_blank">{f}</a></li>' for f in files)
    html = f"<h1>Reportes disponibles</h1><ul>{lis}</ul><p><a href='/'>Home</a></p>"
    return HTMLResponse(html)


@app.post("/upload-report")
async def upload_report(file: UploadFile = File(...), x_upload_token: str | None = Header(None)):
    # Seguridad simple por header X-Upload-Token
    if not UPLOAD_TOKEN or x_upload_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    content = await file.read()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    hist_path = os.path.join(REPORTS_DIR, f"report-{stamp}.html")
    latest_path = _latest_path()

    with open(hist_path, "wb") as f:
        f.write(content)
    with open(latest_path, "wb") as f:
        f.write(content)

    return {"ok": True, "saved": [f"/reports/{os.path.basename(hist_path)}", "/reports/latest.html"]}


@app.post("/run-now")
def run_now(background: BackgroundTasks, x_run_token: str | None = Header(None)):
    # Reutilizamos el mismo token del upload
    if not UPLOAD_TOKEN or x_run_token != UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)

    def _job():
        # Import diferido para que funcione cuando el paquete está instalado
        from py_algo_starter.src.run_backtest import run_once
        # Usa el config por defecto del starter (o monta uno tuyo)
        report_path, _public_url = run_once("config.yaml")

        # Si por alguna razón no subió automáticamente, garantizamos "latest.html" aquí
        latest = _latest_path()
        if report_path and os.path.exists(report_path):
            with open(report_path, "rb") as fr, open(latest, "wb") as fw:
                fw.write(fr.read())

    background.add_task(_job)
    stamp = datetime.utcnow().isoformat()
    return {"status": "running", "hint": "Revisá /list o /reports/latest.html", "started_at": stamp}
