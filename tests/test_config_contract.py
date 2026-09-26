import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "src")

from config import ConfigurationError, load_infrastructure_config


class ProductionPeerConfigurationTests(unittest.TestCase):
    BASE_ENV = {
        "PORT": "8080",
        "SECRET_KEYS": "test-secret-key-1234567890",
        "APP_ENV": "production",
        "AI_ZERO_COST_MODE": "true",
        "MODEL_BASE_URL": "https://vireonix.ai/v1",
        "MODEL_NAME": "auto",
        "LOCAL_FALLBACK_ENABLED": "true",
        "REQUIRE_PROVIDER_REDUNDANCY": "true",
    }

    def test_production_rejects_self_peer(self):
        env = {
            **self.BASE_ENV,
            "PEER_BACKEND_URL": "https://c33-primary.example/peer",
            "PUBLIC_BASE_URL": "https://c33-primary.example",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(
                ConfigurationError,
                "PEER_BACKEND_URL must target a distinct backend",
            ):
                load_infrastructure_config(dotenv_path=None)

    def test_production_rejects_railway_self_peer(self):
        env = {
            **self.BASE_ENV,
            "PEER_BACKEND_URL": "https://c33-primary.example",
            "RAILWAY_PUBLIC_DOMAIN": "c33-primary.example",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(
                ConfigurationError,
                "PEER_BACKEND_URL must target a distinct backend",
            ):
                load_infrastructure_config(dotenv_path=None)

    def test_production_accepts_distinct_peer(self):
        env = {
            **self.BASE_ENV,
            "PEER_BACKEND_URL": "https://c33-peer.example",
            "PUBLIC_BASE_URL": "https://c33-primary.example",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_infrastructure_config(dotenv_path=None)
            self.assertEqual(config.peer_url, "https://c33-peer.example")


if __name__ == "__main__":
    unittest.main()
