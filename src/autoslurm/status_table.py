"""Bounded plain-text tables over supplied cells; no selection or observations."""

import re
import os
import shutil
import sys
import unicodedata


def plain(value):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value))
    return "".join(" " if unicodedata.category(char).startswith("C") else char for char in text)


def cell_width(value):
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in "WF" else 1
               for char in plain(value))


def clipped(value, width):
    text = plain(value)
    if cell_width(text) <= width:
        return text
    result = ""
    for char in text:
        if cell_width(result + char) > width - 1:
            break
        result += char
    return result + "…" if width else ""


def table(headers, rows, *, width=None, optional=(), maximums=None, color="auto"):
    """Drop optional columns, then clip cells; each output line fits width."""
    width = width if width is not None else (shutil.get_terminal_size((120, 24)).columns if sys.stdout.isatty() else 120)
    width = max(1, width)
    maximums = maximums or {}
    columns = list(headers)
    sizes = {name: min(maximums.get(name, 40), max(cell_width(name), *(cell_width(row.get(name, "-")) for row in rows)))
             for name in columns}
    def total():
        return sum(sizes[name] for name in columns) + 2 * (len(columns) - 1)
    for name in optional:
        if total() <= width:
            break
        if name in columns:
            columns.remove(name)
    while total() > width:
        reducible = [name for name in columns if sizes[name] > min(cell_width(name), 8)]
        if not reducible:
            break
        name = max(reducible, key=lambda name: sizes[name])
        sizes[name] -= 1
    def line(row):
        cells = [clipped(row.get(name, "-"), sizes[name]) for name in columns]
        padded = [value + " " * (sizes[name] - cell_width(value)) for name, value in zip(columns, cells)]
        text = "  ".join(padded).rstrip()
        text = clipped(text, width)
        if color == "always" or (color == "auto" and sys.stdout.isatty() and "NO_COLOR" not in os.environ):
            # Only color after sizing/clipping. ANSI bytes never consume columns.
            from .status import _colorize_state_text
            if row.get("status") and "status" in columns:
                label = clipped(row["status"], sizes.get("status", 0))
                index = columns.index("status")
                position = len("  ".join(padded[:index])) + (2 if index else 0)
                if position + len(label) <= len(text):
                    colored = _colorize_state_text(row["status"]).replace(str(row["status"]), label, 1)
                    text = text[:position] + colored + text[position + len(label):]
        return text
    lines = [line({name: name for name in columns})]
    lines.extend(line(row) for row in rows)
    if columns != list(headers) or any(cell_width(row.get(name, "-")) > sizes[name] for row in rows for name in columns):
        lines.append(clipped("… abbreviated; use --details or --json for full evidence.", width))
    return "\n".join(lines)
