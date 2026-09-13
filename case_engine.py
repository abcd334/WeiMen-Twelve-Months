"""Causal false-card episodes. No UI, engine callbacks, or hidden truth rendering."""
from copy import deepcopy
from itertools import combinations

from case_models import CaseAction, CaseQuestion
from data_loader import load_story_data, load_data
from models import SKILLS, RESOURCES, RISK_NAMES

CASE_ENDINGS = ('揭破陰謀', '洗清部分責任', '真相未明但守住山門', '查對案件但門派失和', '門派覆滅')


def is_case(state):
    return state.main_thread == 'false_cards'


def definition():
    return next(t for t in load_story_data()['threads'] if t['id'] == 'false_cards')


def validate_case_thread(thread):
    def require(condition, path):
        if not condition:
            raise ValueError('false_cards 資料錯誤：' + path)
    episodes, questions, actions = (thread[k] for k in ('episodes', 'questions', 'actions'))
    nodes = {n['id']: n for n in thread['evidence_graph']}
    require(len(nodes) == len(thread['evidence_graph']), 'evidence_graph 重複 ID')
    require(set(episodes) == {str(m) for m in range(1, 13)}, 'episodes 必須完整包含十二月')
    require(len({e['id'] for e in episodes.values()}) == 12, 'episode ID 唯一')
    require(len(questions) == 12 and len({e['question_id'] for e in episodes.values()}) == 12, '每月唯一問題')
    require({n['id'] for n in nodes.values() if n['critical']} == set(thread['required_clues']), '核心證據')
    require([nodes[c]['type'] for c in thread['required_clues']] == ['document', 'physical', 'witness'], '核心證據類型')
    hypotheses = {h['id'] for h in thread['hypotheses']}
    for node in nodes.values():
        require(node['thread_id'] == 'false_cards' and node['kind'] in ('evidence', 'lead', 'claim'), node['id'] + '.kind')
        require(set(node['supports'] + node['contradicts']) <= hypotheses, node['id'] + '.hypotheses')
        require(node['kind'] == 'evidence' or not node['supports'], node['id'] + ' 說法不得當作證明')
    for month, episode in episodes.items():
        path = 'episodes.' + month
        require(episode['question_id'] in questions, path + '.question_id')
        q = questions[episode['question_id']]
        require(q['action_ids'] == episode['action_ids'], path + '.action_ids')
        require(set(episode['character_views']) == set(SKILLS), path + '.character_views')
        require(all(v and all(x['thought'] and x['dialogue'] for x in v) for v in episode['character_views'].values()), path + '.dialogue')
        require(set(episode['action_ids']) <= actions.keys(), path + ' 未知 action')
        for targets in q['parts'].values():
            require(set(targets) <= nodes.keys(), path + ' 子問題 targets')
        for aid in episode['action_ids']:
            a = CaseAction(**actions[aid])
            require(a.id == aid and a.question_part in q['parts'], aid + '.question_part')
            require(a.skill in SKILLS and a.risk in RISK_NAMES and a.cost >= 0, aid + '.dispatch')
            require(a.team_size == 0 if a.kind == 'deduction' else a.team_size in (1, 2), aid + '.team_size')
            require((a.kind == 'deduction') == (int(month) in (4, 8, 11)), aid + '.kind')
            for kind, targets in (('evidence', a.possible_evidence), ('claim', a.possible_claims), ('lead', a.possible_leads)):
                require(all(cid in nodes and nodes[cid]['kind'] == kind for cid in targets), aid + '.targets')
            require(set(a.resource_effects) | set(a.failure_effects) <= RESOURCES.keys(), aid + '.resources')
            require(set(a.next_hooks) <= thread['hook_definitions'].keys(), aid + '.next_hooks')
            require(not a.requires_lead or a.requires_lead == thread['cross_lead']['id'], aid + '.requires_lead')
        if int(month) < 12:
            require(episode['next_hook'] in thread['hook_definitions'], path + '.next_hook')
            require(thread['hook_definitions'][episode['next_hook']]['target_month'] == int(month) + 1, path + ' hook 必須前進一月')
        else:
            require(not episode['action_ids'] and not episode['next_hook'], path + ' 結局不可循環')
    require(len(thread['cross_pairs']) == len(thread['cross_reasons']), 'cross_reasons')
    for pair in thread['cross_pairs']:
        require(len(set(pair)) == 2 and all(nodes.get(cid, {}).get('kind') == 'evidence' for cid in pair), 'cross_pairs')
    require({p['evidence_id'] for p in thread['recovery_paths']} == set(thread['required_clues']), 'recovery paths')
    for path in thread['recovery_paths']:
        require(10 in path['months'] and all(a in episodes['10']['action_ids'] and actions[a]['stable'] and path['evidence_id'] in actions[a]['possible_evidence'] for a in path['action_ids']), '第十月補證來源')


def current_episode(state):
    if state.phase == 'ended' and state.current_episode_id:
        return next(e for e in definition()['episodes'].values() if e['id'] == state.current_episode_id)
    episode = definition()['episodes'][str(state.month)]
    if state.current_episode_id and episode['id'] != state.current_episode_id:
        raise ValueError('案件月份與已選定事件不符。')
    return episode


def select_next_episode(state):
    episode = definition()['episodes'][str(state.month)]
    due = sorted((h for h in state.next_hooks if h['due_month'] == state.month and not h['consumed']),
                 key=lambda h: (h['priority'], h['id']))
    if state.month > 1 and not due:
        raise ValueError('下一月缺少上一事件留下的原因。')
    if any(h['source_month'] >= state.month or h['target_episode'] != episode['id'] for h in due):
        raise ValueError('案件承接來源或目標月份不符。')
    for hook in due:
        hook['consumed'] = True
    state.current_episode_id = episode['id']
    state.current_question_id = episode['question_id']
    state.story_flags['case_arrival'] = deepcopy(due)
    state.story_flags['case_variant'] = due[0]['variant'] if due else 'opening'
    return episode


def available_case_actions(state):
    episode = current_episode(state)
    result = []
    for aid in episode['action_ids']:
        action = CaseAction(**deepcopy(definition()['actions'][aid]))
        if action.requires_lead and not any(n['id'] == action.requires_lead for n in state.leads):
            continue
        if action.recovery:
            if set(definition()['required_clues']) <= state.evidence.keys():
                continue
            action.possible_evidence = [cid for cid in action.possible_evidence if cid not in state.evidence]
        variant = state.story_flags.get('case_variant')
        if action.cost and not action.recovery:
            if variant == 'review':
                action.cost = max(0, action.cost - 1)
            elif variant == 'hold' and action.skill == 'diplomacy':
                action.cost += 1
        result.append(action)
    return result


def legal_case_actions(state):
    if not is_case(state) or state.phase != 'day':
        return []
    return [(action, [c.id for c in team]) for action in available_case_actions(state)
            if action.kind == 'investigation' and action.cost < state.resources['treasury']
            for team in combinations(state.actionable(), action.team_size)]


def refresh_progress(state):
    for qid, q in definition()['questions'].items():
        prior = state.case_progress.get(qid, {})
        if prior.get('deduction'):
            continue
        answered = {part: [cid for cid in targets if cid in state.evidence] for part, targets in q['parts'].items()}
        done = [part for part, targets in answered.items() if targets]
        status = 'resolved' if answered and len(done) == len(answered) else 'partial' if done else 'open'
        state.case_progress[qid] = dict(status=status, answered_parts=done,
                                        evidence_ids=list(dict.fromkeys(cid for ids in answered.values() for cid in ids)))


def current_question(state):
    q = definition()['questions'][state.current_question_id]
    progress = state.case_progress.get(q['id'], {})
    known = [state.evidence[cid]['text'] for cid in progress.get('evidence_ids', []) if cid in state.evidence]
    # Prior findings are always explicitly obtained; openings never manufacture proof.
    if not known:
        known = [e['text'] for e in state.evidence.values()]
    return CaseQuestion(q['id'], q['text'], known,
                        [p for p in q['parts'] if p not in progress.get('answered_parts', [])],
                        [a.id for a in available_case_actions(state)], progress.get('status', 'open'))


def public_actions(state):
    nodes = {n['id']: n for n in definition()['evidence_graph']}
    known = state.evidence.keys() | {n['id'] for n in state.claims + state.leads}
    result = []
    for a in available_case_actions(state):
        targets = a.possible_evidence + a.possible_claims + a.possible_leads
        result.append(dict(id=a.id, label=a.label, description=a.description, question_part=a.question_part,
            skill=SKILLS[a.skill], count=a.team_size, cost=a.cost, risk=RISK_NAMES[a.risk], kind=a.kind,
            possible_materials=[nodes[cid]['title'] for cid in targets],
            already_known=bool(targets) and all(cid in known for cid in targets),
            hint='可核對原簿或封存留底，取得不依賴隱藏心理。' if a.stable else '需當場接上獨立來源；受阻只留下待查方向。',
            affected_resources=[RESOURCES[k] for k in a.resource_effects], recovery=a.recovery))
    return result


def event_view_data(state):
    e = current_episode(state)
    npcs = {n['id']: n for n in load_story_data()['npcs']}
    return dict(id=e['id'], title=e['title'], description=e['opening'], scene_opening=e['opening'],
                current_question=definition()['questions'][e['question_id']]['text'],
                npc_identity='、'.join(npcs[n]['identity'] + '・' + npcs[n]['name'] for n in e['npc_refs']),
                npc_refs=e['npc_refs'], tags=['hostile'] if e['kind'] == 'finale' else [],
                key_decision=True, concrete_detail=e['title'], character_views=e['character_views'],
                options=[], character_hooks=[])


def dispatch_spec(action):
    """Adapt one action to shared fatigue/injury/resource rules, not a second choice."""
    return dict(id=action.id, label=action.label, cost=action.cost, skill=action.skill,
        count=action.team_size, risk=action.risk, difficulty=action.difficulty, ability_modifier=1,
        background_modifiers={}, extra_hints=[], visible_hint=action.description,
        affected_resources=list(action.resource_effects), delayed=None, flags=[], intel=[],
        success={k: [v, v] for k, v in action.resource_effects.items()},
        failure={k: [v, v] for k, v in action.failure_effects.items()},
        success_text=action.success_text, failure_text=action.failure_text)


def make_hook(state, fact_ids, variant, text, *, priority=0, phase='night'):
    episode = current_episode(state)
    if not episode['next_hook']:
        return None
    target = definition()['episodes'][str(state.month + 1)]['id']
    return dict(id=f'{state.month}:{phase}:{variant}', source_month=state.month, source_phase=phase,
                source_fact_ids=list(fact_ids), target_episode=target, due_month=state.month + 1,
                priority=priority, variant=variant, text=text, consumed=False)


def capture_day(state, action_id, participants, success, before, fact_ids, *, deduction=None, tags=()):
    evidence = [cid for cid in state.evidence if cid not in before['evidence']]
    claims = [n['id'] for n in state.claims if n['id'] not in before['claims']]
    leads = [n['id'] for n in state.leads if n['id'] not in before['leads']]
    injuries = [dict(character_id=c.id, before=before['injuries'][c.id], after=c.injury) for c in state.characters
                if c.injury > before['injuries'][c.id]]
    relationships = []
    for c in state.characters:
        for other, r in c.relationships.items():
            if c.id < other:
                prev = before['relationships'].get((c.id, other), 0)
                if r['value'] != prev:
                    relationships.append(dict(participants=[c.id, other], delta=r['value'] - prev))
    context_tags = list(dict.fromkeys(current_episode(state)['context_tags'] + list(tags)
                        + (['mission_failure'] if not success and not deduction else [])
                        + (['injury'] if injuries else [])
                        + (['relationship_conflict'] if any(r['delta'] < 0 for r in relationships) else [])))
    hook_facts = list(dict.fromkeys([state.evidence[cid]['fact_id'] for cid in evidence] + list(fact_ids)))
    hook = make_hook(state, hook_facts, 'progress' if success else 'retry',
                     current_episode(state)['next_text'], priority=1, phase='day')
    state.day_context = dict(month=state.month, episode_id=state.current_episode_id,
        question_id=state.current_question_id, action_id=action_id, participants=list(participants), success=success,
        evidence_gained=evidence, claims_gained=claims, lead_ids=leads,
        resources_changed={k: state.resources[k] - v for k, v in before['resources'].items()},
        injuries=injuries, relationship_changes=relationships, next_hooks=[deepcopy(hook)] if hook else [],
        fact_ids=list(fact_ids), context_tags=context_tags, deduction_result=deepcopy(deduction or {}))
    state.case_history.append(dict(phase='day', **deepcopy(state.day_context)))
    if hook:
        state.next_hooks.append(hook)
    refresh_progress(state)
    if deduction:
        supported = deduction['accepted'] and deduction.get('hypothesis') != 'uncertain'
        state.case_progress[state.current_question_id] = dict(deduction=True,
            status='resolved' if supported else 'partial' if deduction['evidence_ids'] else 'open',
            answered_parts=list(definition()['questions'][state.current_question_id]['parts']) if supported else [],
            evidence_ids=deduction['evidence_ids'])


def snapshot(state):
    return dict(resources=dict(state.resources), evidence=set(state.evidence),
        claims={n['id'] for n in state.claims}, leads={n['id'] for n in state.leads},
        injuries={c.id: c.injury for c in state.characters},
        relationships={(c.id, other): r['value'] for c in state.characters for other, r in c.relationships.items()})


def eligible_private_arcs(context, characters, personal):
    tags = set(context['context_tags'])
    arcs = {a['id']: a for a in personal['arcs']}
    return [c for c in characters if c['present'] and c.get('arc_established', False)
            and tags & set(arcs[c['arc']].get('trigger_context', []))]


def night_choice(cid, label, hint, effects, psych, *, cost=0, approach='defer', **extra):
    return dict(id=cid, label=label, hint=hint, cost=cost, effects=effects,
                psych=dict(trust=psych, stress=-psych, loyalty=psych // 2), approach=approach,
                tradeoffs=[hint, '原有證據及未解部分仍需分開說明'], delayed=None,
                reaction=label + '。眾人把引用範圍與接手的人寫在本次記錄旁。', **extra)


def build_night_from_day_context(context, characters, evidence, personal, spotlights):
    """Selection only sees the day record and an explicit character projection."""
    active = [c for c in characters if c['present']]
    if not active:
        raise ValueError('無人在門，不能建立夜談。')
    ordered = sorted(active, key=lambda c: (c['id'] not in context['participants'], spotlights.get(c['id'], 0), c['id']))
    private = eligible_private_arcs(context, characters, personal)
    sources = context['fact_ids']
    gained = [evidence[cid] for cid in context['evidence_gained'] if cid in evidence]
    deduction = context['deduction_result']
    kind, reason, arc_id = 'mainline_scene', 'evidence', None
    extra = []
    if 'final_council' in context['context_tags']:
        speakers = active
        lines = ['明日上斷劍臺前，你請仍在門內的人各說：「明天最確定的是什麼？」', deduction.get('text', '')]
        for i, c in enumerate(speakers):
            known = list(evidence.values())
            answer = known[i % len(known)]['text'] if known else '目前沒有足以串起主線的核心材料，我不會替空缺作證。'
            lines.append(c['name'] + '：『' + answer + '』')
        lines.extend(c['name'] + '的位置留著空碗；今晚沒有人替不在場的人回答。' for c in characters if not c['present'])
        choices = [night_choice(cid, label, '決定明日的共同提醒，不取代證據、人手與資源。', {}, 0, approach=approach)
                   for cid, label, approach in (('keep_people','明日先保人','support'),('hold_gate','明日先守山','discipline'),('show_truth','明日先揭真相','defer'))]
        kind, reason, title = 'group_scene', 'final_council', '留下來的人，各說一件確定的事'
    else:
        speakers = ordered[:2]
        if deduction:
            reason, title = 'deduction', '這個判斷能說到哪裡'
            supported = deduction['accepted'] and deduction.get('hypothesis') != 'uncertain'
            lines = [deduction['text'], speakers[0]['name'] + ('問：「依據已列清，下一次要請誰核對交付？」' if supported else '問：「還沒接上的部分，明天要怎麼向對方說明？」')]
        elif gained:
            title = '今天帶回的材料，明天怎麼使用'
            lines = [speakers[0]['name'] + '把今天查得的材料攤開：'] + [e['text'] for e in gained]
            lines.append('「現在公開這些已知部分、暫時保留，還是請第二人重做核對？」')
        elif not context['success']:
            reason, title = 'failure', '受阻之後，先把缺口說清'
            lines = [speakers[0]['name'] + '帶著今天受阻的查問記錄：「這次沒有接上來源。先向對方說明，或安排下一次核對，都得留下具體範圍。」']
        elif context['injuries']:
            reason, title = 'injury', '把今天受傷的人接回來'
            ids = {r['character_id'] for r in context['injuries']}
            speakers = sorted(active, key=lambda c: c['id'] not in ids)[:2]
            lines = [speakers[0]['name'] + '把傷處交給同門查看：「今天的交接我能說明，接下來的班次需要有人接手。」']
        elif any(r['delta'] < 0 for r in context['relationship_changes']):
            kind, reason, title = 'relationship_scene', 'conflict', '同一次交接，兩個人的代價'
            lines = [c['name'] + '把今天自己負責的交接部分列在紙上。' for c in speakers]
            lines.append('有人要求下次先說清楚分工，再替同伴答應新的差事。')
        elif context.get('source_items'):
            reason, title = 'source', '今天聽來的話，還差哪一步核實'
            lines = [speakers[0]['name'] + '將今天留下的說法與線索另夾一頁：']
            lines.extend(item['text'] for item in context['source_items'])
            lines.append('「這些還不能作證。公開時要保留來源，或再找獨立記錄核對。」')
        elif private:
            kind, reason, title = 'personal_scene', 'private', '今天的事，牽到自己的難處'
            owner = private[0]
            speakers = [owner] + [c for c in ordered if c['id'] != owner['id']][:1]
            arc_id = owner['arc']
            arc = next(a for a in personal['arcs'] if a['id'] == arc_id)
            text = arc['scenes'][min(owner['stage'], 2)]['text']
            lines = [text.format(name=owner['name'], other=speakers[-1]['name'])]
        else:
            kind, reason, title = 'quiet_scene', 'quiet', '先收好今天的說法'
            lines = ['眾人將今天留下的說法與待查部分分開收好。沒有新證明可宣布，今晚先安排歇息與保管。']
        choices = [
            night_choice('publish','公開已核實的部分','只引用已得證據；下月對方會要求對公開內容當面答覆。', {'reputation':4},2,approach='support',strategy='public'),
            night_choice('hold','保留材料，先補守備與交接','下月重新約見需要額外說明；今晚先維持值勤。', {'defense':4,'treasury':1},-3,approach='discipline',strategy='hold'),
            night_choice('review','找第二人複核並協調分工','共同複核既有材料、協調分工，為下一次查證節省一份交接成本；不補發缺件。', {'defense':1},4,cost=1,approach='defer',strategy='review',relationship_delta=4,recovery=12,partner_recovery=12)]
        if not evidence:
            choices[0].update(label='公開目前尚無定論', reaction='向來客明說尚無定論，沒有把口供當作證據。')
        if private and reason != 'private':
            owner = private[0]
            arc = next(a for a in personal['arcs'] if a['id'] == owner['arc'])
            extra.append('今天的情境也讓' + owner['name'] + '提起自己的難處：' + arc['scenes'][min(owner['stage'],2)]['text'].format(name=owner['name'],other=speakers[-1]['name']))
        if private:
            owner = private[0]
            if owner not in speakers:
                speakers.append(owner)
            choices.append(night_choice('private_support','一起處理這次牽涉的私人難處','讓當事人說明今天的事如何影響自己，另排交接；不將私事當案件證明。',
                {'defense':-1},4,cost=2,approach='support',private_owner=owner['id'],private_arc=owner['arc'],strategy='review',recovery=12))
        if context['injuries']:
            injured_names = [c['name'] for c in active if any(r['character_id']==c['id'] for r in context['injuries'])]
            extra.append('今天新受傷的' + '、'.join(injured_names) + '需要交接與照護；傷勢不能被桌上的材料蓋過。')
            choices.append(night_choice('care','先照護今天受傷的人','買藥、減班，既有證據仍封存；這次先保人。',{'defense':-1},4,cost=2,approach='support',care_ids=[r['character_id'] for r in context['injuries']],strategy='hold'))
        action_label = context.get('action_label', context['action_id'])
        materials = '、'.join(e['title'] for e in gained) or '這次留下的來源與待查範圍'
        for choice in choices:
            if choice['id'] == 'publish':
                choice['reaction'] = speakers[0]['name'] + '向來客說明「' + action_label + '」的結果，將' + materials + '分清已知與未解後逐項登記；下次當面答覆不超出這份記錄。'
            elif choice['id'] == 'hold':
                choice['reaction'] = speakers[0]['name'] + '封存「' + action_label + '」的記錄，先補上守門交接與輪值；需要公開的部分留待下次重新約見。'
            elif choice['id'] == 'review':
                reviewer = next((c['name'] for c in speakers if c['id'] not in context['participants']), '郭問舟')
                choice['reaction'] = reviewer + '接過「' + action_label + '」的記錄，複核已有來源並列明缺件；第二人的檢核不替尚未取得的材料下結論。'
            elif choice['id'] == 'private_support':
                owner = next(c for c in private if c['id'] == choice['private_owner'])
                arc = next(a for a in personal['arcs'] if a['id'] == owner['arc'])
                choice['reaction'] = owner['name'] + '因今天「' + action_label + '」而說清私人負擔。' + arc['resolutions']['support']
            elif choice['id'] == 'care':
                choice['reaction'] = '照護「' + action_label + '」中受傷的' + '、'.join(injured_names) + '，讓傷者先減班，手上的查證材料另由留守者保管。'
    return dict(id=f"case_night:{context['month']}:{reason}", title=title, kind=kind, reason=reason,
                speakers=[c['id'] for c in speakers], text='\n\n'.join(lines + extra),
                context='白天處理：' + context.get('action_label', context['action_id']), choices=choices,
                arc_id=None, source_fact_ids=list(sources), day_action_id=context['action_id'],
                source_month=context['month'])


def ending_axes(state, chain_complete):
    mystery = 'complete' if chain_complete else 'partial' if set(definition()['required_clues']) & state.evidence.keys() else 'unresolved'
    active, ready = state.active(), state.actionable()
    survived = state.resources['treasury'] > 0 and len(active) >= 2 and (state.resources['defense'] >= 45 or state.resources['reputation'] >= 50)
    conflict = any(r['value'] < -15 for c in active for oid, r in c.relationships.items() if oid in {x.id for x in active})
    stable = survived and len(active) >= 3 and len(ready) >= 2 and state.resources['defense'] >= 60 and not conflict
    sect = 'collapsed' if not survived or state.ending == '門派覆滅' else 'stable' if stable else 'weakened'
    return mystery, sect


def ending_result(state, chain_complete):
    mystery, sect = ending_axes(state, chain_complete)
    title = ('門派覆滅' if sect == 'collapsed' else
             ('揭破陰謀' if sect == 'stable' else '查對案件但門派失和') if mystery == 'complete' else
             '洗清部分責任' if mystery == 'partial' else '真相未明但守住山門')
    reasons = {'stable':'留門人手、可出勤人員、守備與同門合作仍能支撐山門。',
               'weakened':'山門仍守住，但人手、守備或同門合作至少有一項未恢復。',
               'collapsed':'糧餉、人手、守備或聲援不足以維持山門。'}
    if sect == 'weakened':
        deficits = []
        if len(state.active()) < 3:
            deficits.append('留門人手不足')
        if len(state.actionable()) < 2:
            deficits.append('可出勤人員不足')
        if state.resources['defense'] < 60:
            deficits.append('山門守備仍待修復')
        active_ids = {c.id for c in state.active()}
        if any(r['value'] < -15 for c in state.active() for oid, r in c.relationships.items() if oid in active_ids):
            deficits.append('同門間仍有未解的合作衝突')
        reasons['weakened'] = '山門仍守住，但' + '、'.join(deficits) + '。'
    proofs = [e['fact_id'] for e in state.evidence.values()]
    proofs += [fid for d in state.deduction_history for fid in d['fact_ids']]
    return title, reasons[sect], proofs, mystery, sect


def mystery_reveal(state, complete):
    if complete:
        text = '文件、物證與具名人證接成了假名帖的證據鏈，這些爭議承諾不能認作青崖門的正式授權。'
    elif state.evidence:
        text = '已核實的部分可以逐件說明，仍不足以完整證明假名帖的交付鏈。'
    else:
        text = '目前只有說法與待查方向，尚未取得可組成證據鏈的材料。'
    text += '\n' + '\n'.join(e['text'] for e in state.evidence.values())
    text += '\n前掌門此後的去向仍未查明。'
    return text
