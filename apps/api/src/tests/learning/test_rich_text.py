from src.services.learning.rich_text import markdown_to_doc, task_doc


def test_factory_markdown_becomes_page_blocks() -> None:
    doc = markdown_to_doc(
        "# Akku sicher nutzen\n\nDieser Abschnitt ist **wichtig** und *kurz*.\n\n"
        "- Vor der Arbeit\n- Während der Arbeit\n  mit Schutzbrille\n\n"
        "1. Prüfen\n2. Laden\n\n> Nie beschädigte Akkus laden."
    )

    kinds = [block["type"] for block in doc["content"]]
    assert doc["type"] == "doc"
    assert kinds == ["heading", "paragraph", "bulletList", "orderedList", "blockquote"]
    assert doc["content"][0]["attrs"] == {"level": 1}
    marks = [n.get("marks", [{}])[0].get("type") for n in doc["content"][1]["content"]]
    assert "bold" in marks and "italic" in marks
    second_item = doc["content"][2]["content"][1]["content"][0]["content"][0]["text"]
    assert second_item == "Während der Arbeit mit Schutzbrille"


def test_html_stays_text_and_empty_input_is_a_valid_doc() -> None:
    doc = markdown_to_doc("<script>alert(1)</script>")
    assert doc["content"][0]["content"][0]["text"] == "<script>alert(1)</script>"
    assert markdown_to_doc("") == {"type": "doc", "content": [{"type": "paragraph"}]}


def test_task_page_shows_question_and_note() -> None:
    doc = task_doc("Welche Frage zuerst?", "Hier üben.")
    assert doc["content"][0]["type"] == "heading"
    assert doc["content"][1] == {"type": "calloutInfo", "content": [{"type": "text", "text": "Hier üben."}]}


def test_fenced_commands_become_code_blocks_kept_verbatim() -> None:
    # 27.10.: lessons now show every command in a fenced block; as paragraphs the
    # backticks and the language tag were shown, and the line breaks were lost.
    doc = markdown_to_doc(
        "Fügen Sie diesen Befehl ein:\n\n```powershell\nirm https://claude.ai/install.ps1 | iex\n```\n\n"
        "Für Bash:\n```bash\necho 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc\nsource ~/.bashrc\n```"
    )

    kinds = [block["type"] for block in doc["content"]]
    assert kinds == ["paragraph", "codeBlock", "paragraph", "codeBlock"]
    assert doc["content"][1]["attrs"] == {"language": "powershell"}
    assert doc["content"][1]["content"] == [{"type": "text", "text": "irm https://claude.ai/install.ps1 | iex"}]
    assert doc["content"][3]["content"][0]["text"] == (
        "echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc\nsource ~/.bashrc"
    )


def test_an_unclosed_fence_still_ends_as_a_code_block() -> None:
    doc = markdown_to_doc("```\nclaude --version")
    assert doc["content"] == [
        {"type": "codeBlock", "attrs": {"language": None}, "content": [{"type": "text", "text": "claude --version"}]}
    ]


def test_a_lesson_page_ends_with_its_key_facts() -> None:
    from src.services.learning.rich_text import lesson_doc

    doc = lesson_doc("Text der Lektion.", ["Erster Fakt.", "Zweiter Fakt mit `claude doctor`."])

    kinds = [block["type"] for block in doc["content"]]
    assert kinds == ["paragraph", "heading", "bulletList"]
    assert doc["content"][1]["content"][0]["text"] == "Das Wichtigste in Kürze"
    assert len(doc["content"][2]["content"]) == 2
    assert lesson_doc("Nur Text.", [])["content"] == markdown_to_doc("Nur Text.")["content"]


def test_display_formula_paragraph_becomes_block_math() -> None:
    doc = markdown_to_doc("$$f(x)=x^2$$")
    assert doc["content"] == [{"type": "blockMathEquation", "attrs": {"math_equation": "f(x)=x^2"}}]
    multi = markdown_to_doc("$$\n\\frac{a}{b}\n= c\n$$")
    assert multi["content"][0]["type"] == "blockMathEquation"
    assert multi["content"][0]["attrs"]["math_equation"] == "\\frac{a}{b} = c"


def test_inline_formula_sits_between_text_and_marks() -> None:
    para = markdown_to_doc("Die Ableitung $f'(x)$ ist **wichtig**.")["content"][0]
    kinds = [n["type"] for n in para["content"]]
    assert kinds == ["text", "inlineMathEquation", "text", "text", "text"]
    assert para["content"][1]["attrs"] == {"math_equation": "f'(x)"}
    assert para["content"][3]["marks"] == [{"type": "bold"}]


def test_underscores_in_formulas_are_not_italic() -> None:
    para = markdown_to_doc("Mit $a_1$ und $b_2$ rechnen.")["content"][0]
    formulas = [n["attrs"]["math_equation"] for n in para["content"] if n["type"] == "inlineMathEquation"]
    assert formulas == ["a_1", "b_2"]
    assert all("marks" not in n for n in para["content"])


def test_currency_and_unclosed_dollar_stay_text() -> None:
    for text in ("Kostet 5 $ heute", "Es kostet $5 und $6.", "Offen $x ohne Ende"):
        para = markdown_to_doc(text)["content"][0]
        assert [n["type"] for n in para["content"]] == ["text"], text
        assert para["content"][0]["text"] == text


def test_escaped_dollar_is_a_literal_dollar() -> None:
    para = markdown_to_doc(r"Preis \$5 und \$6")["content"][0]
    assert [n["type"] for n in para["content"]] == ["text"]
    assert para["content"][0]["text"] == "Preis $5 und $6"


def test_dollar_in_code_stays_code() -> None:
    fenced = markdown_to_doc("```\n$$x$$ und $y$\n```")["content"][0]
    assert fenced["type"] == "codeBlock"
    assert fenced["content"][0]["text"] == "$$x$$ und $y$"
    span = markdown_to_doc("Nutze `echo $HOME $x$` hier")["content"][0]
    assert [n["type"] for n in span["content"]] == ["text", "text", "text"]
    assert span["content"][1]["text"] == "echo $HOME $x$"
