import unittest


class HttpSecurityTests(unittest.TestCase):
    def test_security_headers_are_defined(self):
        from nexo.http_security import SECURITY_HEADERS
        self.assertEqual(SECURITY_HEADERS['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(SECURITY_HEADERS['X-Frame-Options'], 'DENY')
        self.assertEqual(SECURITY_HEADERS['Referrer-Policy'], 'no-referrer')


if __name__ == '__main__':
    unittest.main()
