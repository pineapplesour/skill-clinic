"""A sandbox outage during --fix must never be reported as 'fix failed'."""

import json
import os

from clinic.report import INFRA_STATUS
from clinic.sandbox import SandboxInfraError, StepResult

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def test_verify_fix_lets_infra_errors_propagate(monkeypatch):
    """verify_fix must raise, not fake exit 124 (indistinguishable from a bad fix)."""
    import clinic.sandbox as sandbox

    class FakeSandbox:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, command, timeout=180):
            raise SandboxInfraError("[clinic] execution error (ReadTimeout): boom", 3.5)

    monkeypatch.setattr(sandbox, "SkillSandbox", FakeSandbox)
    try:
        sandbox.verify_fix("/tmp", [], "pip install daytona")
    except SandboxInfraError as err:
        assert err.seconds == 3.5
    else:  # pragma: no cover - the whole point of the test
        raise AssertionError("verify_fix swallowed the infrastructure error")


def test_cli_marks_unverified_fix_as_infra_error_not_failure(monkeypatch, capsys, tmp_path):
    """Phase 3: our outage is INFRA_ERROR + 'fix unverified', never 'fix failed'."""
    import clinic.cli as cli

    fabricated = [
        StepResult(index=1, title="Install", command="pip install pandas",
                   exit_code=0, output="", seconds=1.0, status="PASS"),
        StepResult(index=2, title="Create", command="daytona sandbox create --name demo",
                   exit_code=127, output="bash: daytona: command not found",
                   seconds=1.0, status="FAIL"),
    ]
    monkeypatch.setattr(cli, "run_steps", lambda *a, **kw: fabricated)

    def exploding_verify_fix(*a, **kw):
        raise SandboxInfraError("[clinic] execution error (ReadTimeout): boom", 2.0)

    monkeypatch.setattr(cli, "verify_fix", exploding_verify_fix)

    code = cli.main([os.path.join(FIXTURES, "healthy-csv-summary"), "--fix", "--no-llm",
                     "--out", str(tmp_path)])
    out = capsys.readouterr().out

    assert "fix unverified (infrastructure)" in out
    assert "fix failed" not in out
    assert code in (0, 1)  # a real verdict, not a usage/config error

    report = json.loads(next(p for p in tmp_path.iterdir() if p.suffix == ".json").read_text())
    step2 = report["steps"][1]
    assert step2["status"] == INFRA_STATUS          # excluded from the verdict
    assert step2["category"] == "stale_command"     # phase-2 diagnosis is kept
    assert "fix unverified (infrastructure)" in step2["output"]
    assert report["counts"][INFRA_STATUS] == 1
    assert "SKIP" not in report["counts"]
