from __future__ import annotations

from dotkit.fsops import BLOCK_END, BLOCK_START, upsert_block, write_if_changed


def test_block_appended_to_existing_text_once():
    text = "export A=1"
    once = upsert_block(text, "source x")
    assert once == f"export A=1\n\n{BLOCK_START}\nsource x\n{BLOCK_END}\n"
    assert upsert_block(once, "source x") == once


def test_block_replaced_in_place_and_surroundings_kept():
    text = upsert_block("top\n", "old") + "# appended by some tool\n"
    updated = upsert_block(text, "new")
    assert "old" not in updated
    assert updated.startswith("top\n") and updated.endswith("# appended by some tool\n")


def test_block_in_empty_file():
    assert upsert_block("", "x") == f"{BLOCK_START}\nx\n{BLOCK_END}\n"


def test_write_if_changed(tmp_path):
    path = tmp_path / "a/b.txt"
    assert write_if_changed(path, "1") is True
    assert write_if_changed(path, "1") is False
    assert write_if_changed(path, "2") is True and path.read_text() == "2"
