"""Servidor HTTP de solo lectura para búsquedas AbsysNet Opac."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
from typing import Type
from urllib.parse import parse_qs, urlsplit

from .client import OpacClient, OpacError
from .models import SearchQuery, SearchResult

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000
_DEFAULT_MAX_PAGES = 10
_MAX_ALLOWED_PAGES = 100


def _parse_search_query(raw_query: str) -> SearchQuery:
    """Interpreta parámetros GET con los mismos campos que SearchQuery."""
    values = parse_qs(raw_query, keep_blank_values=False, strict_parsing=False)
    allowed = set(SearchQuery._fields)
    unknown = set(values) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Parámetros de búsqueda desconocidos: {names}")

    fields: dict[str, str] = {}
    for name, entries in values.items():
        if len(entries) != 1:
            raise ValueError(f"El parámetro {name} no puede repetirse.")
        fields[name] = entries[0]
    return SearchQuery(**fields)


def _serialize_results(results: tuple[SearchResult, ...]) -> bytes:
    """Serializa NamedTuple anidados a una lista de objetos JSON."""
    payload = []
    for result in results:
        item = result._asdict()
        payload.append(item)
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _make_handler(
    catalog_urls: tuple[str, ...],
    max_pages: int,
) -> Type[BaseHTTPRequestHandler]:
    class SearchHandler(BaseHTTPRequestHandler):
        server_version = "opac-search/1.0"

        def _send_json(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _send_error_json(self, status: int, message: str) -> None:
            payload = json.dumps(
                {"error": message}, ensure_ascii=False
            ).encode("utf-8")
            self._send_json(status, payload)

        def do_GET(self) -> None:
            request = urlsplit(self.path)
            if request.path != "/search":
                self._send_error_json(404, "Ruta no encontrada; usa /search.")
                return
            try:
                query = _parse_search_query(request.query)
            except ValueError as exc:
                self._send_error_json(400, str(exc))
                return

            results: list[SearchResult] = []
            try:
                for catalog_url in catalog_urls:
                    client = OpacClient(catalog_url)
                    results.extend(
                        client.search_all(query, max_pages=max_pages)
                    )
            except (OpacError, OSError, ValueError) as exc:
                self._send_error_json(502, str(exc))
                return

            self._send_json(200, _serialize_results(tuple(results)))

        def log_message(self, format_string: str, *args: object) -> None:
            print(
                f"{self.address_string()} - {format_string % args}",
                file=sys.stderr,
            )

    return SearchHandler


def _environment_config() -> tuple[str, int, tuple[str, ...], int]:
    raw_urls = os.environ.get("OPAC_URL", "")
    catalog_urls = tuple(raw_urls.split())
    if not catalog_urls:
        raise ValueError(
            "Define OPAC_URL con URLs separadas por espacios."
        )

    host = os.environ.get("OPAC_HOST", _DEFAULT_HOST)
    try:
        port = int(os.environ.get("OPAC_PORT", str(_DEFAULT_PORT)))
        max_pages = int(
            os.environ.get("OPAC_MAX_PAGES", str(_DEFAULT_MAX_PAGES))
        )
    except ValueError as exc:
        raise ValueError(
            "OPAC_PORT y OPAC_MAX_PAGES deben ser enteros."
        ) from exc

    if not 1 <= port <= 65535:
        raise ValueError("OPAC_PORT debe estar entre 1 y 65535.")
    if not 1 <= max_pages <= _MAX_ALLOWED_PAGES:
        raise ValueError(
            f"OPAC_MAX_PAGES debe estar entre 1 y {_MAX_ALLOWED_PAGES}."
        )
    return host, port, catalog_urls, max_pages


def main() -> int:
    """Inicia el servidor usando los ajustes del entorno."""
    try:
        host, port, catalog_urls, max_pages = _environment_config()
        server = HTTPServer(
            (host, port),
            _make_handler(catalog_urls, max_pages),
        )
    except (OSError, ValueError) as exc:
        print(f"opac-server: {exc}", file=sys.stderr)
        return 2

    print(f"Servidor opac escuchando en http://{host}:{port}/search")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
