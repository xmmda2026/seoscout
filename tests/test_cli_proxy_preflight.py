import argparse
import unittest
from unittest.mock import AsyncMock, patch

from seoscout import cli


class CliProxyPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_preflights_all_pipeline_stages_once(self):
        args = argparse.Namespace(
            command="run",
            project="example",
            output_dir="/tmp/example-output",
        )

        with (
            patch("seoscout.cli.Config.init"),
            patch(
                "seoscout.cli.preflight_proxy_for_stages",
                new=AsyncMock(return_value=(True, "Proxy preflight passed")),
            ) as preflight,
        ):
            ok = await cli._preflight_proxy(args)

        self.assertTrue(ok)
        preflight.assert_awaited_once_with(["search", "extract", "llm"])

    async def test_failed_proxy_preflight_stops_generate_before_runner(self):
        args = argparse.Namespace(command="generate")

        with (
            patch("seoscout.cli._preflight_proxy", new=AsyncMock(return_value=False)),
            patch("seoscout.cli._run_generate", new=AsyncMock(return_value=0)) as generate,
        ):
            result = await cli._run_command(args)

        self.assertEqual(1, result)
        generate.assert_not_awaited()
