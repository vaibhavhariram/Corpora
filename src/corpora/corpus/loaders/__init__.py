"""Document loaders, in the priority order set by docs/architecture.md.

Markdown, plain text, XLSX/CSV, PDF. Tables come before PDF deliberately: on the prior
system half the ground truth lived in spreadsheets nobody had indexed.
"""

from .markdown import (
    MARKDOWN_LOADER,
    MARKDOWN_LOADER_VERSION,
    MARKDOWN_SUFFIXES,
    load_markdown,
    parse_headings,
)

__all__ = [
    "MARKDOWN_LOADER",
    "MARKDOWN_LOADER_VERSION",
    "MARKDOWN_SUFFIXES",
    "load_markdown",
    "parse_headings",
]
