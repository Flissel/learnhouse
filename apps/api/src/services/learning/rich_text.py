"""Factory text as LearnHouse page documents (Tiptap/ProseMirror JSON).

Lessons were stored as ``SUBTYPE_DYNAMIC_MARKDOWN`` with inline text, but that
renderer only loads a ``markdown_url``: every lesson showed "No markdown URL
configured". A ``SUBTYPE_DYNAMIC_PAGE`` document renders in the page editor and
can later carry quiz, video and checkpoint blocks.

Only the Markdown the course factory writes is supported: headings, paragraphs,
bullet and numbered lists, block quotes, fenced code blocks, and **bold**, *italic*, `code`,
plus, only with ``math=True`` (math courses), formulas: ``$...$`` in a sentence and ``$$...$$``
on its own line(s) (rendered by KaTeX). A lone or currency ``$`` stays text, ``\\$`` is a literal
dollar sign. Without ``math`` the output is exactly that of the converter before formulas, so
Terminal lessons keep ``$env:Path`` and ``$HOME`` as text.
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
_MATH_SPLIT = re.compile(r"(`[^`]+`|(?<![\\$])\$(?![\s$])[^$\n]+?(?<![\s\\])\$(?![\d$]))")
_BLOCK_MATH = re.compile(r"^\$\$\s*(.+?)\s*\$\$$")
# A formula is swapped for a placeholder while emphasis is parsed, so ``**a $x$ b**`` stays one
# bold span; the placeholder is cut back into a formula node between the marked text runs.
_HOLDER = re.compile("\ue000(\\d+)\ue001")


def _inline(text: str, math: bool = False) -> list[dict]:
    if not math:
        return _emphasis(text, unescape=False)
    formulas: list[str] = []
    parts: list[str] = []
    for index, chunk in enumerate(_MATH_SPLIT.split(text.replace("\ue000", "").replace("\ue001", ""))):
        if index % 2 and chunk[0] == "$":
            parts.append(f"\ue000{len(formulas)}\ue001")
            formulas.append(chunk[1:-1].strip())
        else:
            parts.append(chunk)
    nodes: list[dict] = []
    for node in _emphasis("".join(parts)):
        if "\ue000" not in node["text"]:
            nodes.append(node)
            continue
        for position, piece in enumerate(_HOLDER.split(node["text"])):
            if position % 2:
                nodes.append(
                    {"type": "inlineMathEquation", "attrs": {"math_equation": formulas[int(piece)]}}
                )
            elif piece:
                nodes.append({**node, "text": piece})
    return nodes


def _emphasis(text: str, unescape: bool = True) -> list[dict]:
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
        if unescape and mark != "code":
            part = part.replace("\\$", "$")
        node: dict = {"type": "text", "text": part}
        if mark:
            node["marks"] = [{"type": mark}]
        nodes.append(node)
    return nodes


def _display(text: str) -> dict | None:
    if (block := _BLOCK_MATH.match(text.strip())) and "$$" not in block.group(1):
        return {"type": "blockMathEquation", "attrs": {"math_equation": block.group(1)}}
    return None


def _paragraph(text: str, math: bool = False) -> dict:
    if math and (block := _display(text)):
        return block
    content = _inline(text.strip(), math)
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def _list(kind: str, items: list[str], math: bool = False) -> dict:
    return {
        "type": kind,
        "content": [{"type": "listItem", "content": [_paragraph(item, math)]} for item in items],
    }


def markdown_to_doc(markdown: str, math: bool = False) -> dict:
    """Convert factory Markdown to a page document; ``math`` typesets formulas."""
    blocks: list[dict] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_kind = ""
    quote: list[str] = []
    code: list[str] | None = None
    language: str | None = None
    # Lines of a display formula spread over several lines, from ``$$`` to ``$$`` (math only).
    display: list[str] | None = None

    def code_block() -> dict:
        text = "\n".join(code or [])
        block: dict = {"type": "codeBlock", "attrs": {"language": language}}
        if text:
            block["content"] = [{"type": "text", "text": text}]
        return block

    def flush() -> None:
        nonlocal list_kind
        if paragraph:
            blocks.append(_paragraph(" ".join(paragraph), math))
            paragraph.clear()
        if items:
            blocks.append(_list(list_kind, list(items), math))
            items.clear()
            list_kind = ""
        if quote:
            blocks.append({"type": "blockquote", "content": [_paragraph(" ".join(quote), math)]})
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
        stripped = line.strip()
        if display is not None:
            if not stripped:  # never closed: the lines stay text
                blocks.append(_paragraph(" ".join(display), math))
                display = None
                continue
            display.append(stripped)
            if stripped.endswith("$$"):
                joined = " ".join(display)
                blocks.append(_display(joined) or _paragraph(joined, math))
                display = None
            continue
        if math and stripped.startswith("$$"):
            # Ruling 7: a display formula on its own line(s) is its own block, blank lines or not.
            if block := _display(stripped):
                flush()
                blocks.append(block)
                continue
            if stripped == "$$" or not stripped.endswith("$$"):
                flush()
                display = [stripped]
                continue
        if not stripped:
            flush()
            continue
        if heading := _HEADING.match(line):
            flush()
            level = min(len(heading.group(1)), 4)
            blocks.append(
                {"type": "heading", "attrs": {"level": level}, "content": _inline(heading.group(2), math)}
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
    if display is not None:
        blocks.append(_paragraph(" ".join(display), math))
    if code is not None:
        blocks.append(code_block())
    return {"type": "doc", "content": blocks or [{"type": "paragraph"}]}


def lesson_doc(markdown: str, key_facts: list[str], math: bool = False) -> dict:
    """A lesson page: the lesson text, then its key facts (the factory's claims) as a list."""
    doc = markdown_to_doc(markdown, math)
    facts = [fact.strip() for fact in key_facts if fact.strip()]
    if facts:
        doc["content"] = [
            *doc["content"],
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": _KEY_FACTS}]},
            _list("bulletList", facts, math),
        ]
    return doc


def task_doc(prompt: str, note: str, math: bool = False) -> dict:
    """A practice task shown as a page: the question and where it is answered."""
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": _inline(prompt.strip(), math)},
            {"type": "calloutInfo", "content": [{"type": "text", "text": note}]},
        ],
    }
