# Censo - Visualización

App simple para cargar un Excel del censo, filtrarlo y ver gráficos de torta.

## Probarlo en tu máquina

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre solo en el navegador (http://localhost:8501).

## Deploy gratis en Streamlit Community Cloud

1. Creá un repositorio en GitHub y subí estos 3 archivos (`app.py`, `requirements.txt`, `README.md`).
2. Andá a https://share.streamlit.io e iniciá sesión con tu cuenta de GitHub.
3. Click en "New app", elegí el repo, la rama (`main`) y el archivo principal (`app.py`).
4. Click en "Deploy". En un par de minutos tenés una URL pública (algo como `tu-app.streamlit.app`) para compartir con el cliente.

Cada vez que hagas un cambio y lo subas a GitHub, la app se actualiza sola.

## Qué hace la app

- Subís el Excel (`.xlsx`) con las columnas del censo (Establecimiento, Tipo de establecimiento, Sector, Institución, tipo de estadía, etc.).
- Si el archivo tiene una hoja **Establecimientos** (con columnas Establecimiento, Tipo de establecimiento, Sector, Institucion, tipo de estadia), la app cruza automáticamente esos datos con las respuestas del censo y muestra un **resumen general por Ministerio** (Salud, Desarrollo Humano, Seguridad) con tabla y gráfico de barras, antes de los filtros.
- En la barra lateral, las columnas con pocas opciones repetidas (Sexo, Sector, Institución, etc.) aparecen como **multiselect**; las columnas de texto con muchos valores distintos (que no sean datos personales) aparecen como **input de búsqueda**.
- Elegís por qué columna agrupar cada gráfico de torta (por ejemplo uno por Institución y otro por Tipo de establecimiento).
- Podés descargar los datos ya filtrados en CSV.

Las columnas de datos personales (Nombre, Apellido, DNI, Teléfono, Domicilio, y variantes como "1. Nombres y Apellido" o "Nº de Documento de Identidad") se detectan automáticamente y se excluyen siempre de filtros, gráficos y tabla — no se borran del archivo original, solo no se muestran en el dashboard.

## Correr los tests

```bash
python3 -m unittest test_datos.py -v
```