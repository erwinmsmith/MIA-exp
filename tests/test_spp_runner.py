from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mia_exp.spp_runner import run_benchmark


class SPPRunnerTests(unittest.TestCase):
    def test_rejects_duplicate_indices_before_starting_a_run(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            run_benchmark(
                "spp.logic-grid-puzzle",
                indices=[0, 0],
            )

    def test_rejects_an_output_directory_containing_an_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "run.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "already contains"):
                run_benchmark(
                    "spp.logic-grid-puzzle",
                    indices=[0],
                    output_dir=output,
                )


if __name__ == "__main__":
    unittest.main()
