from src.infrastructure.prompts import load_prompt, render_prompt


def test_page_prompt_fills_label_and_keeps_json_braces():
    text = render_prompt("page_region", label="p6_r0c0")
    assert "p6_r0c0" in text and "{label}" not in text
    assert '{"section"' in text


def test_table_prompts_load():
    assert "mảng JSON" in load_prompt("table") and "ĐÚNG MỘT dòng" in load_prompt("table_row")
