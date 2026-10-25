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
