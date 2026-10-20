import unittest
from unittest.mock import Mock, patch

import requests

from agents import agent_scout


class ScoutRedirectSSRFTests(unittest.TestCase):
    def test_private_redirect_is_rejected_before_second_request(self):
        redirect = Mock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://127.0.0.1/latest/meta-data"}
        redirect.url = "https://public.example/"
        redirect.close = Mock()

        def public_host(url):
            if url.startswith("https://public.example/"):
                return True, "public host verified"
            return False, "private or reserved address blocked"

        with patch.object(agent_scout, "_public_host", side_effect=public_host), patch.object(
            agent_scout.requests, "get", return_value=redirect
        ) as get:
            with self.assertRaises(requests.RequestException):
                agent_scout._safe_public_get(
                    "https://public.example/", headers={"User-Agent": "test"}, timeout=1
                )

        redirect.close.assert_called_once()
        get.assert_called_once()
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_public_redirect_is_checked_before_following(self):
        first = Mock()
        first.status_code = 302
        first.headers = {"Location": "https://other.example/path"}
        first.url = "https://public.example/"
        first.close = Mock()
        second = Mock()
        second.status_code = 200
        second.headers = {}
        second.url = "https://other.example/path"

        with patch.object(
            agent_scout, "_public_host", return_value=(True, "public host verified")
        ) as host_check, patch.object(
            agent_scout.requests, "get", side_effect=[first, second]
        ) as get:
            result = agent_scout._safe_public_get(
                "https://public.example/", headers={"User-Agent": "test"}, timeout=1
            )

        self.assertIs(result, second)
        first.close.assert_called_once()
        self.assertEqual(get.call_count, 2)
        self.assertEqual(host_check.call_count, 3)
        self.assertEqual(get.call_args_list[1].args[0], "https://other.example/path")


if __name__ == "__main__":
    unittest.main()
