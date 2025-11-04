# py-algo-web-service

FastAPI web service que:
- Recibe reportes HTML y los sirve públicamente.
- Lista versiones históricas.
- Permite lanzar la corrida **on-demand** (botón *Run now*) si el paquete `py-algo-starter` está disponible.

## Endpoints
- `GET /` — Dashboard con **Run now**, lista y visor del último reporte.
- `GET /latest` — Devuelve el último reporte (`latest.html`) o 404.
- `GET /list` — Lista de reportes (`/reports/*.html`).
- `POST /upload-report` — Sube un HTML (header `X-Upload-Token` obligatorio). Devuelve JSON con `url`.
- `POST /run-now` — Ejecuta el backtest en background (header `X-Run-Token`= `UPLOAD_TOKEN`).

## Variables de entorno
- `UPLOAD_TOKEN` (**requerida**): token para autorizar `/upload-report` y `/run-now`.
- `REPORTS_DIR` (**recomendada**): directorio donde se guardan reportes. En Render usar un **Render Disk** montado en `/var/data/reports`.
- `PYTHON_VERSION` (**Render**): usar `3.11.9`.
- `TZ` (opcional): `America/Argentina/Buenos_Aires`.

## Deploy en Render
- **Service type**: Web Service
- **Build command**: `pip install --upgrade pip && pip install -r requirements.txt`
- **Start command**: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- **Disk**: mount `/var/data/reports` (2–5 GB).

### Recomendado `render.yaml` (opcional)
Ver `render.yaml` para un ejemplo reproducible.

## Probar local
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

export UPLOAD_TOKEN=changeme
export REPORTS_DIR=/tmp/reports
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Subir un reporte
```bash
curl -X POST "http://localhost:8000/upload-report"       -H "X-Upload-Token: $UPLOAD_TOKEN"       -F "file=@/ruta/a/report.html"
```

### Ejecutar on-demand
- Abrí `http://localhost:8000`
- Ingresá el `UPLOAD_TOKEN`
- Presioná **Run now**

> Requiere que `py-algo-starter` sea instalable. En `requirements.txt` ya se incluye:
> `py-algo-starter @ git+https://github.com/marcelodmartini/py-algo-starter@main`

## Notas
- El iframe del dashboard usa `/latest`. Si aún no tenés reportes, verás 404 hasta la primera subida.
- `/run-now` corre en background y actualiza el `latest.html` al finalizar.
