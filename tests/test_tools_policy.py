import asyncio
import unittest


class ToolPolicyTests(unittest.TestCase):
    def test_policy_blocks_network_when_disabled(self):
        from nexo.tool_policy import ToolCapability, ToolPolicy
        policy = ToolPolicy([ToolCapability('web', network=True)])
        self.assertFalse(policy.allows('web', network_allowed=False))
        self.assertTrue(policy.allows('web', network_allowed=True))

    def test_calculator_accepts_basic_arithmetic_and_rejects_calls(self):
        from nexo.tools_builtin import calculate
        self.assertEqual(calculate('2 + 3 * 4'), 14.0)
        with self.assertRaises(ValueError):
            calculate('__import__("os")')

    def test_tool_hub_describes_capabilities(self):
        from nexo.architecture import ToolHub
        hub = ToolHub()
        hub.register('web', lambda: None, network=True, risk='medium')
        description = hub.describe()[0]
        self.assertEqual(description['name'], 'web')
        self.assertTrue(description['network'])
        self.assertEqual(description['risk'], 'medium')

    def test_tool_hub_enforces_capability_policy(self):
        from nexo.architecture import ToolHub

        async def exercise():
            hub = ToolHub()
            hub.register('web', lambda: 'ok', network=True, risk='medium')

            with self.assertRaises(PermissionError):
                await hub.invoke('web', network_allowed=False)

            self.assertEqual(
                await hub.invoke('web', network_allowed=True),
                'ok',
            )

        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
