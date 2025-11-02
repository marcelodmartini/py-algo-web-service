# src/main.py
import os
from datetime import datetime
from pathlib import Path
from fastapi import (
    FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Algo Reports Web Service")

# === Config ===
REPORTS_DIR = os.getenv("REPORTS_DIR", "/var/data/reports")
UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)

# Servir archivos estáticos de reportes
# Quedará disponible en: https://.../report/<archivo.html>
app.mount("/report", StaticFiles(directory=REPORTS_DIR), name="report")


def _latest_path() -> str:
    """Ruta del alias al último reporte."""
    return os.path.join(REPORTS_DIR, "latest.html")


def _html_page(body: str, status: int = 200) -> HTMLResponse:
    """Wrapper simple para responder HTML."""
    return HTMLResponse(body, status_code=status)


@app.get("/", response_class=HTMLResponse)
def index():
    """
    Muestra el último reporte (alias latest.html) si existe,
    o un mensaje si aún no hay reportes.
    """
    lp = _latest_path()
    if not os.path.exists(lp):
        return _html_page("<h1>No hay reporte aún</h1><p>Subí uno o ejecutá /admin</p>", 404)
    with open(lp, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/list", response_class=HTMLResponse)
def list_reports():
    """
    Lista todos los .html disponibles en REPORTS_DIR, del más nuevo al más viejo.
    """
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith(".html")],
        reverse=True
    )
    if not files:
        return _html_page("<h1>No hay reportes generados todavía</h1>", 404)

    items = []
    for fname in files:
        # se sirven desde /report/<fname>
        items.append(
            f'<li><a href="/report/{fname}" target="_blank">{fname}</a></li>')

    html = f"""
    <html>
      <head><meta charset="utf-8"><title>Reportes</title></head>
      <body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif">
        <h1>Reportes disponibles</h1>
        <ul>
          {''.join(items)}
        </ul>
        <p><a href="/">Ver último reporte</a> — <a href="/admin">Admin</a></p>
      </body>
    </html>
    """
    return _html_page(html)


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    """
    Página simple con un botón que dispara /run-now.
    No expone el token; el usuario lo ingresa manualmente.
    """
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Runner – Admin</title>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <style>
        body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:24px;max-width:780px;margin:auto}
        .card{border:1px solid #ddd;border-radius:12px;padding:20px}
        button{padding:12px 18px;border-radius:10px;border:1px solid #333;cursor:pointer}
        .log{white-space:pre-wrap;background:#0b1020;color:#d6e1ff;padding:12px;border-radius:10px;margin-top:16px;display:none}
        .ok{color:#0a7a3f}.err{color:#b00020}
        input[type=password]{padding:10px;border-radius:8px;border:1px solid #ccc;width:100%;max-width:420px}
        label{display:block;margin-top:12px;margin-bottom:6px}
        a.button {display:inline-block;padding:8px 12px;border:1px solid #333;border-radius:10px;text-decoration:none}
      </style>
    </head>
    <body>
      <h1>Run Backtest</h1>
      <p>Esta página permite ejecutar manualmente el backtest y publicar el <code>report.html</code>.</p>
      <p><a class="button" href="/list" target="_blank">Ver lista de reportes</a></p>
      <div class="card">
        <label for="token">Admin token</label>
        <input id="token" type="password" placeholder="ADMIN_TOKEN"/>

        <div style="margin-top:16px">
          <button id="runBtn">▶ Ejecutar ahora</button>
        </div>
        <div id="msg" style="margin-top:12px"></div>
        <div id="log" class="log"></div>
      </div>

      <script>
      const btn = document.getElementById('runBtn');
      const msg = document.getElementById('msg');
      const log = document.getElementById('log');

      btn.onclick = async () => {
        msg.textContent = 'Ejecutando...';
        msg.className = '';
        log.style.display='none'; log.textContent='';
        const token = document.getElementById('token').value.trim();
        try {
          const r = await fetch('/run-now', {
            method: 'POST',
            headers: {'X-Admin-Token': token}
          });
          const j = await r.json();
          if (!r.ok) throw new Error(j.detail || r.statusText);
          msg.innerHTML = `✔ Ejecutado/En curso. Revisa <a href="/list" target="_blank">/list</a>.` +
                          (j.public_url ? ` → <a href="${j.public_url}" target="_blank">abrir reporte</a>` : '');
          msg.className='ok';
          if (j.local_path) { log.style.display='block'; log.textContent = 'Guardado en: ' + j.local_path; }
        } catch (e) {
          msg.textContent = '✖ Error: ' + e.message;
          msg.className='err';
        }
      };
      </script>
    </body>
    </html>
    """
    return _html_page(html)


@app.post("/upload-report")
async def upload_report(
    file: UploadFile = File(...),
    authorization: str | None = Header(None),
    x_upload_token: str | None = Header(None),
):
    """
    Sube un HTML y lo guarda con timestamp + alias latest.html.
    Autenticación:
      - Authorization: Bearer <UPLOAD_TOKEN>
      - o bien X-Upload-Token: <UPLOAD_TOKEN>
    Devuelve URL pública del archivo y del alias.
    """
    token_ok = False
    if UPLOAD_TOKEN:
        if authorization == f"Bearer {UPLOAD_TOKEN}":
            token_ok = True
        if x_upload_token == UPLOAD_TOKEN:
            token_ok = True
    if not token_ok:
        raise HTTPException(status_code=401, detail="Unauthorized")

    content = await file.read()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    # histórico con timestamp + alias “latest.html” y “report.html” por compatibilidad
    hist_path = os.path.join(REPORTS_DIR, f"report-{stamp}.html")
    latest_path = _latest_path()
    default_alias = os.path.join(REPORTS_DIR, "report.html")

    for path in (hist_path, latest_path, default_alias):
        with open(path, "wb") as f:
            f.write(content)

    return {
        "ok": True,
        "saved": [
            f"/report/{os.path.basename(hist_path)}",
            "/report/latest.html",
            "/report/report.html",
        ],
        "url": "/report/report.html"
    }


@app.post("/run-now")
def run_now(
    background: BackgroundTasks,
    x_admin_token: str = Header(None)
):
    """
    Ejecuta el backtest en background y publica el HTML.
    Autenticación:
      - X-Admin-Token: <ADMIN_TOKEN>
    Respuesta inmediata con hint; el upload lo hace el runner.
    """
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)

    def _job():
        # Intentar prioridad: paquete instalable (algo.*). Si no, fallback a src.run_backtest.
        run_once_fn = None
        try:
            from algo.run_backtest import run_once as run_once_fn  # instalado vía pip VCS
        except Exception:
            try:
                from src.run_backtest import run_once as run_once_fn  # runner local
            except Exception as e:
                # No se pudo importar ningún runner
                raise RuntimeError(f"No se encontró run_once(): {e}")

        # Ejecuta usando el config por defecto en el Web Service (o el del starter si está accesible)
        try:
            result = run_once_fn("config.yaml")
            # result puede traer: {"portfolio_value": .., "local_path": .., "public_url": ..}
            # No retornamos nada aquí (BackgroundTasks no usa el retorno)
            return result
        except Exception as e:
            # Log simple a archivo de errores dentro de REPORTS_DIR
            errp = Path(
                REPORTS_DIR) / f"run_error_{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
            errp.write_text(
                f"[{datetime.utcnow().isoformat()}] {e}", encoding="utf-8")

    background.add_task(_job)

    stamp = datetime.utcnow().isoformat()
    return {
        "status": "running",
        "hint": "revisa /list o /report/latest.html; el HTML se publicará al finalizar",
        "started_at": stamp
    }
