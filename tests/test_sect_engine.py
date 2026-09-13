"""v0.7 acceptance: real history, alternate lives, safe turns and persistence."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

import sect_engine as engine
from sect_content import EVENTS, validate_content
from sect_models import date_label


def digest(state):
    data = asdict(state)
    data["rng"] = state.rng.getstate()
    return data


def advance(state, action="work", team=None, jobs=None):
    engine.resolve_turn(state, action, ["c0", "c1"] if team is None else team, jobs)
    if state.phase == "result":
        engine.next_tick(state)


def test_six_ordinary_people_without_preassigned_protagonist():
    state = engine.new_game(4)
    validate_content()
    assert len(EVENTS) == 33
    assert len(state.characters) == 6
    assert len({c.name for c in state.characters}) == 6
    assert all(c.stage == 0 and c.narrative_weight == 0 and not c.goal and not c.secret for c in state.characters)
    assert all(c.relationships for c in state.characters)
    assert state.tick == 1 and state.month == 1 and state.version == "0.7"


@pytest.mark.parametrize("seed", [-1, 2**32, True, "4", None])
def test_invalid_seeds(seed):
    with pytest.raises(engine.InvalidAction):
        engine.new_game(seed)


def test_public_projection_and_reruns_are_pure_and_detached():
    state = engine.new_game(6)
    before = digest(state)
    for _ in range(4):
        view = engine.public_state(state)
        engine.available_actions(state)
        engine.history_review(state)
    assert digest(state) == before
    serialized = json.dumps(view, ensure_ascii=False)
    for field in ("narrative_weight", "weight_sources", "loyalty", "secret", "ambition", "fear_text"):
        assert field not in serialized
    view["characters"][0]["skills"]["武力"] = -100
    assert digest(state) == before


@pytest.mark.parametrize("action,team,jobs", [
    ("missing", ["c0"], {}), ("work", ["c0", "c0"], {}), ("work", [], {}),
    ("work", ["stranger"], {}), ("work", ["c0"], {"c0": "rest"}),
    ("work", ["c0"], {"c1": "unknown"}), ("work", ["c0"], {"stranger": "rest"}),
    ("work", ["c0", "c1", "c2"], {}),
])
def test_invalid_plan_changes_nothing(action, team, jobs):
    state = engine.new_game(4)
    before = digest(state)
    with pytest.raises(engine.InvalidAction):
        engine.resolve_turn(state, action, team, jobs)
    assert digest(state) == before


def test_injury_costs_and_duplicate_submission_validation():
    state = engine.new_game(0)
    state.character("c0").injury = 2
    state.resources["treasury"] = 0
    before = digest(state)
    for aid, team, jobs in [("work", ["c0"], {}), ("work", ["c1"], {"c0": "guard"}),
                             ("build/herbs", ["c1"], {})]:
        with pytest.raises(engine.InvalidAction):
            engine.resolve_turn(state, aid, team, jobs)
        assert digest(state) == before
    engine.resolve_turn(state, "work", ["c1"], token="1:plan")
    resolved = digest(state)
    with pytest.raises(engine.InvalidAction):
        engine.resolve_turn(state, "work", ["c1"], token="1:plan")
    assert digest(state) == resolved
    engine.next_tick(state, "1:next")
    before = digest(state)
    with pytest.raises(engine.InvalidAction):
        engine.next_tick(state, "1:next")
    with pytest.raises(engine.InvalidAction):
        engine.resolve_turn(state, "work", ["c1"], token="1:plan")
    assert digest(state) == before


def rescue_game(monkeypatch):
    state = engine.new_game(4)
    state.offers = ["escort"]
    monkeypatch.setattr(engine, "_chance", lambda *args: 0)
    engine.resolve_turn(state, "escort/direct", ["c0", "c1"])
    return state


def test_actual_rescue_reappears_later_with_directed_roles_and_effect(monkeypatch):
    state = rescue_game(monkeypatch)
    memory = next(m for m in state.shared_memories if "rescue" in m.tags)
    assert memory.actor_id != memory.target_id
    assert state.character(memory.target_id).injury == 2
    assert all(any(e.id == source for c in state.characters for e in c.experiences) for source in memory.source_ids)
    engine.next_tick(state)
    assert not engine.eligible_memories(state, memory.participants, "suspicion")
    for _ in range(4):
        advance(state, "rest", ["c0", "c1"], {"c2": "host", "c3": "guard", "c4": "herbs", "c5": "train"})
    action = next(a for a in engine.available_actions(state) if a.get("event_id") == "suspicion")
    reputation = state.resources["reputation"]
    engine.resolve_turn(state, action["id"], action["required"])
    callback = state.callback_history[-1]
    assert callback["source_id"] == memory.id and callback["source_tick"] == 1
    assert callback["tick"] >= 4 and callback["effect"] == 2
    assert state.character(memory.target_id).name in callback["text"]
    assert state.character(memory.actor_id).name in callback["text"]
    assert state.resources["reputation"] == reputation + 6
    assert "suspicion" in memory.recalled_by
    assert not engine.eligible_memories(state, ["c2", "c3"], "suspicion")


def test_relationship_score_cannot_fabricate_a_rescue():
    state = engine.new_game(4)
    state.character("c0").relationships["c1"]["value"] = 999
    state.tick = 9
    engine.prepare_tick(state)
    assert not any(a.get("event_id") == "suspicion" for a in engine.available_actions(state))
    assert not state.callback_history


@pytest.mark.parametrize("event_id", ["caravan_talk", "petition", "wounded_traveler"])
def test_nonphysical_failure_does_not_invent_an_injury(monkeypatch, event_id):
    state = engine.new_game(42)
    state.offers = [event_id]
    monkeypatch.setattr(engine, "_chance", lambda *args: 0)
    engine.resolve_turn(state, event_id + "/direct", ["c0", "c1"])
    assert any(e.kind == "mission_failure" for e in state.character("c0").experiences)
    assert all(c.injury == 0 for c in state.characters)
    assert not any("rescue" in m.tags for m in state.shared_memories)


def test_repeated_requests_keep_latest_cause_and_routine_work_has_no_personal_scene():
    state = engine.new_game(4)
    engine.enqueue(state, "failure_request", "c0", "first")
    engine.enqueue(state, "failure_request", "c0", "second")
    engine.enqueue(state, "failure_request", "c0", "second")
    requests = [p for p in state.personal_queue if p["event_id"] == "failure_request"]
    assert len(requests) == 1 and requests[0]["source_id"] == "second"
    for _ in range(4):
        advance(state, "work", ["c0", "c1"])
    assert not any(a.get("event_id") == "memory_return" for a in engine.available_actions(state))


def test_fatigue_reduces_work_income_and_rest_recovers_it():
    state = engine.new_game(4)
    char = state.character("c0")
    char.fatigue = 70
    engine.resolve_turn(state, "work", ["c0"])
    assert state.last_changes["treasury"] == 1  # 4 wages - 3 upkeep
    engine.next_tick(state)
    engine.resolve_turn(state, "rest", ["c0"])
    assert char.fatigue == 63
    engine.next_tick(state)
    engine.resolve_turn(state, "work", ["c0"])
    assert state.last_changes["treasury"] == 4  # 7 wages - 3 upkeep


def test_repeated_trivial_work_does_not_create_core_character():
    state = engine.new_game(4)
    for _ in range(12):
        advance(state, "work", ["c0"], {"c1": "host", "c2": "herbs", "c3": "guard", "c4": "host", "c5": "herbs"})
    char = state.character("c0")
    assert char.narrative_weight == 6 and char.stage == 0


def test_same_people_different_assignments_create_different_histories():
    first, second = engine.new_game(6), engine.new_game(6)
    for _ in range(10):
        advance(first, "train", ["c0", "c1"], {"c2": "host", "c3": "guard", "c4": "herbs", "c5": "rest"})
        advance(second, "work", ["c2", "c3"], {"c0": "rest", "c1": "herbs", "c4": "host", "c5": "guard"})
    assert [c.name for c in first.characters] == [c.name for c in second.characters]
    assert first.character("c0").duties["mentoring"] == 10
    assert second.character("c0").neglect_warnings
    assert engine.history_review(first) != engine.history_review(second)


def test_neglect_has_two_earlier_warnings_and_can_be_repaired():
    state = engine.new_game(6)
    for _ in range(16):
        advance(state, "work", ["c0", "c1"])
    char = state.character("c2")
    assert len(char.neglect_warnings) == 2 and char.status == "active"
    protected = deepcopy(state)
    advance(protected, "work", ["c2"])
    assert protected.character("c2").status == "active"
    advance(state, "work", ["c0", "c1"])
    assert char.status == "left"
    outcome = next(o for o in state.major_outcomes if o["character_id"] == "c2")
    assert len(outcome["warnings"]) == 2 and max(outcome["warnings"]) < outcome["tick"]


def test_chain_is_optional_spaced_and_coexists_with_other_events():
    state = engine.new_game(4)
    for _ in range(3):
        advance(state)
    assert state.tick == 4 and "cards_0" in state.offers
    assert len([a for a in engine.available_actions(state) if a["kind"] == "mission"]) == 6
    advance(state, "cards_0/ally", ["c0"])
    assert state.chain["step"] == 1 and state.chain["clues"] == 1
    assert not any(e.startswith("cards_") for e in state.offers)
    while state.tick < 8:
        advance(state)
    assert "cards_1" in state.offers
    advance(state, "cards_1/ally", ["c0"])
    while state.tick < 12:
        advance(state)
    advance(state, "cards_2/ally", ["c0"])
    assert state.chain["status"] == "查明冒名者"
    assert state.phase == "planning" and state.tick == 13


def test_ignored_chain_returns_without_blocking_the_calendar():
    state = engine.new_game(4)
    for _ in range(11):
        advance(state)
    assert state.tick == 12 and state.chain["step"] == 0
    assert any("一直未獲回應" in entry["text"] for entry in state.logs)
    assert "cards_0" in state.offers


def test_office_requires_experience_facility_and_fitness_and_automates_healing():
    state = engine.new_game(4)
    medic = state.character("c0")
    medic.skills["medicine"] = 4
    medic.duties["herbs"] = 6
    assert not engine.office_candidates(state)
    medic.stage = 2
    assert not engine.office_candidates(state)
    state.facilities["herbs"] = 2
    assert (medic.id, "medic") in engine.office_candidates(state)
    medic.injury = 2
    assert not engine.office_candidates(state)
    medic.injury = 0
    advance(state, "appoint/c0/medic", ["c0"])
    assert medic.office == "medic" and medic.stage == 3
    patient = state.character("c1")
    patient.injury = 2
    engine.resolve_turn(state, "work", ["c2"], {"c0": "herbs", "c1": "rest"})
    assert patient.injury == 1 and patient.recovery_progress == 0
    assert any("care" in m.tags and set(m.participants) == {"c0", "c1"} for m in state.shared_memories)


@pytest.mark.parametrize("office,facility,duties", [
    ("leader", "lodge", {"missions": 4, "lead": 3}),
    ("mentor", "training", {"train": 6, "mentoring": 3}),
])
def test_other_offices_produce_real_work(office, facility, duties):
    state = engine.new_game(4)
    holder = state.character("c0")
    holder.stage = 2
    holder.skills["combat"] = 4
    holder.duties.update(duties)
    state.facilities[facility] = 2
    advance(state, f"appoint/c0/{office}", ["c0"])
    engine.resolve_turn(state, "work", ["c2"], {"c0": "guard", "c1": "train"})
    assert any(holder.name in e["text"] and e["kind"] == "autonomous" for e in state.logs)
    assert any(set(m.participants) == {"c0", "c1"} for m in state.shared_memories)
    if office == "mentor":
        assert state.character("c1").duties["train"] == 2
    else:
        assert any(e.kind == "delegated" for e in state.character("c1").experiences)


def test_calendar_continues_into_second_year_after_survival():
    state = engine.new_game(4)
    for _ in range(37):
        advance(state, "work", ["c0", "c1"], {"c2": "guard", "c3": "herbs", "c4": "host", "c5": "guard"})
    assert state.tick == 38 and state.month == 1 and state.phase == "planning"
    assert state.annual_reports[0]["survived"]
    assert date_label(36) == "第 1 年 12 月下旬"
    assert date_label(37) == "第 2 年 1 月上旬"


def test_annual_failure_and_starvation_have_actual_end_states():
    state = engine.new_game(4)
    state.tick = 36
    state.resources.update(defense=0, reputation=0)
    for c in state.characters:
        c.skills["combat"] = 1
    engine.resolve_turn(state, "rest", ["c0"])
    assert state.phase == "ended" and state.ending == "山門失守"
    with pytest.raises(engine.InvalidAction):
        engine.next_tick(state)
    starving = engine.new_game(4)
    starving.resources["treasury"] = 0
    for _ in range(3):
        advance(starving, "rest", ["c0"])
    assert starving.ending == "糧盡散門"
    assert any(e["kind"] == "warning" and "三旬" in e["text"] for e in starving.logs)


def test_identical_seed_and_decisions_reproduce_rng_and_every_history():
    states = [engine.new_game(42), engine.new_game(42)]
    for state in states:
        for _ in range(25):
            advance(state, "work", ["c0", "c1"], {"c2": "herbs", "c3": "guard", "c4": "host", "c5": "guard"})
    assert digest(states[0]) == digest(states[1])


def test_feedback_is_local_versioned_idempotent_and_does_not_change_game(tmp_path):
    from sect_feedback import save_feedback
    state = engine.new_game(4)
    path = tmp_path / "responses.jsonl"
    with pytest.raises(ValueError):
        save_feedback(state, "唐見川", "一起走過山路", "可能很不一樣", "test", path)
    for _ in range(24):
        advance(state)
    before = digest(state)
    args = (state, "唐見川", "一起走過山路", "可能很不一樣", "test", path)
    assert save_feedback(*args)
    assert not save_feedback(*args)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "0.7"
    assert digest(state) == before
