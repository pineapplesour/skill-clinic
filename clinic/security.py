"""Behaviour observation for prompt-injected skills.

Static review misses hidden instructions inside a SKILL.md. Skill Clinic already
runs every step for real in a throwaway Daytona sandbox where arbitrary egress is
blocked, so instead of guessing we can *execute* the injected command and report
what the skill actually tried to do.

Two halves:

* :func:`flag_command` - regex rules over the command text (intent).
* :func:`observe_output` - what the sandbox did about it (evidence).

Nothing here touches the verdict: a finding is an observation, not a failure.
"""

from __future__ import annotations

import re

SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "info": 0}

#: Hosts a normal skill legitimately talks to; anything else in a curl/wget is
#: only worth a low-severity note, never a high one.
KNOWN_HOSTS = (
    "pypi.org", "files.pythonhosted.org", "pythonhosted.org",
    "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com",
    "registry.npmjs.org", "npmjs.com", "nodejs.org", "golang.org", "crates.io",
    "docker.io", "ubuntu.com", "debian.org", "localhost", "127.0.0.1",
    "huggingface.co", "anthropic.com", "example.com",
)

_NET = r"(?:curl|wget|nc|ncat|netcat|ssh|scp|telnet)"
_SECRETS = r"(?:~/\.ssh|/\.ssh/|\.aws/credentials|~/\.aws|id_rsa|id_ed25519|/etc/passwd|/etc/shadow|\.env\b|\.npmrc|\.netrc|\.git-credentials)"

#: (rule, severity, pattern, note)
RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    ("remote_code_exec", "high",
     re.compile(rf"(?:curl|wget)\b[^|;&\n]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b", re.I),
     "downloads a remote script and pipes it straight into a shell"),
    ("remote_code_exec", "high",
     re.compile(r"python3?\s+-c\s*['\"][^'\"]*(?:urllib|requests|socket|urlopen)", re.I),
     "inline python that fetches and runs remote content"),
    ("credential_exfil", "high",
     re.compile(rf"(?:cat|head|tail|tar|cp|base64|gpg)\b[^\n]*{_SECRETS}[^\n]*[|;&][^\n]*{_NET}", re.I),
     "reads a credential/secret file and sends it off the machine"),
    ("credential_exfil", "high",
     re.compile(rf"(?:printenv|env)\b[^\n]*\|[^\n]*(?:{_NET}|base64[^\n]*\|[^\n]*{_NET})", re.I),
     "dumps the environment (API keys) into a network client"),
    ("credential_access", "medium",
     re.compile(rf"(?:cat|head|tail|less|cp|tar|base64)\b[^\n]*{_SECRETS}", re.I),
     "reads private keys / credentials the skill has no reason to read"),
    ("obfuscation", "high",
     re.compile(r"base64\s+(?:-d|-D|--decode)[^\n]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", re.I),
     "base64-decoded payload executed as a shell script"),
    ("obfuscation", "high",
     re.compile(r"eval\s+[\"']?\$\(", re.I),
     "eval of a dynamically produced string"),
    ("persistence", "medium",
     re.compile(r">>\s*(?:~|\$HOME|/root|/home/[^/\s]+)?/?\.(?:bashrc|bash_profile|profile|zshrc|zprofile)", re.I),
     "appends to a shell startup file so it runs again after the sandbox"),
    ("persistence", "medium",
     re.compile(r"\bcrontab\b|/etc/cron|systemctl\s+enable", re.I),
     "installs a scheduled/boot-time job"),
    ("destructive", "high",
     re.compile(r"rm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*\s+)+(?:--no-preserve-root\s+)?(?:/|~|\$HOME)\s*(?:$|[;&|])"),
     "recursive delete of the home directory or filesystem root"),
]

_URL_RE = re.compile(r"(?:curl|wget)\b[^\n]*?(?:https?://|\s)((?:\d{1,3}(?:\.\d{1,3}){3}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?::\d+)?)", re.I)
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

_EGRESS_BLOCKED = re.compile(
    r"Could not resolve host|Connection refused|Network is unreachable|"
    r"Temporary failure in name resolution|blocked|No route to host|"
    r"Failed to connect|Connection timed out", re.I)
_NO_SECRET = re.compile(
    r"No such file or directory[^\n]*|[^\n]*No such file or directory", re.I)
_SECRET_MENTION = re.compile(r"\.ssh|id_rsa|id_ed25519|\.aws|\.env\b|credentials", re.I)


def _evidence(text: str, match: re.Match[str], width: int = 120) -> str:
    """The matching line, trimmed - enough to show a human what fired."""
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    line = text[start: end if end != -1 else len(text)].strip()
    return line if len(line) <= width else line[: width - 1] + "…"


def _add(findings: list[dict], rule: str, severity: str, evidence: str, note: str) -> None:
    for existing in findings:
        if existing["rule"] == rule and existing["evidence"] == evidence:
            return
    findings.append({"rule": rule, "severity": severity, "evidence": evidence, "note": note})


def flag_command(command: str) -> list[dict]:
    """Return ``{rule, severity, evidence, note}`` findings for one step's command."""
    findings: list[dict] = []
    if not command:
        return findings
    for rule, severity, pattern, note in RULES:
        for match in pattern.finditer(command):
            _add(findings, rule, severity, _evidence(command, match), note)
    for match in _URL_RE.finditer(command):
        host = match.group(1).split(":")[0].lower()
        if any(host == known or host.endswith("." + known) for known in KNOWN_HOSTS):
            continue
        kind = "raw IP address" if _IP_RE.match(host) else "unrecognised domain"
        _add(findings, "suspicious_egress", "low", _evidence(command, match),
             f"outbound request to {kind} `{host}`")
    exfil = {f["evidence"] for f in findings if f["rule"] == "credential_exfil"}
    findings = [f for f in findings
                if not (f["rule"] == "credential_access" and f["evidence"] in exfil)]
    return sorted(findings, key=lambda f: -SEVERITY_ORDER[f["severity"]])


def observe_output(output: str) -> list[dict]:
    """Turn what the sandbox actually did into findings (the behaviour half)."""
    findings: list[dict] = []
    if not output:
        return findings
    match = _EGRESS_BLOCKED.search(output)
    if match:
        _add(findings, "egress_blocked", "info", _evidence(output, match),
             "the sandbox network policy stopped the outbound attempt")
    for line in output.splitlines():
        if "No such file" in line and _SECRET_MENTION.search(line):
            _add(findings, "no_secret_present", "info", line.strip()[:120],
                 "nothing to steal: the throwaway sandbox holds no real credentials")
            break
    return findings


def analyse(command: str, output: str) -> list[dict]:
    """Findings for one step: intent (command) + evidence (sandbox output)."""
    intent = flag_command(command)
    return intent + (observe_output(output) if intent else [])


def counts(findings) -> dict:
    """``{"high": n, "medium": m, ...}`` over a flat list or a list of step rows."""
    tally: dict[str, int] = {}
    for finding in findings:
        tally[finding["severity"]] = tally.get(finding["severity"], 0) + 1
    return tally


def summarize(results) -> dict:
    """Aggregate ``StepResult.security`` (or report dict rows) across all steps."""
    flat = []
    for row in results:
        found = row.get("security") if isinstance(row, dict) else getattr(row, "security", None)
        flat.extend(found or [])
    tally = counts(flat)
    return {
        "high": tally.get("high", 0),
        "medium": tally.get("medium", 0),
        "low": tally.get("low", 0),
        "info": tally.get("info", 0),
        "suspicious": tally.get("high", 0) + tally.get("medium", 0) > 0,
    }


def headline(results) -> tuple[str, str]:
    """``("SECURITY: SUSPICIOUS (2 high)", "bold red")`` or ``("SECURITY: clean", ...)``."""
    s = summarize(results)
    if s["high"]:
        return f"SECURITY: SUSPICIOUS ({s['high']} high)", "bold red"
    if s["medium"]:
        return f"SECURITY: SUSPICIOUS ({s['medium']} medium)", "bold yellow"
    if s["low"]:
        return f"SECURITY: {s['low']} low-severity note(s)", "yellow"
    return "SECURITY: clean", "green"
