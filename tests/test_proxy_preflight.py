import unittest
from unittest.mock import patch

from seoscout.core.config import Config
from seoscout.core.proxy import preflight_proxy_for_stages


class ProxyPreflightTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original = {
            "USE_PROXY": Config.USE_PROXY,
            "USE_PROXY_FOR_SEARCH": Config.USE_PROXY_FOR_SEARCH,
            "USE_PROXY_FOR_EXTRACT": Config.USE_PROXY_FOR_EXTRACT,
            "USE_PROXY_FOR_LLM": Config.USE_PROXY_FOR_LLM,
            "TUNNEL_HOST": Config.TUNNEL_HOST,
            "TUNNEL_PORT": Config.TUNNEL_PORT,
            "TUNNEL_USER": Config.TUNNEL_USER,
            "TUNNEL_PASS": Config.TUNNEL_PASS,
            "TUNNEL_PROXY_FORMAT": Config.TUNNEL_PROXY_FORMAT,
            "TUNNEL_CHANNEL_PREFIX": Config.TUNNEL_CHANNEL_PREFIX,
            "TUNNEL_TTL": Config.TUNNEL_TTL,
            "PROXY_DEBUG": Config.PROXY_DEBUG,
        }

    def tearDown(self):
        for name, value in self.original.items():
            setattr(Config, name, value)

    def _configure_search_proxy(self):
        Config.USE_PROXY = False
        Config.USE_PROXY_FOR_SEARCH = "true"
        Config.USE_PROXY_FOR_EXTRACT = ""
        Config.USE_PROXY_FOR_LLM = ""
        Config.TUNNEL_HOST = "proxy.example"
        Config.TUNNEL_PORT = 18866
        Config.TUNNEL_USER = "user"
        Config.TUNNEL_PASS = "pass"
        Config.TUNNEL_PROXY_FORMAT = "standard"
        Config.PROXY_DEBUG = False

    async def test_skips_probe_when_no_selected_stage_uses_proxy(self):
        Config.USE_PROXY = False
        Config.USE_PROXY_FOR_SEARCH = ""
        Config.USE_PROXY_FOR_EXTRACT = ""
        Config.USE_PROXY_FOR_LLM = ""

        ok, message = await preflight_proxy_for_stages(["search", "llm"])

        self.assertTrue(ok)
        self.assertIn("skipped", message)

    async def test_probes_first_selected_proxy_route_without_exposing_egress_ip(self):
        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            async def text(self):
                return "203.0.113.8"

        class FakeSession:
            seen_url = None
            seen_proxy = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            def get(self, url, **kwargs):
                FakeSession.seen_url = url
                FakeSession.seen_proxy = kwargs.get("proxy")
                return FakeResponse()

        self._configure_search_proxy()
        with patch("seoscout.core.proxy.aiohttp.ClientSession", FakeSession):
            ok, message = await preflight_proxy_for_stages(["search", "llm"])

        self.assertTrue(ok)
        self.assertEqual("https://api.ipify.org", FakeSession.seen_url)
        self.assertEqual("http://user:pass@proxy.example:18866", FakeSession.seen_proxy)
        self.assertIn("passed", message)
        self.assertNotIn("203.0.113.8", message)

    async def test_debug_mode_includes_egress_ip(self):
        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            async def text(self):
                return "203.0.113.8"

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            def get(self, _url, **_kwargs):
                return FakeResponse()

        self._configure_search_proxy()
        Config.PROXY_DEBUG = True
        with patch("seoscout.core.proxy.aiohttp.ClientSession", FakeSession):
            ok, message = await preflight_proxy_for_stages(["search"])

        self.assertTrue(ok)
        self.assertIn("203.0.113.8", message)
