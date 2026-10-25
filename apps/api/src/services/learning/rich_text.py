"""Factory text as LearnHouse page documents (Tiptap/ProseMirror JSON).

Lessons were stored as ``SUBTYPE_DYNAMIC_MARKDOWN`` with inline text, but that
renderer only loads a ``markdown_url``: every lesson showed "No markdown URL
configured". A ``SUBTYPE_DYNAMIC_PAGE`` document renders in the page editor and
can later carry quiz, video and checkpoint blocks.

Only the Markdown the course factory writes is supported: headings, paragraphs,
bullet and numbered lists, block quotes, and **bold**, *italic*, `code`.
Anything else stays literal text, never raw HTML.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_INLINE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)")


def _inline(text: str) -> list[dict]:
    nodes: list[dict] = []
    for part in _INLINE.split(text):
        if not part:
            continue
        mark = None
        if (part.startswith("**") and part.endswith("**")) or (
            part.startswith("__") and part.endswith("__")
        ):
            part, mark = part[2:-2], "bold"
        elif part.startswith("`") and part.endswith("`"):
            part, mark = part[1:-1], "code"
        elif len(part) > 2 and part[0] in "*_" and part[-1] == part[0]:
            part, mark = part[1:-1], "italic"
        node: dict = {"type": "text", "text": part}
        if mark:
            node["marks"] = [{"type": mark}]
        nodes.append(node)
    return nodes


def _paragraph(text: str) -> dict:
    content = _inline(text.strip())
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def _list(kind: str, items: list[str]) -> dict:
    return {
        "type": kind,
        "content": [{"type": "listItem", "content": [_paragraph(item)]} for item in items],
    }


def markdown_to_doc(markdown: str) -> dict:
    """Convert factory Markdown to a page document."""
    blocks: list[dict] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_kind = ""
    quote: list[str] = []

    def flush() -> None:
        nonlocal list_kind
        if paragraph:
            blocks.append(_paragraph(" ".join(paragraph)))
            paragraph.clear()
        if items:
            blocks.append(_list(list_kind, list(items)))
            items.clear()
            list_kind = ""
        if quote:
            blocks.append({"type": "blockquote", "content": [_paragraph(" ".join(quote))]})
            quote.clear()

    for raw in (markdown or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if heading := _HEADING.match(line):
            flush()
            level = min(len(heading.group(1)), 4)
            blocks.append(
                {"type": "heading", "attrs": {"level": level}, "content": _inline(heading.group(2))}
            )
            continue
        bullet, numbered = _BULLET.match(line), _NUMBERED.match(line)
        if bullet or numbered:
            kind = "bulletList" if bullet else "orderedList"
            if paragraph or quote or (items and list_kind != kind):
                flush()
            list_kind = kind
            items.append((bullet or numbered).group(1))
            continue
        if quoted := _QUOTE.match(line):
            if paragraph or items:
                flush()
            quote.append(quoted.group(1))
            continue
        if items:
            # A wrapped list line belongs to the last item.
            items[-1] = f"{items[-1]} {line.strip()}"
            continue
        if quote:
            flush()
        paragraph.append(line.strip())
    flush()
    return {"type": "doc", "content": blocks or [{"type": "paragraph"}]}


def task_doc(prompt: str, note: str) -> dict:
    """A practice task shown as a page: the question and where it is answered."""
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": _inline(prompt.strip())},
            {"type": "calloutInfo", "content": [{"type": "text", "text": note}]},
        ],
    }
