"""Run skill steps for real inside a fresh Daytona sandbox."""

from __future__ import annotations

import os
import tarfile
import tempfile
import time
from dataclasses import dataclass, field

from daytona import Daytona

REMOTE_HOME = "/home/daytona"
WORKDIR = f"{REMOTE_HOME}/skill"
MAX_OUTPUT = 4000
INFRA_EXIT_CODE = 124


class ClinicConfigError(RuntimeError):
    """Bad/missing local configuration - report it to the user, never as a traceback."""


class SandboxInfraError(RuntimeError):
    """The SDK/network failed - this says nothing about the skill step itself."""

    def __init__(self, message: str, seconds: float = 0.0):
        super().__init__(message)
        self.seconds = seconds


@dataclass
class StepResult:
    index: int
    title: str
    command: str
    exit_code: int
    output: str
    seconds: float
    status: str = "PASS"
    category: str | None = None
    explanation: str | None = None
    fix_command: str | None = None
    confidence: float | None = None
    judge: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.title,
            "command": self.command,
            "exit_code": self.exit_code,
            "status": self.status,
            "category": self.category,
            "explanation": self.explanation,
            "fix_command": self.fix_command,
            "confidence": self.confidence,
            "judge": self.judge,
            "seconds": round(self.seconds, 1),
            "output": self.output,
        }


def _tar_skill(skill_dir: str) -> str:
    """Pack the skill directory into a local tar.gz; returns the archive path."""
    fd, archive = tempfile.mkstemp(suffix=".tar.gz", prefix="skill-")
    os.close(fd)
    with tarfile.open(archive, "w:gz") as tar:
        for entry in sorted(os.listdir(skill_dir)):
            if entry in {".git", "__pycache__", ".venv", "node_modules"}:
                continue
            tar.add(os.path.join(skill_dir, entry), arcname=entry)
    return archive


def _make_client() -> Daytona:
    """Build the Daytona client, turning config problems into readable messages."""
    if not os.environ.get("DAYTONA_API_KEY"):
        raise ClinicConfigError(
            "DAYTONA_API_KEY is not set, so no sandbox can be created.\n"
            "  Put it in .env and load it:  set -a; source .env; set +a")
    try:
        return Daytona()
    except Exception as err:
        raise ClinicConfigError(
            f"could not create the Daytona client ({type(err).__name__}: {err}).\n"
            "  Check DAYTONA_API_KEY / DAYTONA_TARGET in .env, then: "
            "set -a; source .env; set +a") from err


class SkillSandbox:
    """A single Daytona sandbox with the skill directory unpacked at ~/skill."""

    def __init__(self, skill_dir: str, log=print):
        self.skill_dir = skill_dir
        self.log = log
        self.client = _make_client()
        self.sandbox = None
        self.id = "?"

    def __enter__(self) -> "SkillSandbox":
        t0 = time.time()
        self.sandbox = self.client.create()
        self.id = getattr(self.sandbox, "id", "?")
        self.log(f"  [sandbox] created {self.id} in {time.time() - t0:.1f}s")
        try:
            self._upload()
        except BaseException:
            # never leak a sandbox we already created
            self.close()
            raise
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self.sandbox is not None:
            try:
                self.sandbox.delete()
                self.log(f"  [sandbox] deleted {self.id}")
            except Exception as err:  # never mask the real failure
                self.log(f"  [sandbox] delete failed for {self.id}: {err}")
            finally:
                self.sandbox = None

    def _upload(self) -> None:
        archive = _tar_skill(self.skill_dir)
        try:
            self.sandbox.fs.upload_file(archive, "skill.tar.gz")
            res = self.sandbox.process.exec(
                f"bash -lc 'mkdir -p {WORKDIR} && tar xzf {REMOTE_HOME}/skill.tar.gz "
                f"-C {WORKDIR} && ls {WORKDIR}'",
                timeout=120,
            )
            if res.exit_code != 0:
                raise RuntimeError(f"upload/unpack failed: {res.result}")
            self.log(f"  [sandbox] skill uploaded to {WORKDIR}")
        finally:
            try:
                os.unlink(archive)
            except OSError:
                pass

    def run(self, command: str, timeout: int = 180) -> tuple[int, str, float]:
        """Run one (possibly multi-line) shell command inside the skill dir."""
        script = command.replace("'", "'\"'\"'")
        t0 = time.time()
        try:
            res = self.sandbox.process.exec(
                f"bash -lc '{script}'", cwd=WORKDIR, timeout=timeout
            )
            exit_code, output = res.exit_code, (res.result or "")
        except Exception as err:
            raise SandboxInfraError(
                f"[clinic] execution error ({type(err).__name__}): {err}",
                time.time() - t0,
            ) from err
        return exit_code, output[-MAX_OUTPUT:], time.time() - t0


def run_steps(skill_dir: str, steps, timeout: int = 180, log=print,
              label: str = "A") -> list[StepResult]:
    """Run every step sequentially in ONE sandbox (state persists between steps)."""
    results: list[StepResult] = []
    with SkillSandbox(skill_dir, log=log) as sb:
        log(f"  [sandbox {label}] running {len(steps)} step(s)")
        for step in steps:
            log(f"  [step {step.index}/{len(steps)}] {step.first_line[:70]}")
            try:
                code, out, secs = sb.run(step.command, timeout=timeout)
            except SandboxInfraError as err:
                # Infrastructure, not the skill: never judged, never counted against it.
                code, out, secs = INFRA_EXIT_CODE, str(err), err.seconds
                log(f"      -> INFRA_ERROR in {secs:.1f}s ({out[:80]})")
                results.append(StepResult(
                    index=step.index, title=step.title, command=step.command,
                    exit_code=code, output=out, seconds=secs,
                    status="INFRA_ERROR",
                ))
                continue
            log(f"      -> exit {code} in {secs:.1f}s")
            results.append(StepResult(
                index=step.index, title=step.title, command=step.command,
                exit_code=code, output=out, seconds=secs,
                status="PASS" if code == 0 else "FAIL",
            ))
    return results


def verify_fix(skill_dir: str, prior_commands: list[str], fix_command: str,
               timeout: int = 180, log=print) -> tuple[int, str, float]:
    """Replay previously-passing steps + the fix in a FRESH sandbox.

    Raises:
        SandboxInfraError: the sandbox/SDK itself failed. The caller must report the
            fix as *unverified infrastructure*, never as a failed fix - an exit code
            we made up here would be indistinguishable from the fix not working.
    """
    with SkillSandbox(skill_dir, log=log) as sb:
        for cmd in prior_commands:
            sb.run(cmd, timeout=timeout)
        log(f"      [fix] {fix_command[:70]}")
        return sb.run(fix_command, timeout=timeout)


def fresh(skill_dir: str, log=print) -> SkillSandbox:
    """Open another sandbox for re-verification (use as a context manager)."""
    return SkillSandbox(skill_dir, log=log)
