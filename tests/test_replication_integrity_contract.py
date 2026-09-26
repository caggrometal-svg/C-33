from __future__ import annotations

import inspect
import unittest

from resilience.state import PostgresState


class ReplicationIntegrityContractTests(unittest.TestCase):
    def test_replication_integrity_is_a_real_async_method(self) -> None:
        method = getattr(PostgresState, "replication_integrity", None)
        self.assertIsNotNone(method)
        self.assertTrue(inspect.iscoroutinefunction(method))
        self.assertNotIn("\\n    async def replication_integrity", inspect.getsource(PostgresState))


if __name__ == "__main__":
    unittest.main()
