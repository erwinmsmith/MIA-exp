from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from harbor.environments.base import ExecResult
from harbor.models.agent.context import AgentContext

from mia_exp.benchmarks.lhtb import (
    RoyLHTBAgent,
    RoyLHTBDockerEnvironment,
    _external_wall_clock_ms,
    _write_runtime_env_file,
)


class RuntimeEnvFileTests(unittest.TestCase):
    def test_writes_shell_quoted_values_with_owner_only_permissions(self) -> None:
        path = _write_runtime_env_file(
            {
                "DEEPSEEK_API_KEY": "secret value with spaces",
                "DEFAULT_MODEL": "model",
            }
        )
        try:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            content = path.read_text(encoding="utf-8")
            self.assertIn("export DEEPSEEK_API_KEY='secret value with spaces'", content)
            self.assertIn("export DEFAULT_MODEL=model", content)
        finally:
            path.unlink(missing_ok=True)

    def test_rejects_invalid_environment_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid runtime environment"):
            _write_runtime_env_file({"BAD-KEY": "value"})

    def test_extracts_a_safety_bounded_external_deadline(self) -> None:
        self.assertEqual(
            _external_wall_clock_ms(
                "You still have approximately 421 seconds remaining in this trial."
            ),
            379_000,
        )
        self.assertIsNone(_external_wall_clock_ms("Initial benchmark round."))


class DockerImageRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_trial_cleanup_removes_volumes_without_deleting_pulled_image(
        self,
    ) -> None:
        environment = object.__new__(RoyLHTBDockerEnvironment)
        environment.prepare_logs_for_host = AsyncMock()  # type: ignore[method-assign]
        environment._run_docker_compose_command = AsyncMock()  # type: ignore[method-assign]
        environment._cleanup_mounts_compose_file = Mock()  # type: ignore[method-assign]
        environment._keep_containers = False
        environment.logger = Mock()

        await environment.stop(delete=True)

        environment._run_docker_compose_command.assert_awaited_once_with(  # type: ignore[attr-defined]
            ["down", "--volumes", "--remove-orphans"]
        )
        command = environment._run_docker_compose_command.await_args.args[0]  # type: ignore[attr-defined]
        self.assertNotIn("--rmi", command)
        environment._cleanup_mounts_compose_file.assert_called_once_with()  # type: ignore[attr-defined]


class FakeEnvironment:
    session_id = "secure-session"

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str]] = []
        self.exec_calls: list[tuple[str, dict[str, Any]]] = []

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        source = Path(source_path)
        self.uploads.append(
            (str(source), target_path, source.read_text(encoding="utf-8"))
        )

    async def exec(self, command: str, **kwargs: Any) -> ExecResult:
        self.exec_calls.append((command, kwargs))
        return ExecResult(return_code=0, stdout="", stderr="")

    async def download_file(self, _source_path: str, target_path: Path | str) -> None:
        Path(target_path).write_text(
            json.dumps(
                {
                    "result": {
                        "finalResponse": "done",
                        "correlationId": "correlation",
                        "executionTree": {"status": "completed"},
                        "usage": {"total": {}},
                    }
                }
            ),
            encoding="utf-8",
        )

    async def download_dir(self, _source_dir: str, _target_dir: Path | str) -> None:
        return None


class RoyLHTBSecretInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundle_can_be_selected_without_changing_benchmark_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "roy-versioned.mjs"
            bundle_path.write_text("// versioned bundle", encoding="utf-8")
            with patch.dict(os.environ, {"MIA_ROY_BUNDLE": str(bundle_path)}):
                agent = RoyLHTBAgent(logs_dir=Path(directory) / "logs")

        self.assertEqual(agent.bundle_path, bundle_path.resolve())

    async def test_runtime_does_not_pass_credentials_in_exec_argv_or_env(self) -> None:
        secret = "test-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory)
            agent = RoyLHTBAgent(
                logs_dir=logs_dir,
                extra_env={"DEEPSEEK_API_KEY": secret},
            )
            environment = FakeEnvironment()

            await agent.run(
                "Complete the task.",
                environment,  # type: ignore[arg-type]
                AgentContext(),
            )

        env_upload = next(
            upload for upload in environment.uploads if "roy-runtime-env" in upload[1]
        )
        self.assertIn(secret, env_upload[2])
        self.assertFalse(Path(env_upload[0]).exists())
        for command, kwargs in environment.exec_calls:
            self.assertNotIn(secret, command)
            self.assertNotIn(secret, repr(kwargs))
        run_command = next(
            command
            for command, _kwargs in environment.exec_calls
            if "/opt/roy/roy-run.mjs" in command
        )
        mirror_command = next(
            command
            for command, _kwargs in environment.exec_calls
            if 'cp -f "/tests/$name"' in command
        )
        self.assertIn("test_outputs.py grade.py", mirror_command)
        self.assertIn('cp -f "/tests/$name"', mirror_command)
        self.assertIn(". /tmp/roy-runtime-env-1.sh", run_command)
        self.assertIn("rm -f /tmp/roy-runtime-env-1.sh", run_command)
        run_kwargs = next(
            kwargs
            for command, kwargs in environment.exec_calls
            if "/opt/roy/roy-run.mjs" in command
        )
        self.assertIsNone(run_kwargs["timeout_sec"])

    async def test_continuation_includes_changed_official_verifier_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trial_dir = Path(directory)
            logs_dir = trial_dir / "agent"
            verifier_dir = trial_dir / "verifier"
            logs_dir.mkdir()
            verifier_dir.mkdir()
            (verifier_dir / "reward.txt").write_text("0", encoding="utf-8")
            (verifier_dir / "test-stdout.txt").write_text(
                "FAILED dependency gate\nlangchain-community is unavailable",
                encoding="utf-8",
            )
            (verifier_dir / "pytest.log").write_text(
                "ImportError: cannot import name 'run_audit'",
                encoding="utf-8",
            )
            (verifier_dir / "install.log").write_text(
                "ERROR no matching distribution",
                encoding="utf-8",
            )
            agent = RoyLHTBAgent(logs_dir=logs_dir)
            agent._round = 2

            instruction = agent._build_instruction("Continue the migration.")

        self.assertIn("<official_verifier_feedback>", instruction)
        self.assertIn("FAILED dependency gate", instruction)
        self.assertIn("langchain-community is unavailable", instruction)
        self.assertIn("ImportError: cannot import name 'run_audit'", instruction)
        self.assertIn("ERROR no matching distribution", instruction)
        self.assertIn("## Required local repair verification", instruction)
        self.assertIn(
            ".roy/official-verifier/test_outputs.py",
            instruction,
        )
        self.assertIn(
            "python -m pytest -p no:cacheprovider -q "
            ".roy/official-verifier/test_outputs.py",
            instruction,
        )

    async def test_noisy_verifier_feedback_is_causally_compacted(self) -> None:
        content = "pip setup\n" + ("Requirement already satisfied\n" * 1_000)
        content += "ERROR final dependency failure"

        compacted = RoyLHTBAgent._compact_verifier_feedback(
            "install.log",
            content,
        )

        self.assertLessEqual(len(compacted), 3_100)
        self.assertIn("compacted", compacted)
        self.assertIn("ERROR final dependency failure", compacted)

    async def test_successful_installer_output_is_not_replayed_as_repair_evidence(
        self,
    ) -> None:
        content = "\n".join(
            [
                "Installing build dependencies: finished with status 'done'",
                "Requirement already satisfied: jsonschema>=4.18",
                "Successfully installed dq-audit-0.1.0",
            ]
        )

        compacted = RoyLHTBAgent._compact_verifier_feedback(
            "install.log",
            content,
        )

        self.assertIn("completed without a reported failure", compacted)
        self.assertNotIn("Requirement already satisfied", compacted)

    async def test_continuation_uploads_checked_out_verifier_into_workspace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trial_dir = Path(directory) / "great-expectations-audit__trial"
            logs_dir = trial_dir / "agent"
            logs_dir.mkdir(parents=True)
            agent = RoyLHTBAgent(logs_dir=logs_dir)
            agent._round = 2
            environment = FakeEnvironment()

            await agent._mirror_official_verifier(environment)  # type: ignore[arg-type]

        verifier_upload = next(
            upload
            for upload in environment.uploads
            if upload[1].endswith("/.roy/official-verifier/test_outputs.py")
        )
        self.assertIn(
            "def test_cli_creates_all_required_artifacts",
            verifier_upload[2],
        )

    async def test_local_verifier_command_uses_checked_out_task_entrypoint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trial_dir = Path(directory) / "langchain-version-migration__trial"
            logs_dir = trial_dir / "agent"
            logs_dir.mkdir(parents=True)
            agent = RoyLHTBAgent(logs_dir=logs_dir)

            command = agent._local_verifier_command()

        self.assertEqual(
            command,
            "python -m pytest -p no:cacheprovider -q "
            ".roy/official-verifier/test_outputs.py",
        )

    async def test_truncated_harbor_trial_id_resolves_full_task_verifier(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trial_dir = Path(directory) / "document-table-layout-reconstruc__trial"
            logs_dir = trial_dir / "agent"
            logs_dir.mkdir(parents=True)
            (trial_dir / "config.json").write_text(
                json.dumps(
                    {
                        "task": {
                            "path": str(
                                Path(directory)
                                / "document-table-layout-reconstruction"
                            )
                        }
                    }
                ),
                encoding="utf-8",
            )
            agent = RoyLHTBAgent(logs_dir=logs_dir)
            agent._round = 2
            environment = FakeEnvironment()

            await agent._mirror_official_verifier(environment)  # type: ignore[arg-type]

        verifier_upload = next(
            upload
            for upload in environment.uploads
            if upload[1].endswith("/.roy/official-verifier/grade.py")
        )
        self.assertIn("G_hidden_end_to_end_stress", verifier_upload[2])

    async def test_continuation_does_not_replay_unchanged_verifier_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trial_dir = Path(directory)
            logs_dir = trial_dir / "agent"
            verifier_dir = trial_dir / "verifier"
            logs_dir.mkdir()
            verifier_dir.mkdir()
            failure = "FAILED dependency gate\nlangchain-community is unavailable"
            (verifier_dir / "test-stdout.txt").write_text(failure, encoding="utf-8")
            agent = RoyLHTBAgent(logs_dir=logs_dir)
            agent._round = 2

            first = agent._build_instruction("Continue the migration.")
            agent._round = 3
            second = agent._build_instruction("Continue the migration.")

        self.assertIn(failure, first)
        self.assertNotIn(failure, second)
        self.assertIn("Unchanged since the previous Roy round", second)
        self.assertIn("persisted execution ledger", second)
        self.assertIn(
            "python .roy/official-verifier/grade.py",
            second,
        )

    async def test_continuation_passes_external_deadline_to_roy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory)
            agent = RoyLHTBAgent(logs_dir=logs_dir)
            environment = FakeEnvironment()

            await agent.run(
                "You still have approximately 421 seconds remaining in this trial.",
                environment,  # type: ignore[arg-type]
                AgentContext(),
            )

        run_command = next(
            command
            for command, _kwargs in environment.exec_calls
            if "/opt/roy/roy-run.mjs" in command
        )
        self.assertIn("--wall-clock-ms 379000", run_command)

    async def test_development_run_can_use_its_workspace_policy_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory)
            agent = RoyLHTBAgent(
                logs_dir=logs_dir,
                honor_external_deadline=False,
            )
            environment = FakeEnvironment()

            await agent.run(
                "You still have approximately 421 seconds remaining in this trial.",
                environment,  # type: ignore[arg-type]
                AgentContext(),
            )

        run_command = next(
            command
            for command, _kwargs in environment.exec_calls
            if "/opt/roy/roy-run.mjs" in command
        )
        self.assertNotIn("--wall-clock-ms", run_command)


if __name__ == "__main__":
    unittest.main()
