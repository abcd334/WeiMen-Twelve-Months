import json

import pytest

from feedback import save_feedback, survey_options
from game_engine import (InvalidAction, causal_replay, determine_ending, ending_view,
                         finish, gain_intel, new_game, current_thread)
from simulate_balance import POLICIES, play_game
from investigation import resolve_deduction


def ending_fixture():
    state = new_game(42)
    state.month = 12
    state.resources = {"treasury": 50, "defense": 30, "reputation": 30}
    for char in state.characters:
        char.skills = dict.fromkeys(char.skills, 3)
    return state


@pytest.mark.parametrize("ending", ("揭破陰謀", "聯盟退敵", "正面取勝", "慘勝守山", "門派覆滅"))
def test_five_endings_and_priority(ending):
    state = ending_fixture()
    if ending == "揭破陰謀":
        for item in current_thread(state)["required_clues"]:
            gain_intel(state, item, "test")
        state.month, state.phase = 11, "deduction"
        resolve_deduction(state, evidence_ids=current_thread(state)["required_clues"])
        state.month = 12
        state.flags.add("alliance")
        state.resources.update(defense=70, reputation=70)
    elif ending == "聯盟退敵":
        state.flags.add("villagers_helped")
        state.resources.update(defense=70, reputation=65)
    elif ending == "正面取勝":
        state.resources["defense"] = 60
    elif ending == "慘勝守山":
        state.resources["defense"] = 45
    assert determine_ending(state)[0] == ending


def test_remaining_and_actionable_thresholds():
    state = ending_fixture()
    state.resources.update(defense=100, reputation=100)
    state.flags.add("alliance")
    for item in ("ledger", "pattern", "leak"):
        gain_intel(state, item, "test")
    for char in state.characters[:3]:
        char.status = "left"
    assert determine_ending(state)[0] == "門派覆滅"
    state = ending_fixture()
    state.resources["defense"] = 60
    state.characters[0].injury = 2
    assert determine_ending(state)[0] == "慘勝守山"


def test_ending_requires_unlock_and_each_character_has_fate():
    state = new_game(1)
    with pytest.raises(InvalidAction):
        ending_view(state)
    with pytest.raises(InvalidAction):
        causal_replay(state)
    finish(state, "門派覆滅", "測試結局")
    view = ending_view(state)
    assert len(view["characters"]) == 4
    assert all(c["fate"] and c["heart"] for c in view["characters"])


@pytest.mark.parametrize("policy", POLICIES)
def test_causal_replay_only_references_actual_facts(policy):
    state = play_game(42, policy)
    replay = causal_replay(state)
    assert len(replay) <= 8
    if len(state.decisions) >= 5:
        assert len(replay) >= 5
    facts = {f["id"]: f for f in state.facts}
    for row in replay:
        assert all(fid in facts and facts[fid]["text"] in row["text"] for fid in row["fact_ids"])
        if "在斷劍臺上成為" in row["text"]:
            assert set(row["fact_ids"]) & set(state.ending_evidence)


def test_survey_saved_locally_once_without_affecting_seed_or_result(tmp_path):
    state = play_game(42, "highest_skill_policy")
    before_rng = state.rng.getstate()
    before = ending_view(state)
    answers = {key: values[0] for key, values in survey_options(state).items()}
    target = tmp_path / "feedback" / "responses.jsonl"
    assert save_feedback(state, answers, "test-response", target)
    assert not save_feedback(state, answers, "test-response", target)
    rows = [json.loads(row) for row in target.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["seed"] == 42 and rows[0]["answers"] == answers
    assert state.rng.getstate() == before_rng and ending_view(state) == before
    with pytest.raises(ValueError):
        save_feedback(state, {**answers, "replay": "arbitrary free text"}, "other", target)
    with pytest.raises(ValueError):
        survey_options(new_game(10))
