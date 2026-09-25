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
