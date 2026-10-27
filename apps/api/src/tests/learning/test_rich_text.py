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
