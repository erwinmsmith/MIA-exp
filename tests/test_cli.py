from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mia_exp import cli


class CLITests(unittest.TestCase):
    @patch("mia_exp.cli.run_benchmark")
    def test_run_uses_start_and_limit_without_requiring_index(
        self, run_benchmark
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            (run_root / "summary.json").write_text("{}\n", encoding="utf-8")
            run_benchmark.return_value = run_root
            with patch.object(
                sys,
                "argv",
                [
                    "mia-bench",
                    "run",
                    "spp.logic-grid-puzzle",
                    "--start",
                    "2",
                    "--limit",
                    "3",
                ],
            ):
                with redirect_stdout(io.StringIO()):
                    result = cli.main()

        self.assertEqual(result, 0)
        self.assertEqual(
            list(run_benchmark.call_args.kwargs["indices"]),
            [2, 3, 4],
        )


if __name__ == "__main__":
    unittest.main()
