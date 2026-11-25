"""Cliente de búsqueda para catálogos web basados en AbsysNet Opac."""

from .client import OpacClient, OpacError
from .models import SearchQuery, SearchResult
from .models import SearchResults

__all__ = [
 "OpacClient",
 "OpacError",
 "SearchQuery",
 "SearchResult",
 "SearchResults",
]
