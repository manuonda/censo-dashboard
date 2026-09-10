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
    der = der.drop(columns=[col_join_establecimientos]).drop_duplicates(subset="_clave")

    combinado = izq.merge(der, on="_clave", how="left")
    return combinado.drop(columns=["_clave"])


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
