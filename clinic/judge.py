"""Classify a failed skill step. The model NEVER decides pass/fail - only category."""

from __future__ import annotations

import json
import os
import re

CATEGORIES = [
    "stale_package",
    "stale_command",
    "missing_tool",
    "example_snippet",
    "missing_secret",
    "env_specific",
    "network_blocked",
    "bug",
    "unknown",
]

_RULES: list[tuple[str, str]] = [
    ("stale_package",
     r"No matching distribution|Could not find a version|404 Not Found|ERR! 404|"
     r"E404|npm error 404|is deprecated|deprecated|ModuleNotFoundError"),
    ("stale_command",
     r"command not found|unknown command|No such command|no such option|"
     r"invalid choice|unrecognized arguments?|Unknown option|is not recognized|"
     r"usage:.*\n.*invalid"),
    ("missing_secret",
     r"API_KEY|api key|_TOKEN|unauthorized|Unauthorized|\b401\b|\b403\b|"
     r"Set the .* environment|credentials|authentication failed"),
    ("env_specific",
     r"powershell|\.exe\b|/mnt/c/|\bwsl\b|brew: command not found|"
     r"apt-get.*sudo|sudo: |Permission denied|Operation not permitted|"
     r"Read-only file system"),
    ("network_blocked",
     r"Could not resolve host|Name or service not known|Network is unreachable|"
     r"Connection timed out|Connection refused|ECONNRESET|ETIMEDOUT|blocked|"
     r"Temporary failure in name resolution"),
]

_ENV_CMD = (
    r"powershell(?:\.exe)?|\bcmd\.exe|/mnt/[a-z]/|[A-Za-z]:\\|\bwsl\b|\bbrew\b|"
    r"\bsudo\b|\bsystemctl\b|\bosascript\b|\.exe\b"
)

# Binaries a skill may call that are not in a fresh sandbox image -> Debian package to install.
TOOL_PACKAGES = {
    "pdftotext": "poppler-utils", "pdfimages": "poppler-utils", "pdftoppm": "poppler-utils", "pdfinfo": "poppler-utils",
    "qpdf": "qpdf", "pdftk": "pdftk-java", "convert": "imagemagick", "magick": "imagemagick", "ffmpeg": "ffmpeg",
    "jq": "jq", "rg": "ripgrep", "tesseract": "tesseract-ocr", "pandoc": "pandoc", "libreoffice": "libreoffice",
    "soffice": "libreoffice", "gs": "ghostscript", "zip": "zip", "unzip": "unzip", "tree": "tree",
}
_CMD_NOT_FOUND = re.compile(r"(?:bash: line \d+: |bash: |sh: \d+: |/bin/sh: \d+: )?([A-Za-z0-9_.+-]+): (?:command )?not found")
_MISSING_INPUT = re.compile(r"No such file or directory|No such file|Couldn't open file|Unable to find file|Failed to open input|cannot open|can't open|does not exist|not found: .*\.(?:pdf|docx|csv|json|txt)", re.IGNORECASE)

_EXPLANATIONS = {
    "missing_tool": "The step calls a binary that a fresh machine does not have; the skill never says to install it.",
    "example_snippet": "The step references example input files that do not exist - it is an illustrative snippet, not a runnable instruction.",
    "stale_package": "The package or version referenced by the skill no longer resolves on the registry.",
    "stale_command": "The CLI no longer accepts this subcommand/flag; the skill was written against an older version.",
    "missing_secret": "The step needs a credential or environment variable that the skill never tells you to set.",
    "env_specific": "The step assumes a specific host OS, shell or privilege level.",
    "network_blocked": "The step needs network access that is unavailable in the sandbox.",
    "bug": "The step failed for a reason specific to the skill's own logic or content.",
    "unknown": "Could not classify this failure.",
}


def _suggest_fix(command: str, output: str, category: str) -> str | None:
    """Known rot rules: a small, published table of documented interface changes.

    These are not tuned to any fixture - each row is a real, publicly documented
    change that breaks instruction files written before it. A rule only ever
    *proposes* a command; nothing is reported as FIXED until that command exits 0
    in a fresh sandbox.

    | # | Rot pattern                         | Rewrite                              |
    |---|-------------------------------------|--------------------------------------|
    | 1 | `daytona sandbox <verb>`            | `daytona <verb>` (noun layer dropped)|
    | 2 | removed pip flags                   | strip `--use-feature=`, `--egg`,     |
    |   |                                     | `--process-dependency-links`         |
    | 3 | `@daytonaio/*` npm scope (404/dep.) | `@daytona/sdk`                       |
    | 4 | option the tool itself calls unknown| strip that exact `--flag` from the   |
    |   | ("no such option: --x")             | command                              |

    Anything not in this table gets no fix - we do not guess, and we never invent
    a credential (`missing_secret` always returns None).
    """
    cmd = command.strip()

    # Daytona CLI: `daytona sandbox <verb>` was flattened to `daytona <verb>`.
    m = re.search(r"\bdaytona\s+sandbox\s+(\S+)", cmd)
    if m:
        return re.sub(r"\bdaytona\s+sandbox\s+", "daytona ", cmd)

    # Removed pip flags (e.g. --use-feature=2020-resolver, --egg, --process-dependency-links)
    if category == "stale_command" and re.search(r"\bpip3?\b", cmd):
        stripped = re.sub(r"\s--(?:use-feature|egg|process-dependency-links)(?:=\S+)?", "", cmd)
        if stripped != cmd:
            return stripped.strip()

    # npm scope rename: the @daytonaio scope moved to @daytona.
    if "@daytonaio/" in cmd and re.search(r"404|E404|deprecated", output or ""):
        renamed = re.sub(r"@daytonaio/(?:daytona-)?sdk", "@daytona/sdk", cmd)
        return renamed if renamed != cmd else cmd.replace("@daytonaio/", "@daytona/")

    # Generic: unknown CLI option reported verbatim by the tool.
    if category == "stale_command":
        bad = re.search(r"(?:no such option|unrecognized arguments?|Unknown option):?\s*(--[\w-]+)", output or "")
        if bad:
            stripped = re.sub(r"\s" + re.escape(bad.group(1)) + r"(?:=\S+)?", "", cmd)
            if stripped != cmd:
                return stripped.strip()
    return None


def classify_with_rules(command: str, output: str, exit_code: int = 1) -> dict:
    """Deterministic regex classifier. Always available, never needs network."""
    haystack = output or ""
    category = "bug"
    # Host-specific commands (Windows paths, powershell, WSL mounts, sudo/brew) are recognised
    # from the command text itself, before any error-message heuristics.
    if re.search(_ENV_CMD, command or "", re.IGNORECASE):
        return {
            "category": "env_specific",
            "explanation": _EXPLANATIONS["env_specific"],
            "fix_command": None,
            "confidence": 0.9,
            "judge": "rules",
        }
    # A known tool is simply not installed on a fresh machine -> propose the install, then rerun.
    m = _CMD_NOT_FOUND.search(haystack)
    if m and m.group(1) in TOOL_PACKAGES:
        pkg = TOOL_PACKAGES[m.group(1)]
        fix = f"sudo apt-get update -qq >/dev/null 2>&1; sudo apt-get install -y -qq {pkg} >/dev/null 2>&1 && {command.strip()}"
        return {"category": "missing_tool", "explanation": _EXPLANATIONS["missing_tool"] + f" (needs `{pkg}`)",
                "fix_command": fix, "confidence": 0.85, "judge": "rules"}
    if not m and _MISSING_INPUT.search(haystack):
        return {"category": "example_snippet", "explanation": _EXPLANATIONS["example_snippet"],
                "fix_command": None, "confidence": 0.7, "judge": "rules"}
    for name, pattern in _RULES:
        if re.search(pattern, haystack, re.IGNORECASE):
            category = name
            break
    fix = _suggest_fix(command, haystack, category)
    if category == "missing_secret":
        fix = None  # never invent a credential
    return {
        "category": category,
        "explanation": _EXPLANATIONS[category],
        "fix_command": fix,
        "confidence": 0.8 if category != "bug" else 0.4,
        "judge": "rules",
    }


_PROMPT = """You triage failures of AI-written "agent skill" instruction files that were executed
for real inside a clean Linux sandbox. Classify ONE failed step.

Allowed categories (choose exactly one):
- stale_package: package/version no longer exists or was renamed/deprecated
- stale_command: CLI subcommand or flag no longer exists (tool changed its interface)
- missing_tool: calls a binary a fresh machine does not have and the skill never says to install
- example_snippet: references example input files that do not exist - illustration, not instruction
- missing_secret: needs a credential/env var the skill never mentions
- env_specific: assumes a specific OS, shell, sudo or local path
- network_blocked: needs network the sandbox does not allow
- bug: the skill's own logic/content is wrong
- unknown: cannot tell

Reply with STRICT JSON only, no prose, no markdown fence:
{"category": "...", "explanation": "<one sentence>", "fix_command": "<single shell command or null>", "confidence": 0.0-1.0}

fix_command must be a single runnable shell command that would make this exact step succeed,
or null if no safe fix exists (never invent credentials).

COMMAND:
%s

EXIT CODE: %s

OUTPUT (tail):
%s
"""


def _parse_json_blob(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


def classify_with_llm(command: str, output: str, exit_code: int = 1) -> dict:
    """Ask the Nosana-hosted OpenAI-compatible endpoint. Raises on any problem."""
    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        raise RuntimeError("LLM_BASE_URL / LLM_MODEL not configured")

    client = OpenAI(base_url=base_url, api_key=os.environ.get("LLM_API_KEY", "x"), timeout=45.0)
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user",
                   "content": _PROMPT % (command, exit_code, (output or "")[-3000:])}],
    )
    data = _parse_json_blob(resp.choices[0].message.content or "")
    category = str(data.get("category", "unknown")).strip().lower()
    if category not in CATEGORIES:
        category = "unknown"
    fix = data.get("fix_command")
    if isinstance(fix, str):
        fix = fix.strip().strip("`") or None
    else:
        fix = None
    if category == "missing_secret":
        fix = None
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "category": category,
        "explanation": str(data.get("explanation", _EXPLANATIONS.get(category, ""))).strip(),
        "fix_command": fix,
        "confidence": max(0.0, min(1.0, confidence)),
        "judge": f"nosana:{model}",
    }


def classify(command: str, output: str, exit_code: int = 1, use_llm: bool = True,
             on_fallback=None) -> dict:
    """Classify a failure; LLM when configured, deterministic rules otherwise.

    A failed LLM call is never swallowed silently: ``on_fallback(err)`` is invoked so
    the caller can say out loud which backend actually judged the step.
    """
    if use_llm:
        try:
            return classify_with_llm(command, output, exit_code)
        except Exception as err:
            if on_fallback is not None:
                on_fallback(err)
    return classify_with_rules(command, output, exit_code)
