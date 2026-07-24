from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from harbor.environments.base import ExecResult
from harbor.models.agent.context import AgentContext

from mia_exp.benchmarks.lhtb import RoyLHTBAgent, _write_runtime_env_file


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
        self.assertIn(". /tmp/roy-runtime-env-1.sh", run_command)
        self.assertIn("rm -f /tmp/roy-runtime-env-1.sh", run_command)


if __name__ == "__main__":
    unittest.main()
