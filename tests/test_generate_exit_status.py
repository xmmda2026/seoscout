import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, call, patch

from seoscout import cli
from seoscout.core.config import Config
from seoscout.core.llm_client import LLMClient
from seoscout.generate import _build_repair_prompt, load_prompt_template, run_generate
from seoscout.translate import run_translate


class InvalidArticleClient:
    async def preflight_connectivity(self):
        return True, "test route available"

    async def generate_batch(self, prompts, batch_size=None):
        return [(meta, "not valid MDX") for _, meta in prompts]

    def print_stats(self):
        pass


class GenerateExitStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_debug_log_records_a_redacted_request_response_and_token_usage(self):
        """Removing an LLM audit field would leave a failed model call untraceable."""
        class FakeResponse:
            status = 200
            headers = {"x-request-id": "provider-request-123"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            async def json(self):
                return {
                    "choices": [{"message": {"content": "article"}}],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 34,
                        "total_tokens": 46,
                    },
                }

        class FakeSession:
            def post(self, *_args, **_kwargs):
                return FakeResponse()

        with TemporaryDirectory() as temp_dir:
            original_log_dir = Config.LOG_DIR
            original_debug_flag = getattr(Config, "LLM_DEBUG_LOG", False)
            Config.LOG_DIR = temp_dir
            Config.LLM_DEBUG_LOG = True
            try:
                content = await LLMClient().generate_single(
                    FakeSession(), "full user prompt", {"keyword": "test keyword", "language": "en"}
                )
            finally:
                Config.LOG_DIR = original_log_dir
                Config.LLM_DEBUG_LOG = original_debug_flag

            audit_files = list((Path(temp_dir) / "llm").glob("*.json"))
            self.assertEqual("article", content)
            self.assertEqual(1, len(audit_files))
            audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
            self.assertEqual("full user prompt", audit["request"]["messages"][1]["content"])
            self.assertNotIn("authorization", audit["request"])
            self.assertEqual(200, audit["response"]["status"])
            self.assertEqual("provider-request-123", audit["response"]["provider_request_id"])
            self.assertEqual(46, audit["usage"]["total_tokens"])

    async def test_llm_preflight_stops_before_generation_when_api_is_unreachable(self):
        """The connectivity probe must fail before a batch can waste model requests."""
        class FailingSession:
            seen_proxy = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            def get(self, _url, **kwargs):
                FailingSession.seen_proxy = kwargs.get("proxy")
                raise OSError("proxy route refused")

        client = LLMClient()
        client.base_url = "https://unreachable.example/v1"
        client.api_url = f"{client.base_url}/chat/completions"
        client.proxy_url = "http://proxy.invalid:18866"
        with patch("seoscout.core.llm_client.aiohttp.ClientSession", FailingSession):
            ok, message = await client.preflight_connectivity()

        self.assertFalse(ok)
        self.assertIn("unreachable.example", message)
        self.assertIn("proxy route refused", message)
        self.assertEqual("http://proxy.invalid:18866", FailingSession.seen_proxy)

    async def test_translate_respects_configured_concurrency_limit(self):
        """Translations must not start more API calls than their own limit."""
        class TrackingClient:
            instance = None

            def __init__(self):
                self.stats = {}
                self.active = 0
                self.peak_active = 0
                TrackingClient.instance = self

            async def preflight_connectivity(self):
                return True, "test route available"

            async def generate_single(self, _session, _prompt, _meta):
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
                try:
                    await __import__("asyncio").sleep(0.01)
                    return "export const metadata = {\n};\n\n" + ("translated content " * 8)
                finally:
                    self.active -= 1

            def print_stats(self):
                pass

        with TemporaryDirectory() as temp_dir:
            en_dir = Path(temp_dir) / "articles" / "en" / "guide"
            en_dir.mkdir(parents=True)
            for index in range(3):
                (en_dir / f"article-{index}.mdx").write_text(
                    "export const metadata = {\n};\n\n" + ("English source content " * 8),
                    encoding="utf-8",
                )

            with (
                patch.dict(os.environ, {
                    "TRANSLATE_BATCH_SIZE": "6",
                    "TRANSLATE_CONCURRENT_LIMIT": "2",
                }, clear=False),
                patch("seoscout.translate.LLMClient", TrackingClient),
            ):
                result = await run_translate("example", "ja,es", output_dir=temp_dir)

        self.assertEqual(0, result)
        self.assertLessEqual(TrackingClient.instance.peak_active, 2)

    async def test_generate_batch_respects_configured_concurrency_limit(self):
        """A burst of article prompts must not exceed the configured API limit."""
        class TrackingClient(LLMClient):
            def __init__(self):
                super().__init__()
                self.active = 0
                self.peak_active = 0

            async def generate_single(self, _session, _prompt, _meta):
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
                try:
                    await __import__("asyncio").sleep(0.01)
                    return "ok"
                finally:
                    self.active -= 1

        original_limit = Config.GENERATE_CONCURRENT_LIMIT
        Config.GENERATE_CONCURRENT_LIMIT = 2
        try:
            client = TrackingClient()
            prompts = [(f"prompt-{index}", {"keyword": f"keyword-{index}"}) for index in range(8)]
            results = await client.generate_batch(prompts, batch_size=8)
        finally:
            Config.GENERATE_CONCURRENT_LIMIT = original_limit

        self.assertEqual(8, len(results))
        self.assertLessEqual(client.peak_active, 2)

    async def test_generate_single_retries_503_with_exponential_backoff(self):
        """Temporary upstream cooling must not discard an article after two quick retries."""
        class FakeResponse:
            def __init__(self, status, payload):
                self.status = status
                self.payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback):
                return False

            async def json(self):
                return self.payload

            async def text(self):
                return str(self.payload)

        class FakeSession:
            def __init__(self):
                self.responses = [
                    FakeResponse(503, {"error": "cooling"}),
                    FakeResponse(503, {"error": "cooling"}),
                    FakeResponse(503, {"error": "cooling"}),
                    FakeResponse(200, {"choices": [{"message": {"content": "article"}}]}),
                ]
                self.calls = 0

            def post(self, *_args, **_kwargs):
                response = self.responses[self.calls]
                self.calls += 1
                return response

        client = LLMClient()
        original_attempts = client.retry_attempts
        client.retry_attempts = 4
        client.retry_delay = 10
        session = FakeSession()
        try:
            with patch("seoscout.core.llm_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
                content = await client.generate_single(session, "prompt", {"keyword": "keyword"})
        finally:
            client.retry_attempts = original_attempts

        self.assertEqual("article", content)
        self.assertEqual(4, session.calls)
        self.assertEqual([call(20), call(40), call(80)], sleep.await_args_list)

    async def test_generate_returns_nonzero_when_article_is_still_invalid(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            keywords = root / "keywords.json"
            keywords.write_text(
                '{"categories":[{"category":"guide","keywords":["Example Game guide"]}]}',
                encoding="utf-8",
            )
            collected = root / "out" / "collected" / "guide"
            collected.mkdir(parents=True)
            (collected / "example_game_guide.json").write_text(
                '{"total_sources":1,"sources":[]}', encoding="utf-8"
            )
            (root / "out" / "search_results.json").write_text(
                '{"keywords":[{"keyword":"Example Game guide","category":"guide"}]}',
                encoding="utf-8",
            )
            with patch("seoscout.generate.LLMClient", InvalidArticleClient):
                result = await run_generate("example", str(keywords), output_dir=str(root))

        self.assertEqual(result, 1)

    async def test_generate_stops_before_batch_when_preflight_fails(self):
        """A failed API probe must prevent all article generation requests."""
        class PreflightFailClient:
            async def preflight_connectivity(self):
                return False, "LLM connectivity preflight failed: route refused"

            async def generate_batch(self, *_args, **_kwargs):
                raise AssertionError("generation must not start after a failed preflight")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            keywords = root / "keywords.json"
            keywords.write_text(
                '{"categories":[{"category":"guide","keywords":["Example Game guide"]}]}',
                encoding="utf-8",
            )
            collected = root / "out" / "collected" / "guide"
            collected.mkdir(parents=True)
            (collected / "example_game_guide.json").write_text(
                '{"total_sources":1,"sources":[]}', encoding="utf-8"
            )
            (root / "out" / "search_results.json").write_text(
                '{"keywords":[{"keyword":"Example Game guide","category":"guide"}]}',
                encoding="utf-8",
            )
            with patch("seoscout.generate.LLMClient", PreflightFailClient):
                result = await run_generate("example", str(keywords), output_dir=str(root))

        self.assertEqual(result, 1)

    def test_rendered_article_prompt_requires_semicolon_after_metadata_export(self):
        rendered = load_prompt_template().format(
            merged_data="{}", current_date="2026-11-11", category="guide"
        )

        self.assertIn('videoCreator: "sources.youtube.videos[0].channel or empty string",\n};', rendered)

    def test_repair_prompt_requires_one_closed_metadata_export(self):
        prompt = _build_repair_prompt(
            "unused", {"keyword": "Example Game guide"}, "broken draft", "missing closing"
        )

        self.assertIn("exactly one `export const metadata` block", prompt)
        self.assertIn("a line containing only `};`", prompt)

    def test_generate_cli_propagates_failed_generate_exit_code(self):
        async def failed_generate(_args):
            return 1

        original = cli._run_generate
        original_argv = sys.argv
        cli._run_generate = failed_generate
        sys.argv = ["seoscout", "generate", "--keywords", "keywords.json"]
        try:
            with self.assertRaises(SystemExit) as exc:
                cli.main()
        finally:
            cli._run_generate = original
            sys.argv = original_argv

        self.assertEqual(exc.exception.code, 1)

    def test_translate_cli_propagates_failed_translate_exit_code(self):
        async def failed_translate(_args):
            return 1

        original = cli._run_translate
        original_argv = sys.argv
        cli._run_translate = failed_translate
        sys.argv = ["seoscout", "translate", "--keywords", "keywords.json"]
        try:
            with self.assertRaises(SystemExit) as exc:
                cli.main()
        finally:
            cli._run_translate = original
            sys.argv = original_argv

        self.assertEqual(exc.exception.code, 1)
