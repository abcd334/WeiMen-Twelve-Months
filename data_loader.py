"""Load and validate authored JSON; no UI dependency or network access."""
import json
from functools import lru_cache
from pathlib import Path

from models import SKILLS, RESOURCES

DATA_DIR = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=1)
def load_story_data():
    with (DATA_DIR / "story_threads.json").open(encoding="utf-8") as stream:
        data = json.load(stream)
    assert len(data["threads"]) >= 3
    for thread in data["threads"]:
        assert set(thread["required_clues"]) <= thread["clues"].keys()
        assert all(c["thread_id"] == thread["id"] for c in thread["clues"].values())
    return data


def validate_data(characters, missions, personal):
    banned = ("有了進展", "未能如期完成", "這次的安排已落實", "同行者帶回了具體阻礙與損失", "下回仍得先看清局面", "把今日經過逐項寫下，請你核對")
    authored = json.dumps([characters, missions, personal], ensure_ascii=False)
    assert not any(phrase in authored for phrase in banned), "Generic narrative placeholder"
    events = missions["events"]
    assert len({e["id"] for e in events}) == len(events), "Duplicate event IDs"
    assert len([e for e in events if not e.get("fixed_month")]) >= 16
    assert {e["fixed_month"] for e in events if e.get("fixed_month")} == {1, 4, 8, 12}
    arc_ids = {a["id"] for a in personal["arcs"]}
    assert len(arc_ids) >= 6
    tags = {tag for bg in characters["backgrounds"] for tag in bg["tags"]}
    assert len(characters["signatures"]) >= 4
    for secret in characters["secrets"]:
        assert set(secret["requires"]) <= tags
        assert secret["arc"] is None or secret["arc"] in arc_ids
    for event in events:
        assert 80 <= len(event["scene_opening"]) <= 180, event["id"]
        assert event["concrete_detail"] and event["callback_fact"]
        assert len(event["options"]) == (0 if event.get("fixed_month") == 12 else 3)
        assert len({o["id"] for o in event["options"]}) == len(event["options"])
        for option in event["options"]:
            for key in ("success_narratives", "failure_narratives"):
                assert len(set(option[key])) >= 2
                assert all(len(text) >= 45 for text in option[key])
            assert option["skill"] in SKILLS and option["count"] in (1, 2)
            assert option["risk"] in ("low", "medium", "high", "lethal")
            assert option["cost"] >= 0
            assert set(option["intel"]) <= missions["intel"].keys()
            assert set(option["flags"]) <= missions["flags"].keys()
            assert set(option["background_modifiers"]) <= tags
            for outcome in ("success", "failure"):
                assert set(option[outcome]) <= RESOURCES.keys()
                assert all(len(v) == 2 and v[0] <= v[1] for v in option[outcome].values())
            if option["risk"] == "lethal":
                assert "致命風險" in option["visible_hint"]
    for arc in personal["arcs"]:
        assert len(set(arc["resolutions"].values())) >= 2
        assert len(arc["stages"]) == 3 and 2 <= len(arc["choices"]) <= 3
        assert len({tuple(c["tradeoffs"]) for c in arc["choices"]}) >= 2
        assert all(len(c["tradeoffs"]) >= 2 for c in arc["choices"])
    patterns = [json.dumps([(c["effects"], c["psych"], c["reaction"]) for c in arc["choices"]], sort_keys=True) for arc in personal["arcs"]]
    assert len(set(patterns)) == len(patterns), "Personal arcs share identical mechanics and reactions"


@lru_cache(maxsize=1)
def load_data():
    values = []
    for filename in ("character_templates.json", "mission_events.json", "personal_events.json"):
        with (DATA_DIR / filename).open(encoding="utf-8") as stream:
            values.append(json.load(stream))
    validate_data(*values)
    return tuple(values)
