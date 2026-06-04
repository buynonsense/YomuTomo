import json


def test_reading_state_shape_is_json_serializable():
    state = {
        "furiganaMode": "show",
        "hideMastered": False,
        "masteredWords": ["天気"],
    }

    encoded = json.dumps(state, ensure_ascii=False)

    assert '"furiganaMode": "show"' in encoded
    assert '"hideMastered": false' in encoded
    assert '"masteredWords": ["天気"]' in encoded
