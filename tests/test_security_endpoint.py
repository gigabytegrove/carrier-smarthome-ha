"""Offline contract: credential material is only sent to approved Carrier endpoints."""
import ast
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/carrier_smarthome/api.py"
TEXT = SOURCE.read_text(encoding="utf-8")

class CredentialEndpointContracts(unittest.TestCase):
    def test_transport_has_endpoint_and_auth_context_guards(self):
        ast.parse(TEXT)
        self.assertIn("if url not in (NO_AUTH, REFRESH, GRAPHQL):", TEXT)
        self.assertIn("token is not None and url != GRAPHQL", TEXT)
        self.assertIn("form and url != REFRESH", TEXT)
        self.assertIn("allow_redirects=False", TEXT)
        self.assertNotIn("response.text()", TEXT)

if __name__ == "__main__":
    unittest.main()
