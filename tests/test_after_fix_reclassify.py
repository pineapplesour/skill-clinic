"""A fix that ran and still failed gets its NEW output re-read - without moving the verdict."""

import json
import os

from clinic.sandbox import StepResult

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def test_failed_fix_is_reclassified_from_the_new_output(monkeypatch, capsys, tmp_path):
    """`missing_tool` + a working apt install that reveals the input never existed."""
    import clinic.cli as cli

    fabricated = [
        StepResult(index=1, title="Install", command="pip install pdfplumber",
                   exit_code=0, output="", seconds=1.0, status="PASS"),
        StepResult(index=2, title="Extract the text", command="pdftotext sample.pdf out.txt",
                   exit_code=127, output="bash: pdftotext: command not found",
                   seconds=1.0, status="FAIL"),
    ]
    monkeypatch.setattr(cli, "run_steps", lambda *a, **kw: fabricated)

    # The fix installed poppler-utils fine; the step now fails for a different reason.
    new_output = "I/O Error: Couldn't open file 'sample.pdf': No such file or directory."
    monkeypatch.setattr(cli, "verify_fix", lambda *a, **kw: (1, new_output, 4.0))

    code = cli.main([os.path.join(FIXTURES, "healthy-csv-summary"), "--fix", "--no-llm",
                     "--out", str(tmp_path)])
    out = capsys.readouterr().out

    assert "fix failed (exit 1) -> now: example_snippet" in out
    assert code == 1  # BROKEN: the verdict logic is untouched by the re-classification

    report = json.loads(next(p for p in tmp_path.iterdir() if p.suffix == ".json").read_text())
    step2 = report["steps"][1]
    assert step2["status"] == "FAIL"                 # never FIXED, never INFRA_ERROR
    assert step2["category"] == "missing_tool"       # the phase-2 diagnosis is kept
    assert step2["after_fix"]["category"] == "example_snippet"
    assert step2["after_fix"]["explanation"]
    assert report["verdict"] == "BROKEN"

    md = next(p for p in tmp_path.iterdir() if p.suffix == ".md").read_text()
    assert "missing_tool → example_snippet" in md

    html = next(p for p in tmp_path.iterdir() if p.suffix == ".html").read_text()
    assert "missing_tool" in html and "example_snippet" in html


def test_passing_run_records_no_after_fix(monkeypatch, tmp_path):
    """No fix attempt -> the field stays absent/None and the row renders unchanged."""
    import clinic.cli as cli
    from clinic.report import category_cell

    ok = StepResult(index=1, title="Run", command="python summary.py", exit_code=0,
                    output="ok", seconds=0.5, status="PASS")
    monkeypatch.setattr(cli, "run_steps", lambda *a, **kw: [ok])
    assert cli.main([os.path.join(FIXTURES, "healthy-csv-summary"), "--no-llm",
                     "--out", str(tmp_path)]) == 0
    assert ok.after_fix is None
    assert category_cell(ok) == "-"

    report = json.loads(next(p for p in tmp_path.iterdir() if p.suffix == ".json").read_text())
    assert report["steps"][0]["after_fix"] is None
