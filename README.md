
# 🚀 Algo Reports – Servicio A (FastAPI Web Service)

Servicio FastAPI que recibe reportes HTML generados por el Cron Job y los expone públicamente.

## ⚙️ Configuración en Render

### Tipo
- **Service Type:** Web Service
- **Environment:** Python

### Build Command
```
pip install -r requirements.txt
```

### Start Command
```
uvicorn src.main:app --host 0.0.0.0 --port $PORT
```

### Disco persistente
Para conservar los reportes entre reinicios:
- **Add Disk → Mount Path:** `/var/data/reports`
- **Size:** 1–5 GB

### Variables de entorno
```
REPORTS_DIR=/var/data/reports
UPLOAD_TOKEN=mi_token_seguro_123
```

### Endpoints
| Ruta | Descripción |
|------|--------------|
| `/` | Muestra el último reporte (`latest.html`) |
| `/list` | Lista todos los reportes históricos con links |
| `/reports/...` | Sirve los archivos HTML guardados |
| `POST /upload-report` | Endpoint para subir nuevos reportes desde el Cron Job |
