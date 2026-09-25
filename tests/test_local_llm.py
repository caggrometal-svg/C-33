import os
import unittest

import httpx

from nexo.local_llm import LocalLLMClient, LocalLLMConfig


class LocalLLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_without_runtime(self):
        old = os.environ.pop("C33_LOCAL_LLM_BASE_URL", None)
        try:
            result = await LocalLLMClient(LocalLLMConfig()).probe()
            self.assertFalse(result["available"])
            self.assertEqual(result["status"], "disabled")
        finally:
            if old is not None:
                os.environ["C33_LOCAL_LLM_BASE_URL"] = old

    async def test_real_openai_compatible_complete(self):
        seen = {}
        async def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return httpx.Response(200, json={"choices": [{"message": {"content": "local ok"}}]})
        os.environ["C33_LOCAL_LLM_BASE_URL"] = "http://127.0.0.1:11434/v1"
        try:
            client = LocalLLMClient(
                LocalLLMConfig(base_url="http://127.0.0.1:11434/v1", model="test-local"),
                transport=httpx.MockTransport(handler),
            )
            text, meta = await client.complete([{"role": "user", "content": "hola"}])
        finally:
            os.environ.pop("C33_LOCAL_LLM_BASE_URL", None)
        self.assertEqual(text, "local ok")
        self.assertEqual(meta["provider_used"], "local")
        self.assertEqual(seen["path"], "/v1/chat/completions")

    async def test_probe_uses_models_endpoint(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "test-local"}]})
        os.environ["C33_LOCAL_LLM_BASE_URL"] = "http://127.0.0.1:11434/v1"
        try:
            result = await LocalLLMClient(LocalLLMConfig(), transport=httpx.MockTransport(handler)).probe()
        finally:
            os.environ.pop("C33_LOCAL_LLM_BASE_URL", None)
        self.assertTrue(result["available"])
        self.assertEqual(result["status"], "ready")


if __name__ == "__main__":
    unittest.main()
