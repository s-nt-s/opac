"""Parser tolerante para las fichas HTML de resultados AbsysNet Opac."""

from __future__ import annotations

from typing import Mapping, NamedTuple
from types import MappingProxyType
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from .models import SearchResult, SearchResults


class _Node(NamedTuple):
    tag: str
    attrs: Mapping[str, str]
    children: tuple["_Node | str", ...]

    def text(self) -> str:
        parts = []
        for child in self.children:
            value = child if isinstance(child, str) else child.text()
            if value.strip():
                parts.append(value.strip())
        return " ".join(parts)

    def descendants(self, tag: str | None = None):
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.descendants(tag)

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()


class _TreeParser(HTMLParser):
    _void_tags = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node(
            "document",
            MappingProxyType({}),
            (),
        )
        self.stack = [self.root]
        self._child_lists: dict[int, list[_Node | str]] = {id(self.root): []}

    def finish(self) -> _Node:
        """Devuelve el árbol congelado una vez construido."""
        return self._freeze(self.root)

    def _freeze(self, node: _Node) -> _Node:
        children = tuple(
            self._freeze(child) if isinstance(child, _Node) else child
            for child in self._child_lists[id(node)]
        )
        return _Node(node.tag, node.attrs, children)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        node = _Node(
            tag,
            MappingProxyType({key: value or "" for key, value in attrs}),
            (),
        )
        self._child_lists[id(self.stack[-1])].append(node)
        self._child_lists[id(node)] = []
        if tag not in self._void_tags:
            self.stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._void_tags:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data:
            self._child_lists[id(self.stack[-1])].append(data)


def _first(
    node: _Node,
    *,
    tag: str | None = None,
    class_name: str | None = None,
):
    return next(
        (
            item
            for item in node.descendants(tag)
            if class_name is None or item.has_class(class_name)
        ),
        None,
    )


def _absolute(base_url: str, value: str | None) -> str | None:
    return urljoin(base_url, value) if value else None


def _trim(s: str):
    if s is None:
        return None
    s = s.strip()
    if len(s) == 0:
        return None
    return s


def _text(node: _Node, class_name: str) -> str | None:
    value = _first(node, class_name=class_name)
    if not value:
        return None
    return _trim(value.text())


def _parse_item(item: _Node, base_url: str) -> SearchResult | None:
    """Extrae un registro ``li.c-docs_unit`` del listado AbsysNet."""

    year_match = re.search(
        r"\d{4}",
        _text(item, "js-FEPU") or ""
    )
    year = int(year_match.group()) if year_match else None
    cover_container = _first(item, class_name="c-docs_imgPreLoad")
    cover = _first(cover_container, tag="img") if cover_container else None
    material = _first(item, class_name="c-docs_mat")
    icon = _first(material, tag="i") if material else None

    title = _text(item, "js-T245")
    titn = _text(item, "js-TITN")
    author = _text(item, "js-T1XX")
    if titn is None or not titn.isdigit():
        raise ValueError(f"titn {titn}")
    if title is None:
        raise ValueError("title")
    return SearchResult(
        url=f"{base_url}?TITN={titn}",
        title=title,
        author=author,
        titn=int(titn),
        language=_text(item, "js-LENG"),
        year=year,
        resource_type=_trim(icon.attrs.get("title")) if icon else None,
        description=_text(item, "js-T520"),
        cover_url=(
            _absolute(base_url, cover.attrs.get("src")) if cover else None
        ),
    )


def parse_search_results(html: str, base_url: str) -> SearchResults:
    """Convierte HTML del catálogo en modelos Python."""
    parser = _TreeParser()
    parser.feed(html)
    root = parser.finish()
    result_nodes = (
        node
        for node in root.descendants("li")
        if node.has_class("c-docs_unit")
    )
    items = tuple(
        item
        for result_node in result_nodes
        if (item := _parse_item(result_node, base_url))
    )

    count_node = _first(root, class_name="c-paginator_count")
    count_match = (
        re.search(r"(\d+)\s*/\s*(\d+)", count_node.text())
        if count_node
        else None
    )
    current_page = 1
    if count_match:
        first_record, last_record = map(int, count_match.groups())
        page_size = max(last_record - first_record + 1, 1)
        current_page = (first_record - 1) // page_size + 1

    page_numbers: list[int] = []
    next_href = None
    page_container = _first(root, class_name="c-paginator_cont")
    if page_container:
        for node in page_container.descendants():
            if node.tag not in {"span", "a"}:
                continue
            match = re.fullmatch(r"\s*\d+\s*", node.text())
            if not match:
                continue
            page_number = int(match.group())
            page_numbers.append(page_number)
            if node.tag == "span" and node.has_class("acti"):
                current_page = page_number

    paginator = _first(root, class_name="c-paginator_list--nextPre")
    if paginator:
        for node in paginator.descendants("a"):
            label = node.attrs.get("aria-label", "").casefold()
            if "siguiente" in label or node.has_class("js-evn-AbnOpacListDoc"):
                next_href = node.attrs.get("href") or None
                if next_href:
                    break

    return SearchResults(
        items=items,
        current_page=current_page,
        page_numbers=tuple(dict.fromkeys(page_numbers)),
        next_page_url=_absolute(base_url, next_href),
    )
