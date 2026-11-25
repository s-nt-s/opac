"""Modelos inmutables de datos devueltos por el cliente."""

from typing import NamedTuple, Optional


class SearchResult(NamedTuple):
    """Un libro, película u otro recurso del catálogo."""
    url: str
    # span.js-T245
    title: str
    # span.span.js-TITN
    titn: int
    # span.js-T1XX
    author: Optional[str] = None
    # span.js-LENG
    language: Optional[str] = None
    # span.js-FEPU
    year: Optional[int] = None
    # span.c-docs_mat.m-docs_mat.i
    resource_type: Optional[str] = None
    # span.js-T520
    description: Optional[str] = None
    # span.c-docs_imgPreLoad img
    cover_url: Optional[str] = None


class SearchResults(NamedTuple):
    """Página de resultados e información para continuar la paginación."""

    items: tuple[SearchResult, ...]
    current_page: int = 1
    page_numbers: tuple[int, ...] = ()
    next_page_url: str | None = None


class SearchQuery(NamedTuple):
    normal_any_field: Optional[str] = None
    expert_any_field: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    editorial: Optional[str] = None
    subject: Optional[str] = None
    collection: Optional[str] = None
    genre: Optional[str] = None
    min_publish_date: Optional[str] = None
    max_publish_date: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    medium: Optional[str] = None
    sort_by: Optional[str] = "56297072"  # Relevancia
    items_per_page: Optional[int] = 100
