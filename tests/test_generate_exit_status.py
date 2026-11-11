import sys
import unittest

from seoscout import cli
from seoscout.generate import run_generate


class InvalidArticleClient:
    async def generate_batch(self, prompts, batch_size=None):
        return [(meta, "not valid MDX") for _, meta in prompts]

    def print_stats(self):
        pass


class GenerateExitStatusTests(unittest.IsolatedAsyncioTestCase):
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
