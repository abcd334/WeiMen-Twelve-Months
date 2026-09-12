"""Deterministic twelve-month simulation. UI reads only explicit public projections."""
from itertools import combinations
from random import Random
from copy import deepcopy

from data_loader import load_data, load_story_data
from models import Character, Cue, GameState, RESOURCES, RISK_NAMES, SKILLS, GAME_VERSION
import narrative
import investigation

ENDINGS = ("揭破陰謀", "聯盟退敵", "正面取勝", "慘勝守山", "門派覆滅")


class InvalidAction(ValueError):
    pass


def clamp(value):
    return max(0, min(100, value))


def generate_characters(rng):
    templates, _, personal = load_data()
    names = rng.sample([s + n for s in templates["surnames"] for n in templates["given_names"]], 4)
    signatures = rng.sample(templates["signatures"], 4)
    backgrounds = rng.sample(templates["backgrounds"], 4)
    characters = []
    for i, role in enumerate(SKILLS):
        bg = backgrounds[i]
        compatible = [s for s in templates["secrets"] if set(s["requires"]) <= set(bg["tags"])]
        # Guarantee a mainline secret, never guarantee disloyalty or an infiltrator.
        if i == 3 and not any(c.secret["mainline"] for c in characters):
            compatible = [s for s in compatible if s["mainline"]]
        secret = rng.choice(compatible)
        skills = {skill: min(4, rng.randint(1, 3) + bg["bonuses"].get(skill, 0)) for skill in SKILLS}
        skills[role] = rng.randint(4, 5)
        characters.append(Character(
            id=f"c{i}", name=names[i], age=rng.randint(19, 39), role=role, skills=skills,
            personality=rng.choice(templates["personalities"]), background=bg,
            goal=rng.choice(templates["goals"]), fear_text=rng.choice(templates["fears"]),
            secret=secret, signature=signatures[i],
            arc=secret["arc"] or rng.choice(personal["arcs"])["id"],
            trust=rng.randint(44, 65), loyalty=rng.randint(48, 72),
            stress=rng.randint(12, 30), ambition=rng.randint(20, 80), fear=rng.randint(15, 60)))
    # A ring gives every character a relationship and four distinct pairs.
    for i, char in enumerate(characters):
        other = characters[(i + 1) % 4]
        relation = dict(rng.choice(templates["relationships"]))
        char.relationships[other.id] = dict(relation)
        other.relationships[char.id] = dict(relation)
    return characters


def new_game(seed):
    if not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise InvalidAction("種子須為 0 到 4294967295 的整數。")
    rng = Random(seed)
    state = GameState(seed=seed, rng=rng, characters=generate_characters(rng), version=GAME_VERSION)
    state.main_thread = rng.choice(load_story_data()["threads"])["id"]
    state.spotlight_counts = {c.id: 0 for c in state.characters}
    for char in state.characters:
        char.voice = dict(load_data()[0].get("voice_profiles", {}).get(char.personality, {}))
        char.voice["background_line"] = load_data()[0].get("voice_modifiers", {}).get(char.background["id"], "")
        if "主事" in char.signature:
            char.voice["address"] = "主事"
        char.stance = rng.choice(load_data()[0].get("stances", ["同門優先"]))
    if state.main_thread == "old_letters":
        contact = next((c for c in state.characters if c.secret["id"] == "contact"), state.characters[-1])
        if contact.secret["id"] != "contact":
            contact.secret = next(s for s in load_data()[0]["secrets"] if s["id"] == "contact")
            contact.arc = "enemy_ties"
        state.story_flags["contact_character"] = contact.id
    begin_month(state)
    return state


def current_event(state):
    base = next(e for e in load_data()[1]["events"] if e["id"] == state.event_id)
    overlay = investigation.case_scene(state)
    if overlay.get("event_id") != state.event_id:
        return base
    event = deepcopy(base)
    event.update({k:v for k,v in overlay.items() if k not in ("event_id", "focus_ids")})
    event["description"] = event["scene_opening"]
    event["concrete_detail"] = overlay.get("concrete_detail", base["concrete_detail"])
    event["npc_identity"] = "、".join(n["identity"] + "・" + n["name"] for n in load_story_data()["npcs"] if n["id"] in event["npc_refs"])
    for option in event["options"]:
        option["intel"] = []
    return event


def current_thread(state):
    return next(t for t in load_story_data()["threads"] if t["id"] == state.main_thread)


def public_character_context(state, char):
    """Boundary for narrative.py: no secret, psychology, or raw relationships."""
    public = char.public(state.month)
    public.update(voice=dict(char.voice), background_id=char.background["id"],
                  role_id=char.role, **load_data()[0]["role_judgments"][char.role],
                  stance_line=load_data()[0].get("stance_lines", {}).get(char.stance, "先說清楚今天要守住什麼。"))
    return public


def add_callback(state, fact_id, text, due=None, speaker=None):
    state.pending_callbacks.append({"due": due or min(11, state.month + 2),
                                    "source": fact_id, "text": text, "speaker": speaker})


def prepare_story_event(state, event):
    thread = current_thread(state)
    related = ((state.main_thread == "false_cards" and state.month != 6) or event["id"] in thread["event_links"] or state.month in (1, 4, 8, 12)
               or (state.month == 10 and not any(b["beat"] == "payoff" for b in state.thread_beats)))
    beat = "setup" if state.month <= 3 else "escalation" if state.month <= 8 else "payoff"
    callbacks = []
    for pending in list(state.pending_callbacks):
        if pending["due"] <= state.month and len(callbacks) < 2:
            source = next(f for f in state.facts if f["id"] == pending["source"])
            text = pending["text"]
            if pending.get("speaker"):
                speaker = state.character(pending["speaker"])
                if speaker.status != "active":
                    text = text.replace(speaker.name + "提起", "眾人想起與" + speaker.name + "談過的", 1)
            callback = {"month": state.month, "source_id": source["id"],
                        "text": f"第 {source['month']} 月留下的事又被提起：{text}"}
            callbacks.append(callback)
            state.callback_history.append(callback)
            state.pending_callbacks.remove(pending)
    evidence = []
    if state.month == 8:
        # Always choose actual past records, including uncertainty; never fabricate a suspect.
        prior = [f for f in state.facts if f["month"] < 8 and f["kind"] in ("intel", "story", "evidence")]
        external_ids = {q.id for q in state.observations if q.category in ("external", "betrayal")}
        uncertain = [f for f in prior if f["source"] in external_ids]
        confirmed = [f for f in prior if f["kind"] == "intel"]
        # Prefer a real suspicious observation, a verified clue, and the original
        # contradiction. Routine character reactions are not evidence.
        evidence = list({f["id"]: f for f in uncertain[-1:] + confirmed[-1:] + prior[:1] + prior[-2:]}.values())[:3]
        state.story_flags["suspicion_evidence"] = [f["id"] for f in evidence]
        candidates = [q.character_id for q in state.observations if q.category in ("external", "betrayal")]
        suspect = next((c for c in state.active() if c.id in candidates), None)
        state.story_flags["suspect"] = suspect.id if suspect else ""
    opening = event.get("scene_opening", event["description"])
    for npc_id in event.get("npc_refs", []):
        memory = state.story_flags.get(f"npc:{npc_id}")
        if memory and len(callbacks) < 2:
            npc = next(n for n in load_story_data()["npcs"] if n["id"] == npc_id)
            response = "這回我願意先把手上的原件留下，再談新的安排。" if memory["success"] else "上回還有沒辦妥的部分，這次請先說明誰負責核對，我再答應。"
            item = {"month": state.month, "source_id": memory["fact_id"],
                    "text": f"{npc['identity']}・{npc['name']}提起第 {memory['month']} 月的安排：「你那回選擇『{memory['choice']}』，我還記得。{response}」"}
            callbacks.append(item)
            state.callback_history.append(item)
    beat_index = sum(b["beat"] == beat for b in state.thread_beats)
    beat_texts = thread["beat_texts"][beat]
    beat_text = (event["current_question"] if state.main_thread == "false_cards" else beat_texts[min(beat_index, len(beat_texts) - 1)]) if related else ""
    state.event_context = {"opening": opening, "hooks": event.get("character_hooks", []),
                           "character_views": event["character_views"], "key": (state.seed,state.month,event["id"]),
                           "callbacks": callbacks, "evidence": [dict(f) for f in evidence],
                           "thread_beat": "" if state.main_thread == "false_cards" else beat_text, "related": related}
    if related:
        fid = record_fact(state, beat_text, "story", state.main_thread)
        state.thread_beats.append({"month": state.month, "beat": beat, "fact_id": fid})
        if state.month in (1, 4, 8):
            add_callback(state, fid, f"{thread['object']}仍留在議事桌上。當時的問題是：{thread['question']}", min(11, state.month + 2))
    state.scene_history.append({"month": state.month, "type": "day", "scene_id": event["id"],
                                "related": related, "text": narrative.render_event_opening(state.event_context),
                                "evidence_ids": [f["id"] for f in evidence]})


def choose_story_event(state, events):
    pool = [e for e in events if event_eligible(state, e)]
    linked = [e for e in pool if e["id"] in current_thread(state)["event_links"]]
    if state.month == 2:
        backgrounds = {c.background["id"] for c in state.active()}
        personal = [e for e in pool if any(h["background"] in backgrounds for h in e.get("character_hooks", []))]
        return state.rng.choice([e for e in linked if e in personal] or personal or linked or pool)
    last = [s for s in state.scene_history if s["type"] == "day"][-2:]
    if len(last) == 2 and all(s["related"] for s in last):
        pressure = [e for e in pool if e not in linked]
        return state.rng.choice(pressure or pool)
    if state.month in (2, 5, 7, 9) and linked:
        return state.rng.choice(linked)
    return state.rng.choice(pool)


def mystery_complete(state):
    return investigation.chain_complete(state)


def contact_unavailable(state):
    if state.main_thread != "old_letters":
        return False
    contact = state.character(state.story_flags["contact_character"])
    return contact.status != "active" or contact.blocked_until >= state.month


def record_fact(state, text, kind="event", source=None):
    fact = {"id": f"f{len(state.facts)}", "month": state.month, "text": text,
            "kind": kind, "source": source}
    state.facts.append(fact)
    return fact["id"]


def record_decision(state, label, fact_ids, important=False):
    decision = {"id": f"d{len(state.decisions)}", "month": state.month, "label": label,
                "facts": list(fact_ids), "important": important}
    state.decisions.append(decision)
    return decision


def apply_resources(state, effects, text):
    changes = {}
    for key, delta in effects.items():
        before = state.resources[key]
        state.resources[key] = clamp(before + delta)
        changes[key] = state.resources[key] - before
    suffix = "、".join(f"{RESOURCES[k]} {v:+d}" for k, v in changes.items() if v)
    line = text + (f"（{suffix}）" if suffix else "（公共資源未變）")
    state.logs.append({"month": state.month, "text": line})
    return record_fact(state, line, "resource")


def finish(state, ending, reason, evidence=None):
    state.ending, state.ending_reason = ending, reason
    state.ending_evidence = evidence or []
    state.phase = "ended"
    record_fact(state, reason, "ending")


def check_failure(state, hostile=False):
    reason = ""
    if state.resources["treasury"] <= 0:
        reason = "糧餉耗盡，眾人已無法維持山門，青崖門解散。"
    elif not state.active():
        reason = "四名核心弟子均已不在門內，青崖門瓦解。"
    elif state.resources["defense"] <= 0 and hostile:
        reason = "敵對事件發生時，山門已無防備，烈川堂乘隙攻入。"
    if reason:
        finish(state, "門派覆滅", reason)
    return bool(reason)


def event_eligible(state, event):
    t = event["trigger"]
    return (not event.get("fixed_month") and event["id"] not in state.seen_events
            and t["min_month"] <= state.month <= t["max_month"]
            and state.resources["reputation"] >= t["min_reputation"]
            and not (state.resources["reputation"] == 0 and set(event["tags"]) & {"aid", "high_reward"}))


def begin_month(state):
    if state.phase not in ("new", "night_result", "deduction_result") or state.ending:
        raise InvalidAction("尚未完成本月夜談。")
    if state.phase == "night_result" and state.month in (4,8,11) and f"{state.month}:deduction" not in state.resolved:
        state.phase = "deduction"
        state.last_result = []
        return
    state.month += 1
    state.phase = "day"
    state.last_result = []
    for pending in list(state.pending):
        if pending["due"] <= state.month:
            fid = apply_resources(state, pending["effects"], "延遲後果：" + pending["text"])
            if pending.get("decision"):
                next(d for d in state.decisions if d["id"] == pending["decision"])["facts"].append(fid)
            state.last_result.append(state.facts[-1]["text"])
            state.pending.remove(pending)
    apply_resources(state, {"treasury": -3}, "每月維持費")
    for char in state.active():
        resting = char.id not in state.last_participants
        char.fatigue = clamp(char.fatigue - (24 if resting else 8))
        char.stress = clamp(char.stress - (7 if resting else 3))
        if resting and char.injury:
            char.injury -= 1
            char.experiences.append(f"第 {state.month} 月：留門休養後，傷勢有所好轉。")
            char.recent = "留門休養後，傷勢有所好轉。"
            char.recent_month = state.month
    if check_failure(state):
        return
    events = load_data()[1]["events"]
    fixed = next((e for e in events if e.get("fixed_month") == state.month), None)
    schedule = investigation.case_scene(state)
    event = next(e for e in events if e["id"] == schedule["event_id"]) if schedule else fixed or choose_story_event(state, events)
    state.event_id = event["id"]
    event = current_event(state)
    state.seen_events.append(event["id"])
    if check_failure(state, "hostile" in event["tags"]):
        return
    prepare_story_event(state, event)
    if state.month == 1:
        investigation.store_item(state, investigation.graph_for(state)[state.main_thread + "_claim"], event["npc_identity"])
    if state.month == 12:
        ending, reason, evidence = determine_ending(state)
        finish(state, ending, reason, evidence)


def public_option(state, option, participant_ids=()):
    hints = [h["text"] for h in option["extra_hints"] if h["requires_intel"] in state.intel]
    selected = [state.character(cid) for cid in participant_ids]
    for char in selected:
        if set(char.background["tags"]) & option["background_modifiers"].keys():
            hints.append(f"{char.name}的公開背景「{char.background['name']}」可能有助處理此事。")
    if state.event_id == "suspicion" and "pattern" in state.intel:
        hints.append("先前已查到敵方會同時安排明暗兩路；抄件流出與門內通敵仍須分開查證。")
    return {"id": option["id"], "label": option["label"], "cost": option["cost"],
            "skill": SKILLS[option["skill"]], "count": option["count"],
            "risk": RISK_NAMES[option["risk"]], "hint": option["visible_hint"],
            "affected_resources": [RESOURCES[k] for k in option["affected_resources"]],
            "delayed": option["delayed"] is not None, "extra_hints": hints,
            "character_hooks": narrative.render_assignment_preview(state.event_context, [public_character_context(state, c) for c in selected])}


def public_state(state):
    event = current_event(state) if state.event_id else None
    return {"seed": state.seed, "month": state.month, "phase": state.phase,
            "resources": {RESOURCES[k]: v for k, v in state.resources.items()},
            "characters": [{**c.public(state.month), **load_data()[0]["role_judgments"][c.role], **narrative.render_character_opinion(state.event_context, public_character_context(state,c))} for c in state.characters],
            "chapter": ("人還在一起" if state.month <= 3 else "事情不是表面那樣" if state.month <= 7 else "開始懷疑自己人" if state.month <= 10 else "留下來的人"),
            "event": {"title": event["title"], "description": narrative.render_event_opening({**state.event_context, "callbacks": []}),
                      "callbacks": [dict(c) for c in state.event_context.get("callbacks", [])],
                      "npc_identity":event["npc_identity"], "current_question":event["current_question"],
                      "reactions": [],
                      "options": [public_option(state, o) for o in event["options"]]} if event else None,
            "evidence_board": investigation.evidence_board(state),
            "investigations": investigation.public_investigations(state) if state.phase == "day" else [],
            "observations": [c.public() for c in state.observations],
            "intel": list(state.intel.values()), "logs": [dict(log) for log in state.logs],
            "flags": [load_data()[1]["flags"][f] for f in sorted(state.flags)],
            "last_result": list(state.last_result)}


def legal_actions(state, focus_id="none"):
    if state.phase != "day":
        return []
    actions = []
    focus = next((o for o in investigation.investigation_options(state) if o["id"] == focus_id), None)
    if focus is None:
        return []
    for option in current_event(state)["options"]:
        if option["cost"] + focus["cost"] <= state.resources["treasury"]:
            for team in combinations(state.actionable(), option["count"]):
                actions.append((option, [c.id for c in team]))
    return actions


def mission_score(state, option, team):
    # Public ability dominates. Private disposition is a small, capped modifier.
    abilities = sorted((c.skills[option["skill"]] for c in team), reverse=True)
    skill = abilities[0] + (0.25 * (abilities[1] - 2) if len(abilities) == 2 else 0)
    bg = sum(max([option["background_modifiers"].get(t, 0) for t in c.background["tags"]] or [0]) for c in team) / len(team)
    body = sum(c.fatigue / 65 + c.injury * 0.65 for c in team) / len(team)
    psyche = sum(max(-0.6, min(0.4, (c.trust + c.loyalty - c.stress - c.fear * 0.15 - 90) / 140)) for c in team) / len(team)
    relations = sum(c.relationships.get(other.id, {}).get("value", 0) for c in team for other in team if c != other) / 100
    info = min(0.9, len(state.intel) * 0.15)
    training = 0.25 if "training" in state.flags and option["skill"] == "combat" else 0
    return skill * option["ability_modifier"] + bg - body + psyche + relations + info + training


def gain_intel(state, intel_id, source):
    if intel_id in state.intel:
        return None
    node = investigation.graph_for(state).get(intel_id)
    if node and node["kind"] == "evidence":
        return investigation.store_item(state, node, source, "explicit_import")
    clue = current_thread(state)["clues"].get(intel_id)
    state.intel[intel_id] = clue["text"] if clue else load_data()[1]["intel"][intel_id]
    state.clue_metadata[intel_id] = dict(clue) if clue else {"thread_id": None, "clue_type": "external", "text": state.intel[intel_id]}
    return record_fact(state, "取得情報：" + state.intel[intel_id], "intel", source)


def grow_skill(state, char, skill, success):
    if success and char.skills[skill] < 5 and state.rng.random() < 0.42:
        char.skills[skill] += 1
        text = f"{char.name}的{SKILLS[skill]}成長至 {char.skills[skill]}。"
        char.experiences.append(f"第 {state.month} 月：" + text)
        state.last_result.append(text)
        return record_fact(state, text, "growth", char.id)
    return None


def resolve_day(state, option_id, participant_ids, token=None, focus_id="none"):
    expected = f"{state.month}:day"
    if state.phase != "day" or expected in state.resolved or (token is not None and token != expected):
        raise InvalidAction("此白天已結算，或頁面已過期。")
    investigation_focus = next((o for o in investigation.investigation_options(state) if o["id"] == focus_id), None)
    if investigation_focus is None:
        raise InvalidAction("請選擇本月提供的調查方向。")
    option = next((o for o in current_event(state)["options"] if o["id"] == option_id), None)
    if option is None or (option, participant_ids) not in legal_actions(state, focus_id):
        # Canonical team order makes duplicate/unknown/injured IDs impossible.
        if option is None or len(set(participant_ids)) != len(participant_ids) or not any(
                o["id"] == option_id and set(ids) == set(participant_ids) for o, ids in legal_actions(state, focus_id)):
            raise InvalidAction("請選擇足額糧餉、正確人數及可行動弟子。")
    team = [c for c in state.characters if c.id in participant_ids]
    state.resolved.add(expected)
    state.last_result = []
    state.last_participants = [c.id for c in team]
    option_before = public_option(state, option, state.last_participants)
    facts = [apply_resources(state, {"treasury": -option["cost"] - investigation_focus["cost"]}, "門務與調查確定成本")]
    if check_failure(state):
        record_decision(state, option["label"], facts, True)
        return
    score = mission_score(state, option, team)
    success = score + state.rng.uniform(-2, 2) >= option["difficulty"]
    effects = {k: state.rng.randint(*bounds) for k, bounds in option["success" if success else "failure"].items()}
    variants = option.get("success_narratives" if success else "failure_narratives")
    result_text = narrative.variant(variants, (state.seed, state.month, option_id, tuple(state.last_participants))) if variants else option["success_text" if success else "failure_text"]
    result_text = result_text.format(lead=team[0].name, team="、".join(c.name for c in team))
    facts.append(apply_resources(state, effects, result_text))
    state.last_result.append(state.facts[-1]["text"])
    state.option_stats.append({"event": state.event_id, "option": option_id, "success": success})
    if state.event_id == "suspicion" and "pattern" in state.intel:
        facts.append(record_fact(state, "核對外洩抄件時，也參照了先前取得的明暗兩路行動情報。", "investigation", "pattern"))
    for char in team:
        char.fatigue = clamp(char.fatigue + 21)
        char.stress = clamp(char.stress + (5 if success else 15))
        char.trust = clamp(char.trust + (2 if success else -5))
        char.history.append({"month": state.month, "kind": "mission", "success": success,
                             "text": current_event(state)["title"] + "：" + option["label"]})
        if not success and state.rng.random() < {"low": 0.12, "medium": 0.35, "high": 0.65, "lethal": 0.8}[option["risk"]]:
            severe = option["risk"] in ("high", "lethal") and state.rng.random() < 0.42
            char.injury = 2 if severe else max(1, char.injury)
            if severe:
                state.counters["severe_injury"] += 1
            facts.append(record_fact(state, f"{char.name}在任務中受了{'重' if severe else '輕'}傷。", "injury", char.id))
        # Death always references the exact warning the player saw before confirming.
        if not success and option["risk"] == "lethal" and score < option["difficulty"] and state.rng.random() < 0.18:
            char.status = "dead"
            state.counters["dead"] += 1
            fid = record_fact(state, f"{char.name}未能逃出崩落地帶，已確認死亡。", "major", char.id)
            facts.append(fid)
            state.major_outcomes.append({"month": state.month, "character_id": char.id, "kind": "dead",
                                         "warnings": [], "risk_notice": option_before["hint"], "fact": fid})
        if char.status == "active":
            growth = grow_skill(state, char, option["skill"], success)
            if growth:
                facts.append(growth)
            char.recent = f"參與「{current_event(state)['title']}」，執行「{option['label']}」；" + ("已完成這次差事。" if success else "這次差事受阻，回山後需要調整安排。")
            char.recent_month = state.month
        state.last_result.append(f"{char.name}：{char.status_display(state.month)[0]}")
        if len(team) == 2:
            other = next(c for c in team if c != char)
            if other.id in char.relationships:
                char.relationships[other.id]["value"] = max(-40, min(40, char.relationships[other.id]["value"] + (3 if success else -5)))
    if success:
        for flag in option["flags"]:
            if flag not in state.flags:
                state.flags.add(flag)
                facts.append(record_fact(state, load_data()[1]["flags"][flag], "flag", flag))
        for intel_id in option["intel"]:
            fid = gain_intel(state, intel_id, state.event_id)
            if fid:
                facts.append(fid)
                state.last_result.append(state.facts[-1]["text"])
    if option.get("special") == "restrict":
        suspect = team[0]
        suspect.blocked_until = state.month + 1
        suspect.trust = clamp(suspect.trust - 15)
        suspect.stress = clamp(suspect.stress + 12)
        suspect.experiences.append(f"第 {state.month} 月：被要求留門說明，次月暫停派遣；尚無通敵定論。")
        state.last_result.append(suspect.experiences[-1])
        facts.append(record_fact(state, suspect.experiences[-1], "restriction", suspect.id))
        witness = next((c for c in state.active() if c.id in suspect.relationships and c != suspect), None)
        if witness:
            text = narrative.speak(public_character_context(state, witness), f"{suspect.name}不能出門，那原來的工作由誰接？查證之前，我不會把這當成已經定罪。", "conflict")
            facts.append(record_fact(state, text, "personal", witness.id))
            state.last_result.append(text)
        state.story_flags["restricted_character"] = suspect.id
    facts.extend(investigation.resolve_investigation(state, investigation_focus, team, success, option_id))
    if state.event_id == "suspicion":
        focus = team[0] if option.get("special") == "restrict" else next((c for c in state.active() if c.id == state.story_flags.get("suspect")), team[0])
        previous = next((h for h in reversed(focus.history) if h["kind"] == "night"), None)
        memory = f"上回談好的『{previous['text']}』，我記得。" if previous else "之前出入與交班的記錄可以先核對。"
        request = "房匙留下了，但請告訴我查完哪一項能取回。" if option.get("special") == "restrict" else "有哪一段對不上，請讓我看原件再回答。"
        text = narrative.speak(public_character_context(state, focus), memory + request, "suspected" if focus.trust < 50 else "question")
        facts.append(record_fact(state, text, "personal", focus.id))
        state.last_result.append(text)
        known = [state.intel[k] for k in current_thread(state)["required_clues"] if k in state.intel]
        text = "這次議事能用的主線證據：" + "；".join(known) if known else "這次議事尚缺可互相印證的主線原件，不能將異常直接當作通敵結論。"
        facts.append(record_fact(state, text, "investigation", "suspicion"))
        state.last_result.append(text)
    ready_team = [c for c in team if c.status == "active"]
    bond = "strained" if len(ready_team) == 2 and ready_team[0].relationships.get(ready_team[1].id, {}).get("value", 0) < 0 else "close"
    aftermath = narrative.render_mission_aftermath({"participants": [public_character_context(state, c) for c in ready_team],
                                                  "detail": current_event(state).get("concrete_detail", "現場的物件"), "success": success, "bond": bond})
    for text in aftermath:
        facts.append(record_fact(state, text, "personal", state.event_id))
        state.last_result.append(text)
    for injured in [c for c in team if c.injury and c.status == "active"]:
        friend = next((c for c in state.active() if c not in team and c.relationships.get(injured.id, {}).get("value", 0) > 15), None)
        if friend:
            text = narrative.speak(public_character_context(state, friend), f"先讓{injured.name}坐下。要交代任務，也等傷口看過再說。", "other")
            facts.append(record_fact(state, text, "personal", friend.id))
            state.last_result.append(text)
    outcome_fact = record_fact(state, result_text, "outcome", state.event_id)
    facts.append(outcome_fact)
    detail = current_event(state).get("concrete_detail", current_event(state)["title"])
    if investigation_focus["id"] == "none" and (current_event(state)["key_decision"] or state.event_context.get("related")):
        add_callback(state, outcome_fact, f"談到{detail}時，眾人重新核對了當時「{option['label']}」留下的結果。")
    state.scene_history.append({"month": state.month, "type": "outcome", "scene_id": state.event_id + "/" + option_id, "text": result_text, "speakers": state.last_participants})
    for npc_id in current_event(state).get("npc_refs", []):
        state.story_flags[f"npc:{npc_id}"] = {"month": state.month, "choice": option["label"], "fact_id": outcome_fact, "success": success}
    decision = record_decision(state, current_event(state)["title"] + "／" + option["label"] + "／" + investigation_focus["label"], facts, current_event(state)["key_decision"])
    if option["delayed"] and success:
        queue_delay(state, option["delayed"], decision["id"])
    for char in state.active():
        observe_character(state, char)
    if not check_failure(state, "hostile" in current_event(state)["tags"]):
        state.phase = "day_result"


def queue_delay(state, delay, decision_id):
    state.pending.append({"due": state.month + delay["after"], "effects": dict(delay["effects"]),
                          "text": delay["text"], "decision": decision_id})


def emergency_rest(state):
    if state.phase != "day" or legal_actions(state):
        raise InvalidAction("仍有可執行的事件方案。")
    state.resolved.add(f"{state.month}:day")
    fid = apply_resources(state, {"defense": -4, "reputation": -2}, "無人能出勤，只得暫緩事件、留門休整")
    state.last_participants = []
    state.last_result = [state.facts[-1]["text"]]
    record_decision(state, "全員留門休整", [fid], True)
    if not check_failure(state, "hostile" in current_event(state)["tags"]):
        state.phase = "day_result"


def start_night(state):
    if state.phase != "day_result":
        raise InvalidAction("請先完成白天結算。")
    active = state.active()
    ordered = sorted(active, key=lambda c: (state.spotlight_counts.get(c.id, 0), c.id not in state.last_participants, c.id))
    kind = {2: "relationship_scene", 3: "mainline_scene", 5: "relationship_scene", 6: "quiet_scene", 7: "mainline_scene", 8: "relationship_scene", 11: "group_scene"}.get(state.month, "personal_scene")
    if kind == "personal_scene":
        arcs = {a["id"]: a for a in load_data()[2]["arcs"]}
        fresh = [c for c in ordered if arcs[c.arc]["scenes"][min(c.stage, 2)]["id"] + "/" + c.id not in state.used_night_scenes]
        ordered = fresh or ordered
    count = len(active) if kind == "group_scene" else min(2, len(active)) if kind in ("relationship_scene", "mainline_scene", "quiet_scene") else 1
    nights = [s for s in state.scene_history if s["type"] in ("personal_scene", "relationship_scene", "mainline_scene", "quiet_scene", "group_scene")][-2:]
    sole = [s["speakers"][0] for s in nights if len(s["speakers"]) == 1]
    if count == 1 and len(sole) == 2 and sole[0] == sole[1] and len(ordered) > 1:
        ordered = [c for c in ordered if c.id != sole[0]] + [c for c in ordered if c.id == sole[0]]
    speakers = ordered[:count]
    char = speakers[0]
    if kind == "personal_scene" and char.arc == "protect_other" and len(active) > 1:
        speakers = ordered[:2]
    if len(speakers) == 2:
        for owner, other in ((speakers[0], speakers[1]), (speakers[1], speakers[0])):
            owner.relationships.setdefault(other.id, {"id": "discussed", "text": "曾一起討論分工", "value": 0})
    state.night_character = char.id
    state.night_scene = build_night_scene(state, kind, speakers)
    for speaker in speakers:
        state.spotlight_counts[speaker.id] = state.spotlight_counts.get(speaker.id, 0) + 1
    state.used_night_scenes.append(state.night_scene["id"])
    state.scene_history.append({"month": state.month, "type": kind, "scene_id": state.night_scene["id"],
                                "speakers": [c.id for c in speakers], "text": state.night_scene["text"],
                                "spotlights": dict(state.spotlight_counts)})
    state.phase = "night"


def build_night_scene(state, kind, speakers):
    from copy import deepcopy
    char = speakers[0]
    partner = speakers[1] if len(speakers) > 1 else next((c for c in state.active() if c != char), None)
    other = partner.name if partner else "留守的人"
    personal = load_data()[2]
    context = {"name": char.name, "other": other}
    if kind == "group_scene":
        characters = []
        for c in speakers:
            public = public_character_context(state, c)
            choices = [h["text"] for h in c.history if h["kind"] == "night"]
            public["last_choice"] = choices[0] if choices else ""
            public["tomorrow"] = {"combat": "明日我守石階，先看清退路再拔劍。", "strategy": "明日我帶好原件，先說能證明的事。", "medicine": "明日藥與布放在門邊，誰回來都先讓我看傷。", "diplomacy": "明日山下有人開口，我先把話聽完。"}[c.role]
            public["attitude"] = "supported" if c.trust >= 60 else "suspected" if c.trust < 40 else "neutral"
            characters.append(public)
        absent = [{"name": c.name, "memory": "他留下的值勤空缺仍在那張舊表上。"} for c in state.characters if c.status != "active"]
        text = narrative.render_group_scene({"characters": characters, "absent": absent, "callbacks": ending_callback_facts(state)})
        choices = [{"id": key, "label": label, "approach": approach, "hint": "決定明日的共同提醒，不會取代之前累積的人手、證據與資源。", "cost": 0, "effects": {}, "psych": {}, "tradeoffs": [label, "仍須承擔此前選擇"], "delayed": None,
                    "reaction": "眾人把這句話記在明日的分工旁，沒有撤回先前答應的事。"}
                   for key, label, approach in [("keep_people", "明日先保人", "support"), ("hold_gate", "明日先守山", "discipline"), ("show_truth", "明日先揭真相", "defer")]]
        return {"id": "battle_eve_group", "title": "決戰前夕", "kind": kind, "speakers": [c.id for c in speakers], "text": text, "context": "", "choices": choices}
    arc = next(a for a in personal["arcs"] if a["id"] == char.arc)
    if kind == "personal_scene":
        scene = deepcopy(arc["scenes"][min(char.stage, 2)])
    elif kind == "relationship_scene":
        if state.month == 2:
            scene = deepcopy(next(s for s in personal["situations"] if s["id"] == "work_dispute"))
            scene["title"] = "兩張班表，兩個人的意思"
            scene["text"] = "{name}把兩張班表攤在桌上，問{other}：『下次誰先報訊，我想先說清楚。』\n\n{other}回答：『可以。但別在我還沒說完之前，替我答應下一班。』"
        else:
            relation_arc = next(a for a in personal["arcs"] if a["id"] == "protect_other")
            scene = deepcopy(relation_arc["scenes"][1 if state.month == 5 else 2])
            scene["text"] += "\n\n{other}把自己的班表也拿出來：『我在這裡。需要我做什麼，可以直接問我。』"
    elif kind == "mainline_scene":
        scene = deepcopy(next(s for s in personal["situations"] if s["id"] == "check_evidence"))
        scene["title"] = "原件攤開的那一晚"
        scene["text"] = "{name}把手邊的記錄推向{other}：『" + current_thread(state)["question"] + "』\n\n{other}回答：『先分清楚親眼見的、查證過的，還有只是聽來的。』"
        if state.month >= 7:
            scene["id"] = "evidence_crosscheck"
            scene["title"] = "這一頁能替誰作證"
            scene["text"] = "{name}把先前整理的紙分成兩疊：『查過的資料和仍待追問的清單，都在這裡。』\n\n{other}壓住其中一角：『明日若有人問這一頁能替誰作證，我們要說到哪裡？』"
            labels = ["重整已知資料，列出還要問誰", "先將可用的安排交給守門人", "保留不同說法，約好下月再核對"]
            reactions = ["{name}按現有記錄重列來源，{other}將未核實的頁面另夾起來。還缺的材料寫進待問清單，留待白天安排調查。", "{name}將能用於值勤的部分單獨抄出，{other}在空白處寫下『尚待核實』。守門人領到的安排沒有把推測混進去。", "{name}留下各份說法的來源，{other}收好需要再問的名單。今晚沒有要求誰先改口，下一次核對也有了確切的問題。"]
            for choice, label, reaction in zip(scene["choices"], labels, reactions):
                choice.update(label=label, reaction=reaction)
    else:
        scene = deepcopy(personal.get("quiet_scenes", [next(s for s in personal["situations"] if s["id"] == "shared_credit")])[0])
    earlier = [h for h in char.history if h["kind"] == "night" and (
        (scene.get("arc_id") and h.get("arc_id") == scene["arc_id"])
        or (kind in ("relationship_scene", "mainline_scene") and h.get("scene_kind") == kind))]
    previous = earlier[-1]["text"] if earlier else ""
    framing = scene["text"].format(**context).replace("查證过", "查證過").replace("两", "兩")
    if kind == "mainline_scene":
        external = next((q for q in state.observations if q.category == "external"), None)
        if external:
            framing += f"\n\n兩人也翻到第 {external.month} 月關於{state.character(external.character_id).name}的札記：{external.text}地址是核對的起點，還不能代替對內容的查證。"
    if kind == "personal_scene":
        framing += "\n\n" + narrative.speak(public_character_context(state, char), "這次要怎麼安排，我想聽你說清楚。", "question")
        if char.arc == "protect_other" and partner:
            framing += "\n\n" + narrative.speak(public_character_context(state, partner), "需要什麼幫忙，讓我自己先說。", "other")
    signature_key = f"signature:{state.month}:{char.id}"
    if char.stress >= 55 and signature_key not in state.story_flags:
        framing += "\n\n" + char.name + load_data()[0]["signature_tension"][char.signature]
        state.story_flags[signature_key] = True
    render = narrative.render_relationship_scene if kind == "relationship_scene" else narrative.render_night_scene
    text = render({"framing": framing, "previous": previous, "dialogue": []})
    for choice in scene["choices"]:
        choice.setdefault("approach", choice["id"])
        choice["id"] = scene["id"] + "/" + choice["id"]
        reactions = choice.get("reactions", {})
        choice["reaction"] = reactions.get("supported" if char.trust >= 55 else "suspected", choice["reaction"]).format(**context)
    return {"id": scene["id"] + "/" + char.id, "title": scene["title"], "kind": kind,
            "speakers": [c.id for c in speakers], "text": text, "context": "", "arc_id": scene.get("arc_id"),
            "choices": scene["choices"]}


def ending_callback_facts(state):
    ids = list(dict.fromkeys(c["source_id"] for c in state.callback_history))
    return [dict(f) for f in state.facts if f["id"] in ids][:3]


def night_view(state):
    if state.phase != "night":
        raise InvalidAction("現在不是夜談階段。")
    char = state.character(state.night_character)
    scene = state.night_scene
    return {"name": char.name, "character_id": char.id,
            "title": scene["title"], "kind": scene["kind"], "context": scene["context"], "text": scene["text"],
            "choices": [{"id": c["id"], "label": c["label"], "cost": c["cost"],
                         "approach": c.get("approach", "defer"),
                         "tradeoffs": list(c["tradeoffs"]), "delayed": c["delayed"] is not None,
                         "hint": c["hint"]}
                        for c in scene["choices"]]}


def response_effects(char, choice):
    effects = dict(choice["psych"])
    approach = choice.get("approach", choice["id"])
    if char.personality in ("剛直", "謹慎") and approach == "discipline":
        effects.update(trust=3, stress=3, loyalty=4)
    if char.personality in ("好勝", "多疑") and approach == "support":
        effects.update(trust=0, stress=-5, loyalty=1)
    if char.background["id"] in ("refugee", "enemy") and approach == "discipline":
        effects["trust"] -= 5
    if char.arc == "protect_other" and any(r["value"] < 0 for r in char.relationships.values()):
        effects["stress"] += 3
    if char.stance == "自主優先" and approach == "discipline":
        effects["trust"] = effects.get("trust", 0) - 3
    if char.stance == "山門優先" and choice["effects"].get("defense", 0) > 0:
        effects["loyalty"] = effects.get("loyalty", 0) + 3
    if char.stance == "真相優先" and choice.get("growth") == "strategy":
        effects["trust"] = effects.get("trust", 0) + 4
    return effects


def resolve_night(state, choice_id, token=None):
    expected = f"{state.month}:night"
    if state.phase != "night" or expected in state.resolved or (token is not None and token != expected):
        raise InvalidAction("此夜談已結算，或頁面已過期。")
    char = state.character(state.night_character)
    scene = state.night_scene
    choice = next((c for c in scene["choices"] if c["id"] == choice_id), None)
    if choice is None and choice_id in ("support", "discipline", "defer"):
        choice = next((c for c in scene["choices"] if c["approach"] == choice_id), None)
    if not choice or choice["cost"] > state.resources["treasury"]:
        raise InvalidAction("此回應無法執行，請確認糧餉。")
    state.resolved.add(expected)
    state.last_result = []
    if scene["kind"] == "group_scene":
        state.final_priority = choice["label"]
        fid = record_fact(state, "決戰前夕，眾人答應「" + choice["label"] + "」。", "personal", "group")
        record_decision(state, choice["label"], [fid], True)
        state.last_result = [choice["reaction"]]
        state.phase = "night_result"
        return
    effects = dict(choice["effects"])
    effects["treasury"] = effects.get("treasury", 0) - choice["cost"]
    fid = apply_resources(state, effects, char.name + "／" + choice["label"])
    facts = [fid]
    for key, change in response_effects(char, choice).items():
        setattr(char, key, clamp(getattr(char, key) + change))
    approach = choice["approach"]
    char.choices.append(approach)
    char.appearances += 1
    if scene.get("arc_id") == char.arc:
        arc = next(a for a in load_data()[2]["arcs"] if a["id"] == char.arc)
        played_stage = next(i for i, s in enumerate(arc["scenes"]) if scene["id"].startswith(s["id"] + "/"))
        char.stage = min(2, max(char.stage, played_stage) + 1)
    char.goal_progress += choice.get("goal_progress", 0)
    char.fatigue = clamp(char.fatigue - choice.get("recovery", 0))
    char.injury = max(0, char.injury - choice.get("heal", 0))
    for other_id in scene["speakers"][1:]:
        other = state.character(other_id)
        other.fatigue = clamp(other.fatigue - choice.get("partner_recovery", 0))
        other.trust = clamp(other.trust + response_effects(other, choice).get("trust", 0) // 2)
        for owner, target in ((char, other), (other, char)):
            if target.id in owner.relationships:
                relation = owner.relationships[target.id]
                relation["value"] = max(-40, min(40, relation["value"] + choice.get("relationship_delta", 0)))
        other.history.append({"month": state.month, "kind": "night", "choice": approach, "text": choice["label"], "arc_id": scene.get("arc_id"), "scene_kind": scene["kind"]})
    reaction = choice["reaction"]
    char.history.append({"month": state.month, "kind": "night", "choice": approach, "text": choice["label"], "scene_id": scene["id"], "arc_id": scene.get("arc_id"), "scene_kind": scene["kind"]})
    facts.append(record_fact(state, reaction, "personal", char.id))
    state.last_result = [state.facts[-2]["text"], reaction, f"{char.name}：{char.status_display(state.month)[0]}"]
    char.recent = f"夜談「{scene['title']}」後，接受了「{choice['label']}」的安排。"
    char.recent_month = state.month
    if choice.get("growth"):
        skill = char.role if choice["growth"] == "role" else choice["growth"]
        if char.skills[skill] < 5:
            char.skills[skill] += 1
            text = f"{char.name}經過演練，{SKILLS[skill]}提升至 {char.skills[skill]}。"
            facts.append(record_fact(state, text, "growth", char.id))
            state.last_result.append(text)
    state.story_flags[f"choice:{char.id}:{scene['id']}"] = choice["id"]
    personal_fact = next(f for f in state.facts if f["id"] == facts[1])
    if scene["kind"] in ("personal_scene", "relationship_scene"):
        arc = next((a for a in load_data()[2]["arcs"] if a["id"] == scene.get("arc_id")), None)
        followup = arc["resolutions"][approach] if arc else "這次再排班，兩人先把各自能負責的部分說清楚，才在表上落筆。"
        add_callback(state, personal_fact["id"], f"{char.name}提起「{choice['label']}」。當時定下的界線是：{followup}", speaker=char.id)
    state.scene_history.append({"month": state.month, "type": "night_reaction", "scene_id": scene["id"], "text": reaction, "speakers": scene["speakers"]})
    decision = record_decision(state, char.name + "／" + choice["label"], facts, True)
    if choice["delayed"]:
        queue_delay(state, choice["delayed"], decision["id"])
    # Evaluate against prior-month evidence, never the cue just emitted in this response.
    for member in list(state.active()):
        update_intentions(member)
        resolve_major_outcome(state, member, decision)
        if member.status == "active":
            observe_character(state, member)
    if not check_failure(state, "hostile" in current_event(state)["tags"]):
        state.phase = "night_result"


def update_intentions(char):
    failed = sum(h["kind"] == "mission" and not h["success"] for h in char.history)
    grievance = char.choices.count("discipline") >= 2 or failed >= 3
    departure_goal = char.secret["id"] == "departure" and char.goal_progress >= 3
    char.leave_intent = (grievance and char.trust <= 42 and char.stress >= 46) or departure_goal
    char.betrayal_intent = (char.secret["id"] == "contact" and grievance and char.trust <= 34
                             and char.loyalty <= 52 and char.stress >= 52)


def cue_evidence(char, category):
    tests = {
        "leaving": char.leave_intent, "betrayal": char.betrayal_intent,
        "external": char.secret["id"] == "contact",
        "concealed_injury": char.secret["id"] == "old_wound" and char.injury > 0,
        "trust_down": char.trust < 45, "trust_up": char.trust > 64,
        "stress": char.stress >= 50 or char.fatigue >= 55,
        "resentment": any(r["value"] < -15 for r in char.relationships.values()),
        "recognition": char.trust >= 72 and char.loyalty >= 66 and char.goal_progress >= 2,
        "noise": True,
    }
    return {"supported": bool(tests.get(category, False)), "category": category}


def emit_cue(state, char, category, strength):
    evidence = cue_evidence(char, category)
    if not evidence["supported"]:
        raise InvalidAction("線索不符合人物事實。")
    existing = [c for c in state.observations if c.character_id == char.id]
    same = [c for c in existing if c.category == category]
    warning = category in ("leaving", "betrayal")
    if any(c.month == state.month and c.category == category for c in existing):
        return None
    if category == "noise" or (warning and len(same) >= 2):
        return None
    if not warning and category in char.observed_conditions:
        return None
    templates = load_data()[0]["cue_templates"][category]
    other_id = next((cid for cid, r in char.relationships.items() if r["value"] < -15), next(iter(char.relationships)))
    candidates = [t.format(other=state.character(other_id).name) for t in templates]
    seen = {c.text.replace(char.signature, "").strip() for c in same}
    candidates = [text for text in candidates if text not in seen]
    if not candidates:
        return None
    text = candidates[0] if warning else narrative.variant(candidates, (state.seed, char.id, category))
    cue = Cue(f"q{len(state.observations)}", state.month, char.id, category, strength, text, evidence)
    state.observations.append(cue)
    char.recent = text
    char.recent_month = state.month
    char.observed_conditions.add(category)
    if category in ("external", "concealed_injury"):
        if text not in char.experiences:
            char.experiences.append(text)
    return cue


def observe_character(state, char):
    update_intentions(char)
    char.observed_conditions = {category for category in char.observed_conditions if cue_evidence(char, category)["supported"]}
    if char.betrayal_intent:
        category, strength = "betrayal", "strong"
    elif char.leave_intent:
        category, strength = "leaving", "strong"
    elif char.secret["id"] == "old_wound" and char.injury:
        category, strength = "concealed_injury", "strong"
    elif char.secret["id"] == "contact" and state.month in (3, 7):
        category, strength = "external", "strong"
    elif cue_evidence(char, "recognition")["supported"]:
        category, strength = "recognition", "weak"
    elif cue_evidence(char, "stress")["supported"]:
        category, strength = "stress", "weak"
    elif cue_evidence(char, "trust_down")["supported"]:
        category, strength = "trust_down", "weak"
    elif cue_evidence(char, "trust_up")["supported"]:
        category, strength = "trust_up", "weak"
    elif cue_evidence(char, "resentment")["supported"] and state.month % 3 == 0:
        category, strength = "resentment", "weak"
    else:
        return
    cue = emit_cue(state, char, category, strength)
    if cue and strength == "strong":
        record_fact(state, char.name + "：" + cue.text, "evidence", cue.id)


def qualifying_warnings(state, char, category):
    cues = [c for c in state.observations if c.character_id == char.id and c.category == category
            and c.month < state.month and c.strength in ("weak", "strong") and c.evidence["supported"]]
    return cues if len({c.month for c in cues}) >= 2 and any(c.strength == "strong" for c in cues) else []


def resolve_major_outcome(state, char, decision=None):
    if char.status != "active":
        return False
    update_intentions(char)
    category = "betrayal" if char.betrayal_intent else "leaving" if char.leave_intent else None
    if not category:
        return False
    warnings = qualifying_warnings(state, char, category)
    if not warnings:
        return False
    char.status = "defected" if category == "betrayal" else "left"
    state.counters[char.status] += 1
    consequence = "投靠烈川堂，帶走其熟悉的巡山路線。" if char.status == "defected" else "完成交接後離開青崖門。"
    text = char.name + consequence
    fid = record_fact(state, text, "major", char.id)
    if char.status == "defected":
        damage = apply_resources(state, {"defense": -8}, "巡山路線外流，必須撤換哨位")
        if decision:
            decision["facts"].append(damage)
    state.last_result.append(text)
    state.logs.append({"month": state.month, "text": text})
    outcome = {"month": state.month, "character_id": char.id, "kind": char.status,
               "warnings": [c.id for c in warnings], "fact": fid}
    state.major_outcomes.append(outcome)
    # Link to actual prior personal choices, not whichever character happened to talk tonight.
    linked = [d for d in state.decisions if d["label"].startswith(char.name + "／")]
    for prior in linked:
        prior["facts"].append(fid)
        prior["important"] = True
    return True


def determine_ending(state):
    active, ready = state.active(), state.actionable()
    strategy = sum(c.skills["strategy"] for c in ready)
    diplomacy = sum(c.skills["diplomacy"] for c in ready)
    combat = sum(c.skills["combat"] for c in ready)
    info_facts = [state.evidence[cid]["fact_id"] for cid in current_thread(state)["required_clues"] if cid in state.evidence]
    info_facts += [fid for row in state.deduction_history if row["month"] == 11 and row["accepted"] for fid in row["fact_ids"]]
    if mystery_complete(state) and strategy >= 9 and len(active) >= 2:
        return "揭破陰謀", "數份獨立線索經弟子比對後互相印證，烈川堂的藉口在斷劍臺上被揭破。", info_facts
    if state.resources["reputation"] >= 65 and state.flags & {"alliance", "villagers_helped"} and diplomacy >= 9 and len(active) >= 2:
        evidence = [f["id"] for f in state.facts if f["kind"] == "flag" and f["source"] in ("alliance", "villagers_helped")]
        return "聯盟退敵", "曾經援助或結交的人站到青崖門一側，弟子以盟約迫使烈川堂退讓。", evidence
    if state.resources["defense"] >= 60 and combat >= 12 and len(active) >= 3:
        return "正面取勝", "完整守備與仍可出戰的弟子互相支應，在斷劍臺正面擊退烈川堂。", []
    if (state.resources["defense"] >= 45 or state.resources["reputation"] >= 50) and len(active) >= 2:
        return "慘勝守山", "守備或地方聲援撐過了最險的一刻；青崖門留下，往後仍須慢慢修復。", []
    return "門派覆滅", "剩下的人手、守備與聲援不足以支撐十二月之戰，青崖門就此失守。", []


def causal_replay(state):
    if not state.ending:
        raise InvalidAction("遊戲結束後才開放因果回放。")
    facts = {f["id"]: f for f in state.facts}
    scored = sorted(state.decisions, key=lambda d: (
        any(facts[f]["kind"] == "major" for f in d["facts"]),
        bool(set(d["facts"]) & set(state.ending_evidence)), d["important"], len(d["facts"])), reverse=True)
    chosen = sorted(scored[:8], key=lambda d: (d["month"], int(d["id"][1:])))
    result = []
    for decision in chosen:
        ids = list(dict.fromkeys(decision["facts"]))
        meaningful = [i for i in ids if facts[i]["kind"] != "resource"]
        ids = (meaningful or ids)[-3:]
        chain = [f"第 {decision['month']} 月：{decision['label']}"] + [facts[i]["text"] for i in ids]
        if set(ids) & set(state.ending_evidence):
            chain.append("在斷劍臺上成為「" + state.ending + "」的依據")
        result.append({"decision_id": decision["id"], "fact_ids": ids, "text": " → ".join(chain)})
    return result


def ending_view(state):
    if not state.ending:
        raise InvalidAction("人物心跡尚未解鎖。")
    characters = []
    for char in state.characters:
        fate = {"dead": "長眠於任務途中，同門將名字刻在山石上。", "left": "離開青崖門，沿自己安排的山外道路而去。",
                "defected": "改投烈川堂，從此與青崖門分道。"}.get(char.status)
        if fate is None:
            if state.ending == "門派覆滅":
                fate = "在山門失守後攜同門名冊離散，生死未受決戰額外改寫。"
            elif char.goal_progress >= 2 and char.trust >= 60:
                fate = "留在青崖門，願將自己的打算與門內未來一起商量。"
            else:
                fate = "仍留在山門，與掌門的距離及未完成的私事一併延續。"
        causes = [f"第 {h['month']} 月{h['text']}" for h in char.history if h["kind"] == "night"]
        heart = f"{char.name}入門後一直想{char.goal}。不願先說出口的，是{char.fear_text}這件事；這讓同一句安排，在他耳中與旁人不同。{char.secret['text']}"
        heart += "回看「" + "；".join(causes[-3:]) + "」，這些答覆才逐漸把兩人的相處帶到今日。" if causes else "尚未有機會深入夜談，許多事便隨局勢告終。"
        if char.choices.count("discipline") >= 2:
            if char.personality in ("剛直", "謹慎"):
                heart += "明文規矩讓其較能理解掌門的安排，但規矩本身沒有解決私事與傷疲。"
            else:
                heart += "幾次私事都被要求讓位於門規，逐漸少向掌門開口；任務中的傷疲又加重了負擔。"
        if char.choices.count("support") >= 2:
            heart += "幾次回應留出了協助與商量的餘地。"
            if char.personality in ("好勝", "多疑"):
                heart += "然而直接援助未必就是其想要的認同，仍需要證明自己或核實承諾。"
        if char.choices.count("defer") >= 2:
            heart += "先前保留的彈性也累積成未完的約定，往後仍須有人承擔。"
        outcome = next((m for m in state.major_outcomes if m["character_id"] == char.id), None)
        warnings = [q.public() for q in state.observations if outcome and q.id in outcome["warnings"]]
        memories = [h["text"] for h in char.history if h["kind"] == "night"]
        epilogue = f"{char.name}的去向是：{fate}"
        if memories:
            epilogue += f"回望這些月，『{memories[0]}』是確實談過的一次安排；"
            epilogue += f"後來又談到『{memories[-1]}』。" if len(memories) > 1 else "那次談話留下的要求，往後仍要有人記得。"
        else:
            epilogue += "你們一起經過山門的幾次變動，卻還沒能把私下的難題逐件談清。"
        arc_history = [h for h in char.history if h.get("arc_id") == char.arc]
        if arc_history and char.status == "active":
            arc = next(a for a in load_data()[2]["arcs"] if a["id"] == char.arc)
            epilogue += arc["resolutions"][arc_history[-1]["choice"]]
        else:
            epilogue += ("同門留下這些記錄，沒有讓最後那次任務蓋過他先前做過的所有事。" if char.status == "dead" else "做完的工作與未履行的約定都還在，再提起青崖門時，記得的不會只有最後一日的勝負。")
        characters.append({"name": char.name, "fate": fate, "heart": heart, "epilogue": epilogue,
                           "warnings": warnings, "risk_notice": outcome.get("risk_notice") if outcome else None})
    thread = current_thread(state)
    mystery = thread["ending_reveal"] if mystery_complete(state) else thread["partial_reveal"]
    if not mystery_complete(state):
        known = [state.evidence[k]["text"] for k in thread["required_clues"] if k in state.evidence]
        mystery = "已能確認：" + "；".join(known) + "\n" + mystery if known else "這一局沒有取得足以串起主線的核心證據。" + mystery
    callbacks = ending_callback_facts(state)
    personal_callbacks = [{"name": c.name, **h} for c in state.characters for h in c.history if h["kind"] == "night" and h["month"] < state.month]
    first_choices = list({h["name"]: h for h in reversed(personal_callbacks)}.values())
    endings = narrative.render_ending_scene({"opening": load_story_data()["ending_scenes"][state.ending],
                                            "mystery": mystery, "motif": thread["object"], "priority": state.final_priority, "callbacks": callbacks})
    endings["character_epilogues"] = [{"name": c["name"], "text": c["epilogue"]} for c in characters]
    endings["personal_callbacks"] = [f"第 {h['month']} 月，你與{h['name']}定下『{h['text']}』。" for h in first_choices[:2]]
    return {"ending": state.ending, "reason": state.ending_reason, "characters": characters, **endings,
            "replay": causal_replay(state), "resources": {RESOURCES[k]: v for k, v in state.resources.items()}}
