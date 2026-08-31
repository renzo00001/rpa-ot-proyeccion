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
import plotly.express as px
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

COLOR_GENERADO = "#2E86AB"
COLOR_PENDIENTE = "#E67E22"
COLOR_IMPORTE = "#1F4E78"

LIMITE_FILAS_EXCEL = 500_000

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
def grafico_evolucion_lineas(evolucion: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=evolucion["fecha"], y=evolucion["generadas"],
        mode="lines+markers", name="Generadas", line=dict(color=COLOR_GENERADO, width=3),
    ))
    fig.add_trace(go.Scatter(
        x=evolucion["fecha"], y=evolucion["pendientes"],
        mode="lines+markers", name="Pendientes", line=dict(color=COLOR_PENDIENTE, width=3),
    ))
    fig.update_layout(
        xaxis_title="Fecha", yaxis_title="N° de líneas",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380, margin=dict(t=10, b=10),
    )
    return fig


def grafico_evolucion_importe(evolucion: pd.DataFrame) -> go.Figure:
    fig = px.line(evolucion, x="fecha", y="importe_total", markers=True)
    fig.update_traces(line_color=COLOR_IMPORTE, line_width=3)
    fig.update_layout(
        xaxis_title="Fecha", yaxis_title="Importe (S/)",
        height=380, margin=dict(t=10, b=10),
    )
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


def grafico_barras_categoria(df_cat: pd.DataFrame) -> go.Figure:
    orden = df_cat.iloc[::-1]  # para que la categoria de mayor volumen quede arriba
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=orden["categoria"], x=orden["generadas"], name="Generadas",
        orientation="h", marker_color=COLOR_GENERADO,
    ))
    fig.add_trace(go.Bar(
        y=orden["categoria"], x=orden["pendientes"], name="Pendientes",
        orientation="h", marker_color=COLOR_PENDIENTE,
    ))
    fig.update_layout(
        barmode="stack", xaxis_title="N° de líneas",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380, margin=dict(t=10, b=10),
    )
    return fig


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
st.title("📦 Seguimiento de Órdenes de Traslado ")
st.caption("Evolución de líneas de órdenes de traslado a tienda — Equipo Abastecimientos Non Food")

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
pct_pendiente = (kpis["pendientes"] / total) if total else 0

if total == 0:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total de Líneas", f"{total:,}")
c2.metric("Generadas", f"{int(kpis['generadas']):,}")
c3.metric("Pendientes", f"{int(kpis['pendientes']):,}", f"{pct_pendiente:.1%} del total")
c4.metric("Importe Total", f"S/ {kpis['importe_total']:,.0f}")
c5.metric("Importe Pendiente", f"S/ {kpis['importe_pendiente']:,.0f}")

st.divider()

# --- Fila 1: evolución temporal ---
evolucion = calcular_evolucion(con, where, params)
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Evolución de líneas (generadas vs. pendientes)")
    st.plotly_chart(grafico_evolucion_lineas(evolucion), width="stretch")
with col_b:
    st.subheader("Evolución del importe total")
    st.plotly_chart(grafico_evolucion_importe(evolucion), width="stretch")

# --- Fila 2: por gerencia y unidad de negocio ---
por_gerencia = calcular_por_categoria(con, COL_GERENCIA, where, params)
por_unidad = calcular_por_categoria(con, COL_UNIDAD, where, params)

col_c, col_d = st.columns(2)
with col_c:
    st.subheader("Líneas generadas vs. pendientes por Gerencia")
    st.plotly_chart(grafico_barras_categoria(por_gerencia), width="stretch")
with col_d:
    st.subheader("Líneas generadas vs. pendientes por Unidad de Negocio")
    st.plotly_chart(grafico_barras_categoria(por_unidad), width="stretch")

