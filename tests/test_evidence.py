import unittest


class EvidenceGradeTests(unittest.TestCase):
    def test_grounded_response_is_classified(self):
        from nexo.evidence import grade_evidence
        result = grade_evidence('Dato respaldado [1].', ['https://example.com'])
        self.assertEqual(result.grade, 'GROUNDED')
        self.assertEqual(result.citation_count, 1)

    def test_missing_citation_is_not_called_grounded(self):
        from nexo.evidence import grade_evidence
        result = grade_evidence('Dato.', ['https://example.com'])
        self.assertEqual(result.grade, 'INVALID')
        self.assertIn('web_sources_without_inline_citations', result.warnings)

    def test_no_sources_is_explicitly_unverified(self):
        from nexo.evidence import grade_evidence
        self.assertEqual(grade_evidence('Respuesta.', []).grade, 'NONE')


if __name__ == '__main__':
    unittest.main()
