"""Harbor adapter that runs Roy inside an LHTB task container."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.agent.context import AgentContext


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE = REPO_ROOT / "artifacts" / "roy-run.mjs"
DEFAULT_NODE_ARCHIVE = REPO_ROOT / "artifacts" / "node-v20.20.2-linux-x64.tar.gz"
DEFAULT_POLICY = REPO_ROOT / "experiments" / "lhtb" / "roy-workspace-config.json"
LHTB_TASKS_ROOT = REPO_ROOT / "benchmarks" / "LHTB" / "tasks"
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
    "pytest.log",
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


class RoyLHTBDockerEnvironment(DockerEnvironment):
    """Delete trial containers and volumes while retaining pulled benchmark images."""

    async def stop(self, delete: bool) -> None:
        if not delete:
            await super().stop(delete=False)
            return
        try:
            await self.prepare_logs_for_host()
            if self._keep_containers:
                self.logger.warning(
                    "Both keep_containers and delete are set; keep_containers takes precedence."
                )
                await self._run_docker_compose_command(["stop"])
            else:
                await self._run_docker_compose_command(
                    ["down", "--volumes", "--remove-orphans"]
                )
        except Exception as error:
            self.logger.warning("Docker compose cleanup failed: %s", error)
        finally:
            self._cleanup_mounts_compose_file()


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
        timeout_sec: int | None = None,
        token_budget: int | None = None,
        honor_external_deadline: bool = True,
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
        self.honor_external_deadline = honor_external_deadline
        self.extra_env = {
            key: value for key in PASSTHROUGH_ENV if (value := os.environ.get(key))
        }
        if extra_env:
            self.extra_env.update(extra_env)
        self._round = 0
        self._verifier_feedback_hashes: dict[str, str] = {}

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
        """Load changed verifier evidence and avoid replaying identical artifacts."""

        verifier_dir = self.logs_dir.parent / "verifier"
        sections: list[str] = []
        for filename in VERIFIER_FEEDBACK_FILES:
            path = verifier_dir / filename
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                continue
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            prior_digest = self._verifier_feedback_hashes.get(filename)
            self._verifier_feedback_hashes[filename] = digest
            if prior_digest == digest:
                sections.append(
                    f"### {filename}\n"
                    f"Unchanged since the previous Roy round (sha256:{digest[:16]}). "
                    "Use the persisted execution ledger for the previously supplied details."
                )
            else:
                compacted = self._compact_verifier_feedback(filename, content)
                sections.append(
                    f"### {filename} (new or changed; sha256:{digest[:16]})\n"
                    f"{compacted}"
                )
        return "\n\n".join(sections)

    @staticmethod
    def _compact_verifier_feedback(filename: str, content: str) -> str:
        """Keep causal verifier evidence and summarize successful installer plumbing."""

        if filename == "install.log":
            failure_lines = [
                line.strip()
                for line in content.splitlines()
                if re.search(
                    r"\b(?:error|failed|failure|traceback|exception|"
                    r"no matching distribution|resolution impossible|"
                    r"incompatible|conflict|could not|cannot)\b",
                    line,
                    re.IGNORECASE,
                )
            ]
            if not failure_lines:
                return (
                    "Dependency installation completed without a reported failure; "
                    "routine package-manager output is stored in install.log and "
                    "omitted from the reasoning context."
                )

        limits = {
            "reward.txt": 512,
            "test-stdout.txt": 8_000,
            "pytest.log": 12_000,
            "install.log": 3_000,
        }
        limit = limits.get(filename, 6_000)
        if len(content) <= limit:
            return content
        head_size = min(1_000, limit // 3)
        tail_size = max(0, limit - head_size - 120)
        return (
            f"{content[:head_size].rstrip()}\n"
            f"...[compacted {len(content) - head_size - tail_size} noisy characters; "
            "latest failure frontier follows]...\n"
            f"{content[-tail_size:].lstrip()}"
        )

    def _local_verifier_command(self) -> str | None:
        """Return the task's mounted verifier entrypoint after Harbor has exposed it."""

        local_tests = LHTB_TASKS_ROOT / self._task_name() / "tests"
        if (local_tests / "test_outputs.py").is_file():
            return (
                "python -m pytest -p no:cacheprovider -q "
                ".roy/official-verifier/test_outputs.py"
            )
        if (local_tests / "grade.py").is_file():
            return "python .roy/official-verifier/grade.py"
        verifier_dir = self.logs_dir.parent / "verifier"
        if (verifier_dir / "pytest.log").is_file():
            return (
                "python -m pytest -p no:cacheprovider -q "
                ".roy/official-verifier/test_outputs.py"
            )
        if (verifier_dir / "test-stdout.txt").is_file():
            return "python .roy/official-verifier/grade.py"
        return None

    def _task_name(self) -> str:
        """Resolve the full task name without relying on Harbor's truncated trial id."""

        trial_config = self.logs_dir.parent / "config.json"
        if trial_config.is_file():
            try:
                config = json.loads(trial_config.read_text(encoding="utf-8"))
                task = config.get("task", {})
                configured_name = task.get("name")
                configured_path = task.get("path")
                candidate = (
                    configured_name
                    if isinstance(configured_name, str) and configured_name
                    else Path(configured_path).name
                    if isinstance(configured_path, str) and configured_path
                    else ""
                )
                if candidate and (LHTB_TASKS_ROOT / candidate).is_dir():
                    return candidate
            except (OSError, ValueError, TypeError):
                pass

        trial_prefix = self.logs_dir.parent.name.split("__", 1)[0]
        candidates = sorted(
            path.name
            for path in LHTB_TASKS_ROOT.iterdir()
            if path.is_dir() and path.name.startswith(trial_prefix)
        )
        if len(candidates) == 1:
            return candidates[0]
        return trial_prefix

    async def _mirror_official_verifier(self, environment: BaseEnvironment) -> None:
        """Expose the complete verifier bundle to workspace-scoped Roy tools."""

        workspace = shlex.quote(self.workspace)
        mirror_root = f"{self.workspace}/.roy/official-verifier"
        task_name = self._task_name()
        local_tests = LHTB_TASKS_ROOT / task_name / "tests"
        checked_out_files = (
            sorted(
                path
                for path in local_tests.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            )
            if self._round > 1 and local_tests.is_dir()
            else []
        )
        mirror_directories = sorted(
            {
                Path(mirror_root),
                *(
                    Path(mirror_root) / source.relative_to(local_tests).parent
                    for source in checked_out_files
                ),
            },
            key=lambda path: (len(path.parts), str(path)),
        )
        prepared = await environment.exec(
            command="mkdir -p "
            + " ".join(shlex.quote(str(path)) for path in mirror_directories),
            user="root",
            timeout_sec=30,
        )
        if prepared.return_code != 0:
            raise RuntimeError(
                "Could not prepare Roy's verifier mirror directory: "
                f"{prepared.stderr or prepared.stdout or 'unknown mkdir error'}"
            )
        expected_remote_files: list[str] = []
        for source in checked_out_files:
            relative = source.relative_to(local_tests)
            target = f"{mirror_root}/{relative.as_posix()}"
            await environment.upload_file(source, target)
            expected_remote_files.append(relative.as_posix())
        mirrored = await environment.exec(
            command=(
                "set -eu; "
                "if [ -d /tests ]; then "
                f"cp -a /tests/. {workspace}/.roy/official-verifier/; "
                "fi; "
                "if [ ! -e /tests ]; then "
                f"ln -s {workspace}/.roy/official-verifier /tests; "
                "fi; "
                f"find {workspace}/.roy/official-verifier "
                "-type f -exec chmod 444 {} +; "
                f"find {workspace}/.roy/official-verifier "
                "-type d -exec chmod 555 {} +"
            ),
            user="root",
            timeout_sec=30,
        )
        if mirrored.return_code != 0:
            raise RuntimeError(
                "Could not mirror the mounted verifier into Roy's workspace: "
                f"{mirrored.stderr or mirrored.stdout or 'unknown copy error'}"
            )
        if expected_remote_files:
            expected_checks = " && ".join(
                f"test -f {shlex.quote(f'{mirror_root}/{filename}')}"
                for filename in expected_remote_files
            )
            verified = await environment.exec(
                command=expected_checks,
                user="root",
                timeout_sec=30,
            )
            if verified.return_code != 0:
                raise RuntimeError(
                    "Checked-out official verifier bundle did not materialize "
                    f"inside the task workspace: {', '.join(expected_remote_files)}"
                )

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
                "Resume the persisted execution tree rather than rebuilding the "
                "initial team. These are delta-aware official verifier artifacts: "
                "changed content is included in full, while an unchanged marker "
                "refers to evidence already stored in the execution ledger. Treat "
                "concrete errors as authoritative feedback, repair them, and rerun "
                "the relevant local checks before finalizing.\n\n"
                f"{feedback}\n"
                "</official_verifier_feedback>"
            )
            local_verifier = self._local_verifier_command()
            if local_verifier:
                mirrored_verifier = (
                    ".roy/official-verifier/test_outputs.py"
                    if "pytest" in local_verifier
                    else ".roy/official-verifier/grade.py"
                )
                content += (
                    "\n\n## Required local repair verification\n\n"
                    "The official verifier entrypoint is mirrored read-only inside "
                    "the workspace at "
                    f"`{mirrored_verifier}`. Read the relevant assertions from "
                    "that exact file before making a structural rewrite. "
                    "After each concrete repair, run this command inside the task "
                    "container and use its newest failures for the next repair. "
                    "Do not wait for another outer continuation to discover whether "
                    "the current workspace passes.\n\n"
                    "```bash\n"
                    f"{local_verifier}\n"
                    "```"
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
        await self._mirror_official_verifier(environment)
        local_instruction = self.logs_dir / f"instruction-{round_id}.txt"
        local_instruction.write_text(self._build_instruction(instruction), encoding="utf-8")
        remote_instruction = f"/tmp/roy-instruction-{round_id}.txt"
        remote_result = f"/tmp/roy-run-{round_id}.json"
        await environment.upload_file(local_instruction, remote_instruction)
        budget_flag = (
            f" --budget {self.token_budget}" if self.token_budget is not None else ""
        )
        external_wall_clock_ms = (
            _external_wall_clock_ms(instruction)
            if self.honor_external_deadline
            else None
        )
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
        artifact: dict[str, Any] | None = None
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
            metadata["runtime_artifact_status"] = artifact.get("status")
            metadata["runtime_error"] = artifact.get("error")
        transient_failure_handoff = bool(
            execution.return_code != 0
            and artifact
            and artifact.get("status") == "failed"
            and artifact.get("error", {}).get("retryable") is True
            and artifact.get("error", {}).get("persistedState") is True
        )
        metadata["transient_failure_handoff"] = transient_failure_handoff
        context.metadata = {**(context.metadata or {}), **metadata}

        if execution.return_code != 0 and not transient_failure_handoff:
            raise RuntimeError(
                "Roy exited with code "
                f"{execution.return_code}: {execution.stderr or execution.stdout}"
            )
        if result_download_error:
            raise RuntimeError(
                "Roy exited without a downloadable JSON run artifact: "
                f"{result_download_error}"
            )
