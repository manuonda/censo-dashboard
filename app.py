import pandas as pd
import plotly.express as px
import streamlit as st

from datos import (
    columnas_categoricas,
    columnas_texto_libre,
    combinar_con_establecimientos,
    es_pii,
    normalizar_columnas,
    opciones_unicas,
    resumen_por_ministerio,
)

COLUMNA_INSTITUCION_RESPUESTAS = "Nombre de la institucion2"
HOJA_ESTABLECIMIENTOS = "Establecimientos"

st.set_page_config(page_title="Censo - Visualización", layout="wide")

st.title("Visualización del censo")
st.caption("Cargá el Excel, filtrá y mirá la distribución en gráficos de torta.")

archivo = st.file_uploader("Subí el archivo Excel (.xlsx)", type=["xlsx"])

if archivo is None:
    st.info("Subí un archivo para empezar.")
    st.stop()

xl = pd.ExcelFile(archivo)
hoja = (
    st.selectbox("Pestaña", xl.sheet_names)
    if len(xl.sheet_names) > 1
    else xl.sheet_names[0]
)
if len(xl.sheet_names) == 1:
    st.caption(f"Pestaña: {hoja}")

df = normalizar_columnas(pd.read_excel(xl, sheet_name=hoja))
st.success(f"Se cargaron {len(df)} filas.")

if (
    HOJA_ESTABLECIMIENTOS in xl.sheet_names
    and hoja != HOJA_ESTABLECIMIENTOS
    and COLUMNA_INSTITUCION_RESPUESTAS in df.columns
):
    df_establecimientos = normalizar_columnas(
        pd.read_excel(xl, sheet_name=HOJA_ESTABLECIMIENTOS)
    )
    combinado = combinar_con_establecimientos(
        df, df_establecimientos, col_join_respuestas=COLUMNA_INSTITUCION_RESPUESTAS
    )
    resumen = resumen_por_ministerio(combinado).rename(columns={"Institucion": "Ministerio"})
    resumen["Ministerio"] = resumen["Ministerio"].fillna("Privado / sin ministerio")

    st.subheader("Resumen general por ministerio")
    st.dataframe(resumen, width="stretch")
    fig_resumen = px.bar(
        resumen,
        x="Ministerio",
        y="cantidad",
        color="Tipo de establecimiento",
        title="Personas censadas por ministerio y tipo de establecimiento",
    )
    st.plotly_chart(fig_resumen, width="stretch", key="grafico_resumen_ministerio")

cols_select = columnas_categoricas(df)
cols_input = columnas_texto_libre(df)
if not cols_select:
    st.warning("No encontré columnas de texto para agrupar en esta pestaña.")
    st.dataframe(df.drop(columns=[c for c in df.columns if es_pii(c)], errors="ignore"))
    st.stop()

st.sidebar.header("Filtros")
df_filtrado = df.copy()

for col in cols_select:
    opciones = opciones_unicas(df[col])
    seleccion = st.sidebar.multiselect(col, opciones, default=opciones)
    if seleccion:
        df_filtrado = df_filtrado[df_filtrado[col].isin(seleccion)]

for col in cols_input:
    busqueda = st.sidebar.text_input(col)
    if busqueda:
        df_filtrado = df_filtrado[
            df_filtrado[col].astype(str).str.contains(busqueda, case=False, na=False)
        ]

st.write(f"**{len(df_filtrado)}** filas después de aplicar los filtros.")

if df_filtrado.empty:
    st.warning("No hay datos con esos filtros.")
    st.stop()

st.subheader("Distribución")
col_izq, col_der = st.columns(2)

with col_izq:
    dim1 = st.selectbox("Agrupar por", cols_select, index=0, key="dim1")
    conteo1 = df_filtrado[dim1].value_counts().reset_index()
    conteo1.columns = [dim1, "cantidad"]
    fig1 = px.pie(conteo1, names=dim1, values="cantidad", title=f"Por {dim1}")
    st.plotly_chart(fig1, width="stretch", key="grafico_dim1")

with col_der:
    dim2 = st.selectbox(
        "Agrupar por (segundo gráfico)",
        cols_select,
        index=min(1, len(cols_select) - 1),
        key="dim2",
    )
    conteo2 = df_filtrado[dim2].value_counts().reset_index()
    conteo2.columns = [dim2, "cantidad"]
    fig2 = px.pie(conteo2, names=dim2, values="cantidad", title=f"Por {dim2}")
    st.plotly_chart(fig2, width="stretch", key="grafico_dim2")

visibles = [c for c in df_filtrado.columns if not es_pii(c)]
st.subheader("Tabla de datos filtrados")
st.dataframe(df_filtrado[visibles], width="stretch")

csv = df_filtrado[visibles].to_csv(index=False).encode("utf-8")
st.download_button("Descargar datos filtrados (CSV)", csv, "datos_filtrados.csv", "text/csv")
