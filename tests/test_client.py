import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from opac.client import OpacClient
from opac.models import SearchQuery


LANDING_HTML = """
<form id="abnformSearch" action="/session/NT1" method="post">
  <input type="hidden" name="ACC" value="131">
  <input type="hidden" name="START" value="1">
  <input type="hidden" name="FORM" value="1">
  <input type="hidden" name="xindbt" value="">
  <input type="text" name="not_hidden" value="ignored">
</form>
"""

RESULTS_HTML = """
<ol>
  <li class="c-docs_unit">
    <span class="js-TITN">123</span>
    <span class="js-T245">Resultado de prueba</span>
    <span class="js-T1XX">Autora, Ana</span>
    <span class="js-FEPU">2026</span>
  </li>
</ol>
<div class="c-paginator_cont">
  <span class="acti">1</span><a>2</a>
</div>
<ul class="c-paginator_list--nextPre">
  <a aria-label="Página Siguiente" href="/session?ACC=161&amp;DOC=11">
    Siguiente
  </a>
</ul>
"""


class OpacClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OpacClient("https://catalog.example/catalog")

    def test_search_posts_form_fields_and_returns_results(self):
        landing_url = "https://catalog.example/catalog/landing?ACC=101"
        results_url = "https://catalog.example/session/NT1"
        with patch.object(
            self.client,
            "_fetch",
            side_effect=[
                (LANDING_HTML, landing_url),
                (RESULTS_HTML, results_url),
            ],
        ) as fetch:
            result = self.client.search(
                SearchQuery(
                    normal_any_field="El hombre",
                    author="Alison Bechdel",
                    language="spa",
                    items_per_page=10,
                )
            )

        self.assertEqual(fetch.call_count, 2)
        landing_call, search_call = fetch.call_args_list
        self.assertEqual(
            landing_call.args, ("https://catalog.example/catalog",)
        )
        self.assertEqual(
            search_call.args, ("https://catalog.example/session/NT1",)
        )
        self.assertEqual(search_call.kwargs["referer"], landing_url)
        fields = parse_qs(search_call.kwargs["data"].decode("utf-8"))
        self.assertEqual(fields["ACC"], ["131"])
        self.assertEqual(fields["START"], ["1"])
        self.assertEqual(fields["FORM"], ["1"])
        self.assertEqual(fields["xsqf01"], ["El hombre"])
        self.assertEqual(fields["xsqf03"], ["Alison Bechdel"])
        self.assertEqual(fields["select01"], ["spa"])
        self.assertEqual(fields["xsnlis"], ["10"])
        self.assertEqual(fields["xssort"], ["56297072"])
        self.assertNotIn("not_hidden", fields)
        self.assertEqual(result.items[0].title, "Resultado de prueba")
        self.assertEqual(result.items[0].titn, 123)
        self.assertTrue(result.next_page_url.endswith("DOC=11"))

    def test_search_uses_record_offset_for_requested_page(self):
        landing_url = "https://catalog.example/landing"
        results_url = "https://catalog.example/session/NT1"
        with patch.object(
            self.client,
            "_fetch",
            side_effect=[
                (LANDING_HTML, landing_url),
                (RESULTS_HTML, results_url),
                (RESULTS_HTML, "https://catalog.example/session"),
            ],
        ) as fetch:
            result = self.client.search(
                SearchQuery(normal_any_field="Mabuse", items_per_page=10),
                page=3,
            )

        self.assertEqual(fetch.call_count, 3)
        page_call = fetch.call_args_list[2]
        self.assertEqual(
            page_call.args[0],
            "https://catalog.example/session?ACC=161&DOC=21",
        )
        self.assertEqual(page_call.kwargs["referer"], results_url)
        self.assertEqual(result.items[0].title, "Resultado de prueba")

    def test_get_bytes_replaces_query_and_preserves_binary_content(self):
        image_bytes = b"\x89PNG\r\n\x1a\n\xff\x00"
        landing_url = "https://catalog.example/session?ACC=101"
        with (
            patch.object(
                self.client, "_fetch", return_value=("", landing_url)
            ),
            patch.object(
                self.client,
                "_fetch_raw",
                return_value=(image_bytes, landing_url, "binary"),
            ) as fetch_raw,
        ):
            content = self.client.get_bytes("cover/123")

        self.assertEqual(content, image_bytes)
        requested = urlsplit(fetch_raw.call_args.args[0])
        self.assertEqual(
            parse_qs(requested.query),
            {"ACC": ["299"], "MLKOB": ["cover/123"]},
        )
        self.assertEqual(fetch_raw.call_args.kwargs["referer"], landing_url)

    def test_get_bytes_rejects_empty_identifier(self):
        with self.assertRaises(ValueError):
            self.client.get_bytes("")

    def test_search_requires_search_query_and_valid_page(self):
        with self.assertRaises(TypeError):
            self.client.search("Mabuse")
        with self.assertRaises(ValueError):
            self.client.search(SearchQuery(normal_any_field="Mabuse"), page=0)

    def test_validates_catalog_url_and_timeout(self):
        with self.assertRaises(ValueError):
            OpacClient("catalog.example")
        with self.assertRaises(ValueError):
            OpacClient("https://catalog.example", timeout=0)


class RedirectHandlingTests(unittest.TestCase):
    def test_meta_and_http_redirects_keep_cookies_and_referer(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(
                    (
                        self.path,
                        self.headers.get("Cookie"),
                        self.headers.get("Referer"),
                    )
                )
                if self.path == "/start":
                    self.send_response(200)
                    self.send_header("Set-Cookie", "sid=abc; Path=/")
                    self.send_header(
                        "Content-Type", "text/html; charset=utf-8"
                    )
                    self.end_headers()
                    self.wfile.write(
                        b'<meta http-equiv="Refresh" '
                        b'content="0; URL=/middle">'
                    )
                elif self.path == "/middle":
                    self.send_response(302)
                    self.send_header("Set-Cookie", "step=two; Path=/")
                    self.send_header("Location", "/final")
                    self.end_headers()
                elif self.path == "/final":
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "text/html; charset=utf-8"
                    )
                    self.end_headers()
                    self.wfile.write(b"finished")
                else:
                    self.send_error(404)

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            client = OpacClient(f"{base_url}/start")
            content, final_url = client._fetch(f"{base_url}/start")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        self.assertEqual(content, "finished")
        self.assertEqual(final_url, f"{base_url}/final")
        self.assertIn("sid=abc", requests[1][1])
        self.assertEqual(requests[1][2], f"{base_url}/start")
        self.assertIn("step=two", requests[2][1])
        self.assertEqual(requests[2][2], f"{base_url}/middle")


if __name__ == "__main__":
    unittest.main()
