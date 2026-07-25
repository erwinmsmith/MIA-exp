from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mia_exp.harbor_results import summarize_harbor_job


class HarborResultTests(unittest.TestCase):
    def _write_trial(
        self,
        job_dir: Path,
        *,
        task: str,
        attempt: int,
        reward: float | None,
        exception: str | None = None,
    ) -> None:
        trial_dir = job_dir / f"{task}__{attempt}"
        trial_dir.mkdir()
        payload = {
            "task_name": task,
            "trial_name": trial_dir.name,
            "started_at": f"2026-07-25T00:00:0{attempt}",
            "finished_at": f"2026-07-25T00:01:0{attempt}",
            "verifier_result": (
                {"rewards": {"reward": reward}} if reward is not None else None
            ),
            "exception_info": (
                {"exception_type": exception} if exception else None
            ),
        }
        (trial_dir / "result.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_threshold_aware_pass_at_1_and_pass_at_5(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_dir = Path(directory)
            (job_dir / "result.json").write_text(
                json.dumps({
                    "n_total_trials": 10,
                    "stats": {
                        "n_completed_trials": 10,
                        "n_errored_trials": 0,
                        "n_cancelled_trials": 0,
                        "n_pending_trials": 0,
                        "n_input_tokens": 123,
                    },
                }),
                encoding="utf-8",
            )
            for attempt, reward in enumerate([0.95, 0.2, 0.1, 0.0, 0.0], 1):
                self._write_trial(
                    job_dir,
                    task="task-a",
                    attempt=attempt,
                    reward=reward,
                )
            for attempt in range(1, 6):
                self._write_trial(
                    job_dir,
                    task="task-b",
                    attempt=attempt,
                    reward=1.0,
                )

            summary = summarize_harbor_job(
                job_dir,
                success_threshold=0.95,
                k_values=[1, 5],
            )

        self.assertAlmostEqual(summary["tasks"]["task-a"]["passAtK"]["1"], 0.2)
        self.assertEqual(summary["tasks"]["task-a"]["passAtK"]["5"], 1.0)
        self.assertEqual(summary["aggregate"]["passAtK"]["1"], 0.6)
        self.assertEqual(summary["aggregate"]["passAtK"]["5"], 1.0)
        self.assertTrue(summary["aggregate"]["allTasksObservedPassAtK"]["1"])
        self.assertEqual(summary["aggregate"]["inputTokens"], 123)

    def test_records_insufficient_attempts_and_failed_trials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_dir = Path(directory)
            (job_dir / "result.json").write_text(
                json.dumps({
                    "n_total_trials": 2,
                    "stats": {
                        "n_completed_trials": 2,
                        "n_errored_trials": 1,
                    },
                }),
                encoding="utf-8",
            )
            self._write_trial(
                job_dir,
                task="task-a",
                attempt=1,
                reward=1.0,
            )
            self._write_trial(
                job_dir,
                task="task-b",
                attempt=1,
                reward=None,
                exception="AgentTimeoutError",
            )

            summary = summarize_harbor_job(job_dir)

        self.assertIsNone(summary["aggregate"]["passAtK"]["5"])
        self.assertFalse(summary["aggregate"]["allTasksObservedPassAtK"]["1"])
        self.assertEqual(summary["aggregate"]["erroredTrials"], 1)
        self.assertEqual(
            summary["tasks"]["task-b"]["trials"][0]["exceptionType"],
            "AgentTimeoutError",
        )


if __name__ == "__main__":
    unittest.main()
