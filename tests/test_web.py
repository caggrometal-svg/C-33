import unittest
import httpx


class TestableWebTool:
    pass


class BoundedWebToolTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_transport(self, response_factory, url):
        import tools.web as web_module
        from tools.web import WebTool

        class TestTool(WebTool):
            @staticmethod
            async def _validate_public_url(url):
                return None

        transport = httpx.MockTransport(response_factory)
        original = web_module.httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        web_module.httpx.AsyncClient = factory
        try:
            return await TestTool(timeout=2, max_results=2).fetch(url)
        finally:
            web_module.httpx.AsyncClient = original

    async def test_search_rejects_oversized_query_before_transport(self):
        from tools.web import WebTool

        tool = WebTool(timeout=2, max_results=2)
        with self.assertRaisesRegex(ValueError, "web_query_too_long"):
            await tool.search("x" * (WebTool.MAX_QUERY_CHARS + 1))

    async def test_ssrf_guard_rejects_private_and_credential_urls(self):
        from tools.web import WebTool

        with self.assertRaisesRegex(ValueError, "Private or non-public"):
            await WebTool._validate_public_url("http://127.0.0.1/admin")
        with self.assertRaisesRegex(ValueError, "Private or non-public"):
            await WebTool._validate_public_url("http://10.0.0.1/internal")
        with self.assertRaisesRegex(ValueError, "embedded credentials"):
            await WebTool._validate_public_url("https://user:pass@example.com/")

    async def test_fetch_rejects_excessive_redirect_chain(self):
        async def redirect(request):
            return httpx.Response(
                302,
                headers={"location": str(request.url)},
                request=request,
            )

        with self.assertRaisesRegex(RuntimeError, "too_many_redirects"):
            await self._run_with_transport(redirect, "https://example.com/loop")

    async def test_fetch_rejects_declared_oversized_response_before_reading(self):
        from tools.web import WebTool

        async def too_large(request):
            return httpx.Response(
                200,
                content=b"x",
                headers={
                    "content-type": "text/plain",
                    "content-length": str(WebTool.MAX_PAGE_BYTES + 1),
                },
                request=request,
            )

        with self.assertRaisesRegex(RuntimeError, "web_response_too_large"):
            await self._run_with_transport(too_large, "https://example.com/large")

    async def test_fetch_rejects_undeclared_oversized_stream(self):
        from tools.web import WebTool

        async def too_large(request):
            return httpx.Response(
                200,
                content=b"x" * (WebTool.MAX_PAGE_BYTES + 1),
                headers={"content-type": "text/plain"},
                request=request,
            )

        with self.assertRaisesRegex(RuntimeError, "web_response_too_large"):
            await self._run_with_transport(too_large, "https://example.com/large")

    async def test_fetch_parses_small_html_response(self):
        async def small(request):
            return httpx.Response(
                200,
                content=b"<html><title>C33</title><body>Hello NEXO</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )

        page = await self._run_with_transport(small, "https://example.com/")
        self.assertEqual(page.title, "C33")
        self.assertIn("Hello NEXO", page.text)


if __name__ == "__main__":
    unittest.main()
