import json
import re
from pathlib import Path


def test_request_capture_is_sanitized_and_not_mislabeled_complete():
    fixture_path = Path(__file__).parent / "fixtures" / "search_request.json"
    raw = fixture_path.read_text(encoding="utf-8")
    evidence = json.loads(raw)

    assert not re.search(
        r"(?i)(sessionid|csrftoken|fb_dtsg|access_token|authorization)\s*[=:]\s*[^\s\"']+",
        raw,
    )
    assert evidence["credential_material_removed"] is True
    assert evidence["response_captured"] is False
    assert evidence["records"] is None
    assert evidence["pagination_termination"] == "UNTESTED"
    assert evidence["protocol_complete"] == "UNTESTED"
    assert evidence["reported_count_consistent"] == "UNTESTED"
