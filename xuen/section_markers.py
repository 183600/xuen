"""Section marker constants and regex patterns for research.md.

This module is shared between state.py (main logic) and the generated
write_section.py helper script (standalone script for external agents).
"""
from __future__ import annotations

import re

# Section names
SECTION_IDEA = "IDEA"
SECTION_ARTIFACT = "ARTIFACT"

# Raw regex pattern string for section markers.
# Used by both state.py (compiled) and the generated write_section.py (standalone).
# Pattern matches marker lines: <!-- NAME:START --> / <!-- NAME:END -->
# Must occupy a full line (allowing leading/trailing whitespace and optional BOM).
# Line boundary accepts LF, CRLF, and bare CR: re.M ^/$ only matches \n,
# so CR-only state files would make all markers unrecognizable.
_SECTION_MARKER_PATTERN = (
    r"(?m)(?:(?<=\r)|^)[ \t\ufeff]*"
    r"(<!-- (IDEA|ARTIFACT):(START|END) -->)"
    r"[ \t\ufeff]*(?=\r\n|\r|\n|$)"
)

_SECTION_MARKER = re.compile(_SECTION_MARKER_PATTERN)


def start_marker(name: str) -> str:
    """Generate the START marker for a section."""
    return f"<!-- {name}:START -->"


def end_marker(name: str) -> str:
    """Generate the END marker for a section."""
    return f"<!-- {name}:END -->"


def section_marker_pattern() -> re.Pattern:
    """Return the compiled regex for matching section markers."""
    return _SECTION_MARKER


def section_marker_pattern_string() -> str:
    """Return the raw regex pattern string (for standalone script generation)."""
    return _SECTION_MARKER_PATTERN