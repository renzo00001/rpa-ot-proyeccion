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
COL_ACTUALIZACION = "fecha_hora_actualizacion"
COL_CLASE_DOC = "clase_documento"
COL_TIENE_ENTREGA = "tiene_entrega"

ESTADO_GENERADO = "generado"
ESTADO_PENDIENTE = "pendiente"

COLOR_GENERADO = "#2DD4BF"
COLOR_PENDIENTE = "#F59E0B"
COLOR_ALERTA = "#EF4444"

LIMITE_FILAS_EXCEL = 500_000
LIMITE_ALERTA_LINEAS = 6000

st.set_page_config(
    page_title="Dashboard Ejecutivo ",
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
    requeridas = {COL_STATUS, COL_FECHA, COL_GERENCIA, COL_UNIDAD, COL_IMPORTE, COL_CLASE_DOC}
    faltantes = requeridas - columnas
    if faltantes:
        raise ValueError(f"A la tabla '{TABLA}' le faltan columnas: {sorted(faltantes)}")
    return con


def obtener_metadatos(con):
    gerencias = con.execute(
        f"SELECT DISTINCT {COL_GERENCIA} FROM {TABLA} WHERE tiene_entrega = 'NO' OR ( tiene_entrega = 'SI' AND Status = 'generado')  ORDER BY 1"
    ).df()[COL_GERENCIA].tolist()
    clases_doc = con.execute(
        f"SELECT DISTINCT {COL_CLASE_DOC} FROM {TABLA} WHERE tiene_entrega = 'NO' OR ( tiene_entrega = 'SI' AND Status = 'generado')  ORDER BY 1"
    ).df()[COL_CLASE_DOC].tolist()
    fecha_min, fecha_max = con.execute(
        f"""SELECT MIN(CAST({COL_FECHA} AS DATE)), MAX(CAST({COL_FECHA} AS DATE)) FROM {TABLA} WHERE tiene_entrega = 'NO' OR ( tiene_entrega = 'SI' AND Status = 'generado')  """
    ).fetchone()
    return gerencias, clases_doc, fecha_min, fecha_max


def obtener_ultima_actualizacion(con):
    return con.execute(f"SELECT MAX({COL_ACTUALIZACION}) FROM {TABLA}").fetchone()[0]


def construir_filtro(gerencias_sel, clases_sel, fecha_ini, fecha_fin):
    ph_gerencias = ",".join(["?"] * len(gerencias_sel))
    ph_clases = ",".join(["?"] * len(clases_sel))
    where = (
        f"WHERE {COL_GERENCIA} IN ({ph_gerencias}) "
        f"""AND {COL_CLASE_DOC} IN ({ph_clases}) AND (tiene_entrega = 'NO' OR ( tiene_entrega = 'SI' AND Status = 'generado'))   """
        f"AND CAST({COL_FECHA} AS DATE) BETWEEN ? AND ?"
    )
    params = list(gerencias_sel) + list(clases_sel) + [fecha_ini, fecha_fin]
    return where, params


def construir_filtro_total(gerencias_sel, clases_sel, fecha_ini, fecha_fin):
    """Igual que construir_filtro, pero SIN la restricción de tiene_entrega:
    para métricas de brecha/total real (Brecha Acumulada), donde interesa el
    universo completo de líneas sin excluir nada por tiene_entrega."""
    ph_gerencias = ",".join(["?"] * len(gerencias_sel))
    ph_clases = ",".join(["?"] * len(clases_sel))
    where = (
        f"WHERE {COL_GERENCIA} IN ({ph_gerencias}) "
        f"AND {COL_CLASE_DOC} IN ({ph_clases}) "
        f"AND CAST({COL_FECHA} AS DATE) BETWEEN ? AND ?"
    )
    params = list(gerencias_sel) + list(clases_sel) + [fecha_ini, fecha_fin]
    return where, params


def construir_filtro_entregas(gerencias_sel, clases_sel, fecha_ini, fecha_fin):
    """Igual que construir_filtro, pero sin la excepción de tiene_entrega='NO':
    aquí solo interesan las órdenes que YA tienen una entrega generada en SAP
    (tiene_entrega='SI'), sea cual sea su Status."""
    ph_gerencias = ",".join(["?"] * len(gerencias_sel))
    ph_clases = ",".join(["?"] * len(clases_sel))
    where = (
        f"WHERE {COL_GERENCIA} IN ({ph_gerencias}) "
        f"AND {COL_CLASE_DOC} IN ({ph_clases}) "
        f"AND {COL_TIENE_ENTREGA} = 'SI' "
        f"AND CAST({COL_FECHA} AS DATE) BETWEEN ? AND ?"
    )
    params = list(gerencias_sel) + list(clases_sel) + [fecha_ini, fecha_fin]
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


MESES_ABREV = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
                7: "Jul", 8: "Ago", 9: "Set", 10: "Oct", 11: "Nov", 12: "Dic"}


def _fmt_dia_mes(fecha) -> str:
    return f"{fecha.day:02d} {MESES_ABREV[fecha.month]}"


def agrupar_evolucion(evolucion: pd.DataFrame, vista: str) -> pd.DataFrame:
    """Agrupa la evolución diaria a nivel Día / Semana (lun-dom) / Mensual."""
    df = evolucion.copy()
    if df.empty or vista == "Día":
        df["etiqueta"] = df["fecha"].apply(_fmt_dia_mes) if len(df) else []
        return df

    df["fecha"] = pd.to_datetime(df["fecha"])
    periodo = df["fecha"].dt.to_period("W-SUN") if vista == "Semana" else df["fecha"].dt.to_period("M")

    agg = df.groupby(periodo).agg(
        generadas=("generadas", "sum"),
        pendientes=("pendientes", "sum"),
        importe_total=("importe_total", "sum"),
        fecha_ini=("fecha", "min"),
        fecha_fin=("fecha", "max"),
    ).reset_index(drop=True)

    if vista == "Semana":
        def etiqueta_semana(row):
            d1, d2 = row["fecha_ini"], row["fecha_fin"]
            if d1.date() == d2.date():
                return _fmt_dia_mes(d1)
            if d1.month == d2.month:
                return f"{d1.day}-{d2.day} {MESES_ABREV[d1.month]}"
            return f"{d1.day} {MESES_ABREV[d1.month]} - {d2.day} {MESES_ABREV[d2.month]}"
        agg["etiqueta"] = agg.apply(etiqueta_semana, axis=1)
    else:
        agg["etiqueta"] = agg["fecha_ini"].apply(lambda d: f"{MESES_ABREV[d.month]} {d.year}")

    agg["fecha"] = agg["fecha_ini"]
    return agg.sort_values("fecha_ini").reset_index(drop=True)


def grafico_ritmo_diario(df: pd.DataFrame, mostrar_alerta: bool = True,
                          limite_alerta: int = LIMITE_ALERTA_LINEAS,
                          usar_categorias: bool = False) -> go.Figure:
    x = df["etiqueta"] if usar_categorias else df["fecha"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=df["generadas"], name="Generadas",
        marker=dict(color=COLOR_GENERADO, line_width=0),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(
        x=x, y=df["pendientes"], name="Pendientes",
        marker=dict(color=COLOR_PENDIENTE, line_width=0),
        hoverinfo="skip",
    ))
    if len(df):
        totales = df["generadas"] + df["pendientes"]
        fig.add_trace(go.Scatter(
            x=x, y=totales, mode="text",
            text=[f"{t:,.0f}" for t in totales], textposition="top center",
            textfont=dict(color="#c7ccd6", size=10),
            hoverinfo="skip", showlegend=False,
        ))
        customdata = list(zip(df["etiqueta"], df["generadas"], df["pendientes"]))
        prefijo_fecha = "" if usar_categorias else "%{customdata[0]}<br>"
        fig.add_trace(go.Scatter(
            x=x, y=totales, mode="markers",
            marker=dict(size=6, color="rgba(0,0,0,0)"),
            customdata=customdata,
            hovertemplate=(
                f"{prefijo_fecha}"
                f'<span style="color:{COLOR_GENERADO}">■</span> Generadas: %{{customdata[1]:,}}<br>'
                f'<span style="color:{COLOR_PENDIENTE}">■</span> Pendientes: %{{customdata[2]:,}}'
                "<extra></extra>"
            ),
            showlegend=False,
        ))
        if mostrar_alerta:
            fig.add_trace(go.Scatter(
                x=[x.iloc[0], x.iloc[-1]], y=[limite_alerta, limite_alerta],
                mode="lines", name=f"Alerta {limite_alerta:,}",
                line=dict(color=COLOR_ALERTA, width=1.5, dash="dash"), hoverinfo="skip",
            ))
    fig.update_layout(barmode="stack", bargap=0.25, hovermode="x unified")
    if usar_categorias:
        fig.update_xaxes(type="category")
    else:
        fig.update_xaxes(hoverformat=" ")
    fig.update_yaxes(title_text="N° de líneas")
    fig = _layout_oscuro(fig, margen_top=28)
    fig.update_yaxes(gridcolor="rgba(140,150,170,0.08)")
    return fig


def grafico_brecha_acumulada(evolucion: pd.DataFrame) -> go.Figure:
    df = evolucion.sort_values("fecha").copy()
    df["gen_acum"] = df["generadas"].cumsum()
    df["pend_acum"] = df["pendientes"].cumsum()
    df["etiqueta"] = df["fecha"].apply(_fmt_dia_mes) if len(df) else []
    brecha_final = int(df["pend_acum"].iloc[-1] - df["gen_acum"].iloc[-1]) if len(df) else 0

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["gen_acum"], mode="lines", name="Generadas (acum.)",
        line=dict(color=COLOR_GENERADO, width=2),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["pend_acum"], mode="lines", name="Pendientes (acum.)",
        line=dict(color=COLOR_PENDIENTE, width=2), fill="tonexty", fillcolor=_rgba(COLOR_PENDIENTE, 0.12),
        hoverinfo="skip",
    ))
    if len(df):
        customdata = list(zip(df["etiqueta"], df["gen_acum"], df["pend_acum"]))
        fig.add_trace(go.Scatter(
            x=df["fecha"], y=df["pend_acum"], mode="markers",
            marker=dict(size=6, color="rgba(0,0,0,0)"),
            customdata=customdata,
            hovertemplate=(
                "%{customdata[0]}<br>"
                f'<span style="color:{COLOR_GENERADO}">■</span> Generadas (acum.): %{{customdata[1]:,}}<br>'
                f'<span style="color:{COLOR_PENDIENTE}">■</span> Pendientes (acum.): %{{customdata[2]:,}}'
                "<extra></extra>"
            ),
            showlegend=False,
        ))
    signo = "+" if brecha_final >= 0 else ""
    color_brecha = COLOR_PENDIENTE if brecha_final >= 0 else COLOR_GENERADO
    fig.add_annotation(
        xref="paper", yref="paper", x=1, y=1.1, showarrow=False, align="right",
        text=f"brecha final {signo}{brecha_final:,}",
        font=dict(color=color_brecha, size=13, family="Courier New, monospace"),
    )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(hoverformat=" ")
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
.rpa-topbar-meta { display: flex; gap: 32px; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #8b93a7; line-height: 1.5; }
.rpa-topbar-meta-item { text-align: right; white-space: nowrap; }
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
.rpa-fila { margin-bottom: 14px; position: relative; }
.rpa-fila-head { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 5px; }
.rpa-fila-nums { font-family: 'Courier New', monospace; font-size: 12px; color: #8b93a7; }
.rpa-tooltip-wrap { cursor: default; }
.rpa-tooltip-box {
    visibility: hidden; opacity: 0; transition: opacity 0.15s ease;
    position: absolute; bottom: 100%; left: 0; margin-bottom: 6px;
    background: #1c2436; border: 1px solid rgba(140,150,170,0.3);
    border-radius: 6px; padding: 6px 10px; font-size: 11px; color: #c7ccd6;
    white-space: nowrap; z-index: 20; font-family: Arial, Helvetica, sans-serif;
}
.rpa-tooltip-wrap:hover .rpa-tooltip-box { visibility: visible; opacity: 1; }
div[data-testid="stColumn"]:has(.st-key-vista_ritmo) {
    display: flex; justify-content: flex-end; align-items: center;
}
div[data-testid="stColumn"]:has(.st-key-vista_entregas) {
    display: flex; justify-content: flex-end; align-items: center;
}
.st-key-card_entregas {
    background: rgba(139, 92, 246, 0.08) !important;
    border-color: rgba(139, 92, 246, 0.4) !important;
}
.rpa-badge-morado {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(139, 92, 246, 0.18); border: 1px solid rgba(139, 92, 246, 0.5);
    color: #C4B5FD; font-size: 10px; font-family: Arial, Helvetica, sans-serif;
    letter-spacing: 1px; padding: 4px 10px; border-radius: 999px;
}
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


def fila_categoria(categoria: str, generadas: float, pendientes: float, ancho_pct: float) -> None:
    total_cat = generadas + pendientes
    pct_gen = (generadas / total_cat * 100) if total_cat else 0
    pct_pend = 100 - pct_gen
    tooltip = f"Generadas: {generadas:,.0f} · Pendientes: {pendientes:,.0f} · Total: {total_cat:,.0f}"
    st.markdown(f"""
    <div class="rpa-fila rpa-tooltip-wrap">
        <div class="rpa-fila-head">
            <span>{categoria}</span>
            <span class="rpa-fila-nums">
                <b style="color:{COLOR_PENDIENTE if pct_pend >= 50 else COLOR_GENERADO}">{pct_pend:.1f}% pend.</b></span>
        </div>
        <div class="rpa-bar-track" style="width:{ancho_pct:.3f}%;">
            <div class="rpa-bar-fill" style="width:{pct_gen:.3f}%; background:{COLOR_GENERADO};"></div>
            <div class="rpa-bar-fill" style="width:{pct_pend:.3f}%; background:{COLOR_PENDIENTE};"></div>
        </div>
        <div class="rpa-tooltip-box">{tooltip}</div>
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
        fila_categoria(row["categoria"], row["generadas"], row["pendientes"], ancho)


def render_por_unidad(por_unidad: pd.DataFrame) -> None:
    if por_unidad.empty:
        st.caption("Sin datos.")
        return
    df = por_unidad.copy()
    df["total"] = df["generadas"] + df["pendientes"]
    df = df.sort_values("total", ascending=False)
    max_total = df["total"].max()
    for _, row in df.iterrows():
        ancho = (row["total"] / max_total * 100) if max_total else 0
        fila_categoria(row["categoria"], row["generadas"], row["pendientes"], ancho)


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

try:
    con = conectar(token)
except Exception as e:
    st.error(f"No se pudo conectar a la tabla '{TABLA}': {e}")
    st.stop()

with st.sidebar:
    ultima_actualizacion = obtener_ultima_actualizacion(con)
    if ultima_actualizacion is not None:
        st.caption(f"🕒 Dashboard actualizado: \n\t{ultima_actualizacion:%d/%m/%Y %H:%M}")
    if st.button("🔄 Recargar datos"):
        st.cache_resource.clear()
        st.rerun()

gerencias_disp, clases_doc_disp, fecha_min, fecha_max = obtener_metadatos(con)

with st.sidebar:
    st.header("Filtros")
    gerencias_sel = st.multiselect("Gerencia", gerencias_disp, default=gerencias_disp)
    rango = st.date_input("Rango de fechas", value=(fecha_min, fecha_max),
                           min_value=fecha_min, max_value=fecha_max)
    clases_sel = st.multiselect("Clase de documento", clases_doc_disp, default=clases_doc_disp)

if not gerencias_sel:
    st.warning("Selecciona al menos una gerencia.")
    st.stop()

if not clases_sel:
    st.warning("Selecciona al menos una clase de documento.")
    st.stop()

if isinstance(rango, tuple) and len(rango) == 2:
    fecha_ini, fecha_fin = rango
else:
    fecha_ini, fecha_fin = fecha_min, fecha_max

where, params = construir_filtro(gerencias_sel, clases_sel, fecha_ini, fecha_fin)

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
    <div class="rpa-topbar-title">Seguimiento de Órdenes de Traslado - CD10</div>
    <div class="rpa-topbar-meta">
        <div class="rpa-topbar-meta-item">PERIODO<br><b>{fecha_ini:%d %b} — {fecha_fin:%d %b %Y}</b></div>
        <div class="rpa-topbar-meta-item">ÓRDENES · LÍNEAS<br><b>{total:,} líneas</b></div>
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
where_total, params_total = construir_filtro_total(gerencias_sel, clases_sel, fecha_ini, fecha_fin)
evolucion_total = calcular_evolucion(con, where_total, params_total)
col_a, col_b = st.columns(2)
with col_a:
    with st.container(border=True):
        col_titulo, col_vista = st.columns([1, 1.6])
        with col_titulo:
            st.markdown('<div class="rpa-card-title" style="padding-top:8px;">RITMO DIARIO</div>',
                         unsafe_allow_html=True)
        with col_vista:
            vista_ritmo = st.segmented_control(
                "Vista", ["Día", "Semana", "Mensual"], default="Día",
                key="vista_ritmo", label_visibility="collapsed",
            )
        vista_ritmo = vista_ritmo or "Día"
        st.caption(f"Barra apilada por {vista_ritmo.lower()} · total sobre la barra")
        df_ritmo = agrupar_evolucion(evolucion, vista_ritmo)
        st.plotly_chart(
            grafico_ritmo_diario(
                df_ritmo,
                mostrar_alerta=(vista_ritmo == "Día"),
                usar_categorias=(vista_ritmo != "Día"),
            ),
            width="stretch",
        )
with col_b:
    with st.container(border=True):
        st.markdown('<div class="rpa-card-title">BRECHA ACUMULADA</div>', unsafe_allow_html=True)
        st.caption("Cuánto se abre el pendiente sobre lo generado · total sin filtrar por entrega")
        st.plotly_chart(grafico_brecha_acumulada(evolucion_total), width="stretch")

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
        st.caption("Ordenado por cantidad de líneas")
        render_por_unidad(por_unidad)

# --- Fila 4: evolución de órdenes con entrega ya generada (tiene_entrega = 'SI') ---
where_entregas, params_entregas = construir_filtro_entregas(gerencias_sel, clases_sel, fecha_ini, fecha_fin)
evolucion_entregas = calcular_evolucion(con, where_entregas, params_entregas)

with st.container(border=True, key="card_entregas"):
    col_t_ent, col_v_ent = st.columns([2.2, 1.6])
    with col_t_ent:
        st.markdown(
            '<div class="rpa-card-title">EVOLUCIÓN DE ÓRDENES CON ENTREGA GENERADA'
            '&nbsp;&nbsp;<span class="rpa-badge-morado">● YA TRABAJADOS</span></div>',
            unsafe_allow_html=True,
        )
    with col_v_ent:
        vista_entregas = st.segmented_control(
            "Vista entregas", ["Día", "Semana", "Mensual"], default="Día",
            key="vista_entregas", label_visibility="collapsed",
        )
    vista_entregas = vista_entregas or "Día"
    st.caption(f"Solo traslados con entrega generada (tiene_entrega = 'SI') · por {vista_entregas.lower()}")
    df_entregas = agrupar_evolucion(evolucion_entregas, vista_entregas)
    st.plotly_chart(
        grafico_ritmo_diario(
            df_entregas,
            mostrar_alerta=False,
            usar_categorias=(vista_entregas != "Día"),
        ),
        width="stretch",
    )

