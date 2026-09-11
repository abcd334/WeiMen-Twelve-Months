from dataclasses import asdict
import json
from random import Random

import pytest

from data_loader import load_data
from game_engine import generate_characters, new_game, public_state


def test_same_seed_identical_and_other_seed_distinct():
    first = [asdict(c) for c in generate_characters(Random(42))]
    assert first == [asdict(c) for c in generate_characters(Random(42))]
    assert first != [asdict(c) for c in generate_characters(Random(43))]


@pytest.mark.parametrize("seed", range(30))
def test_balanced_compatible_distinct_characters(seed):
    chars = generate_characters(Random(seed))
    assert len({c.role for c in chars}) == len({c.name for c in chars}) == 4
    assert len({c.signature for c in chars}) == 4
    assert any(c.secret["mainline"] for c in chars)
    for c in chars:
        assert c.skills[c.role] in (4, 5)
        assert all(1 <= n <= 5 for n in c.skills.values())
        assert set(c.secret["requires"]) <= set(c.background["tags"])
        assert c.relationships and c.goal and c.fear_text
    pairs = {tuple(sorted((c.id, other))) for c in chars for other in c.relationships}
    assert len(pairs) >= 2


def test_contact_not_guaranteed_and_template_coverage():
    games = [generate_characters(Random(seed)) for seed in range(60)]
    assert any(all(c.secret["id"] != "contact" for c in chars) for chars in games)
    assert len({c.arc for chars in games for c in chars}) == 6
    assert all(c.status == "active" and not c.betrayal_intent for chars in games for c in chars)


def test_public_projection_is_allowlist_and_copies_collections():
    state = new_game(1)
    char = state.characters[0]
    char.secret = {"id": "SENTINEL_SECRET", "text": "SENTINEL_TEXT"}
    char.goal = "SENTINEL_GOAL"
    payload = public_state(state)
    text = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("trust", "stress", "loyalty", "ambition", "fear", "relationships", "secret", "goal_progress", "SENTINEL"):
        assert forbidden not in text
    payload["characters"][0]["experiences"].append("mutated")
    assert "mutated" not in char.experiences


def test_all_json_valid():
    templates, missions, personal = load_data()
    assert len(missions["events"]) == 20
    assert len(personal["arcs"]) >= 6
    assert all(len(cues) >= 2 for cues in templates["cue_templates"].values())
