import json
from pathlib import Path
from typing import Dict

from xhs_alpha_picks.cli import main
from xhs_alpha_picks.note_parser import extract_notes


def build_fake_payload(keyword: str) -> Dict[str, object]:
    return {
        "data": {
            "notes": [
                {
                    "note_id": "n1",
                    "title": f"{keyword} overview",
                    "desc": "Key takeaways from today",
                    "user_nickname": "Researcher",
                    "image_text": "Important OCR detail",
                    "note_url": "https://www.xiaohongshu.com/explore/n1",
                }
            ]
        }
    }
def test_cli_offline_mode(tmp_path: Path, monkeypatch):
    keyword = "alpha pick 2099-01-01"
    payload = build_fake_payload(keyword)

    output_path = tmp_path / "payload.json"

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def search_notes(self, keyword: str, limit: int, raw_payload: Dict[str, object] | None = None):
            assert keyword == "alpha pick 2099-01-01"
            return {"notes": extract_notes(payload), "raw": payload}

    monkeypatch.setattr("xhs_alpha_picks.cli.XiaohongshuMCPClient", DummyClient)

    from io import StringIO

    buffer = StringIO()
    exit_code = main(
        [
            "--keyword",
            keyword,
            "--offline",
            "--count",
            "1",
            "--save-json",
            str(output_path),
        ],
        stream=buffer,
    )

    assert exit_code == 0
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == payload
    text = buffer.getvalue()
    assert "Retrieved 1 notes" in text
    assert keyword in text
