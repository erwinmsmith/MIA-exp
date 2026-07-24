"""Harbor adapter that runs Roy inside an LHTB task container."""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE = REPO_ROOT / "artifacts" / "roy-run.mjs"
DEFAULT_NODE_ARCHIVE = REPO_ROOT / "artifacts" / "node-v20.20.2-linux-x64.tar.gz"
DEFAULT_POLICY = REPO_ROOT / "experiments" / "lhtb" / "roy-workspace-config.json"
PASSTHROUGH_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_ANTHROPIC_BASE_URL",
    "OPENROUTER_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "DEFAULT_MODEL",
)
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REMAINING_SECONDS_PATTERN = re.compile(
    r"approximately\s+(\d+)\s+seconds\s+remaining",
    re.IGNORECASE,
)
VERIFIER_FEEDBACK_FILES = (
    "reward.txt",
    "test-stdout.txt",
    "install.log",
)


def _write_runtime_env_file(values: dict[str, str]) -> Path:
    """Create a short-lived 0600 shell file without exposing values in argv."""

    invalid = sorted(key for key in values if not ENV_KEY_PATTERN.fullmatch(key))
    if invalid:
        raise ValueError(f"Invalid runtime environment key(s): {', '.join(invalid)}")
    descriptor, raw_path = tempfile.mkstemp(prefix="mia-exp-roy-env-", suffix=".sh")
    path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for key, value in sorted(values.items()):
                handle.write(f"export {key}={shlex.quote(value)}\n")
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        raise
    return path


def _external_wall_clock_ms(instruction: str) -> int | None:
    """Translate Harbor continuation time into a deadline Roy can honor."""

    matches = REMAINING_SECONDS_PATTERN.findall(instruction)
    if not matches:
        return None
    remaining_seconds = int(matches[-1])
    safety_margin_seconds = min(45, max(5, remaining_seconds // 10))
    return max(1_000, (remaining_seconds - safety_margin_seconds) * 1_000)


class RoyLHTBAgent(BaseAgent):
    """Install a bundled Roy CLI and run it within Harbor's task environment."""

    SUPPORTS_ATIF = False
    SUPPORTS_WINDOWS = False

    @staticmethod
    def name() -> str:
        return "roy-lhtb"

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        bundle_path: str | None = None,
        node_archive_path: str | None = None,
        policy_path: str | None = None,
        workspace: str = "/app",
        timeout_sec: int = 5400,
        token_budget: int | None = None,
        extra_env: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            logs_dir=logs_dir,
            model_name=model_name,
            **kwargs,
        )
        self.bundle_path = Path(
            bundle_path or os.environ.get("MIA_ROY_BUNDLE") or DEFAULT_BUNDLE
        ).resolve()
        self.node_archive_path = Path(
            node_archive_path or DEFAULT_NODE_ARCHIVE
        ).resolve()
        self.policy_path = Path(policy_path or DEFAULT_POLICY).resolve()
        self.workspace = workspace
        self.timeout_sec = timeout_sec
        self.token_budget = token_budget
        self.extra_env = {
            key: value for key in PASSTHROUGH_ENV if (value := os.environ.get(key))
        }
        if extra_env:
            self.extra_env.update(extra_env)
        self._round = 0

    def version(self) -> str:
        package = json.loads((REPO_ROOT / "core" / "Roy" / "package.json").read_text())
        return str(package["version"])

    def _validate_local_artifacts(self) -> None:
        missing = [
            path
            for path in (
                self.bundle_path,
                self.node_archive_path,
                self.policy_path,
            )
            if not path.is_file()
        ]
        if missing:
            rendered = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(
                f"Roy LHTB artifacts are missing: {rendered}. Run make bootstrap."
            )

    async def setup(self, environment: BaseEnvironment) -> None:
        self._validate_local_artifacts()
        workspace = shlex.quote(self.workspace)
        await environment.exec(
            command=(
                "mkdir -p /opt/roy /opt/node "
                f"{workspace}/.roy && chmod 777 {workspace}/.roy"
            ),
            user="root",
        )
        await environment.upload_file(
            self.node_archive_path,
            "/tmp/node-v20.20.2-linux-x64.tar.gz",
        )
        await environment.upload_file(self.bundle_path, "/opt/roy/roy-run.mjs")
        await environment.upload_file(
            self.policy_path,
            f"{self.workspace}/.roy/config.json",
        )
        install = await environment.exec(
            command=(
                "set -eu; "
                f"chmod 666 {workspace}/.roy/config.json; "
                "tar -xzf /tmp/node-v20.20.2-linux-x64.tar.gz "
                "-C /opt/node --strip-components=1; "
                "chmod 755 /opt/node/bin/node /opt/roy/roy-run.mjs; "
                "/opt/node/bin/node /opt/roy/roy-run.mjs --help >/dev/null"
            ),
            user="root",
            timeout_sec=180,
        )
        if install.return_code != 0:
            raise RuntimeError(
                "Roy setup failed: "
                f"{install.stderr or install.stdout or 'unknown setup error'}"
            )

    def _runtime_env(self) -> dict[str, str]:
        runtime_env = dict(self.extra_env)
        if "OPENAI_API_BASE" in runtime_env and "OPENAI_BASE_URL" not in runtime_env:
            runtime_env["OPENAI_BASE_URL"] = runtime_env["OPENAI_API_BASE"]
        if "OPENROUTER_API_KEY" in runtime_env:
            runtime_env.setdefault("OPENAI_API_KEY", runtime_env["OPENROUTER_API_KEY"])
            runtime_env.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        if self.model_name and "DEFAULT_MODEL" not in runtime_env:
            runtime_env["DEFAULT_MODEL"] = self.model_name.split("/", 1)[-1]
        runtime_env["LOG_LEVEL"] = "error"
        return runtime_env

    def _official_verifier_feedback(self) -> str:
        """Load bounded official verifier evidence for continuation rounds."""

        verifier_dir = self.logs_dir.parent / "verifier"
        sections: list[str] = []
        for filename in VERIFIER_FEEDBACK_FILES:
            path = verifier_dir / filename
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                sections.append(f"### {filename}\n{content[-4000:]}")
        return "\n\n".join(sections)

    def _build_instruction(self, instruction: str) -> str:
        content = (
            "This is a long-horizon terminal benchmark task. Work directly in "
            f"{self.workspace}. Use the terminal and filesystem tools, inspect "
            "actual state, implement the solution, run verification where "
            "possible, and continue until the task is genuinely complete. "
            "Do not merely describe commands.\n\n"
            f"{instruction}"
        )
        feedback = self._official_verifier_feedback()
        if self._round > 1 and feedback:
            content += (
                "\n\n<official_verifier_feedback>\n"
                "These are the latest official verifier artifacts. Treat their "
                "concrete errors as authoritative feedback, repair them, and rerun "
                "the relevant local checks before finalizing.\n\n"
                f"{feedback}\n"
                "</official_verifier_feedback>"
            )
        return content

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        self._round += 1
        round_id = self._round
        local_instruction = self.logs_dir / f"instruction-{round_id}.txt"
        local_instruction.write_text(self._build_instruction(instruction), encoding="utf-8")
        remote_instruction = f"/tmp/roy-instruction-{round_id}.txt"
        remote_result = f"/tmp/roy-run-{round_id}.json"
        await environment.upload_file(local_instruction, remote_instruction)
        budget_flag = (
            f" --budget {self.token_budget}" if self.token_budget is not None else ""
        )
        external_wall_clock_ms = _external_wall_clock_ms(instruction)
        wall_clock_flag = (
            f" --wall-clock-ms {external_wall_clock_ms}"
            if external_wall_clock_ms is not None
            else ""
        )
        command = (
            "/opt/node/bin/node /opt/roy/roy-run.mjs "
            f"--workspace {shlex.quote(self.workspace)} "
            f"--task-file {shlex.quote(remote_instruction)} "
            f"--session-id {shlex.quote(environment.session_id)} "
            f"--output {shlex.quote(remote_result)}"
            f"{budget_flag}"
            f"{wall_clock_flag}"
        )
        remote_env = f"/tmp/roy-runtime-env-{round_id}.sh"
        local_env = _write_runtime_env_file(self._runtime_env())
        try:
            await environment.upload_file(local_env, remote_env)
        finally:
            local_env.unlink(missing_ok=True)
        secured = await environment.exec(
            command=f"chmod 600 {shlex.quote(remote_env)}",
            user="root",
            timeout_sec=30,
        )
        if secured.return_code != 0:
            raise RuntimeError(
                "Could not secure Roy runtime environment file: "
                f"{secured.stderr or secured.stdout or 'unknown chmod error'}"
            )
        try:
            execution = await environment.exec(
                command=(
                    f"set -eu; . {shlex.quote(remote_env)}; "
                    f"rm -f {shlex.quote(remote_env)}; exec {command}"
                ),
                cwd=self.workspace,
                timeout_sec=self.timeout_sec,
            )
        finally:
            try:
                await environment.exec(
                    command=f"rm -f {shlex.quote(remote_env)}",
                    user="root",
                    timeout_sec=30,
                )
            except Exception:
                self.logger.warning("Could not remove the remote Roy environment file")

        local_result = self.logs_dir / f"roy-run-{round_id}.json"
        result_download_error: Exception | None = None
        try:
            try:
                await environment.download_file(remote_result, local_result)
            except Exception as error:
                result_download_error = error
        finally:
            try:
                await environment.download_dir(
                    f"{self.workspace}/.roy",
                    self.logs_dir / f"roy-state-{round_id}",
                )
            except Exception as error:  # Preserve the primary execution result.
                self.logger.warning("Could not download Roy state: %s", error)

        metadata: dict[str, Any] = {
            "round": round_id,
            "return_code": execution.return_code,
            "stdout_tail": (execution.stdout or "")[-4000:],
            "stderr_tail": (execution.stderr or "")[-4000:],
            "result_path": str(local_result),
            "state_path": str(self.logs_dir / f"roy-state-{round_id}"),
            "result_download_error": (
                str(result_download_error) if result_download_error else None
            ),
            "external_wall_clock_ms": external_wall_clock_ms,
        }
        if local_result.is_file():
            artifact = json.loads(local_result.read_text(encoding="utf-8"))
            usage = artifact.get("result", {}).get("usage", {}).get("total", {})
            context.n_input_tokens = usage.get("inputTokens")
            context.n_output_tokens = usage.get("outputTokens")
            context.n_cache_tokens = usage.get("cachedInputTokens")
            context.cost_usd = usage.get("estimatedCostUsd")
            metadata["correlation_id"] = artifact.get("result", {}).get("correlationId")
            metadata["execution_tree_status"] = (
                artifact.get("result", {}).get("executionTree", {}).get("status")
            )
        context.metadata = {**(context.metadata or {}), **metadata}

        if execution.return_code != 0:
            raise RuntimeError(
                "Roy exited with code "
                f"{execution.return_code}: {execution.stderr or execution.stdout}"
            )
        if result_download_error:
            raise RuntimeError(
                "Roy exited without a downloadable JSON run artifact: "
                f"{result_download_error}"
            )
