"""
Dashboard Ejecutivo — Logística y Abastecimiento Non Food
Se conecta a MotherDuck (DuckDB en la nube), a la tabla
"proyeccion_operativa_diaria" dentro de la base "DB_proyeccion_final".

El token de acceso se lee de (en este orden):
1. st.secrets["TOKEN_MOTHERDUCK"]   -> usado cuando la app corre en Streamlit
   Community Cloud (se configura en la sección "Secrets" de la app, nunca en
   el repositorio).
2. Variable de entorno TOKEN_MOTHERDUCK / archivo .env local (vía
   python-dotenv) -> usado para correr la app en tu propia máquina.

El archivo .env NUNCA debe subirse al repositorio (está en .gitignore).
"""

import os
import tempfile

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------
# CONFIGURACIÓN — ajustar aquí si cambian nombres o base de datos
# ------------------------------------------------------------------
MOTHERDUCK_DB = "DB_proyeccion_final"
TABLA = "proyeccion_operativa_diaria"

COL_STATUS = "Status"
COL_FECHA = "fecha_entrega_actualizada"
COL_GERENCIA = "gerencia"
COL_UNIDAD = "unidad_de_negocio"
COL_IMPORTE = "Importe"

ESTADO_GENERADO = "generado"
ESTADO_PENDIENTE = "pendiente"

COLOR_GENERADO = "#2DD4BF"
COLOR_PENDIENTE = "#F59E0B"
COLOR_ALERTA = "#EF4444"

LIMITE_FILAS_EXCEL = 500_000
LIMITE_ALERTA_LINEAS = 4000

st.set_page_config(
    page_title="Dashboard Ejecutivo — Non Food",
    page_icon="📦",
    layout="wide",
)


def obtener_token() -> str | None:
    try:
        if "TOKEN_MOTHERDUCK" in st.secrets:
            return st.secrets["TOKEN_MOTHERDUCK"]
    except Exception:
        pass
    return os.environ.get("TOKEN_MOTHERDUCK")


# ------------------------------------------------------------------
# Conexión
# ------------------------------------------------------------------
@st.cache_resource(show_spinner="Conectando a MotherDuck...")
def conectar(token: str):
    con = duckdb.connect(f"md:{MOTHERDUCK_DB}?motherduck_token={token}", read_only=True)
    con.execute("INSTALL excel; LOAD excel;")
    columnas = {c[0] for c in con.execute(f"DESCRIBE {TABLA}").fetchall()}
    requeridas = {COL_STATUS, COL_FECHA, COL_GERENCIA, COL_UNIDAD, COL_IMPORTE}
    faltantes = requeridas - columnas
    if faltantes:
        raise ValueError(f"A la tabla '{TABLA}' le faltan columnas: {sorted(faltantes)}")
    return con


def obtener_metadatos(con):
    gerencias = con.execute(
        f"SELECT DISTINCT {COL_GERENCIA} FROM {TABLA} ORDER BY 1"
    ).df()[COL_GERENCIA].tolist()
    fecha_min, fecha_max = con.execute(
        f"SELECT MIN(CAST({COL_FECHA} AS DATE)), MAX(CAST({COL_FECHA} AS DATE)) FROM {TABLA}"
    ).fetchone()
    return gerencias, fecha_min, fecha_max


def construir_filtro(gerencias_sel, fecha_ini, fecha_fin):
    placeholders = ",".join(["?"] * len(gerencias_sel))
    where = (
        f"WHERE {COL_GERENCIA} IN ({placeholders}) "
        f"AND CAST({COL_FECHA} AS DATE) BETWEEN ? AND ?"
    )
    params = list(gerencias_sel) + [fecha_ini, fecha_fin]
    return where, params


# ------------------------------------------------------------------
# Consultas
# ------------------------------------------------------------------
def calcular_kpis(con, where, params) -> pd.Series:
    q = f"""
        SELECT
            COUNT(*) AS total_lineas,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_GENERADO}' THEN 1 ELSE 0 END) AS generadas,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_PENDIENTE}' THEN 1 ELSE 0 END) AS pendientes,
            SUM({COL_IMPORTE}) AS importe_total,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_PENDIENTE}' THEN {COL_IMPORTE} ELSE 0 END) AS importe_pendiente
        FROM {TABLA}
        {where}
    """
    return con.execute(q, params).df().iloc[0]


def calcular_evolucion(con, where, params) -> pd.DataFrame:
    q = f"""
        SELECT
            CAST({COL_FECHA} AS DATE) AS fecha,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_GENERADO}' THEN 1 ELSE 0 END) AS generadas,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_PENDIENTE}' THEN 1 ELSE 0 END) AS pendientes,
            SUM({COL_IMPORTE}) AS importe_total
        FROM {TABLA}
        {where}
        GROUP BY fecha
        ORDER BY fecha
    """
    return con.execute(q, params).df()


def calcular_por_categoria(con, columna: str, where, params) -> pd.DataFrame:
    q = f"""
        SELECT
            {columna} AS categoria,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_GENERADO}' THEN 1 ELSE 0 END) AS generadas,
            SUM(CASE WHEN {COL_STATUS} = '{ESTADO_PENDIENTE}' THEN 1 ELSE 0 END) AS pendientes
        FROM {TABLA}
        {where}
        GROUP BY categoria
        ORDER BY (generadas + pendientes) DESC
    """
    return con.execute(q, params).df()


# ------------------------------------------------------------------
# Gráficos
# ------------------------------------------------------------------
def _rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _layout_oscuro(fig: go.Figure, altura: int = 340, margen_top: int = 10) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c7ccd6"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=altura, margin=dict(t=margen_top, b=10, l=10, r=10),
        xaxis=dict(gridcolor="#232C3F", title=None),
        yaxis=dict(gridcolor="#232C3F"),
    )
    return fig


def grafico_ritmo_diario(evolucion: pd.DataFrame, limite_alerta: int = LIMITE_ALERTA_LINEAS) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=evolucion["fecha"], y=evolucion["generadas"], mode="lines", name="Generadas",
        line=dict(color=COLOR_GENERADO, width=2), fill="tozeroy", fillcolor=_rgba(COLOR_GENERADO, 0.15),
        hovertemplate="%{y:,}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=evolucion["fecha"], y=evolucion["pendientes"], mode="lines", name="Pendientes",
        line=dict(color=COLOR_PENDIENTE, width=2), fill="tozeroy", fillcolor=_rgba(COLOR_PENDIENTE, 0.15),
        hovertemplate="%{y:,}<extra></extra>",
    ))
    if len(evolucion):
        fig.add_trace(go.Scatter(
            x=[evolucion["fecha"].min(), evolucion["fecha"].max()], y=[limite_alerta, limite_alerta],
            mode="lines", name=f"Alerta {limite_alerta:,}",
            line=dict(color=COLOR_ALERTA, width=1.5, dash="dash"), hoverinfo="skip",
        ))
    fig.update_yaxes(title_text="N° de líneas")
    return _layout_oscuro(fig)


def grafico_brecha_acumulada(evolucion: pd.DataFrame) -> go.Figure:
    df = evolucion.sort_values("fecha").copy()
    df["gen_acum"] = df["generadas"].cumsum()
    df["pend_acum"] = df["pendientes"].cumsum()
    brecha_final = int(df["pend_acum"].iloc[-1] - df["gen_acum"].iloc[-1]) if len(df) else 0

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["gen_acum"], mode="lines", name="Generadas (acum.)",
        line=dict(color=COLOR_GENERADO, width=2),
        hovertemplate="%{y:,}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["pend_acum"], mode="lines", name="Pendientes (acum.)",
        line=dict(color=COLOR_PENDIENTE, width=2), fill="tonexty", fillcolor=_rgba(COLOR_PENDIENTE, 0.12),
        hovertemplate="%{y:,}<extra></extra>",
    ))
    signo = "+" if brecha_final >= 0 else ""
    color_brecha = COLOR_PENDIENTE if brecha_final >= 0 else COLOR_GENERADO
    fig.add_annotation(
        xref="paper", yref="paper", x=1, y=1.1, showarrow=False, align="right",
        text=f"brecha final {signo}{brecha_final:,}",
        font=dict(color=color_brecha, size=13, family="Courier New, monospace"),
    )
    fig.update_yaxes(title_text="Líneas acumuladas")
    fig = _layout_oscuro(fig, margen_top=30)
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0))
    return fig


def exportar_excel(con, where: str, params: list) -> tuple[bytes | None, int]:
    """Exporta a XLSX (vía DuckDB, rápido) el resultado filtrado.
    Devuelve (bytes, conteo). bytes es None si no hay filas o se pasa el límite."""
    total = con.execute(f"SELECT COUNT(*) FROM {TABLA} {where}", params).fetchone()[0]
    if total == 0 or total > LIMITE_FILAS_EXCEL:
        return None, total

    with tempfile.TemporaryDirectory() as tmp_dir:
        ruta_tmp = os.path.join(tmp_dir, "proyeccion_operativa.xlsx")
        con.execute(
            f"COPY (SELECT * FROM {TABLA} {where}) TO '{ruta_tmp}' (FORMAT XLSX, HEADER TRUE)",
            params,
        )
        with open(ruta_tmp, "rb") as f:
            data = f.read()
    return data, total


CSS_TARJETAS = """
<style>
.rpa-topbar-label {
    font-family: Arial, Helvetica, sans-serif;
    letter-spacing: 3px; font-size: 11px; color: #8b93a7; margin-bottom: 6px;
}
.rpa-topbar-title { font-size: 32px; font-weight: 800; margin: 0; line-height: 1.2; }
.rpa-topbar-meta { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #8b93a7; text-align: right; line-height: 1.5; }
.rpa-topbar-meta b { color: inherit; font-size: 15px; }
.rpa-topbar-wrap { display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom: 1px solid rgba(140,150,170,0.25); padding-bottom: 16px; margin-bottom: 22px; }
.rpa-card { background: rgba(140,150,170,0.06); border: 1px solid rgba(140,150,170,0.2);
    border-radius: 10px; padding: 18px 20px; margin-bottom: 18px; }
.rpa-card-title { font-family: Arial, Helvetica, sans-serif;
    letter-spacing: 2px; font-size: 11px; color: #8b93a7; }
.rpa-card-total { float: right; font-family: 'Courier New', monospace; font-size: 12px; color: #8b93a7; }
.rpa-metric-row { display: flex; gap: 44px; margin: 14px 0 16px 0; }
.rpa-metric-label { font-size: 12px; color: #8b93a7; }
.rpa-metric-value { font-size: 28px; font-weight: 700; font-family: 'Courier New', monospace; }
.rpa-metric-pct { font-size: 12px; color: #8b93a7; }
.rpa-bar-track { display: flex; height: 8px; border-radius: 6px; overflow: hidden;
    background: rgba(140,150,170,0.15); }
.rpa-bar-fill { height: 100%; }
.rpa-fila { margin-bottom: 14px; }
.rpa-fila-head { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 5px; }
.rpa-fila-nums { font-family: 'Courier New', monospace; font-size: 12px; color: #8b93a7; }
</style>
"""


def tarjeta_dos_metricas(titulo: str, total_texto: str,
                          m1_label: str, m1_valor: str, m1_pct: float, color1: str,
                          m2_label: str, m2_valor: str, m2_pct: float, color2: str) -> None:
    st.markdown(f"""
    <div class="rpa-card">
        <div class="rpa-card-title">{titulo}<span class="rpa-card-total">{total_texto}</span></div>
        <div class="rpa-metric-row">
            <div>
                <div class="rpa-metric-label">● {m1_label}</div>
                <div class="rpa-metric-value" style="color:{color1}">{m1_valor}</div>
                <div class="rpa-metric-pct">{m1_pct:.1%} del total</div>
            </div>
            <div>
                <div class="rpa-metric-label">● {m2_label}</div>
                <div class="rpa-metric-value" style="color:{color2}">{m2_valor}</div>
                <div class="rpa-metric-pct">{m2_pct:.1%} del total</div>
            </div>
        </div>
        <div class="rpa-bar-track">
            <div class="rpa-bar-fill" style="width:{m1_pct * 100:.3f}%; background:{color1};"></div>
            <div class="rpa-bar-fill" style="width:{m2_pct * 100:.3f}%; background:{color2};"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def fila_categoria(categoria: str, generadas: float, pendientes: float, ancho_pct: float,
                    etiqueta_derecha: str) -> None:
    total_cat = generadas + pendientes
    pct_gen = (generadas / total_cat * 100) if total_cat else 0
    pct_pend = 100 - pct_gen
    st.markdown(f"""
    <div class="rpa-fila">
        <div class="rpa-fila-head">
            <span>{categoria}</span>
            <span class="rpa-fila-nums">{generadas:,.0f} &nbsp; {pendientes:,.0f} &nbsp;
                <b style="color:{COLOR_PENDIENTE if pct_pend >= 50 else COLOR_GENERADO}">{etiqueta_derecha}</b></span>
        </div>
        <div class="rpa-bar-track" style="width:{ancho_pct:.3f}%;">
            <div class="rpa-bar-fill" style="width:{pct_gen:.3f}%; background:{COLOR_GENERADO};"></div>
            <div class="rpa-bar-fill" style="width:{pct_pend:.3f}%; background:{COLOR_PENDIENTE};"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_por_gerencia(por_gerencia: pd.DataFrame) -> None:
    if por_gerencia.empty:
        st.caption("Sin datos.")
        return
    totales = por_gerencia["generadas"] + por_gerencia["pendientes"]
    max_total = totales.max()
    for _, row in por_gerencia.assign(total=totales).sort_values("total", ascending=False).iterrows():
        ancho = (row["total"] / max_total * 100) if max_total else 0
        pct_pend = (row["pendientes"] / row["total"] * 100) if row["total"] else 0
        fila_categoria(row["categoria"], row["generadas"], row["pendientes"], ancho, f"{pct_pend:.1f}%")


def render_por_unidad(por_unidad: pd.DataFrame) -> None:
    if por_unidad.empty:
        st.caption("Sin datos.")
        return
    df = por_unidad.copy()
    df["total"] = df["generadas"] + df["pendientes"]
    df["pct_pend"] = df["pendientes"] / df["total"].replace(0, pd.NA)
    df = df.sort_values("pct_pend", ascending=False, na_position="last")
    max_total = df["total"].max()
    for _, row in df.iterrows():
        ancho = (row["total"] / max_total * 100) if max_total else 0
        pct_pend = (row["pct_pend"] * 100) if pd.notna(row["pct_pend"]) else 0
        fila_categoria(row["categoria"], row["generadas"], row["pendientes"], ancho,
                        f"{row['total']:,.0f} · {pct_pend:.1f}% pend.")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
st.markdown(CSS_TARJETAS, unsafe_allow_html=True)

token = obtener_token()
if not token:
    st.error(
        "No se encontró el token de MotherDuck. Defínelo en `TOKEN_MOTHERDUCK` "
        "dentro de un archivo `.env` local, o en los *Secrets* de la app en "
        "Streamlit Community Cloud."
    )
    st.stop()

with st.sidebar:
    if st.button("🔄 Recargar datos"):
        st.cache_resource.clear()
        st.rerun()

try:
    con = conectar(token)
except Exception as e:
    st.error(f"No se pudo conectar a la tabla '{TABLA}': {e}")
    st.stop()

gerencias_disp, fecha_min, fecha_max = obtener_metadatos(con)

with st.sidebar:
    st.header("Filtros")
    gerencias_sel = st.multiselect("Gerencia", gerencias_disp, default=gerencias_disp)
    rango = st.date_input("Rango de fechas", value=(fecha_min, fecha_max),
                           min_value=fecha_min, max_value=fecha_max)

if not gerencias_sel:
    st.warning("Selecciona al menos una gerencia.")
    st.stop()

if isinstance(rango, tuple) and len(rango) == 2:
    fecha_ini, fecha_fin = rango
else:
    fecha_ini, fecha_fin = fecha_min, fecha_max

where, params = construir_filtro(gerencias_sel, fecha_ini, fecha_fin)

with st.sidebar:
    st.divider()
    st.header("Exportar")
    if st.button("📥 Preparar Excel del rango filtrado"):
        with st.spinner("Generando archivo..."):
            data, conteo_export = exportar_excel(con, where, params)
        if data is None and conteo_export == 0:
            st.warning("No hay filas para exportar con los filtros actuales.")
        elif data is None:
            st.error(
                f"El rango filtrado tiene {conteo_export:,} filas, "
                f"por encima del límite de {LIMITE_FILAS_EXCEL:,}. "
                "Acota el rango de fechas o las gerencias seleccionadas."
            )
        else:
            st.download_button(
                "⬇️ Descargar Excel",
                data=data,
                file_name=f"proyeccion_{fecha_ini}_{fecha_fin}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# --- KPIs ---
kpis = calcular_kpis(con, where, params)
total = int(kpis["total_lineas"]) if kpis["total_lineas"] else 0
generadas = int(kpis["generadas"]) if kpis["generadas"] else 0
pendientes = int(kpis["pendientes"]) if kpis["pendientes"] else 0
pct_generado = (generadas / total) if total else 0
pct_pendiente = (pendientes / total) if total else 0

importe_total = float(kpis["importe_total"]) if kpis["importe_total"] else 0.0
importe_pendiente = float(kpis["importe_pendiente"]) if kpis["importe_pendiente"] else 0.0
importe_atendido = importe_total - importe_pendiente
pct_importe_atendido = (importe_atendido / importe_total) if importe_total else 0
pct_importe_pendiente = (importe_pendiente / importe_total) if importe_total else 0

if total == 0:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()


def _monto_corto(valor: float) -> str:
    if abs(valor) >= 1_000_000:
        return f"S/ {valor / 1_000_000:,.1f}M"
    return f"S/ {valor:,.0f}"


# --- Topbar ---
st.markdown(f"""
<div class="rpa-topbar-label">LOGÍSTICA · TRASLADOS A TIENDA</div>
<div class="rpa-topbar-wrap">
    <div class="rpa-topbar-title">Seguimiento de Órdenes de Traslado</div>
    <div class="rpa-topbar-meta">
        PERIODO<br><b>{fecha_ini:%d %b} — {fecha_fin:%d %b %Y}</b>
        &nbsp;&nbsp;&nbsp;&nbsp;
        ÓRDENES · LÍNEAS<br><b>{total:,} líneas</b>
    </div>
</div>
""", unsafe_allow_html=True)

# --- Fila 1: tarjetas resumen ---
col1, col2 = st.columns(2)
with col1:
    tarjeta_dos_metricas(
        "Líneas de Traslado", f"Total {total:,}",
        "Generadas", f"{generadas:,}", pct_generado, COLOR_GENERADO,
        "Pendientes", f"{pendientes:,}", pct_pendiente, COLOR_PENDIENTE,
    )
with col2:
    tarjeta_dos_metricas(
        "Importe", f"Total {_monto_corto(importe_total)}",
        "Atendido", _monto_corto(importe_atendido), pct_importe_atendido, COLOR_GENERADO,
        "Pendiente", _monto_corto(importe_pendiente), pct_importe_pendiente, COLOR_PENDIENTE,
    )

# --- Fila 2: ritmo diario y brecha acumulada ---
evolucion = calcular_evolucion(con, where, params)
col_a, col_b = st.columns(2)
with col_a:
    with st.container(border=True):
        st.markdown('<div class="rpa-card-title">RITMO DIARIO</div>', unsafe_allow_html=True)
        st.caption("Líneas generadas y pendientes por día")
        st.plotly_chart(grafico_ritmo_diario(evolucion), width="stretch")
with col_b:
    with st.container(border=True):
        st.markdown('<div class="rpa-card-title">BRECHA ACUMULADA</div>', unsafe_allow_html=True)
        st.caption("Cuánto se abre el pendiente sobre lo generado")
        st.plotly_chart(grafico_brecha_acumulada(evolucion), width="stretch")

# --- Fila 3: por gerencia y unidad de negocio ---
por_gerencia = calcular_por_categoria(con, COL_GERENCIA, where, params)
por_unidad = calcular_por_categoria(con, COL_UNIDAD, where, params)

col_c, col_d = st.columns(2)
with col_c:
    with st.container(border=True):
        st.markdown('<div class="rpa-card-title">POR GERENCIA</div>', unsafe_allow_html=True)
        st.caption("Ancho = volumen total de líneas")
        render_por_gerencia(por_gerencia)
with col_d:
    with st.container(border=True):
        st.markdown('<div class="rpa-card-title">POR UNIDAD DE NEGOCIO</div>', unsafe_allow_html=True)
        st.caption("Ordenado por % de pendientes")
        render_por_unidad(por_unidad)

