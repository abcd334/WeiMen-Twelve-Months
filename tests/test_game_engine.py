from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from data_loader import load_data
from game_engine import (InvalidAction, begin_month, check_failure, current_event, emit_cue,
                         emergency_rest, gain_intel, grow_skill, legal_actions, mission_score,
                         new_game, night_view, observe_character, public_option, public_state,
                         queue_delay, record_decision, resolve_day, resolve_major_outcome,
                         resolve_night, response_effects, start_night, update_intentions)
from models import Cue
from simulate_balance import POLICIES, audit_outcomes, play_game


def digest(state):
    data = asdict(state)
    data["rng"] = state.rng.getstate()
    return data


def complete_day(state):
    action = legal_actions(state)[0]
    resolve_day(state, action[0]["id"], action[1])


@pytest.mark.parametrize("policy", POLICIES)
def test_same_seed_same_events_and_results(policy):
    assert digest(play_game(42, policy)) == digest(play_game(42, policy))


def test_fixed_months_random_without_replacement():
    state = new_game(17)
    seen = []
    while not state.ending:
        state.resources = {"treasury": 100, "defense": 100, "reputation": 100}
        seen.append((state.month, state.event_id))
        complete_day(state)
        start_night(state)
        resolve_night(state, "support")
        begin_month(state)
    seen.append((state.month, state.event_id))
    assert dict(seen)[1] == "inventory"
    assert dict(seen)[4] == "provocation"
    assert dict(seen)[8] == "suspicion"
    assert dict(seen)[12] == "finale"
    assert len({event for _, event in seen}) == 12


def test_confirmation_once_and_stale_tokens_and_invalid_team_are_atomic():
    state = new_game(1)
    before = digest(state)
    for option, team, token in [("pay", ["c0"], "2:day"), ("pay", ["c0", "c0"], None), ("missing", ["c0"], None)]:
        with pytest.raises(InvalidAction):
            resolve_day(state, option, team, token)
        assert digest(state) == before
    complete_day(state)
    before = digest(state)
    with pytest.raises(InvalidAction):
        resolve_day(state, "pay", ["c0"])
    assert digest(state) == before
    start_night(state)
    resolve_night(state, "discipline")
    before = digest(state)
    with pytest.raises(InvalidAction):
        resolve_night(state, "support")
    assert digest(state) == before
    begin_month(state)
    before = digest(state)
    with pytest.raises(InvalidAction):
        begin_month(state)
    assert digest(state) == before


def test_delay_applies_exactly_once_and_links_real_fact():
    state = new_game(2)
    decision = record_decision(state, "測試周轉", [])
    queue_delay(state, {"after": 2, "effects": {"treasury": 7}, "text": "周轉款送達"}, decision["id"])
    state.phase = "night_result"
    before = state.resources["treasury"]
    begin_month(state)
    assert state.resources["treasury"] == before - 3
    assert len(state.pending) == 1
    state.phase = "night_result"
    begin_month(state)
    assert state.resources["treasury"] == before - 6 + 7
    assert not state.pending and len(decision["facts"]) == 1
    state.phase = "night_result"
    begin_month(state)
    assert state.resources["treasury"] == before - 9 + 7


def test_heavy_injury_and_restriction_prevent_dispatch_and_no_replacement():
    state = new_game(3)
    char = state.characters[0]
    char.injury = 2
    assert all(char.id not in team for _, team in legal_actions(state))
    with pytest.raises(InvalidAction):
        resolve_day(state, "pay", [char.id])
    original_ids = [c.id for c in state.characters]
    char.status = "dead"
    state.characters[1].status = "left"
    state.phase = "night_result"
    begin_month(state)
    assert [c.id for c in state.characters] == original_ids
    assert len(state.characters) == 4


def test_all_incapacitated_can_rest_without_softlock():
    state = new_game(4)
    for char in state.characters:
        char.injury = 2
    assert not legal_actions(state)
    emergency_rest(state)
    start_night(state)
    resolve_night(state, "discipline")
    begin_month(state)
    assert state.actionable()


@pytest.mark.parametrize("risk", ("low", "medium", "high"))
def test_nonlethal_risks_never_kill_even_on_failure(risk):
    event, option_id = {"low": ("inventory", "pay"), "medium": ("caravan", "road"), "high": ("manual", "practice")}[risk]
    for seed in range(60):
        state = new_game(seed)
        state.event_id = event
        for char in state.characters:
            char.skills = dict.fromkeys(char.skills, 1)
            char.fatigue = 95
        option = next(o for o in current_event(state)["options"] if o["id"] == option_id)
        resolve_day(state, option_id, [c.id for c in state.characters[:option["count"]]])
        assert not any(c.status == "dead" for c in state.characters)


def test_lethal_failure_can_kill_and_records_prechoice_notice():
    deaths = []
    for seed in range(80):
        state = new_game(seed)
        state.event_id = "treasure"
        for char in state.characters:
            char.skills = dict.fromkeys(char.skills, 1)
        resolve_day(state, "enter", ["c0", "c1"])
        deaths.extend(audit_outcomes(state))
    assert deaths and all("致命風險" in row["risk_notice"] for row in deaths)


def prepare_intent(state, betrayal=False):
    char = state.characters[0]
    char.trust, char.stress, char.loyalty = 20, 80, 25
    char.choices = ["discipline", "discipline"]
    if betrayal:
        char.secret = next(s for s in load_data()[0]["secrets"] if s["id"] == "contact")
    else:
        char.secret = next(s for s in load_data()[0]["secrets"] if s["id"] == "debt")
    update_intentions(char)
    return char


@pytest.mark.parametrize("betrayal", (False, True))
def test_permanent_outcome_requires_two_prior_months_and_strong_cue(betrayal):
    state = new_game(5)
    char = prepare_intent(state, betrayal)
    category = "betrayal" if betrayal else "leaving"
    assert not resolve_major_outcome(state, char)
    emit_cue(state, char, category, "strong")
    assert not resolve_major_outcome(state, char)
    state.month = 2
    emit_cue(state, char, category, "weak")
    assert not resolve_major_outcome(state, char)  # current-month observation cannot authorize it
    state.month = 3
    assert resolve_major_outcome(state, char)
    assert char.status == ("defected" if betrayal else "left")
    assert len(audit_outcomes(state)[0]["warnings"]) == 2


def test_weak_only_same_month_or_noise_cannot_authorize_departure():
    for strengths, months in [(["weak", "weak"], [1, 2]), (["strong", "weak"], [1, 1]), (["noise", "noise"], [1, 2])]:
        state = new_game(6)
        char = prepare_intent(state)
        state.observations = [Cue(f"q{i}", m, char.id, "leaving", strength, "test", {"supported": True}) for i, (m, strength) in enumerate(zip(months, strengths))]
        state.month = 4
        assert not resolve_major_outcome(state, char)


def test_no_single_hidden_value_can_trigger_major_result():
    state = new_game(7)
    char = state.characters[0]
    char.trust = 0
    char.loyalty = 0
    update_intentions(char)
    assert not char.leave_intent and not char.betrayal_intent
    char.stress = 100
    update_intentions(char)
    assert not char.leave_intent  # no actual prior failed missions / multiple choices


def test_false_strong_cue_rejected_and_templates_do_not_repeat():
    state = new_game(8)
    char = state.characters[0]
    with pytest.raises(InvalidAction):
        emit_cue(state, char, "leaving", "strong")
    char = prepare_intent(state)
    for month in (1, 2, 3):
        state.month = month
        observe_character(state, char)
    cues = state.observations
    assert all(q.evidence["supported"] for q in cues)
    assert all(a.text != b.text for a, b in zip(cues, cues[1:]))


@pytest.mark.parametrize("seed,kind", [(0, "left"), (13, "left"), (99, "defected"), (113, "defected"), (224, "defected")])
def test_natural_fixed_seed_permanent_consequences_have_prior_evidence(seed, kind):
    state = play_game(seed, "conservative_policy")
    outcomes = audit_outcomes(state)
    assert any(row["kind"] == kind for row in outcomes)
    for row in outcomes:
        if row["kind"] != "dead":
            assert len({q["month"] for q in row["warnings"]}) >= 2
            assert all(q["month"] < row["month"] for q in row["warnings"])


def test_extra_hints_known_background_and_reading_does_not_change_engine():
    state = new_game(9)
    state.event_id = "suspicion"
    option = current_event(state)["options"][1]
    poor = public_option(state, option)
    gain_intel(state, "pattern", "test")
    rich = public_option(state, option)
    assert len(rich["extra_hints"]) > len(poor["extra_hints"])
    before = digest(state)
    public_option(state, option, ["c1"])
    public_state(state)
    assert digest(state) == before
    twin = deepcopy(state)
    resolve_day(state, "watch", ["c1"])
    resolve_day(twin, "watch", ["c1"])
    assert digest(state) == digest(twin)
    assert "success" not in rich and "difficulty" not in rich and "psych" not in rich


def test_physical_skill_background_intel_relationships_affect_performance():
    state = new_game(10)
    option = current_event(state)["options"][1]
    team = state.characters[:2]
    initial = mission_score(state, option, team)
    team[0].fatigue = 90
    assert mission_score(state, option, team) < initial
    team[0].fatigue = 0
    team[0].skills["combat"] = 1
    assert mission_score(state, option, team) < initial
    before_info = mission_score(state, option, team)
    gain_intel(state, "pattern", "test")
    assert mission_score(state, option, team) > before_info


def test_night_tradeoffs_are_distinct_and_personality_changes_response():
    state = new_game(11)
    for arc in load_data()[2]["arcs"]:
        assert len({tuple(c["tradeoffs"]) for c in arc["choices"]}) >= 2
        discipline = next(c for c in arc["choices"] if c["approach"] == "discipline")
        char = state.characters[0]
        char.personality = "剛直"
        straight = response_effects(char, discipline)
        char.personality = "重情"
        emotional = response_effects(char, discipline)
        assert straight["trust"] > emotional["trust"]
    complete_day(state)
    start_night(state)
    assert state.night_character in state.last_participants
    assert len(night_view(state)["choices"]) == 3


def test_growth_and_bounds():
    state = new_game(12)
    char = state.characters[0]
    char.skills["strategy"] = 1
    for _ in range(100):
        grow_skill(state, char, "strategy", True)
    assert char.skills["strategy"] == 5
    assert char.experiences


def test_all_early_failure_conditions_and_reputation_gate():
    state = new_game(13)
    state.resources["reputation"] = 0
    assert not check_failure(state)
    from game_engine import event_eligible
    state.month = 2
    assert all(not event_eligible(state, e) for e in load_data()[1]["events"] if set(e["tags"]) & {"aid", "high_reward"})
    state.resources["defense"] = 0
    assert not check_failure(state)
    assert check_failure(state, hostile=True)
    state = new_game(13)
    state.resources["treasury"] = 0
    assert check_failure(state) and "糧餉" in state.ending_reason
    state = new_game(13)
    for char in state.characters:
        char.status = "left"
    assert check_failure(state) and "瓦解" in state.ending_reason


@pytest.mark.parametrize("seed", (0, 7, 17, 42, 99))
def test_general_public_ui_never_contains_private_fields_over_whole_game(seed):
    state = play_game(seed, "random_policy")
    serialized = json.dumps(public_state(state), ensure_ascii=False)
    for word in ("trust", "stress", "loyalty", "ambition", "relationships", "goal_progress", "betrayal_intent", "成功率", "信任 -", "壓力 +", "忠誠度"):
        assert word not in serialized
    assert all(c.evidence["supported"] for c in state.observations if c.strength == "strong")
