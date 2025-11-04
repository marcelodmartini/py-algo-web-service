# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from typing import List, Dict


def build_report_html(per_symbol: List[Dict], ts: str):
    title = f"Report {ts}"
    rows = []
    for s in per_symbol:
        if "error" in s and s["error"]:
            rows.append(f"""
            <section style="border:1px solid #e0e0e0;border-radius:8px;padding:12px;margin-bottom:16px;">
              <h3>{s['symbol']} — <span style="color:#c62828;">ERROR</span></h3>
              <p>{s['error']}</p>
            </section>
            """)
            continue

        badge = s.get("traffic", "?")
        color = "#2e7d32" if badge == "🟢" else "#ef6c00" if badge == "🟡" else "#c62828"

        rows.append(f"""
        <section style="border:1px solid #e0e0e0;border-radius:8px;padding:12px;margin-bottom:16px;">
          <h3>{s['symbol']} — <span style="font-size:1.4rem;">{badge}</span></h3>
          <div style="display:flex;gap:16px;flex-wrap:wrap;">
            <div style="flex:1;min-width:320px;">
              <table style="width:100%;border-collapse:collapse;">
                <tr><th style="text-align:left;">Entrada ideal</th><td>{s['entry']}</td></tr>
                <tr><th style="text-align:left;">Salida sugerida</th><td>{s['exit']}</td></tr>
                <tr><th style="text-align:left;">Stop loss</th><td>{s['stop']}</td></tr>
                <tr><th style="text-align:left;">R1 / R2</th><td>{s['r1']} / {s['r2']}</td></tr>
                <tr><th style="text-align:left;">S1 / S2</th><td>{s['s1']} / {s['s2']}</td></tr>
                <tr><th style="text-align:left;">RSI(14)</th><td>{s['rsi']}</td></tr>
                <tr><th style="text-align:left;">EMA20 / EMA50</th><td>{s['ema20']} / {s['ema50']}</td></tr>
                <tr><th style="text-align:left;">ATR(14)</th><td>{s['atr']}</td></tr>
              </table>
              <p style="margin-top:10px;"><strong>Conclusión:</strong> {s['conclusion_text']}</p>
              <p style="color:{color};font-weight:600;">Semáforo: {badge}</p>
            </div>
            <div style="flex:1;min-width:320px;">
              <img src="./{s['chart_png']}" alt="chart {s['symbol']}" style="max-width:100%;border:1px solid #ddd;border-radius:6px;" />
            </div>
          </div>
        </section>
        """)

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", "DejaVu Sans", sans-serif; margin:18px; }}
    h2 {{ margin:10px 0 16px; }}
    th, td {{ padding:6px 8px; border-bottom:1px solid #eee; }}
    th {{ width:160px; color:#555; }}
  </style>
</head>
<body>
  <h2>{title}</h2>
  {''.join(rows)}
</body>
</html>
"""
    name = f"report-{ts}.html"
    return html, name


def save_report_files(html: str, filename: str, outdir: str):
    # Guardar el index del reporte
    out_path = os.path.join(outdir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Actualizar latest.html
    latest = os.path.join(outdir, "latest.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)

    return out_path, latest
