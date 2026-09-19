#!/usr/bin/env python3
"""Root shim: python clinic.py <skill-dir-or-SKILL.md> [--fix] ..."""

import sys

from clinic.cli import main

if __name__ == "__main__":
    sys.exit(main())
