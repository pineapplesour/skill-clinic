"""Extract runnable shell steps out of a SKILL.md / README.md instruction file."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

SHELL_LANGS = {"bash", "sh", "shell", "console", "zsh", "shell-session", "terminal"}

_FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([A-Za-z0-9_.+-]*)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_PROMPT_RE = re.compile(r"^\s*(?:\$|>|#\s*\$)\s+")

# First tokens that make an untagged block look like a shell block.
_COMMAND_WORDS = {
    "pip", "pip3", "python", "python3", "npm", "npx", "node", "yarn", "pnpm",
    "bash", "sh", "zsh", "cd", "ls", "cat", "echo", "curl", "wget", "git",
    "mkdir", "rm", "cp", "mv", "export", "source", "apt", "apt-get", "brew",
    "sudo", "make", "docker", "chmod", "tar", "unzip", "pytest", "uv", "uvx",
    "daytona", "nosana", "go", "cargo", "rustup", "java", "mvn", "gradle",
    "poetry", "conda", "ollama", "helm", "kubectl", "terraform", "aws", "gcloud",
}


@dataclass
class Step:
    """One runnable step lifted from the skill document."""

    index: int
    title: str
    command: str
    lang: str

    @property
    def first_line(self) -> str:
        return self.command.splitlines()[0] if self.command else ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.title,
            "command": self.command,
            "lang": self.lang,
        }


def _looks_like_command(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _PROMPT_RE.match(line):
        return True
    head = stripped.split()[0]
    head = head.split("=")[0] if "=" in head and " " not in head else head
    return head in _COMMAND_WORDS


def _clean_block(lines: list[str]) -> str:
    """Strip prompts / console output / pure comments; keep the rest as one step."""
    prompted = [ln for ln in lines if _PROMPT_RE.match(ln)]
    if prompted:
        # A console transcript: only prompt lines are input, the rest is output.
        lines = prompted
    out: list[str] = []
    for raw in lines:
        line = _PROMPT_RE.sub("", raw).rstrip()
        if not line.strip():
            continue
        if line.strip().startswith("#"):  # pure comment line
            continue
        out.append(line)
    return "\n".join(out).strip()


def extract_steps(markdown: str, max_steps: int | None = None) -> list[Step]:
    """Return the ordered runnable steps found in a markdown instruction file."""
    steps: list[Step] = []
    heading = "Setup"
    lines = markdown.splitlines()
    i = 0
    in_frontmatter = False
    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        i = 1

    while i < len(lines):
        line = lines[i]
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            i += 1
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            heading = heading_match.group(2).strip()
            i += 1
            continue

        fence = _FENCE_RE.match(line)
        if not fence:
            i += 1
            continue

        marker, lang = fence.group(2), fence.group(3).lower()
        body: list[str] = []
        i += 1
        while i < len(lines):
            closing = _FENCE_RE.match(lines[i])
            if closing and closing.group(2)[0] == marker[0] and not closing.group(3):
                break
            body.append(lines[i])
            i += 1
        i += 1  # skip closing fence

        if lang and lang not in SHELL_LANGS:
            continue
        if not lang and not any(_looks_like_command(b) for b in body):
            continue

        command = _clean_block(body)
        if not command:
            continue
        steps.append(Step(index=len(steps) + 1, title=heading, command=command,
                          lang=lang or "bash"))
        if max_steps and len(steps) >= max_steps:
            break

    return steps


def load_skill(path: str, max_steps: int | None = None) -> dict:
    """Resolve a skill dir or file into {dir, file, name, steps, has_scripts}."""
    path = os.path.abspath(path)
    if os.path.isdir(path):
        skill_dir = path
        skill_file = None
        for candidate in ("SKILL.md", "skill.md", "README.md", "readme.md"):
            full = os.path.join(path, candidate)
            if os.path.isfile(full):
                skill_file = full
                break
        if skill_file is None:
            raise FileNotFoundError(f"No SKILL.md or README.md found in {path}")
    else:
        skill_file = path
        skill_dir = os.path.dirname(path)

    with open(skill_file, "r", encoding="utf-8") as fh:
        text = fh.read()

    return {
        "dir": skill_dir,
        "file": skill_file,
        "name": os.path.basename(skill_dir.rstrip("/")) or "skill",
        "steps": extract_steps(text, max_steps=max_steps),
        "has_scripts": os.path.isdir(os.path.join(skill_dir, "scripts")),
    }
