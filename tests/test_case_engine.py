"""v0.6 causal contracts, failures, public boundaries and real twelve-month paths."""
from copy import deepcopy
from dataclasses import asdict
from itertools import combinations
import json

import pytest

import case_engine as case
import game_engine as game
from investigation import store_item, graph_for, resolve_deduction, checkpoint_view, chain_complete
from simulate_balance import play_game, POLICIES


def digest(state):
    result = asdict(state)
    result['rng'] = state.rng.getstate()
    return result


def dispatch(state, aid=None):
    legal = case.legal_case_actions(state)
    if aid:
        legal = [(a, team) for a, team in legal if a.id == aid]
    a, ids = max(legal, key=lambda row: max(state.character(cid).skills[row[0].skill] for cid in row[1]))
    game.resolve_case_action(state, a.id, ids)


def next_step(state):
    if state.phase == 'day':
        dispatch(state)
    elif state.phase in ('day_result', 'deduction_result'):
        game.start_night(state)
    elif state.phase == 'night':
        game.resolve_night(state, 'review' if state.month != 11 else 'keep_people')
    elif state.phase == 'deduction':
        resolve_deduction(state, hypothesis='uncertain' if state.month == 4 else None)
    else:
        game.begin_month(state)


def at_month(month):
    state = game.new_game(4)
    while state.month < month and not state.ending:
        next_step(state)
    assert state.month == month and not state.ending
    return state


def obtain(state, cid):
    store_item(state, graph_for(state)[cid], '測試：獨立核對來源', 'fixture')


def test_case_question_drives_actions():
    state = game.new_game(4)
    question = case.current_question(state)
    assert question.id == state.current_question_id and question.status == 'open'
    assert not question.known_facts
    assert {a.id for a in case.available_case_actions(state)} == set(question.action_ids)
    assert all(a.question_part in question.unresolved_parts for a in case.available_case_actions(state))
    before = digest(state)
    with pytest.raises(game.InvalidAction):
        game.resolve_case_action(state, 'compare_ink', ['c2'])
    assert digest(state) == before
    dispatch(state, 'compare_seal')
    assert state.case_progress[question.id]['status'] == 'partial'
    assert set(state.evidence) == {'card_original'}
    assert 'card_ink' not in state.evidence
    assert state.evidence['card_original']['action_id'] == 'compare_seal'


def test_case_action_replaces_dual_selection():
    state = game.new_game(4)
    before = digest(state)
    with pytest.raises(game.InvalidAction, match='雙重選擇'):
        game.resolve_day(state, 'ledger', ['c1'], focus_id='inspect_seal')
    assert before == digest(state) and not game.legal_actions(state)
    assert not game.public_state(state)['investigations']
    amount = state.resources['treasury']
    dispatch(state, 'compare_seal')
    assert state.resources['treasury'] == amount - 2 + 4
    assert state.day_context['resources_changed']['treasury'] == 2


@pytest.mark.parametrize('policy', POLICIES)
def test_false_cards_months_are_causal(policy):
    state = play_game(4, policy)
    assert state.month == 12
    episodes = [r for r in state.scene_history if r['type'] == 'day']
    assert len(episodes) == 12 and all(r['scene_id'].startswith('fc_') for r in episodes)
    hooks = {h['id']: h for h in state.next_hooks}
    facts = {f['id']: f for f in state.facts}
    for episode in episodes[1:]:
        assert episode['source_hook_ids']
        for hid in episode['source_hook_ids']:
            h = hooks[hid]
            assert h['consumed'] and h['source_month'] == episode['month'] - 1
            assert all(facts[fid]['month'] == h['source_month'] for fid in h['source_fact_ids'])
    assert [d['month'] for d in state.deduction_history] == [4, 8, 11]
    assert digest(play_game(4, policy)) == digest(state)


def test_day_context_drives_night():
    seal, claim = game.new_game(4), game.new_game(4)
    dispatch(seal, 'compare_seal')
    dispatch(claim, 'question_receiver')
    for state in (seal, claim):
        frozen = deepcopy(state.day_context)
        game.start_night(state)
        assert state.night_scene['day_action_id'] == state.day_context['action_id']
        assert state.night_scene['source_fact_ids'] == frozen['fact_ids']
        game.resolve_night(state, 'review')
        assert state.day_context == frozen
    assert seal.night_scene['text'] != claim.night_scene['text']
    assert '印痕與前掌門原印' in seal.night_scene['text']
    assert '印痕與前掌門原印' not in claim.night_scene['text']
    assert not claim.evidence


def test_night_does_not_ignore_day_event(monkeypatch):
    state = at_month(3)
    monkeypatch.setattr(game, 'mission_score', lambda *args: -100)
    monkeypatch.setattr(state.rng, 'random', lambda: 0)
    dispatch(state, 'check_port')
    assert not state.day_context['success'] and state.day_context['injuries']
    game.start_night(state)
    assert state.night_scene['reason'] == 'failure'
    assert '今天新受傷' in state.night_scene['text']
    assert any(c['id'] == 'care' for c in state.night_scene['choices'])
    assert not state.evidence.get('card_dates')
    assert any(n['id'] == 'pending:card_dates' for n in state.leads)


def test_private_arc_requires_context():
    state = game.new_game(4)
    chars = [dict(id=c.id, name=c.name, present=True, arc='family_debt', stage=0, arc_established=True) for c in state.characters]
    personal = game.load_data()[2]
    assert not case.eligible_private_arcs({'context_tags':['material_supply']}, chars, personal)
    assert len(case.eligible_private_arcs({'context_tags':['merchant_debt']}, chars, personal)) == 4
    chars[0]['present'] = False
    assert len(case.eligible_private_arcs({'context_tags':['merchant_debt']}, chars, personal)) == 3
    chars[1]['arc_established'] = False
    assert len(case.eligible_private_arcs({'context_tags':['merchant_debt']}, chars, personal)) == 2
    dispatch(state, 'compare_seal')
    game.start_night(state)
    before = [c.stage for c in state.characters]
    game.resolve_night(state, 'review')
    assert [c.stage for c in state.characters] == before


def test_next_episode_uses_previous_hooks():
    review, hold = game.new_game(4), game.new_game(4)
    for state, response in ((review,'review'), (hold,'hold')):
        dispatch(state, 'compare_seal')
        game.start_night(state)
        game.resolve_night(state, response)
        game.begin_month(state)
    assert review.current_episode_id == hold.current_episode_id
    assert review.story_flags['case_variant'] != hold.story_flags['case_variant']
    costs = lambda s: {a.id:a.cost for a in case.available_case_actions(s)}
    assert costs(review)['check_workshop'] < costs(hold)['check_workshop']
    assert review.event_context['callbacks'] != hold.event_context['callbacks']
    before = digest(review)
    game.public_state(review); game.public_state(review)
    assert digest(review) == before


def test_no_random_generic_event_in_false_cards(monkeypatch):
    monkeypatch.setattr(game, 'choose_story_event', lambda *args: (_ for _ in ()).throw(AssertionError('generic mission')))
    state = play_game(4, 'highest_skill_policy')
    assert state.month == 12
    broken = deepcopy(case.definition())
    broken['episodes'].pop('7')
    with pytest.raises(ValueError, match='十二月'):
        case.validate_case_thread(broken)


@pytest.mark.parametrize('month', (4,8,11))
def test_deduction_only_uses_obtained_evidence(month):
    state = at_month(month)
    before = digest(state)
    for ids in (['merchant_claim'], ['not_obtained'], ['card_original','card_original']):
        with pytest.raises(game.InvalidAction):
            resolve_deduction(state, evidence_ids=ids)
        assert digest(state) == before
    view = checkpoint_view(state)
    assert {e['id'] for e in view['evidence']} == set(state.evidence)
    assert not {'correct_hypothesis','cross_pairs'} & view.keys()
    resolve_deduction(state, hypothesis='uncertain' if month == 4 else None)
    assert state.phase == 'deduction_result' and state.day_context['month'] == month
    before = digest(state)
    with pytest.raises(game.InvalidAction):
        game.begin_month(state)
    assert digest(state) == before
    game.start_night(state)
    assert state.night_scene['reason'] == ('final_council' if month == 11 else 'deduction')


@pytest.mark.parametrize('held', [list(c) for n in range(4) for c in combinations(('card_original','card_ink','card_witness'), n)])
def test_month10_recovery_available(held, monkeypatch):
    state = at_month(10)
    state.evidence.clear(); state.intel.clear()
    for cid in held:
        obtain(state, cid)
    original = deepcopy(state.evidence)
    missing = set(case.definition()['required_clues']) - set(held)
    if not missing:
        assert not any(a.recovery for a in case.available_case_actions(state))
        return
    monkeypatch.setattr(game, 'mission_score', lambda *args: -100)
    dispatch(state, 'recover_missing')
    assert missing <= state.evidence.keys()
    assert all(state.evidence[c] == original[c] for c in original)
    assert all(state.evidence[c]['month'] == 10 for c in missing)
    assert not chain_complete(state)


def test_low_funds_recovery_and_incapacitated_rest_are_real_paths():
    state = at_month(10)
    state.evidence.clear(); state.intel.clear()
    state.resources['treasury'] = 5
    for c in state.characters[:3]:
        c.injury = 2
    dispatch(state, 'recover_on_credit')
    assert set(case.definition()['required_clues']) <= state.evidence.keys()
    assert state.pending[-1]['effects'] == {'treasury':-4}
    game.start_night(state)
    game.resolve_night(state, 'hold')
    game.begin_month(state)
    assert state.month == 11 and state.phase == 'deduction'
    state = game.new_game(4)
    for c in state.characters:
        c.injury = 2
    game.emergency_rest(state)
    assert state.day_context['action_id'] == 'rest'
    game.start_night(state)
    game.resolve_night(state, 'hold')
    game.begin_month(state)
    assert case.legal_case_actions(state)


@pytest.mark.parametrize('mystery', ('complete','partial','unresolved'))
@pytest.mark.parametrize('sect', ('stable','weakened','collapsed'))
def test_month12_uses_two_axis_ending(mystery, sect):
    state = at_month(11)
    state.evidence.clear(); state.intel.clear()
    for cid in case.definition()['required_clues'] if mystery == 'complete' else ['card_original'] if mystery == 'partial' else []:
        obtain(state, cid)
    resolve_deduction(state, evidence_ids=case.definition()['required_clues'] if mystery == 'complete' else [])
    game.start_night(state); game.resolve_night(state, 'show_truth')
    state.resources = dict(treasury=50, defense=70 if sect == 'stable' else 46 if sect == 'weakened' else 0, reputation=30)
    for c in state.characters:
        c.status, c.injury, c.blocked_until = 'active', 0, 0
        for relation in c.relationships.values():
            relation['value'] = 0
    game.begin_month(state)
    view = game.ending_view(state)
    assert (view['mystery_axis'], view['sect_axis']) == (mystery,sect)
    assert ('門派覆滅' == state.ending) == (sect == 'collapsed')
    assert '烈川堂一直以仿刻' not in view['mystery_reveal']
    assert '問葉氏使者' not in view['mystery_reveal']


def test_atomic_tokens_team_order_and_public_projection():
    state = game.new_game(4)
    before = digest(state)
    for team,token in ((['c0','c0'],None), (['merchant'],None), (['c0'],'2:day')):
        with pytest.raises(game.InvalidAction):
            game.resolve_case_action(state,'compare_seal',team,token)
        assert digest(state) == before
    view = game.public_state(state)
    text = json.dumps(view, ensure_ascii=False)
    assert not any(s in text for s in ('"trust"','"secret"','"relationships"','"correct_hypothesis"','"supports"'))
    view['case_actions'].clear()
    assert game.public_state(state)['case_actions']
    dispatch(state,'compare_seal')
    before = digest(state)
    with pytest.raises(game.InvalidAction):
        game.resolve_case_action(state,'compare_seal',['c0'])
    assert digest(state) == before
    first = at_month(3); second = deepcopy(first)
    game.resolve_case_action(first,'check_port',['c0','c1'])
    game.resolve_case_action(second,'check_port',['c1','c0'])
    assert digest(first) == digest(second)


def test_single_failure_recovers_without_fabricating_evidence(monkeypatch):
    state = at_month(5)
    old_evidence = deepcopy(state.evidence)
    with monkeypatch.context() as m:
        m.setattr(game,'mission_score',lambda *args:-100)
        dispatch(state,'public_witness')
    assert state.evidence == old_evidence and 'card_witness' not in state.evidence
    assert any(n['id'] == 'pending:card_witness' for n in state.leads)
    while state.month < 10:
        next_step(state)
    dispatch(state,'recover_missing')
    assert 'card_witness' in state.evidence
    assert not any(n['id'] == 'pending:card_witness' for n in state.leads)


def test_early_collapse_keeps_last_scene_readable():
    state = game.new_game(4)
    dispatch(state,'compare_seal'); game.start_night(state); game.resolve_night(state,'hold')
    state.resources['treasury'] = 1
    game.begin_month(state)
    assert state.ending == '門派覆滅'
    assert game.public_state(state)['event']['title']
    assert game.ending_view(state)['sect_axis'] == 'collapsed'


@pytest.mark.parametrize('branch,axes', [
    ('complete', ('complete','stable')),
    ('partial', ('partial','stable')),
    ('unresolved', ('unresolved','weakened')),
    ('failure_recovery', ('complete','weakened')),
    ('damaged', ('complete','weakened')),
])
def test_real_case_branches_replay_all_inputs(branch, axes):
    from review_playthroughs import CASE_PLANS, run_review, replay_case
    plan = CASE_PLANS[branch]
    state, transcript, actions = run_review(plan['seed'], plan)
    assert state.month == 12 and (state.mystery_axis, state.sect_axis) == axes
    assert digest(replay_case(plan['seed'], actions)) == digest(state)
    assert not state.pending_callbacks
    if branch == 'failure_recovery':
        failed = next(r for r in state.case_history if r['phase'] == 'day' and r['month'] == 5)
        assert not failed['success'] and 'card_witness' not in failed['evidence_gained']
        assert state.evidence['card_witness']['month'] == 10
    if branch == 'unresolved':
        assert not set(case.definition()['required_clues']) & state.evidence.keys()
        assert any(c['id'] == 'courier_claim' for c in state.claims)
        assert '這是他本人的說法' in transcript
