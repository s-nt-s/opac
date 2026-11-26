"""Parser tolerante para las fichas HTML de resultados AbsysNet Opac."""

from __future__ import annotations

import re
from .treeparser import TreeParser, Node

from .models import SearchResult, SearchResults


def _parse_item(item: Node, base_url: str) -> SearchResult | None:
    """Extrae un registro ``li.c-docs_unit`` del listado AbsysNet."""

    year_match = re.search(
        r"\d{4}",
        item.first_text("span", "js-FEPU") or ""
    )
    year = int(year_match.group()) if year_match else None
    cover_container = item.first("span", "c-docs_imgPreLoad")
    cover = cover_container.first("img") if cover_container else None
    material = item.first("p", "c-docs_mat")
    icon = material.first("i") if material else None

    title = item.first_text("span", "c-docs_title", "m-docs_title") or item.first_text("span", "js-T245")
    titn = item.first_text("span", "js-TITN")
    author = item.first_text("span", "js-T1XX")
    if titn is None or not titn.isdigit():
        raise ValueError(f"titn {titn}")
    if title is None:
        raise ValueError("title")
    if author:
        author = re.sub(r"\s+\(\d{4}-(\d{4})?\)\s*$", "", author)
    root_url = re.sub(r"(/abnetopac)/.*", r"\1", base_url)
    title = re.sub(r"\s*/\s*(\[.+\])?\s*$", "", title)
    title = re.sub(r"\s+:\s+", ": ", title)
    return SearchResult(
        url=f"{root_url}?TITN={titn}",
        title=title,
        author=author,
        titn=int(titn),
        language=item.first_text("span", "js-LENG"),
        year=year,
        resource_type=icon.get("title") if icon else None,
        description=item.first_text("span", "js-T520"),
        cover_url=(
            cover.get_absolute(base_url, "src") if cover else None
        ),
    )


def parse_search_results(html: str, base_url: str) -> SearchResults:
    """Convierte HTML del catálogo en modelos Python."""
    root = TreeParser.parse(html)
    result_nodes = tuple(root.descendants("li", "c-docs_unit"))
    items = tuple(
        item
        for result_node in result_nodes
        if (item := _parse_item(result_node, base_url))
    )

    count_match = re.search(
        r"(\d+)\s*/\s*(\d+)",
        root.first_text("p", "c-paginator_count") or ""
    )

    current_page = 1
    if count_match:
        first_record, last_record = map(int, count_match.groups())
        page_size = max(last_record - first_record + 1, 1)
        current_page = (first_record - 1) // page_size + 1

    page_numbers: list[int] = []
    next_href = None
    page_container = root.first("p", "c-paginator_cont")
    if page_container:
        for node in page_container.descendants(("span", "a")):
            match = re.fullmatch(
                r"\s*\d+\s*",
                node.text() or ""
            )
            if not match:
                continue
            page_number = int(match.group())
            page_numbers.append(page_number)
            if node.tag == "span" and node.has_class("acti"):
                current_page = page_number

    paginator = root.first("ul", "c-paginator_list--nextPre")
    if paginator:
        for node in paginator.descendants("a", "js-evn-AbnOpacListDoc"):
            label = node.attrs.get("aria-label", "").casefold()
            if "siguiente" in label:
                next_href = node.get_absolute(base_url, "href")
                if next_href:
                    break

    return SearchResults(
        items=items,
        current_page=current_page,
        page_numbers=tuple(dict.fromkeys(page_numbers)),
        next_page_url=next_href,
    )
