import contextlib
import io
import json
import unittest
from unittest.mock import patch

from opac.cli import main
from opac.models import SearchQuery, SearchResult, SearchResults


class OpacCliTests(unittest.TestCase):
    def test_search_options_and_json_output(self):
        result = SearchResult(
            url="https://catalog.example/NT1?TITN=123",
            title="Fun home",
            author="Alison Bechdel",
            titn=123,
            language="eng",
            year=2025,
            resource_type="Monografías",
            description="Una memoria gráfica.",
            cover_url="https://catalog.example/cover.jpg",
        )
        page = SearchResults(
            items=(result,),
            current_page=1,
            page_numbers=(1, 2),
            next_page_url="https://catalog.example/NT1?ACC=161&DOC=101",
        )
        stdout = io.StringIO()
        with patch("opac.cli.OpacClient") as client_class:
            client_class.return_value.search.return_value = page
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "https://catalog.example/",
                        "Fun home",
                        "--author",
                        "Alison Bechdel",
                        "--items-per-page",
                        "10",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        client_class.return_value.search.assert_called_once_with(
            SearchQuery(
                normal_any_field="Fun home",
                author="Alison Bechdel",
                items_per_page=10,
            ),
            page=1,
        )
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["items"][0]["title"], "Fun home")
        self.assertEqual(
            output["items"][0]["author"], "Alison Bechdel"
        )
        self.assertEqual(output["items"][0]["titn"], 123)
        self.assertEqual(output["items"][0]["year"], 2025)
        self.assertEqual(output["next_page_url"], page.next_page_url)
        self.assertEqual(output["page_numbers"], [1, 2])

    def test_network_errors_return_nonzero(self):
        stderr = io.StringIO()
        with patch("opac.cli.OpacClient") as client_class:
            client_class.return_value.search.side_effect = ValueError(
                "bad URL"
            )
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["https://catalog.example/", "Mabuse"])

        self.assertEqual(exit_code, 2)
        self.assertIn("bad URL", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
