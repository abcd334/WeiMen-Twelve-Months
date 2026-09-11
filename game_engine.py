"""Deterministic twelve-month simulation. UI reads only explicit public projections."""
from itertools import combinations
from random import Random

from data_loader import load_data
from models import Character, Cue, GameState, RESOURCES, RISK_NAMES, SKILLS

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
    state = GameState(seed=seed, rng=rng, characters=generate_characters(rng))
    begin_month(state)
    return state


def current_event(state):
    return next(e for e in load_data()[1]["events"] if e["id"] == state.event_id)


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
    if state.phase not in ("new", "night_result") or state.ending:
        raise InvalidAction("尚未完成本月夜談。")
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
    if check_failure(state):
        return
    events = load_data()[1]["events"]
    fixed = next((e for e in events if e.get("fixed_month") == state.month), None)
    event = fixed or state.rng.choice([e for e in events if event_eligible(state, e)])
    state.event_id = event["id"]
    state.seen_events.append(event["id"])
    if check_failure(state, "hostile" in event["tags"]):
        return
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
            "delayed": option["delayed"] is not None, "extra_hints": hints}


def public_state(state):
    event = current_event(state) if state.event_id else None
    return {"seed": state.seed, "month": state.month, "phase": state.phase,
            "resources": {RESOURCES[k]: v for k, v in state.resources.items()},
            "characters": [c.public(state.month) for c in state.characters],
            "event": {"title": event["title"], "description": event["description"],
                      "options": [public_option(state, o) for o in event["options"]]} if event else None,
            "observations": [c.public() for c in state.observations],
            "intel": list(state.intel.values()), "logs": [dict(log) for log in state.logs],
            "flags": [load_data()[1]["flags"][f] for f in sorted(state.flags)],
            "last_result": list(state.last_result)}


def legal_actions(state):
    if state.phase != "day":
        return []
    actions = []
    for option in current_event(state)["options"]:
        if option["cost"] <= state.resources["treasury"]:
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
    state.intel[intel_id] = load_data()[1]["intel"][intel_id]
    return record_fact(state, "取得情報：" + state.intel[intel_id], "intel", source)


def grow_skill(state, char, skill, success):
    if success and char.skills[skill] < 5 and state.rng.random() < 0.42:
        char.skills[skill] += 1
        text = f"{char.name}的{SKILLS[skill]}成長至 {char.skills[skill]}。"
        char.experiences.append(f"第 {state.month} 月：" + text)
        state.last_result.append(text)
        return record_fact(state, text, "growth", char.id)
    return None


def resolve_day(state, option_id, participant_ids, token=None):
    expected = f"{state.month}:day"
    if state.phase != "day" or expected in state.resolved or (token is not None and token != expected):
        raise InvalidAction("此白天已結算，或頁面已過期。")
    option = next((o for o in current_event(state)["options"] if o["id"] == option_id), None)
    if option is None or (option, participant_ids) not in legal_actions(state):
        # Canonical team order makes duplicate/unknown/injured IDs impossible.
        if option is None or len(set(participant_ids)) != len(participant_ids) or not any(
                o["id"] == option_id and set(ids) == set(participant_ids) for o, ids in legal_actions(state)):
            raise InvalidAction("請選擇足額糧餉、正確人數及可行動弟子。")
    team = [c for c in state.characters if c.id in participant_ids]
    state.resolved.add(expected)
    state.last_result = []
    state.last_participants = [c.id for c in team]
    option_before = public_option(state, option, state.last_participants)
    facts = [apply_resources(state, {"treasury": -option["cost"]}, "方案確定成本")]
    if check_failure(state):
        record_decision(state, option["label"], facts, True)
        return
    score = mission_score(state, option, team)
    success = score + state.rng.uniform(-2, 2) >= option["difficulty"]
    effects = {k: state.rng.randint(*bounds) for k, bounds in option["success" if success else "failure"].items()}
    result_text = option["success_text" if success else "failure_text"]
    facts.append(apply_resources(state, effects, result_text))
    state.last_result.append(state.facts[-1]["text"])
    state.option_stats.append({"event": state.event_id, "option": option_id, "success": success})
    if state.event_id == "suspicion" and "pattern" in state.intel:
        facts.append(record_fact(state, "核對外洩抄件時，沿用了第四月查到的明暗兩路行動模式。", "investigation", "pattern"))
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
            previous = next((q.text for q in reversed(state.observations) if q.character_id == char.id and q.category == "mission"), "")
            lines = [char.signature + " " + text.format(name=char.name) for text in option["cue_templates"]]
            observation = state.rng.choice([line for line in lines if line != previous] or lines)
            state.observations.append(Cue(f"q{len(state.observations)}", state.month, char.id,
                                          "mission", "noise", observation, {"supported": True, "event": state.event_id}))
        state.last_result.append(f"{char.name}：{char.physical(state.month)}")
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
    decision = record_decision(state, current_event(state)["title"] + "／" + option["label"], facts, current_event(state)["key_decision"])
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
    # Participants / affected members take priority, with fewest appearances as the tie break.
    active = state.active()
    candidates = [c for c in active if c.id in state.last_participants]
    if not candidates:
        candidates = active
    least = min(c.appearances for c in candidates)
    char = state.rng.choice([c for c in candidates if c.appearances == least])
    state.night_character = char.id
    state.phase = "night"


def night_view(state):
    if state.phase != "night":
        raise InvalidAction("現在不是夜談階段。")
    char = state.character(state.night_character)
    arc = next(a for a in load_data()[2]["arcs"] if a["id"] == char.arc)
    other = state.character(next(iter(char.relationships))).name
    return {"name": char.name, "character_id": char.id,
            "text": char.signature + "\n\n" + arc["stages"][min(char.stage, 2)].format(name=char.name, other=other),
            "choices": [{"id": c["id"], "label": c["label"], "cost": c["cost"],
                         "tradeoffs": list(c["tradeoffs"]), "delayed": c["delayed"] is not None,
                         "hint": {"support": "支出糧餉、安排休養，但守備人手暫減。", "discipline": "補回值勤與門內收入；人物的私事仍未解決。", "defer": "眼前不支出，後續須補足盤纏與值勤。"}[c["id"]]}
                        for c in arc["choices"]]}


def response_effects(char, choice):
    effects = dict(choice["psych"])
    if char.personality in ("剛直", "謹慎") and choice["id"] == "discipline":
        effects.update(trust=3, stress=3, loyalty=4)
    if char.personality in ("好勝", "多疑") and choice["id"] == "support":
        effects.update(trust=0, stress=-5, loyalty=1)
    if char.background["id"] in ("refugee", "enemy") and choice["id"] == "discipline":
        effects["trust"] -= 5
    if char.arc == "protect_other" and any(r["value"] < 0 for r in char.relationships.values()):
        effects["stress"] += 3
    return effects


def resolve_night(state, choice_id, token=None):
    expected = f"{state.month}:night"
    if state.phase != "night" or expected in state.resolved or (token is not None and token != expected):
        raise InvalidAction("此夜談已結算，或頁面已過期。")
    char = state.character(state.night_character)
    arc = next(a for a in load_data()[2]["arcs"] if a["id"] == char.arc)
    choice = next((c for c in arc["choices"] if c["id"] == choice_id), None)
    if not choice or choice["cost"] > state.resources["treasury"]:
        raise InvalidAction("此回應無法執行，請確認糧餉。")
    state.resolved.add(expected)
    state.last_result = []
    effects = dict(choice["effects"])
    effects["treasury"] = effects.get("treasury", 0) - choice["cost"]
    fid = apply_resources(state, effects, char.name + "／" + choice["label"])
    facts = [fid]
    for key, change in response_effects(char, choice).items():
        setattr(char, key, clamp(getattr(char, key) + change))
    char.choices.append(choice_id)
    char.appearances += 1
    char.stage = min(2, char.stage + 1)
    if choice_id == "support":
        char.goal_progress += 1
        char.fatigue = clamp(char.fatigue - 22)
        char.injury = max(0, char.injury - 1)
    for relationship in char.relationships.values():
        relationship["value"] = max(-40, min(40, relationship["value"] + (3 if choice_id == "support" else -2)))
    reaction = choice["reaction"].format(name=char.name)
    if choice_id == "discipline" and char.personality in ("剛直", "謹慎"):
        reaction = f"{char.name}說把規矩寫清才好辦事，願按此分工；家中的難題仍要另尋出路。"
    char.history.append({"month": state.month, "kind": "night", "choice": choice_id, "text": choice["label"]})
    facts.append(record_fact(state, reaction, "personal", char.id))
    state.last_result = [state.facts[-2]["text"], reaction, f"{char.name}：{char.physical(state.month)}"]
    if char.appearances >= 2:
        if char.choices.count("support") >= 2 and char.trust >= 60:
            result = arc["resolutions"]["support"]
        elif char.choices.count("discipline") >= 2:
            result = arc["resolutions"]["discipline"]
        elif char.choices.count("defer") >= 2:
            result = arc["resolutions"]["defer"]
        else:
            result = "幾次談話後，安排仍需磨合，暫時留門處理未了的事。"
        char.recent = result
        state.last_result.append(result)
        facts.append(record_fact(state, char.name + "：" + result, "arc", char.id))
    decision = record_decision(state, char.name + "／" + choice["label"], facts, char.appearances >= 2)
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
    if any(c.month == state.month and c.category == category for c in existing):
        return None
    templates = load_data()[0]["cue_templates"][category]
    other_id = next((cid for cid, r in char.relationships.items() if r["value"] < -15), next(iter(char.relationships)))
    candidates = [char.signature + " " + t.format(other=state.character(other_id).name) for t in templates]
    recent = next((c.text for c in reversed(existing) if c.category == category), "")
    text = state.rng.choice([t for t in candidates if t != recent] or candidates)
    cue = Cue(f"q{len(state.observations)}", state.month, char.id, category, strength, text, evidence)
    state.observations.append(cue)
    char.recent = text
    if category in ("external", "concealed_injury"):
        if text not in char.experiences:
            char.experiences.append(text)
    return cue


def observe_character(state, char):
    update_intentions(char)
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
        category, strength = "noise", "noise"
    emit_cue(state, char, category, strength)


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
    info_facts = [f["id"] for f in state.facts if f["kind"] == "intel"]
    if len(state.intel) >= 3 and strategy >= 9 and len(active) >= 2:
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
        heart = f"原本想{char.goal}，最怕{char.fear_text}。{char.secret['text']}"
        heart += "先後經歷「" + "；".join(causes) + "」，才走到今日。" if causes else "尚未有機會深入夜談，許多事便隨局勢告終。"
        if char.choices.count("discipline") >= 2:
            if char.personality in ("剛直", "謹慎"):
                heart += "明文規矩讓其較能理解掌門的安排，但規矩本身沒有解決私事與傷疲。"
            else:
                heart += "幾次私事都被要求讓位於門規，逐漸少向掌門開口；任務中的傷疲又加重了負擔。"
        if char.choices.count("support") >= 2:
            heart += "多次撥糧支持使個人打算往前走了一段。"
            if char.personality in ("好勝", "多疑"):
                heart += "然而直接援助未必就是其想要的認同，仍需要證明自己或核實承諾。"
        if char.choices.count("defer") >= 2:
            heart += "先前保留的彈性也累積成未完的約定，往後仍須有人承擔。"
        outcome = next((m for m in state.major_outcomes if m["character_id"] == char.id), None)
        warnings = [q.public() for q in state.observations if outcome and q.id in outcome["warnings"]]
        characters.append({"name": char.name, "fate": fate, "heart": heart,
                           "warnings": warnings, "risk_notice": outcome.get("risk_notice") if outcome else None})
    return {"ending": state.ending, "reason": state.ending_reason, "characters": characters,
            "replay": causal_replay(state), "resources": {RESOURCES[k]: v for k, v in state.resources.items()}}
