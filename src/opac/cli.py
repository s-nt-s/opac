"""Interfaz de línea de comandos para opac-client."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .client import OpacClient, OpacError
from .models import SearchQuery, SearchResult


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opac",
        description=(
            "Busca libros, películas y otros recursos "
            "en un catálogo AbsysNet Opac."
        ),
    )
    parser.add_argument(
        "url",
        help="URL del catálogo (p. ej. http://gestiona.comunidad.madrid/biblio_publicas/cgi-bin/abnetopac)",
    )
    parser.add_argument(
        "keywords",
        nargs="?",
        default="",
        help="Palabras clave",
    )
    parser.add_argument(
        "--page", type=int, default=1, help="Página que se consultará"
    )
    parser.add_argument(
        "--all",
        dest="all_pages",
        action="store_true",
        help="Recorrer todas las páginas",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Límite de páginas para --all",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Tiempo máximo de espera en segundos",
    )

    parser.add_argument("--expert-search", dest="expert_any_field")
    parser.add_argument("--title")
    parser.add_argument("--author")
    parser.add_argument("--editorial")
    parser.add_argument("--subject")
    parser.add_argument("--collection")
    parser.add_argument("--genre")
    parser.add_argument("--min-publish-date")
    parser.add_argument("--max-publish-date")
    parser.add_argument("--language")
    parser.add_argument("--country")
    parser.add_argument("--medium")
    parser.add_argument("--sort-by")
    parser.add_argument("--items-per-page", type=int, default=100)
    parser.add_argument(
        "--json", action="store_true", help="Imprimir resultados como JSON"
    )
    return parser


def _query_from_args(args: argparse.Namespace) -> SearchQuery:
    return SearchQuery(
        normal_any_field=args.keywords or None,
        expert_any_field=args.expert_any_field,
        title=args.title,
        author=args.author,
        editorial=args.editorial,
        subject=args.subject,
        collection=args.collection,
        genre=args.genre,
        min_publish_date=args.min_publish_date,
        max_publish_date=args.max_publish_date,
        language=args.language,
        country=args.country,
        medium=args.medium,
        sort_by=args.sort_by or "56297072",
        items_per_page=args.items_per_page,
    )


def _print_result(item: SearchResult, index: int) -> None:
    kind = item.resource_type or "Recurso"
    print(f"{index}. {item.title} [{kind}]")
    if item.author:
        print(f"   Autoría: {item.author}")
    if item.year:
        print(f"   Año: {item.year}")
    if item.language:
        print(f"   Idioma: {item.language}")
    if item.titn:
        print(f"   Número de registro: {item.titn}")
    if item.description:
        print(f"   {item.description}")
    if item.cover_url:
        print(f"   Cubierta: {item.cover_url}")


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada del comando `opac`."""
    args = _build_parser().parse_args(argv)
    query = _query_from_args(args)
    try:
        client = OpacClient(args.url, timeout=args.timeout)
        if args.all_pages:
            items = client.search_all(
                query,
                max_pages=args.max_pages,
            )
            page_result = None
        else:
            page_result = client.search(
                query,
                page=args.page,
            )
            items = page_result.items
    except (OpacError, TypeError, ValueError) as exc:
        print(f"Opac: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload: dict[str, object] = {
            "items": [_result_to_dict(item) for item in items]
        }
        if page_result is not None:
            payload.update(
                current_page=page_result.current_page,
                page_numbers=page_result.page_numbers,
                next_page_url=page_result.next_page_url,
            )
        else:
            payload["all_pages"] = True
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not items:
        print("No se encontraron recursos.")
    else:
        for index, item in enumerate(items, start=1):
            _print_result(item, index)
    if page_result and page_result.next_page_url:
        print(f"Página siguiente: {page_result.next_page_url}")
    if args.all_pages:
        print(f"Total de recursos recuperados: {len(items)}")
    return 0


def _result_to_dict(item: SearchResult) -> dict[str, object]:
    """Serializa los campos del modelo de resultado a un objeto JSON."""
    return item._asdict()


if __name__ == "__main__":
    raise SystemExit(main())
