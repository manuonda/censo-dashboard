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
    rellenar_sin_dato,
    resumen_por_ministerio,
    sanear_tipos_mixtos,
)

COLUMNA_INSTITUCION_RESPUESTAS = "Nombre de la institucion2"
HOJA_ESTABLECIMIENTOS = "Establecimientos"
# Orden del filtro en cascada: cada select acota las opciones del siguiente.
COLUMNAS_CASCADA_ESTABLECIMIENTO = [
    ("Institucion", "Institución"),
    ("Sector", "Sector"),
    ("Tipo de establecimiento", "Tipo de establecimiento"),
    ("Establecimiento", "Establecimiento"),
]


def _sincronizar_seleccion(key: str, opciones_validas: list) -> None:
    """Antes de crear el widget, saca del session_state los valores que ya
    no están entre las opciones (por haber cambiado un filtro anterior en la
    cascada, o por un "Completar todos" con opciones de otro alcance). Sin
    esto, Streamlit tira error porque el valor guardado ya no pertenece a
    las opciones nuevas."""
    if key in st.session_state:
        st.session_state[key] = [v for v in st.session_state[key] if v in opciones_validas]


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

df = sanear_tipos_mixtos(normalizar_columnas(pd.read_excel(xl, sheet_name=hoja)))
st.success(f"Se cargaron {len(df)} filas.")

hay_establecimientos = (
    HOJA_ESTABLECIMIENTOS in xl.sheet_names
    and hoja != HOJA_ESTABLECIMIENTOS
    and COLUMNA_INSTITUCION_RESPUESTAS in df.columns
)

if hay_establecimientos:
    df_establecimientos = sanear_tipos_mixtos(
        normalizar_columnas(pd.read_excel(xl, sheet_name=HOJA_ESTABLECIMIENTOS))
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

    df_base = combinado
else:
    df_base = df

cols_select = columnas_categoricas(df_base)
cols_input = columnas_texto_libre(df_base)
if not cols_select:
    st.warning("No encontré columnas de texto para agrupar en esta pestaña.")
    st.dataframe(df_base.drop(columns=[c for c in df_base.columns if es_pii(c)], errors="ignore"))
    st.stop()

df_base = rellenar_sin_dato(df_base, cols_select)

nombres_cascada = {col for col, _ in COLUMNAS_CASCADA_ESTABLECIMIENTO}
cols_select_genericas = [c for c in cols_select if c not in nombres_cascada]
opciones_completas_genericas = {col: opciones_unicas(df_base[col]) for col in cols_select_genericas}
opciones_completas_cascada = (
    {col: sorted(v for v in df_base[col].dropna().unique()) for col, _ in COLUMNAS_CASCADA_ESTABLECIMIENTO}
    if hay_establecimientos
    else {}
)

st.sidebar.header("Filtros")
col_btn_todos, col_btn_limpiar = st.sidebar.columns(2)
if col_btn_todos.button("Completar todos", width="stretch"):
    for col in cols_select_genericas:
        st.session_state[f"filtro_{col}"] = opciones_completas_genericas[col]
    for col, _ in COLUMNAS_CASCADA_ESTABLECIMIENTO:
        st.session_state[f"filtro_cascada_{col}"] = opciones_completas_cascada.get(col, [])
    for col in cols_input:
        st.session_state[f"busqueda_{col}"] = ""
    st.rerun()
if col_btn_limpiar.button("Limpiar todos", width="stretch"):
    for col in cols_select_genericas:
        st.session_state[f"filtro_{col}"] = []
    for col, _ in COLUMNAS_CASCADA_ESTABLECIMIENTO:
        st.session_state[f"filtro_cascada_{col}"] = []
    for col in cols_input:
        st.session_state[f"busqueda_{col}"] = ""
    st.rerun()

df_filtrado = df_base.copy()

if hay_establecimientos:
    st.sidebar.header("Filtro por establecimiento")
    for columna, etiqueta in COLUMNAS_CASCADA_ESTABLECIMIENTO:
        opciones_col = sorted(v for v in df_filtrado[columna].dropna().unique())
        key = f"filtro_cascada_{columna}"
        _sincronizar_seleccion(key, opciones_col)
        seleccion_col = st.sidebar.multiselect(
            etiqueta, opciones_col, default=opciones_col, key=key
        )
        if seleccion_col:
            df_filtrado = df_filtrado[df_filtrado[columna].isin(seleccion_col)]

st.sidebar.header("Otros filtros")
for col in cols_select_genericas:
    opciones = opciones_unicas(df_filtrado[col])
    key = f"filtro_{col}"
    _sincronizar_seleccion(key, opciones)
    seleccion = st.sidebar.multiselect(col, opciones, default=opciones, key=key)
    if seleccion:
        df_filtrado = df_filtrado[df_filtrado[col].isin(seleccion)]

for col in cols_input:
    busqueda = st.sidebar.text_input(col, key=f"busqueda_{col}")
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

visibles = list(df_filtrado.columns)
st.subheader("Tabla de datos filtrados")
st.dataframe(df_filtrado[visibles], width="stretch")

st.caption(
    "El CSV descargable incluye columnas con datos personales "
    "(Nombre y Apellido, DNI, Teléfono, Domicilio). Manejalo con cuidado."
)
csv = df_filtrado.to_csv(index=False).encode("utf-8")
st.download_button("Descargar datos filtrados (CSV)", csv, "datos_filtrados.csv", "text/csv")
