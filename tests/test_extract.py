"""Offline tests for the step extractor and the deterministic classifier."""

import os
import textwrap

from clinic.extract import extract_steps, load_skill
from clinic.judge import classify_with_rules

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def test_extracts_tagged_blocks_with_headings():
    md = textwrap.dedent("""\
        ---
        name: demo
        description: pip install nothing
        ---

        # Title

        ## Install

        ```bash
        pip install requests
        ```

        ## Run

        ```python
        print("not a shell step")
        ```

        ```sh
        python -c "import requests"
        ```
        """)
    steps = extract_steps(md)
    assert [s.command for s in steps] == [
        "pip install requests", 'python -c "import requests"']
    assert [s.title for s in steps] == ["Install", "Run"]


def test_strips_prompts_comments_and_keeps_multiline_blocks():
    md = textwrap.dedent("""\
        ## Setup

        ```console
        $ export FOO=1
        total 4
        $ echo done
        ```

        ```
        # this is only a comment
        mkdir -p build
        cd build
        ```
        """)
    steps = extract_steps(md)
    assert steps[0].command == "export FOO=1\necho done"   # console output dropped
    assert steps[1].command == "mkdir -p build\ncd build"  # multi-line = one step
    assert len(steps) == 2


def test_load_skill_finds_file_steps_and_scripts_dir():
    skill = load_skill(os.path.join(FIXTURES, "healthy-csv-summary"))
    assert skill["has_scripts"] is True
    assert skill["file"].endswith("SKILL.md")
    assert skill["steps"][0].command == "pip install pandas"
    assert any("summarize.py" in s.command for s in skill["steps"])


def test_max_steps_limit():
    skill = load_skill(os.path.join(FIXTURES, "stale-daytona-quickstart"), max_steps=2)
    assert len(skill["steps"]) == 2


def test_rules_classifier_categories_and_fixes():
    stale_cmd = classify_with_rules(
        "daytona sandbox create --name demo", "bash: daytona: command not found")
    assert stale_cmd["category"] == "stale_command"
    assert stale_cmd["fix_command"] == "daytona create --name demo"
    assert stale_cmd["judge"] == "rules"

    pip_flag = classify_with_rules(
        "pip install --use-feature=2020-resolver daytona",
        "option --use-feature: invalid choice: '2020-resolver'")
    assert pip_flag["category"] == "stale_command"
    assert pip_flag["fix_command"] == "pip install daytona"

    secret = classify_with_rules(
        "python -c \"...\"",
        "AssertionError: Set the DAYTONA_API_KEY environment variable")
    assert secret["category"] == "missing_secret"
    assert secret["fix_command"] is None  # never invents a credential

    assert classify_with_rules("pip install ghostpkg",
                               "ERROR: No matching distribution found for ghostpkg"
                               )["category"] == "stale_package"
    assert classify_with_rules("curl https://example.com",
                               "curl: (6) Could not resolve host: example.com"
                               )["category"] == "network_blocked"
    assert classify_with_rules("python app.py",
                               "TypeError: unsupported operand")["category"] == "bug"
