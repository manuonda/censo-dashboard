import pandas as pd

# Substrings (en minúscula) que marcan una columna como dato personal identificable.
# Se busca por substring, no por match exacto, porque las columnas reales vienen con
# prefijos de pregunta como "1. Nombres y Apellido" o "Nº de Documento de Identidad".
PII_SUBSTRINGS = (
    "nombre",
    "apellido",
    "dni",
    "documento",
    "telefono",
    "teléfono",
    "domicilio",
)

# Cantidad de valores únicos a partir de la cual una columna de texto deja de ser
# una buena candidata para un select/multiselect y pasa a filtrarse por texto libre.
UMBRAL_CARDINALIDAD = 25

# Etiqueta para celdas vacías (NaN) en columnas categóricas. Se unifica con
# respuestas como "Se desconoce" para que las filas sin dato no queden
# invisibles en los filtros y gráficos.
ETIQUETA_SIN_DATO = "Se desconoce"


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Nombres de columna usables: sin NaN, vacíos ni Unnamed."""
    df = df.copy()
    nombres = []
    vistos = {}
    for i, crudo in enumerate(df.columns):
        if pd.isna(crudo):
            nombre = f"columna_{i + 1}"
        else:
            nombre = str(crudo).strip()
            if not nombre or nombre.lower().startswith("unnamed"):
                nombre = f"columna_{i + 1}"
        if nombre in vistos:
            vistos[nombre] += 1
            nombre = f"{nombre}_{vistos[nombre]}"
        else:
            vistos[nombre] = 1
        nombres.append(nombre)
    df.columns = nombres
    return df


def sanear_tipos_mixtos(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte a texto las columnas object que mezclan tipos (p. ej. DNI o
    Teléfono con números y textos tipo "No tiene").

    Son campos de texto libre en el formulario: pandas los deja como object
    con Python int/float/str mezclados, y pyarrow no puede serializar eso
    para mostrarlo en una tabla de Streamlit (ArrowTypeError/ArrowInvalid).
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype != object:
            continue
        tipos = {type(v) for v in df[col].dropna()}
        if len(tipos) > 1:
            df[col] = df[col].apply(lambda v: str(v) if pd.notna(v) else v)
    return df


def es_pii(nombre: str) -> bool:
    normalizado = str(nombre).strip().lower()
    return any(sub in normalizado for sub in PII_SUBSTRINGS)


def es_texto(serie: pd.Series) -> bool:
    return (
        pd.api.types.is_string_dtype(serie)
        or pd.api.types.is_object_dtype(serie)
        or isinstance(serie.dtype, pd.CategoricalDtype)
    )


def columnas_categoricas(df: pd.DataFrame, umbral: int = UMBRAL_CARDINALIDAD) -> list[str]:
    """Columnas de texto, no PII, con pocos valores únicos: candidatas a select/multiselect."""
    return [
        c
        for c in df.columns
        if not es_pii(c) and es_texto(df[c]) and df[c].dropna().nunique() <= umbral
    ]


def columnas_numericas(df: pd.DataFrame) -> list[str]:
    """Columnas numéricas, no PII: candidatas a filtro de rango (slider).

    Ej.: "2. Edad". El DNI también es numérico en el Excel pero se excluye
    por PII, igual que en columnas_categoricas/columnas_texto_libre. La "#"
    de Establecimientos también se excluye: es la numeración correlativa de
    la fila, no un dato del censo.
    """
    return [
        c
        for c in df.columns
        if str(c).strip() != "#"
        and not es_pii(c)
        and pd.api.types.is_numeric_dtype(df[c])
    ]


def columnas_texto_libre(df: pd.DataFrame, umbral: int = UMBRAL_CARDINALIDAD) -> list[str]:
    """Columnas de texto, no PII, con muchos valores únicos: candidatas a input de búsqueda."""
    return [
        c
        for c in df.columns
        if not es_pii(c) and es_texto(df[c]) and df[c].dropna().nunique() > umbral
    ]


def opciones_unicas(serie: pd.Series) -> list:
    valores = [v for v in serie.dropna().unique().tolist()]
    return sorted(valores, key=lambda v: str(v))


def rellenar_sin_dato(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Reemplaza NaN por ETIQUETA_SIN_DATO en las columnas dadas.

    Sin esto, una fila con la celda vacía nunca matchea en un filtro
    multiselect (NaN no es igual a ningún valor de la lista) ni aparece
    como opción, aunque el usuario seleccione "Se desconoce" a mano.
    """
    df = df.copy()
    for col in columnas:
        df[col] = df[col].fillna(ETIQUETA_SIN_DATO)
    return df


def normalizar_dni(valor) -> str | None:
    """Deja el DNI como solo dígitos para poder cruzar excels que lo tipean
    distinto (con puntos, con espacios, como número o como texto).

    Devuelve None si no queda ningún dígito (valor vacío o "No tiene"), para
    que esos casos no matcheen entre sí como si fueran la misma persona.
    """
    if pd.isna(valor):
        return None
    digitos = "".join(c for c in str(valor) if c.isdigit())
    return digitos or None


def _clave_join(valor) -> str:
    """Normaliza un nombre de institución para cruzar hojas sin que rompan
    mayúsculas/minúsculas ni espacios de más."""
    if pd.isna(valor):
        return ""
    return " ".join(str(valor).strip().lower().split())


def combinar_con_establecimientos(
    df_respuestas: pd.DataFrame,
    df_establecimientos: pd.DataFrame,
    col_join_respuestas: str = "Nombre de la institucion2",
    col_join_establecimientos: str = "Establecimiento",
) -> pd.DataFrame:
    """Cruza las respuestas del censo con el catálogo de Establecimientos
    (Tipo de establecimiento, Sector, Institucion/ministerio, tipo de estadia).

    El cruce es case-insensitive e ignora espacios extra en el nombre de la
    institución, porque los datos reales vienen con inconsistencias de tipeo.
    Las filas sin match conservan la persona, con las columnas del catálogo
    en NaN (no se descartan personas por un nombre de institución que no
    matcheó).
    """
    izq = df_respuestas.copy()
    der = df_establecimientos.copy()
    izq["_clave"] = izq[col_join_respuestas].map(_clave_join)
    der["_clave"] = der[col_join_establecimientos].map(_clave_join)
    # Se conserva el nombre canónico de "Establecimiento" (a diferencia de
    # col_join_respuestas, que puede venir con mayúsculas/espacios distintos)
    # porque también se usa como filtro en pantalla.
    der = der.drop_duplicates(subset="_clave")

    combinado = izq.merge(der, on="_clave", how="left")
    return combinado.drop(columns=["_clave"])


def combinar_con_equipo_tratante(
    df_censo: pd.DataFrame,
    df_equipo: pd.DataFrame,
    col_dni_censo: str,
    col_dni_equipo: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cruza el censo con las respuestas de Equipo tratante por DNI,
    agregando las columnas de Equipo tratante al final.

    El DNI se normaliza (sin puntos/espacios) porque cada excel lo tipea
    distinto. Un DNI vacío o "No tiene" nunca matchea, ni siquiera contra
    otro "No tiene" (normalizar_dni los deja en None, y None no matchea con
    None en un merge por clave).

    Devuelve (combinado, sin_cruzar):
    - combinado: todas las filas del censo, con las columnas de Equipo
      tratante en NaN si no hubo match (no se pierde a nadie del censo).
    - sin_cruzar: filas de Equipo tratante cuyo DNI no está en el censo,
      para poder mostrarlas aparte como "no se pudieron cruzar".
    """
    izq = df_censo.copy()
    der = df_equipo.copy()
    izq["_dni"] = izq[col_dni_censo].map(normalizar_dni)
    der["_dni"] = der[col_dni_equipo].map(normalizar_dni)

    der_dedup = der[der["_dni"].notna()].drop_duplicates(subset="_dni", keep="first")

    combinado = izq.merge(
        der_dedup.drop(columns=[col_dni_equipo]), on="_dni", how="left"
    ).drop(columns=["_dni"])

    dnis_censo = set(izq["_dni"].dropna())
    # Sin DNI válido (vacío/"No tiene") tampoco se pudo cruzar: no hay forma
    # de saber a qué persona del censo corresponde.
    matcheo = der["_dni"].notna() & der["_dni"].isin(dnis_censo)
    sin_cruzar = der[~matcheo].drop(columns=["_dni"])

    return combinado, sin_cruzar


def resumen_por_ministerio(df_combinado: pd.DataFrame) -> pd.DataFrame:
    """Cantidad de personas censadas por Institucion (ministerio) x Tipo de
    establecimiento x Sector, a partir del resultado de
    `combinar_con_establecimientos`.

    Las instituciones privadas sin ministerio a cargo quedan con Institucion
    en NaN (no pertenecen a ninguno de los 3 ministerios).
    """
    columnas = ["Institucion", "Tipo de establecimiento", "Sector"]
    resumen = (
        df_combinado.groupby(columnas, dropna=False)
        .size()
        .reset_index(name="cantidad")
    )
    return resumen.sort_values("cantidad", ascending=False).reset_index(drop=True)
