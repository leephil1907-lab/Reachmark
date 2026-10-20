import unittest
from unittest.mock import patch

from web import public_audit


class PublicAuditProxyTrustTests(unittest.TestCase):
    def test_untrusted_peer_cannot_spoof_forwarded_ip(self):
        with patch.dict("os.environ", {"TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}):
            with public_audit.request.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "203.0.113.9"},
                headers={"X-Forwarded-For": "198.51.100.77"},
            ):
                self.assertEqual(public_audit._client_ip(), "203.0.113.9")

    def test_trusted_proxy_chain_resolves_first_untrusted_address(self):
        with patch.dict("os.environ", {"TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}):
            with public_audit.request.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "10.1.2.3"},
                headers={"X-Forwarded-For": "198.51.100.77, 10.2.3.4"},
            ):
                self.assertEqual(public_audit._client_ip(), "198.51.100.77")

    def test_forwarded_header_is_ignored_when_no_proxy_is_configured(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("TRUSTED_PROXY_CIDRS", None)
            with public_audit.request.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "192.0.2.5"},
                headers={"X-Forwarded-For": "198.51.100.77"},
            ):
                self.assertEqual(public_audit._client_ip(), "192.0.2.5")


if __name__ == "__main__":
    unittest.main()
