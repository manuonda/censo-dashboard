import unittest
from io import BytesIO

import pandas as pd

from datos import (
    columnas_categoricas,
    columnas_texto_libre,
    combinar_con_establecimientos,
    combinar_con_equipo_tratante,
    es_pii,
    normalizar_columnas,
    normalizar_dni,
    resumen_por_ministerio,
    sanear_tipos_mixtos,
)


def _excel_con(df: pd.DataFrame) -> pd.DataFrame:
    buf = BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return pd.read_excel(buf)


class TestColumnasCategoricas(unittest.TestCase):
    def test_pandas3_str_columns_se_detectan(self):
        """El bug: dtype str de pandas 3 no es object, y el selectbox quedaba en None."""
        crudo = _excel_con(
            pd.DataFrame(
                {
                    "Institución": ["Hospital público", "Casa del adolescente"],
                    "Sector": ["Público", "Público"],
                    "Nombre": ["A", "B"],
                    "DNI": ["30111222", "30111223"],
                }
            )
        )
        texto = [c for c in crudo.columns if pd.api.types.is_string_dtype(crudo[c])]
        self.assertIn("Institución", texto, f"dtypes: {crudo.dtypes.to_dict()}")
        viejo = [c for c in crudo.columns if crudo[c].dtype == object]
        self.assertEqual(viejo, [], "el criterio viejo (dtype == object) no ve columnas str")
        self.assertEqual(columnas_categoricas(crudo), ["Institución", "Sector"])

    def test_alta_cardinalidad_no_es_categorica(self):
        """Más de 25 valores únicos: no sirve como select, pasa a texto libre."""
        valores = [f"Institución {i}" for i in range(30)]
        df = pd.DataFrame({"Institución": valores, "Sector": ["Público"] * 30})
        self.assertNotIn("Institución", columnas_categoricas(df))
        self.assertIn("Institución", columnas_texto_libre(df))
        self.assertIn("Sector", columnas_categoricas(df))

    def test_pii_nunca_es_filtro(self):
        """DNI/Nombre no deben aparecer ni como select ni como input, aunque tengan alta cardinalidad."""
        df = pd.DataFrame(
            {
                "1. Nombres y Apellido": [f"Persona {i}" for i in range(30)],
                "Nº de Documento de Identidad": [str(30000000 + i) for i in range(30)],
                "Sector": ["Público"] * 30,
            }
        )
        self.assertNotIn("1. Nombres y Apellido", columnas_categoricas(df))
        self.assertNotIn("1. Nombres y Apellido", columnas_texto_libre(df))
        self.assertNotIn("Nº de Documento de Identidad", columnas_categoricas(df))
        self.assertNotIn("Nº de Documento de Identidad", columnas_texto_libre(df))

    def test_normaliza_headers_nan(self):
        df = pd.DataFrame([["a", "b"]], columns=["Institución", float("nan")])
        limpio = normalizar_columnas(df)
        self.assertNotIn(True, [pd.isna(c) for c in limpio.columns])
        self.assertTrue(all(isinstance(c, str) and c for c in limpio.columns))

    def test_pii_por_substring(self):
        self.assertTrue(es_pii("DNI"))
        self.assertTrue(es_pii("Nombre"))
        self.assertTrue(es_pii("1. Nombres y Apellido"))
        self.assertTrue(es_pii("Nº de Documento de Identidad"))
        self.assertTrue(es_pii("Teléfono de contacto"))
        self.assertTrue(es_pii("Domicilio"))
        self.assertFalse(es_pii("Institución"))
        self.assertFalse(es_pii("Sector"))


class TestSanearTiposMixtos(unittest.TestCase):
    def test_columna_mixta_pasa_a_texto(self):
        """DNI/Teléfono con números y texto ('No tiene') rompían la
        serialización a Arrow; deben quedar todos como str."""
        df = pd.DataFrame({"DNI": [30111222, "No tiene", 30111223]})
        saneado = sanear_tipos_mixtos(df)
        self.assertTrue(all(isinstance(v, str) for v in saneado["DNI"]))
        self.assertEqual(saneado["DNI"].tolist(), ["30111222", "No tiene", "30111223"])

    def test_columna_sin_mezcla_no_se_toca(self):
        df = pd.DataFrame({"Sector": ["Público", "Privado"]})
        saneado = sanear_tipos_mixtos(df)
        self.assertEqual(saneado["Sector"].tolist(), ["Público", "Privado"])

    def test_nan_se_preserva(self):
        df = pd.DataFrame({"DNI": [30111222, "No tiene", float("nan")]})
        saneado = sanear_tipos_mixtos(df)
        self.assertTrue(pd.isna(saneado["DNI"].iloc[2]))


class TestNormalizarDni(unittest.TestCase):
    def test_saca_puntos_y_espacios(self):
        self.assertEqual(normalizar_dni("30.111.222"), "30111222")
        self.assertEqual(normalizar_dni(" 30111222 "), "30111222")

    def test_numero_se_convierte_a_string(self):
        self.assertEqual(normalizar_dni(30111222), "30111222")

    def test_no_tiene_devuelve_none(self):
        self.assertIsNone(normalizar_dni("No tiene"))

    def test_nan_devuelve_none(self):
        self.assertIsNone(normalizar_dni(float("nan")))


class TestCruceEstablecimientos(unittest.TestCase):
    def setUp(self):
        self.establecimientos = pd.DataFrame(
            {
                "Establecimiento": [
                    "Hospital Nuestro Señor De la Buena Esperanza",
                    "Casa de Adolescente ",
                    "Comunidad Terapeutica. Servicio penitenciario",
                    'Residencia "Nicky"',
                ],
                "Tipo de establecimiento": [
                    "Hospital",
                    "Residencial-convivencial",
                    "Residencial-convivencial",
                    "Residencial-convivencial",
                ],
                "Sector": ["Publico", "Publico", "Publico", "Privado"],
                "Institucion": [
                    "Ministerio de salud",
                    "Ministerio de Desarrollo Humano",
                    "Ministerio de Seguridad",
                    None,
                ],
            }
        )

    def test_join_case_insensitive_y_con_espacios(self):
        respuestas = pd.DataFrame(
            {
                # distinta capitalización y espacios que en Establecimientos
                "Nombre de la institucion2": [
                    "hospital nuestro señor de la buena esperanza",
                    "CASA DE ADOLESCENTE",
                ],
                "5. Sexo": ["Mujer", "Hombre"],
            }
        )
        combinado = combinar_con_establecimientos(respuestas, self.establecimientos)
        self.assertEqual(
            combinado["Sector"].tolist(),
            ["Publico", "Publico"],
        )
        self.assertEqual(
            combinado["Institucion"].tolist(),
            ["Ministerio de salud", "Ministerio de Desarrollo Humano"],
        )

    def test_institucion_sin_match_queda_sin_dato_no_se_pierde_la_fila(self):
        respuestas = pd.DataFrame(
            {
                "Nombre de la institucion2": ["Establecimiento inexistente"],
                "5. Sexo": ["Mujer"],
            }
        )
        combinado = combinar_con_establecimientos(respuestas, self.establecimientos)
        self.assertEqual(len(combinado), 1)
        self.assertTrue(pd.isna(combinado["Sector"].iloc[0]))

    def test_resumen_por_ministerio_cuenta_personas(self):
        respuestas = pd.DataFrame(
            {
                "Nombre de la institucion2": [
                    "Hospital Nuestro Señor De la Buena Esperanza",
                    "Hospital Nuestro Señor De la Buena Esperanza",
                    "Casa de Adolescente",
                    'Residencia "Nicky"',
                ],
            }
        )
        combinado = combinar_con_establecimientos(respuestas, self.establecimientos)
        resumen = resumen_por_ministerio(combinado)

        fila_salud = resumen[
            (resumen["Institucion"] == "Ministerio de salud")
            & (resumen["Tipo de establecimiento"] == "Hospital")
        ]
        self.assertEqual(fila_salud["cantidad"].iloc[0], 2)

        fila_privado = resumen[resumen["Institucion"].isna()]
        self.assertEqual(fila_privado["cantidad"].iloc[0], 1)

        self.assertEqual(resumen["cantidad"].sum(), 4)


class TestCruceEquipoTratante(unittest.TestCase):
    def setUp(self):
        self.censo = pd.DataFrame(
            {
                "4. Nº de Documento de Identidad": [30111222, 40222333],
                "5. Sexo": ["Mujer", "Hombre"],
            }
        )
        self.equipo = pd.DataFrame(
            {
                "DNI del paciente": ["30.111.222", "40.222.333"],
                "35. ¿Qué tipo de internación/ingreso realizo el equipo?": [
                    "Judicial",
                    "Voluntaria",
                ],
            }
        )

    def test_cruza_por_dni_normalizado_y_agrega_columnas_al_final(self):
        combinado, sin_cruzar = combinar_con_equipo_tratante(
            self.censo,
            self.equipo,
            col_dni_censo="4. Nº de Documento de Identidad",
            col_dni_equipo="DNI del paciente",
        )
        self.assertEqual(list(combinado.columns)[:2], list(self.censo.columns))
        self.assertEqual(
            combinado["35. ¿Qué tipo de internación/ingreso realizo el equipo?"].tolist(),
            ["Judicial", "Voluntaria"],
        )
        self.assertTrue(sin_cruzar.empty)

    def test_persona_del_censo_sin_equipo_tratante_no_se_pierde(self):
        censo = pd.DataFrame(
            {
                "4. Nº de Documento de Identidad": [30111222, 99999999],
                "5. Sexo": ["Mujer", "Hombre"],
            }
        )
        combinado, _ = combinar_con_equipo_tratante(
            censo,
            self.equipo,
            col_dni_censo="4. Nº de Documento de Identidad",
            col_dni_equipo="DNI del paciente",
        )
        self.assertEqual(len(combinado), 2)
        col_equipo = "35. ¿Qué tipo de internación/ingreso realizo el equipo?"
        self.assertTrue(pd.isna(combinado[col_equipo].iloc[1]))

    def test_dni_duplicado_en_equipo_se_queda_con_el_primero(self):
        equipo_duplicado = pd.DataFrame(
            {
                "DNI del paciente": ["30.111.222", "30.111.222"],
                "35. ¿Qué tipo de internación/ingreso realizo el equipo?": [
                    "Judicial",
                    "Voluntaria",
                ],
            }
        )
        combinado, _ = combinar_con_equipo_tratante(
            self.censo,
            equipo_duplicado,
            col_dni_censo="4. Nº de Documento de Identidad",
            col_dni_equipo="DNI del paciente",
        )
        self.assertEqual(len(combinado), 2)
        self.assertEqual(
            combinado["35. ¿Qué tipo de internación/ingreso realizo el equipo?"].iloc[0],
            "Judicial",
        )

    def test_dni_de_equipo_que_no_esta_en_el_censo_va_a_sin_cruzar(self):
        equipo = pd.DataFrame(
            {
                "DNI del paciente": ["30.111.222", "55.555.555"],
                "35. ¿Qué tipo de internación/ingreso realizo el equipo?": [
                    "Judicial",
                    "Voluntaria",
                ],
            }
        )
        _, sin_cruzar = combinar_con_equipo_tratante(
            self.censo,
            equipo,
            col_dni_censo="4. Nº de Documento de Identidad",
            col_dni_equipo="DNI del paciente",
        )
        self.assertEqual(len(sin_cruzar), 1)
        self.assertEqual(sin_cruzar["DNI del paciente"].iloc[0], "55.555.555")

    def test_dni_no_tiene_no_matchea_entre_si(self):
        censo = pd.DataFrame(
            {
                "4. Nº de Documento de Identidad": ["No tiene"],
                "5. Sexo": ["Mujer"],
            }
        )
        equipo = pd.DataFrame(
            {
                "DNI del paciente": ["No tiene"],
                "35. ¿Qué tipo de internación/ingreso realizo el equipo?": ["Judicial"],
            }
        )
        combinado, sin_cruzar = combinar_con_equipo_tratante(
            censo,
            equipo,
            col_dni_censo="4. Nº de Documento de Identidad",
            col_dni_equipo="DNI del paciente",
        )
        col_equipo = "35. ¿Qué tipo de internación/ingreso realizo el equipo?"
        self.assertTrue(pd.isna(combinado[col_equipo].iloc[0]))
        self.assertEqual(len(sin_cruzar), 1)


if __name__ == "__main__":
    unittest.main()
