import unittest

from opac.parser import _TreeParser, parse_search_results


class ParseSearchResultsTests(unittest.TestCase):
    def test_tree_parser_builds_immutable_child_tuples(self):
        parser = _TreeParser()
        parser.feed("<div><span>uno</span><span>dos</span></div>")
        root = parser.finish()

        div = root.children[0]
        self.assertIsInstance(root.children, tuple)
        self.assertIsInstance(div.children, tuple)
        self.assertEqual(
            [node.text() for node in root.descendants("span")],
            ["uno", "dos"],
        )

    def test_extracts_absysnet_fields_and_pagination(self):
        html = """
        <ol aria-label="Listado de resultados">
          <li class="c-docs_unit">
            <h3>
              <a>
                <span class="js-T1XX">Autora, Ana</span>
                <span class="js-T245">Título de prueba /</span>
              </a>
            </h3>
            <div class="c-docs_data">
              <p><span class="js-T520">Descripción &amp; detalles.</span></p>
            </div>
            <p class="c-docs_marc">
              <span class="js-TITN">123456</span>
              <span class="js-LENG">spa</span>
              <span class="js-FEPU">2026</span>
            </p>
            <p class="c-docs_mat"><i title="Monografías"></i></p>
            <span class="c-docs_imgPreLoad">
              <img src="/covers/book.jpg" alt="Cubierta">
            </span>
          </li>
          <li class="c-docs_unit">
            <span class="js-TITN">654321</span>
            <span class="js-T245">Registro sin año</span>
          </li>
        </ol>
        <p class="c-paginator_count">1 / 2 de 10 resultados</p>
        <div class="c-paginator_list c-paginator_list--nextPre">
          <li class="c-paginator_cont">
            <span class="acti">1</span><span class="barr">|</span>
            <a class="noacti">2</a>
          </li>
          <a class="js-evn-AbnOpacListDoc"
             aria-label="Página Siguiente"
             href="/catalog/NT1?ACC=161&amp;DOC=3">Siguiente</a>
        </div>
        """

        results = parse_search_results(
            html, "https://catalog.example/catalog/NT1"
        )

        self.assertEqual(len(results.items), 2)
        item = results.items[0]
        self.assertEqual(item.title, "Título de prueba /")
        self.assertEqual(item.author, "Autora, Ana")
        self.assertEqual(item.titn, 123456)
        self.assertIsInstance(item.titn, int)
        self.assertEqual(item.language, "spa")
        self.assertEqual(item.year, 2026)
        self.assertEqual(item.resource_type, "Monografías")
        self.assertEqual(item.description, "Descripción & detalles.")
        self.assertEqual(
            item.cover_url,
            "https://catalog.example/covers/book.jpg",
        )
        self.assertEqual(
          item.url,
          "https://catalog.example/catalog/NT1?TITN=123456",
        )
        self.assertEqual(results.current_page, 1)
        self.assertEqual(results.page_numbers, (1, 2))
        self.assertEqual(results.items[1].title, "Registro sin año")
        self.assertEqual(results.items[1].titn, 654321)
        self.assertIsNone(results.items[1].year)
        self.assertEqual(
            results.next_page_url,
            "https://catalog.example/catalog/NT1?ACC=161&DOC=3",
        )

    def test_empty_results_and_optional_fields_are_supported(self):
        empty = parse_search_results("<ol></ol>", "https://catalog.example/")
        self.assertEqual(empty.items, ())
        self.assertIsNone(empty.next_page_url)

        partial = parse_search_results(
            '<li class="c-docs_unit">'
            '<span class="js-T245">Título</span>'
            '<span class="js-TITN">42</span>'
            '</li>',
            "https://catalog.example/catalog/NT1",
        )
        self.assertEqual(len(partial.items), 1)
        self.assertEqual(partial.items[0].title, "Título")
        self.assertEqual(partial.items[0].titn, 42)
        self.assertIsNone(partial.items[0].author)
        self.assertIsNone(partial.items[0].year)

    def test_records_without_title_or_titn_are_rejected(self):
        for fields in (
            '<span class="js-TITN">42</span>',
            '<span class="js-T245">Título</span>',
        ):
            with self.subTest(fields=fields):
                html = f'<li class="c-docs_unit">{fields}</li>'
                with self.assertRaises(ValueError):
                    parse_search_results(html, "https://catalog.example/")


if __name__ == "__main__":
    unittest.main()
