# Cliente OPAC para AbsysNet

Cliente de solo lectura, sin dependencias externas, para buscar recursos en catálogos compatibles con AbsysNet OPAC. Incluye una API Python, una interfaz de línea de comandos y un servidor HTTP opcional.

Requiere Python 3.10 o posterior.

## Instalación

Desde la raíz del proyecto:

```bash
python -m pip install -e .
```

La instalación editable crea los comandos `opac` y `opac-server`.

## Línea de comandos

Buscar «capital» y mostrar los primeros 10 resultados como JSON:

```bash
opac "https://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac" capital --items-per-page 10 --json
```

También se pueden usar filtros:

```bash
opac "https://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac" \
  --title "Madrid histórico" \
  --author "Sara Medialdea" \
  --language spa
```

Opciones frecuentes:

- `--page N`: consulta una página concreta.
- `--all`: recorre las páginas disponibles.
- `--max-pages N`: limita las páginas de `--all` (por defecto, 100).
- `--items-per-page N`: cantidad de registros por página (por defecto, 100).
- `--json`: imprime los resultados en JSON.
- `--expert-search`, `--title`, `--author`, `--editorial`, `--subject`, `--collection`, `--genre`.
- `--min-publish-date`, `--max-publish-date`, `--language`, `--country`, `--medium`, `--sort-by`.
- `--timeout SEGUNDOS`: tiempo máximo de espera por solicitud.

Sin instalar el paquete, se puede invocar desde la raíz con:

```bash
PYTHONPATH=src python -m opac.cli "https://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac" capital --items-per-page 10 --json
```

## Uso desde Python

```python
from opac import OpacClient, SearchQuery

catalog_url = (
    "https://gestiona.comunidad.madrid/"
    "biblio_publicas/cgi-bin/abnetopac"
)
client = OpacClient(catalog_url)
query = SearchQuery(normal_any_field="capital", items_per_page=10)

page = client.search(query)
for result in page.items:
    print(result.title, result.author, result.year)

if page.next_page_url:
    print("Siguiente página:", page.next_page_url)

# Recuperar varias páginas, con un límite para controlar las solicitudes.
results = client.search_all(query, max_pages=3)
print("Recursos recuperados:", len(results))
```

`SearchQuery` admite estos campos opcionales: `normal_any_field`, `expert_any_field`, `title`, `author`, `editorial`, `subject`, `collection`, `genre`, `min_publish_date`, `max_publish_date`, `language`, `country`, `medium`, `sort_by` e `items_per_page`.

Los filtros `language`, `country` y `medium` reciben el valor numérico exacto de la opción del catálogo (por ejemplo, `language="04"` para inglés). Cuando se usan, el cliente consulta el formulario avanzado. Si son los únicos criterios, agrega `*` a `normal_any_field`, como requiere el formulario AbsysNet para búsquedas solo con desplegables.

Cada elemento de `SearchResults.items` es un `SearchResult` con los campos `url`, `title`, `author`, `titn`, `language`, `year`, `resource_type`, `description` y `cover_url`. Los campos textuales no siempre están presentes en los registros del catálogo.

## Descargar un contenido binario

`get_bytes()` descarga el recurso identificado por `MLKOB` y devuelve el cuerpo sin decodificarlo. Por ejemplo, para guardar una cubierta:

```python
from pathlib import Path

image_data = client.get_bytes("1615031543737")
Path("cubierta.jpg").write_bytes(image_data)
```

Usa la extensión correspondiente al formato que entregue el catálogo. El cliente conserva las cookies y sigue redirecciones HTTP y `meta Refresh`.

## Servidor HTTP opcional

Configura `OPAC_URL` con una o varias URL de catálogos separadas por espacios y ejecuta el servidor:

```bash
OPAC_URL="https://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac" \
OPAC_HOST=127.0.0.1 OPAC_PORT=8000 OPAC_MAX_PAGES=10 opac-server
```

El servidor expone `GET /search`. Los nombres de los parámetros son los campos de `SearchQuery`:

```bash
curl --get http://127.0.0.1:8000/search \
  --data-urlencode "normal_any_field=capital" \
  --data-urlencode "language=spa"
```

Variables de entorno:

- `OPAC_URL`: requerido; URL o URLs de catálogos separadas por espacios.
- `OPAC_HOST`: dirección de escucha (por defecto, `127.0.0.1`).
- `OPAC_PORT`: puerto (por defecto, `8000`).
- `OPAC_MAX_PAGES`: máximo de páginas por catálogo (por defecto, `10`; máximo, `100`).

## Pruebas

Desde la raíz del repositorio:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Licencia

Consulta el archivo [LICENSE](LICENSE).
