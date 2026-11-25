"""Cliente HTTP de solo lectura para búsquedas en catálogos AbsysNet Opac."""

from __future__ import annotations

from html.parser import HTMLParser
from http.cookiejar import CookieJar
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    Request,
    build_opener,
)

from .models import SearchQuery, SearchResult, SearchResults
from .parser import parse_search_results
from types import MappingProxyType


MAP_PARAM = MappingProxyType({
    "normal_any_field": "xsqf01",
    "expert_any_field": "xsqf99",
    "title": "xsqf02",
    "author": "xsqf03",
    "editorial": "xsqf04",
    "subject": "xsqf05",
    "collection": "xsqf06",
    "genre": "xsqf09",
    "min_publish_date": "xsqf07",
    "max_publish_date": "xsqf08",
    "language": "select01",
    "country": "select02",
    "medium": "select03",
    "sort_by": "xssort",
    "items_per_page": "xsnlis",
})


class _RedirectHandler(HTTPRedirectHandler):
    """Permite cadenas largas de redirecciones, evitando ciclos infinitos."""

    max_redirections = 50
    max_repeats = 10

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        redirected = super().redirect_request(
            req, fp, code, msg, headers, newurl
        )
        if redirected is not None:
            referer = _referer_header(req.full_url, newurl)
            if referer:
                redirected.add_unredirected_header("Referer", referer)
        return redirected


def _referer_header(source_url: str, target_url: str) -> str | None:
    """Devuelve un Referer seguro, siguiendo la política web habitual."""
    source = urlsplit(source_url)
    target = urlsplit(target_url)
    is_https_downgrade = (
        source.scheme.casefold() == "https"
        and target.scheme.casefold() != "https"
    )
    if is_https_downgrade:
        return None

    hostname = source.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = source.port
    netloc = hostname
    if port is not None:
        netloc += f":{port}"
    origin = f"{source.scheme}://{netloc}"

    source_port = port or (443 if source.scheme.casefold() == "https" else 80)
    target_port = target.port or (
        443 if target.scheme.casefold() == "https" else 80
    )
    same_origin = (
        source.scheme.casefold() == target.scheme.casefold()
        and (source.hostname or "").casefold()
        == (target.hostname or "").casefold()
        and source_port == target_port
    )
    if same_origin:
        return urlunsplit(
            (source.scheme, netloc, source.path, source.query, "")
        )
    return origin


class _MetaRefreshParser(HTMLParser):
    """Extrae el destino de una redirección HTML ``meta refresh``."""

    _refresh_pattern = re.compile(
        r"^\s*\d+(?:\.\d+)?\s*;\s*url\s*=\s*(.*?)\s*$",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.target: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "meta":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        if values.get("http-equiv", "").strip().casefold() != "refresh":
            return
        match = self._refresh_pattern.fullmatch(values.get("content", ""))
        if match:
            self.target = match.group(1).strip().strip("\"'")


class _SearchFormParser(HTMLParser):
    """Lee la acción y los campos ocultos del formulario de búsqueda."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.method = "get"
        self.hidden_fields: dict[str, str] = {}
        self._inside_search_form = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "form":
            self._inside_search_form = values.get("id") == "abnformSearch"
            if self._inside_search_form:
                self.action = values.get("action") or None
                self.method = values.get("method", "get").casefold()
            return
        if not self._inside_search_form or tag.casefold() != "input":
            return
        if values.get("type", "").casefold() != "hidden":
            return
        name = values.get("name")
        if name:
            self.hidden_fields[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "form" and self._inside_search_form:
            self._inside_search_form = False


class OpacError(Exception):
    """Error de red o de respuesta del catálogo."""


class OpacClient:
    """Busca recursos en un sitio compatible con el catálogo AbsysNet Opac.

    Ejemplo::

        client = OpacClient(
            "https://gestiona.comunidad.madrid/biblio_publicas/"
            "cgi-bin/abnetopac"
        )
        query = SearchQuery(keywords="Mabuse", language="spa", nature="ebook")
        results = client.search(query)
        for item in results.items:
            print(item.title, item.authors, item.url)
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 20.0,
        user_agent: str = "opac-client/0.1 (+https://www.python.org/)",
    ) -> None:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("La URL debe ser absoluta y usar http o https.")
        if timeout <= 0:
            raise ValueError("timeout debe ser mayor que cero.")
        self._base_url = url
        self._timeout = timeout
        self._user_agent = user_agent
        self._cookies = CookieJar()
        self._opener = build_opener(
            _RedirectHandler(),
            HTTPCookieProcessor(self._cookies),
        )

    def get_bytes(self, mlkob: str) -> bytes:
        """Descarga el contenido asociado a un identificador ``MLKOB``."""
        if not mlkob:
            raise ValueError("mlkob no puede estar vacío.")

        _, landing_url = self._fetch(self._base_url)
        parsed_url = urlsplit(landing_url)
        content_url = urlunsplit(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                urlencode({"ACC": "299", "MLKOB": mlkob}),
                "",
            )
        )
        content, _, _ = self._fetch_raw(
            content_url,
            referer=landing_url,
            #accept="image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        )
        return content

    def _fetch(
        self,
        url: str,
        *,
        data: bytes | None = None,
        referer: str | None = None,
    ) -> tuple[str, str]:
        content, final_url, charset = self._fetch_raw(
            url, data=data, referer=referer
        )
        return content.decode(charset, errors="replace"), final_url

    def _fetch_raw(
        self,
        url: str,
        *,
        data: bytes | None = None,
        referer: str | None = None,
        accept: str = "text/html,application/xhtml+xml",
    ) -> tuple[bytes, str, str]:
        """Obtiene bytes sin alterar el cuerpo y sigue redirecciones."""
        current_url = url
        referer_url = referer
        request_data = data
        visited: set[str] = set()
        meta_refreshes = 0
        while True:
            if current_url in visited:
                raise OpacError(
                    "Bucle de redirección detectado al consultar "
                    f"{current_url}."
                )
            visited.add(current_url)
            request = Request(
                current_url,
                data=request_data,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": accept,
                },
            )
            if request_data is not None:
                request.add_header(
                    "Content-Type", "application/x-www-form-urlencoded"
                )
            if referer_url:
                referer = _referer_header(referer_url, current_url)
                if referer:
                    request.add_unredirected_header("Referer", referer)
            try:
                with self._opener.open(
                    request, timeout=self._timeout
                ) as response:
                    charset = (
                        response.headers.get_content_charset() or "utf-8"
                    )
                    content = response.read()
                    final_url = response.geturl()
            except (HTTPError, URLError, OSError) as exc:
                raise OpacError(
                    f"No se pudo consultar {current_url}: {exc}"
                ) from exc
            request_data = None

            refresh = _MetaRefreshParser()
            refresh.feed(content.decode(charset, errors="replace"))
            if not refresh.target:
                return content, final_url, charset
            meta_refreshes += 1
            if meta_refreshes > 50:
                raise OpacError(
                    "Se superó el límite de 50 redirecciones HTML."
                )
            referer_url = final_url
            current_url = urljoin(final_url, refresh.target)

    def search(
        self,
        query: SearchQuery,
        *,
        page: int = 1,
    ) -> SearchResults:
        """Ejecuta una búsqueda y devuelve los recursos de la página indicada.

        Los términos y filtros se especifican en un ``SearchQuery``.
        """
        if not isinstance(query, SearchQuery):
            raise TypeError("query debe ser una instancia de SearchQuery.")
        if page < 1:
            raise ValueError("page debe ser un entero positivo.")

        landing_html, landing_url = self._fetch(self._base_url)
        form = _SearchFormParser()
        form.feed(landing_html)
        if not form.action:
            raise OpacError(
                "No se encontró el formulario de búsqueda abnformSearch."
            )

        fields = dict(form.hidden_fields)
        fields.update(
            {
                MAP_PARAM[name]: str(value)
                for name, value in query._asdict().items()
                if value not in (None, "")
            }
        )
        request_url = urljoin(landing_url, form.action)
        if form.method == "post":
            html, final_url = self._fetch(
                request_url,
                data=urlencode(fields).encode("utf-8"),
                referer=landing_url,
            )
        else:
            separator = "&" if urlsplit(request_url).query else "?"
            html, final_url = self._fetch(
                f"{request_url}{separator}{urlencode(fields)}",
                referer=landing_url,
            )

        if page > 1:
            result = urlsplit(final_url)
            path = result.path.removesuffix("/NT1")
            page_start = (page - 1) * max(query.items_per_page or 100, 1) + 1
            page_url = urlunsplit(
                (
                    result.scheme,
                    result.netloc,
                    path,
                    urlencode({"ACC": "161", "DOC": page_start}),
                    "",
                )
            )
            html, final_url = self._fetch(page_url, referer=final_url)

        parsed = parse_search_results(html, final_url)
        next_page_url = parsed.next_page_url
        return SearchResults(
            items=parsed.items,
            current_page=(
                parsed.current_page
                if parsed.current_page > 1 or page == 1
                else page
            ),
            page_numbers=parsed.page_numbers,
            next_page_url=next_page_url,
        )

    def search_all(
        self,
        query: SearchQuery,
        *,
        max_pages: int = 100,
    ) -> tuple[SearchResult, ...]:
        """Recorre páginas siguientes hasta el final o ``max_pages``."""
        if max_pages < 1:
            raise ValueError("max_pages debe ser un entero positivo.")
        results: list[SearchResult] = []
        page = 1
        while page <= max_pages:
            current = self.search(query, page=page)
            results.extend(current.items)
            if not current.next_page_url:
                break
            next_page = parse_qs(
                urlsplit(current.next_page_url).query
            ).get("page", [])
            page = (
                int(next_page[0])
                if next_page and next_page[0].isdigit()
                else page + 1
            )
        return tuple(results)
