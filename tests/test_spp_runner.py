from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from mia_exp.spp_runner import run_benchmark
from mia_exp.roy_runner import RoyInvocation, RoyInvocationFailure


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

    def test_records_failed_roy_invocation_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"

            def fail_with_artifact(*_args, **kwargs):
                artifact_path = kwargs["artifact_path"]
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text('{"status":"failed"}\n', encoding="utf-8")
                invocation = RoyInvocation(
                    response="",
                    artifact_path=artifact_path,
                    duration_seconds=1.25,
                    telemetry={
                        "runtimeStatus": "failed",
                        "turnRecoveryAttempts": 3,
                    },
                )
                raise RoyInvocationFailure(
                    "Roy exited with code 1: Connection error.",
                    invocation,
                )

            with patch("mia_exp.spp_runner.run_roy", side_effect=fail_with_artifact):
                result = run_benchmark(
                    "spp.logic-grid-puzzle",
                    indices=[0],
                    output_dir=output,
                )

            record = json.loads(
                (result / "items.jsonl").read_text(encoding="utf-8")
            )

        self.assertEqual(record["status"], "failed")
        self.assertEqual(
            record["invocations"]["solver"]["telemetry"]["runtimeStatus"],
            "failed",
        )
        self.assertEqual(
            record["invocations"]["solver"]["telemetry"]["turnRecoveryAttempts"],
            3,
        )


if __name__ == "__main__":
    unittest.main()
