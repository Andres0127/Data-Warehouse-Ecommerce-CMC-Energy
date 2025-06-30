import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px

# ---------------------------------------
# 1. CONFIGURACIÓN DE LA CONEXIÓN
# ---------------------------------------
DB_URL = "postgresql+psycopg2://postgres:200127@localhost:5432/ecommerce_dw"
engine = create_engine(DB_URL)

@st.cache_data(ttl=300)
def run_query(query: str) -> pd.DataFrame:
    """Ejecuta una consulta SQL y devuelve un DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(query, conn)

# ---------------------------------------
# 2. INTERFAZ Y FILTROS LATERALES
# ---------------------------------------
st.set_page_config(layout="wide", page_title="DW Dashboard CMC Energy")

st.sidebar.header("Filtros Globales")

# Rango de fechas
min_date = run_query("SELECT MIN(fecha) AS m FROM dim_fecha;")["m"][0]
max_date = run_query("SELECT MAX(fecha) AS m FROM dim_fecha;")["m"][0]
date_range = st.sidebar.date_input(
    "Rango de venta",
    value=[min_date, max_date],
    min_value=min_date,
    max_value=max_date
)

# Selección de productos con búsqueda
prods = run_query("SELECT DISTINCT nombre FROM dim_producto ORDER BY nombre;")["nombre"].tolist()
sel_prod = st.sidebar.multiselect(
    "Producto (busca y selecciona)",
    options=prods,
    default=[],
    help="Escribe para buscar productos"
)

# Selección de canales con búsqueda
canales = run_query("SELECT DISTINCT canal FROM dim_canal ORDER BY canal;")["canal"].tolist()
sel_canal = st.sidebar.multiselect(
    "Canal de venta (busca y selecciona)",
    options=canales,
    default=[],
    help="Escribe para buscar canales"
)

# Selección de regiones/ciudades con búsqueda (opcional)
ciudades = run_query("SELECT DISTINCT ciudad FROM dim_region ORDER BY ciudad;")["ciudad"].tolist()
sel_ciudad = st.sidebar.multiselect(
    "Ciudad (busca y selecciona)",
    options=ciudades,
    default=[],
    help="Escribe para buscar ciudades"
)

# ---------------------------------------
# 3. CONSULTAS DINÁMICAS
# ---------------------------------------

# 3.1 Fact table join dimensiones
# Si no hay filtros seleccionados, no filtrar por ese campo
where_clauses = [
    "t.fecha BETWEEN :start AND :end"
]
params = {
    "start": date_range[0],
    "end": date_range[1]
}

if sel_prod:
    where_clauses.append("p.nombre = ANY(:prods)")
    params["prods"] = sel_prod
if sel_canal:
    where_clauses.append("c.canal = ANY(:canales)")
    params["canales"] = sel_canal
if sel_ciudad:
    where_clauses.append("r.ciudad = ANY(:ciudades)")
    params["ciudades"] = sel_ciudad

where_sql = " AND ".join(where_clauses)

sql = text(f"""
SELECT 
  f.cantidad,
  f.precio,
  f.ingresos,
  f.costo,
  f.margen,
  p.categoria,
  p.nombre AS producto,
  c.canal,
  t.fecha,
  r.ciudad
FROM fact_ventas f
JOIN dim_producto p ON f.prod_key = p.prod_key
JOIN dim_canal c ON f.canal_key = c.canal_key
JOIN dim_fecha t ON f.date_key = t.date_key
JOIN dim_cliente cli ON f.cliente_key = cli.cliente_key
JOIN dim_region r ON cli.region_key = r.region_key
WHERE {where_sql}
""")

df = pd.read_sql(sql, engine, params=params)

# ---------------------------------------
# 4. MÉTRICAS PRINCIPALES
# ---------------------------------------
st.title("📈 Dashboard en Tiempo Real – CMC Energy")
st.markdown("**Ventas y márgenes por categoría, canal y producto**")

if df.empty:
    st.warning("No hay datos para los filtros seleccionados.")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Unidades Vendidas", f"{int(df['cantidad'].sum()):,}")
    col2.metric("Ingresos Totales (COP)", f"${df['ingresos'].sum():,.0f}")
    col3.metric("Margen Total (COP)", f"${df['margen'].sum():,.0f}")

    st.markdown("---")

    # ---------------------------------------
    # 5. VISUALIZACIONES
    # ---------------------------------------

    # 5.X Top 10 productos más vendidos
    # Consulta independiente para Top 10 productos más vendidos (solo filtra por fecha, canal y ciudad)
    sql_top10 = text("""
    SELECT 
      p.nombre AS producto,
      SUM(f.cantidad) AS total_vendida
    FROM fact_ventas f
    JOIN dim_producto p ON f.prod_key = p.prod_key
    JOIN dim_canal c ON f.canal_key = c.canal_key
    JOIN dim_fecha t ON f.date_key = t.date_key
    JOIN dim_cliente cli ON f.cliente_key = cli.cliente_key
    JOIN dim_region r ON cli.region_key = r.region_key
    WHERE t.fecha BETWEEN :start AND :end
      {canal_filter}
      {ciudad_filter}
    GROUP BY p.nombre
    ORDER BY total_vendida DESC
    LIMIT 10
    """.format(
        canal_filter="AND c.canal = ANY(:canales)" if sel_canal else "",
        ciudad_filter="AND r.ciudad = ANY(:ciudades)" if sel_ciudad else ""
    ))

    params_top10 = {
        "start": date_range[0],
        "end": date_range[1]
    }
    if sel_canal:
        params_top10["canales"] = sel_canal
    if sel_ciudad:
        params_top10["ciudades"] = sel_ciudad

    df_top10 = pd.read_sql(sql_top10, engine, params=params_top10)

    st.subheader("Top 10 Productos Más Vendidos")
    fig_top10 = px.bar(
        df_top10,
        x="total_vendida",
        y="producto",
        orientation="h",
        color="total_vendida",
        color_continuous_scale=px.colors.sequential.Blues,
        labels={"total_vendida": "Unidades Vendidas", "producto": "Producto"},
        title="Top 10 Productos por Unidades Vendidas",
        text_auto=True
    )
    fig_top10.update_layout(
        plot_bgcolor="#F9F9F9",
        paper_bgcolor="#F9F9F9",
        font=dict(size=14),
        title_font=dict(size=22, color="#2C3E50"),
        xaxis_title="Unidades Vendidas",
        yaxis_title="Producto",
        yaxis=dict(autorange="reversed")
    )
    fig_top10.update_traces(marker_line_width=1.5, marker_line_color="#34495E", textfont_size=14)
    st.plotly_chart(fig_top10, use_container_width=True)


    # 5.1 Ventas por categoría
    st.subheader("Ventas por Categoría")
    vc = df.groupby("categoria")["cantidad"].sum().reset_index()
    fig1 = px.bar(
        vc,
        x="categoria",
        y="cantidad",
        color="categoria",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        labels={"cantidad": "Unidades"},
        title="Unidades Vendidas por Categoría",
        text_auto=True
    )
    fig1.update_layout(
        plot_bgcolor="#F9F9F9",
        paper_bgcolor="#F9F9F9",
        font=dict(size=14),
        showlegend=False,
        title_font=dict(size=22, color="#2C3E50"),
        xaxis_title="Categoría",
        yaxis_title="Unidades"
    )
    fig1.update_traces(marker_line_width=1.5, marker_line_color="#34495E", textfont_size=14)
    st.plotly_chart(fig1, use_container_width=True)

    # 5.2 Margen vs Rotación (acumulada)
    st.subheader("Margen vs Volumen de Ventas (Productos)")
    prod_sum = df.groupby("producto").agg(
        unidades=("cantidad","sum"),
        margen=("margen","sum")
    ).reset_index()
    fig2 = px.scatter(
        prod_sum,
        x="unidades",
        y="margen",
        hover_data=["producto"],
        color="margen",
        color_continuous_scale=px.colors.sequential.Teal,
        labels={"unidades":"Unidades Vendidas", "margen":"Margen (COP)"},
        title="Rotación vs Margen por Producto",
        size="unidades"
    )
    fig2.update_layout(
        plot_bgcolor="#F9F9F9",
        paper_bgcolor="#F9F9F9",
        font=dict(size=14),
        title_font=dict(size=22, color="#2C3E50"),
        xaxis_title="Unidades Vendidas",
        yaxis_title="Margen (COP)",
        coloraxis_colorbar=dict(title="Margen")
    )
    fig2.update_traces(marker=dict(line=dict(width=1, color="#34495E")))
    st.plotly_chart(fig2, use_container_width=True)

    # 5.3 Comparativa de ventas por canal (total de ventas por canal)
    st.subheader("Comparativa de Ventas por Canal")

    ventas_canal = df.groupby("canal")["ingresos"].sum().reset_index().sort_values("ingresos", ascending=False)

    fig3 = px.bar(
        ventas_canal,
        x="canal",
        y="ingresos",
        color="canal",
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"ingresos": "Ingresos Totales (COP)", "canal": "Canal"},
        title="Total de Ventas por Canal",
        text_auto=True
    )
    fig3.update_layout(
        plot_bgcolor="#F9F9F9",
        paper_bgcolor="#F9F9F9",
        font=dict(size=14),
        showlegend=False,
        title_font=dict(size=22, color="#2C3E50"),
        xaxis_title="Canal",
        yaxis_title="Ingresos Totales (COP)"
    )
    fig3.update_traces(marker=dict(line=dict(width=1, color="#34495E")), textfont_size=14)
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")

    # 5.4 Satisfacción según producto (si tu fact_ventas tuviera calificaciones)
    if "calificacion_cliente" in df.columns:
        st.subheader("Satisfacción del Cliente por Producto")
        sat = df.groupby("producto").mean(numeric_only=True)["calificacion_cliente"].reset_index()
        fig4 = px.bar(
            sat,
            x="producto",
            y="calificacion_cliente",
            color="calificacion_cliente",
            color_continuous_scale=px.colors.sequential.Oranges,
            labels={"calificacion_cliente":"Rating"},
            title="Rating Promedio por Producto",
            text_auto=".2f"
        )
        fig4.update_layout(
            plot_bgcolor="#F9F9F9",
            paper_bgcolor="#F9F9F9",
            font=dict(size=14),
            title_font=dict(size=22, color="#2C3E50"),
            xaxis_title="Producto",
            yaxis_title="Rating",
            coloraxis_colorbar=dict(title="Rating")
        )
        fig4.update_xaxes(tickangle= -45)
        fig4.update_traces(marker_line_width=1.5, marker_line_color="#34495E", textfont_size=14)
        st.plotly_chart(fig4, use_container_width=True)

    # 5.X Tendencia de ventas en el tiempo
    st.subheader("Tendencia de Ventas en el Tiempo")
    ventas_tiempo = df.groupby("fecha").agg(
        unidades=("cantidad", "sum"),
        ingresos=("ingresos", "sum")
    ).reset_index()
    fig_tiempo = px.line(
        ventas_tiempo,
        x="fecha",
        y="ingresos",
        markers=True,
        labels={"fecha": "Fecha", "ingresos": "Ingresos (COP)"},
        title="Ingresos Totales por Fecha"
    )
    fig_tiempo.update_layout(
        plot_bgcolor="#F9F9F9",
        paper_bgcolor="#F9F9F9",
        font=dict(size=14),
        title_font=dict(size=22, color="#2C3E50"),
        xaxis_title="Fecha",
        yaxis_title="Ingresos (COP)"
    )
    st.plotly_chart(fig_tiempo, use_container_width=True)


    # 5.X Ventas por región 

    # Si tienes la columna 'ciudad' en df:
    if "ciudad" in df.columns:
        st.subheader("Ventas por Ciudad")
        ventas_ciudad = df.groupby("ciudad")["cantidad"].sum().sort_values(ascending=False).head(10).reset_index()
        fig_ciudad = px.bar(
            ventas_ciudad,
            x="cantidad",
            y="ciudad",
            orientation="h",
            color="cantidad",
            color_continuous_scale=px.colors.sequential.Greens,
            labels={"cantidad": "Unidades Vendidas", "ciudad": "Ciudad"},
            title="Top 10 Ciudades por Unidades Vendidas",
            text_auto=True
        )
        fig_ciudad.update_layout(
            plot_bgcolor="#F9F9F9",
            paper_bgcolor="#F9F9F9",
            font=dict(size=14),
            title_font=dict(size=22, color="#2C3E50"),
            xaxis_title="Unidades Vendidas",
            yaxis_title="Ciudad",
            yaxis=dict(autorange="reversed")
        )
        fig_ciudad.update_traces(marker_line_width=1.5, marker_line_color="#34495E", textfont_size=14)
        st.plotly_chart(fig_ciudad, use_container_width=True)

    # 5.X Participación de canales de venta
    st.subheader("Participación de Canales de Venta")
    canal_share = df.groupby("canal")["cantidad"].sum().reset_index()
    fig_canal = px.pie(
        canal_share,
        names="canal",
        values="cantidad",
        color_discrete_sequence=px.colors.qualitative.Set3,
        title="Participación de Unidades Vendidas por Canal"
    )
    fig_canal.update_traces(textinfo='percent+label')
    fig_canal.update_layout(
        plot_bgcolor="#F9F9F9",
        paper_bgcolor="#F9F9F9",
        font=dict(size=14),
        title_font=dict(size=22, color="#2C3E50")
    )
    st.plotly_chart(fig_canal, use_container_width=True)

    # 5.5 Detalle de datos
    with st.expander("Ver datos brutos"):
        st.dataframe(df, use_container_width=True)
