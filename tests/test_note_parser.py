from xhs_alpha_picks.note_parser import XhsNote, extract_notes


def test_extract_notes_handles_nested_payload():
    payload = {
        "data": {
            "notes": [
                {
                    "note_id": "123",
                    "title": "Alpha pick insights",
                    "desc": "Great stock tips",
                    "user_nickname": "Analyst A",
                    "image_texts": ["Buy low", "Sell high"],
                },
                {
                    "id": "456",
                    "name": "Another post",
                    "note_desc": "General commentary",
                    "author": "Trader B",
                    "images": [
                        {"ocr_text": "Important data"},
                        {"ocr_text": "Watch carefully"},
                    ],
                },
            ]
        }
    }

    notes = extract_notes(payload)

    assert len(notes) == 2
    first, second = notes
    assert isinstance(first, XhsNote)
    assert first.note_id == "123"
    assert "Buy low" in first.image_texts
    assert second.note_id == "456"
    assert "Important data" in second.image_texts
