import unittest

import httpx

from nexo.actions import ActionPolicyError, ActionRequest, ExternalActionExecutor


class ExternalActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_explicit_authorization(self):
        with self.assertRaisesRegex(ActionPolicyError, "explicit_authorization_required"):
            await ExternalActionExecutor(("example.com",)).execute(
                ActionRequest(action="webhook", url="https://example.com", authorized=False)
            )

    async def test_scope_and_allowlist_are_enforced(self):
        executor = ExternalActionExecutor(("example.com",))
        with self.assertRaisesRegex(ActionPolicyError, "action_outside_authorized_scope"):
            await executor.execute(ActionRequest(
                action="webhook", url="https://example.com", authorized=True, scope=("calendar.read",)
            ))
        with self.assertRaisesRegex(ActionPolicyError, "action_target_not_allowlisted"):
            await executor.execute(ActionRequest(
                action="webhook", url="https://evil.example", authorized=True, scope=("webhook",)
            ))

    async def test_real_http_contract_and_idempotency(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["Idempotency-Key"], "id-1")
            self.assertEqual(request.headers["X-C33-Action"], "webhook")
            return httpx.Response(204)
        result = await ExternalActionExecutor(
            ("example.com",), transport=httpx.MockTransport(handler)
        ).execute(ActionRequest(
            action="webhook",
            url="https://example.com/hook",
            authorized=True,
            scope=("webhook",),
            body={"hello": "world"},
            idempotency_key="id-1",
        ))
        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 204)
        self.assertEqual(len(result.response_sha256), 64)


if __name__ == "__main__":
    unittest.main()
