import unittest


class SourceLedgerTests(unittest.TestCase):
    def test_ledger_deduplicates_and_limits(self):
        from nexo.sources import SourceLedger
        ledger = SourceLedger(limit=2)
        first = ledger.add('https://one.invalid/a')
        same = ledger.add('https://one.invalid/a')
        second = ledger.add('https://two.invalid/b')
        third = ledger.add('https://three.invalid/c')
        self.assertEqual(first.source_id, 'WEB-1')
        self.assertIsNone(same)
        self.assertEqual(second.source_id, 'WEB-2')
        self.assertIsNone(third)
        self.assertEqual(len(ledger.as_dicts()), 2)


if __name__ == '__main__':
    unittest.main()
