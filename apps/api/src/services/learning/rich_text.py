"""Factory text as LearnHouse page documents (Tiptap/ProseMirror JSON).

Lessons were stored as ``SUBTYPE_DYNAMIC_MARKDOWN`` with inline text, but that
renderer only loads a ``markdown_url``: every lesson showed "No markdown URL
configured". A ``SUBTYPE_DYNAMIC_PAGE`` document renders in the page editor and
can later carry quiz, video and checkpoint blocks.

Only the Markdown the course factory writes is supported: headings, paragraphs,
bullet and numbered lists, block quotes, fenced code blocks, and **bold**, *italic*, `code`,
plus formulas: ``$...$`` in a sentence and a paragraph of only ``$$...$$`` (rendered by KaTeX).
A lone or currency ``$`` stays text, ``\\$`` is a literal dollar sign.
Anything else stays literal text, never raw HTML.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_FENCE = re.compile(r"^\s*```\s*([A-Za-z0-9_+-]*)\s*$")
_KEY_FACTS = "Das Wichtigste in Kürze"
_INLINE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)")
# `code` spans first (so a ``$`` in code stays code), then ``$formula$``: the opener is not
# followed by a space, the closer is not preceded by one nor followed by a digit ("5 $ and 6 $").
_MATH_SPLIT = re.compile(r"(`[^`]+`|(?<![\$])\$(?![\s$])[^$\n]+?(?<![\s\\])\$(?![\d$]))")
_BLOCK_MATH = re.compile(r"^\$\$\s*(.+?)\s*\$\$$")


def _inline(text: str) -> list[dict]:
    nodes: list[dict] = []
    for chunk in _MATH_SPLIT.split(text):
        if not chunk:
            continue
        if len(chunk) > 2 and chunk[0] == chunk[-1] == "$":
            nodes.append({"type": "inlineMathEquation", "attrs": {"math_equation": chunk[1:-1].strip()}})
        else:
            nodes.extend(_emphasis(chunk))
    return nodes


def _emphasis(text: str) -> list[dict]:
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
        if mark != "code":
            part = part.replace("\\$", "$")
        node: dict = {"type": "text", "text": part}
        if mark:
            node["marks"] = [{"type": mark}]
        nodes.append(node)
    return nodes


def _paragraph(text: str) -> dict:
    if (block := _BLOCK_MATH.match(text.strip())) and "$$" not in block.group(1):
        return {"type": "blockMathEquation", "attrs": {"math_equation": block.group(1)}}
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
    code: list[str] | None = None
    language: str | None = None

    def code_block() -> dict:
        text = "\n".join(code or [])
        block: dict = {"type": "codeBlock", "attrs": {"language": language}}
        if text:
            block["content"] = [{"type": "text", "text": text}]
        return block

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
        fence = _FENCE.match(line)
        if code is not None:
            # Inside a fence every line is kept verbatim, blank lines included.
            if fence and not fence.group(1):
                blocks.append(code_block())
                code, language = None, None
            else:
                code.append(line)
            continue
        if fence:
            flush()
            code, language = [], fence.group(1) or None
            continue
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
    if code is not None:
        blocks.append(code_block())
    return {"type": "doc", "content": blocks or [{"type": "paragraph"}]}


def lesson_doc(markdown: str, key_facts: list[str]) -> dict:
    """A lesson page: the lesson text, then its key facts (the factory's claims) as a list."""
    doc = markdown_to_doc(markdown)
    facts = [fact.strip() for fact in key_facts if fact.strip()]
    if facts:
        doc["content"] = [
            *doc["content"],
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": _KEY_FACTS}]},
            _list("bulletList", facts),
        ]
    return doc


def task_doc(prompt: str, note: str) -> dict:
    """A practice task shown as a page: the question and where it is answered."""
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": _inline(prompt.strip())},
            {"type": "calloutInfo", "content": [{"type": "text", "text": note}]},
        ],
    }
