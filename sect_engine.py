"""Deterministic, open-ended sect simulation driven by shared history."""
from copy import deepcopy
from itertools import combinations
from random import Random

from models import SKILLS, RESOURCES, RISK_NAMES
from sect_content import EVENTS, REGULAR_IDS, ROSTER, validate_content
from sect_models import (GAME_VERSION, STAGES, FACILITIES, JOBS, OFFICES,
                         Experience, SharedMemory, SectCharacter, SectState, date_label)


class InvalidAction(ValueError):
    pass


def new_game(seed):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise InvalidAction("種子須為 0 到 4294967295 的整數。")
    validate_content()
    rng = Random(seed)
    characters = []
    roles = list(SKILLS) + rng.sample(list(SKILLS), 2)
    rng.shuffle(roles)
    for i, (name, age, background, personality, signature) in enumerate(ROSTER):
        skills = {key: rng.randint(2, 4) for key in SKILLS}
        skills[roles[i]] = 5
        characters.append(SectCharacter(id=f"c{i}", name=name, age=age, role=roles[i],
            skills=skills, personality=personality, background={"summary": background},
            signature=signature, goal="", fear_text="", secret={}, arc="",
            recent="初入門冊，尚未與你共同經歷大事。"))
    state = SectState(seed=seed, rng=rng, characters=characters, phase="planning", month=1,
                      resources={"treasury": 65, "defense": 40, "reputation": 25})
    for i, char in enumerate(characters):
        other = characters[(i + 1) % len(characters)]
        char.relationships[other.id] = {"label": "入門時便認識", "value": 0, "cooperations": 0}
        other.relationships[char.id] = {"label": "入門時便認識", "value": 0, "cooperations": 0}
    prepare_tick(state)
    return state


def record(state, char, kind, text, importance=1, event_id=""):
    """Repetition has bounded weight; stages require diverse experiences over time."""
    exp = Experience(f"x:{char.id}:{len(char.experiences) + 1}", state.tick, kind, text, importance, event_id)
    char.experiences.append(exp)
    char.history.append({"tick": state.tick, "kind": kind, "experience_id": exp.id})
    char.recent, char.recent_month = text, state.month
    budget = max(0, 6 - char.weight_sources.get(kind, 0))
    gained = min(budget, importance)
    char.weight_sources[kind] = char.weight_sources.get(kind, 0) + gained
    char.narrative_weight += gained
    kinds = sum(value > 0 for value in char.weight_sources.values())
    dates = {e.tick for e in char.experiences if e.importance >= 3}
    stage = 2 if char.narrative_weight >= 32 and kinds >= 5 and len(dates) >= 4 else 1 if char.narrative_weight >= 6 and kinds >= 2 else 0
    char.stage = max(char.stage, 3 if char.office else stage)
    return exp


def log(state, text, kind="sect"):
    state.logs.append({"tick": state.tick, "kind": kind, "text": text})
    state.last_result.append(text)


def milestone(state, char, key, text, importance=3):
    if key not in char.milestones:
        char.milestones.add(key)
        record(state, char, key, text, importance)
        log(state, f"{char.name}：{text}", "person")


def shared_memory(state, team, text, tags, source_ids, importance=2, actor_id="", target_id=""):
    memory = SharedMemory(f"m:{len(state.shared_memories) + 1}", [c.id for c in team],
        state.tick, text, importance, tags, source_ids, actor_id, target_id)
    state.shared_memories.append(memory)
    for left, right in combinations(team, 2):
        for a, b in ((left, right), (right, left)):
            rel = a.relationships.setdefault(b.id, {"label": "同門", "value": 0, "cooperations": 0})
            rel["cooperations"] += 1
            rel["value"] += -1 if "conflict" in tags else importance
            rel["label"] = "救援之交" if "rescue" in tags else "曾有摩擦" if "conflict" in tags else "共同辦過事"
    return memory


def eligible_memories(state, ids, event_id):
    wanted = set(ids)
    return [m for m in state.shared_memories if set(m.participants) <= wanted
            and state.tick - m.tick >= 3 and event_id not in m.recalled_by
            and not any(c["source_id"] == m.id and state.tick - c["tick"] < 3 for c in state.callback_history)
            and set(m.tags) & {"rescue", "failure", "cooperation", "care", "conflict"}]


def recall(state, memory, event_id):
    memory.recalled_by.append(event_id)
    if "rescue" in memory.tags:
        actor, target = state.character(memory.actor_id), state.character(memory.target_id)
        text = f"{target.name}說：「那次山路上，{actor.name}沒有把我留下。我願意先聽他把事情說完。」" if event_id == "suspicion" else f"{target.name}把水袋遞給{actor.name}：「上次是你背我回來，這次我們一起走穩。」"
        bonus = 2
    elif "failure" in memory.tags:
        text = "他們提起上次共同失手的細節，先約好撤回與接應的位置。這次不用再從頭摸索。"
        bonus = 1
    elif "conflict" in memory.tags:
        text = "上次的爭執仍在，兩人先把各自負責的部分說清楚，才願意動身。"
        bonus = 0
    else:
        text = "幾旬前一起辦事的經驗還在，兩人不必多說，就知道該由誰接手下一步。"
        bonus = 1
    entry = {"tick": state.tick, "source_id": memory.id, "source_tick": memory.tick,
             "event_id": event_id, "participants": list(memory.participants), "text": text,
             "effect": bonus}
    state.callback_history.append(entry)
    log(state, f"記起{date_label(memory.tick)}：{memory.text}\n{text}", "callback")
    return bonus


def enqueue(state, event_id, char_id, source_id="", partner_id=""):
    key = f"{event_id}:{char_id}:{source_id}"
    if key in state.triggered:
        return
    # Keep the latest cause for a recurring personal request, rather than stacking
    # a new conversation for every failure or every wound.
    if event_id in ("failure_request", "injury_request", "neglect"):
        state.personal_queue = [p for p in state.personal_queue
                                if (p["event_id"], p["character_id"]) != (event_id, char_id)]
    if key not in state.triggered:
        state.triggered.add(key)
        state.personal_queue.append({"id": key, "event_id": event_id, "character_id": char_id,
                                     "source_id": source_id, "partner_id": partner_id, "tick": state.tick})


def office_candidates(state):
    result = []
    occupied = {c.office for c in state.active() if c.office}
    for char in state.active():
        if char.office or char.stage < 2 or char.injury >= 2:
            continue
        duties = char.duties
        checks = {
            "medic": state.facilities["herbs"] >= 2 and duties.get("herbs", 0) >= 6 and char.skills["medicine"] >= 4,
            "leader": state.facilities["lodge"] >= 2 and duties.get("missions", 0) >= 4 and duties.get("lead", 0) >= 3,
            "mentor": state.facilities["training"] >= 2 and duties.get("train", 0) >= 6 and duties.get("mentoring", 0) >= 3 and char.skills["combat"] >= 4,
        }
        result.extend((char.id, office) for office, allowed in checks.items() if allowed and office not in occupied)
    return result


def prepare_tick(state):
    state.month = (state.tick - 1) % 36 // 3 + 1
    state.phase = "planning"
    if len(state.event_deck) < 3:
        fresh = list(REGULAR_IDS)
        state.rng.shuffle(fresh)
        state.event_deck.extend(fresh)
    state.offers = []
    while len(state.offers) < 3:
        event_id = state.event_deck.pop(0)
        if event_id not in state.offers:
            state.offers.append(event_id)
    if state.chain["step"] < 3 and state.tick >= state.chain["due"]:
        state.offers.append(f"cards_{state.chain['step']}")
    for char in state.active():
        if char.stage >= 2 and not char.goal:
            enqueue(state, "goal", char.id)
    # Every available callback is attached to a real, sufficiently old memory.
    for memory in state.shared_memories:
        if memory.importance < 2:
            continue
        if not all(state.character(cid).actionable(state.tick) for cid in memory.participants):
            continue
        if state.tick - memory.tick < 3:
            continue
        eid = "suspicion" if "rescue" in memory.tags else "memory_return"
        if memory.recalled_by or f"{eid}:{memory.participants[0]}:{memory.id}" in state.triggered:
            continue
        enqueue(state, eid, memory.participants[0], memory.id, memory.participants[1])
        break
    for cid, office in office_candidates(state):
        key = f"promotion:{cid}:{office}"
        if key not in state.triggered:
            state.triggered.add(key)
            log(state, f"{state.character(cid).name}已有資格擔任{OFFICES[office]}，可在本旬安排中任命。", "person")


def _action(aid, title, description, kind, **kwargs):
    return dict(id=aid, title=title, description=description, kind=kind,
                cost=kwargs.pop("cost", 0), minimum=kwargs.pop("minimum", 1),
                maximum=kwargs.pop("maximum", 2), risk=kwargs.pop("risk", "low"), **kwargs)


def available_actions(state):
    """Pure projection: never generate events or consume RNG during UI reruns."""
    if state.phase != "planning":
        return []
    actions = []
    for eid in state.offers:
        event = EVENTS[eid]
        if event["kind"] == "chain":
            approaches = [("investigate", "派人調查", "strategy", 1), ("negotiate", "與商隊協商", "diplomacy", 0),
                          ("pay", "先賠付貨款", "diplomacy", 9), ("ally", "請地方行會協助", "diplomacy", 4),
                          ("ignore", "暫不處理", "strategy", 0)]
            for method, label, skill, cost in approaches:
                actions.append(_action(f"{eid}/{method}", f"{event['title']} · {label}", event["opening"], "chain",
                    event_id=eid, method=method, skill=skill, cost=cost,
                    minimum=0 if method == "ignore" else 1, maximum=0 if method == "ignore" else 2,
                    risk="medium" if method == "investigate" else "low"))
        else:
            for method, label, surcharge in (("direct", "出面處理", 0), ("supported", "備妥支援再出發", 3)):
                actions.append(_action(f"{eid}/{method}", f"{event['title']} · {label}", event["opening"], "mission",
                    event_id=eid, method=method, skill=event["skill"], cost=event["cost"] + surcharge,
                    injury_risk=event["physical_danger"],
                    risk=event["risk"] if not surcharge else {"high": "medium", "medium": "low", "low": "low"}[event["risk"]]))
    for item in state.personal_queue:
        char = state.character(item["character_id"])
        if char.status != "active":
            continue
        event = EVENTS[item["event_id"]]
        memory = next((m for m in state.shared_memories if m.id == item["source_id"]), None)
        required = memory.participants if memory else [char.id]
        if any(state.character(cid).status != "active" for cid in required):
            continue
        if memory and item["event_id"] not in ("suspicion",) and any(not state.character(cid).actionable(state.tick) for cid in required):
            continue
        description = event["opening"] + (f"\n源於{date_label(memory.tick)}：{memory.text}" if memory else f"\n{char.name}：{char.recent}")
        actions.append(_action(f"personal/{item['id']}", f"{event['title']} · {char.name}", description, "personal",
            event_id=item["event_id"], item_id=item["id"], required=list(required), minimum=len(required), maximum=len(required),
            allow_injured=True, cost=2 if item["event_id"] == "injury_request" else 0))
    actions.extend([
        _action("rest", "安排休養", "讓受傷或疲憊的門人休息。每旬恢復疲勞；傷勢每休養兩旬減輕一級。", "rest", maximum=6, allow_injured=True),
        _action("train", "修煉與帶新人", "第一位帶領者陪同第二位練功。每三次修煉提升武力；共同練功會留下師友經歷。", "train"),
        _action("work", "下山做工補充糧餉", "每人帶回 7 糧餉；疲勞達 65 時只得 4 糧餉。工作累積疲勞，可與同門一起接下。", "work"),
    ])
    for facility, label in FACILITIES.items():
        level = state.facilities[facility]
        if level < 3:
            actions.append(_action(f"build/{facility}", f"整修{label} · 升至 {level + 1} 級",
                "參與者會留下修建經歷。二級設施可支持相關職位；設施也改善日常工作。", "build", facility=facility, cost=10 * level))
    for cid, office in office_candidates(state):
        actions.append(_action(f"appoint/{cid}/{office}", f"任命{state.character(cid).name}為{OFFICES[office]}",
            {"medic": "每旬自動協助一名傷員治療。", "leader": "每旬自選一名留門修煉的同伴處理普通差事，增加糧餉與合作經歷。", "mentor": "每旬指導一名留門修煉者，讓修煉進度更快。"}[office],
            "appoint", required=[cid], minimum=1, maximum=1, office=office))
    return actions


def validate_plan(state, action_id, participant_ids, assignments=None, token=None):
    if state.phase != "planning" or f"{state.tick}:plan" in state.resolved or (token is not None and token != f"{state.tick}:plan"):
        raise InvalidAction("這旬已結算，或頁面已過期。")
    action = next((a for a in available_actions(state) if a["id"] == action_id), None)
    if action is None:
        raise InvalidAction("請選擇本旬仍可執行的安排。")
    if not isinstance(participant_ids, (list, tuple)) or any(not isinstance(cid, str) for cid in participant_ids):
        raise InvalidAction("門人名單格式不正確。")
    ids = list(participant_ids)
    if len(set(ids)) != len(ids) or not action["minimum"] <= len(ids) <= action["maximum"]:
        raise InvalidAction(f"此安排需 {action['minimum']}～{action['maximum']} 名不同門人。")
    if action.get("required") and set(ids) != set(action["required"]):
        raise InvalidAction("這件事需要當事人一起處理。")
    active_ids = {c.id for c in state.active()}
    if not set(ids) <= active_ids:
        raise InvalidAction("已離門或不存在的門人不能參與。")
    if not action.get("allow_injured") and any(not state.character(cid).actionable(state.tick) for cid in ids):
        raise InvalidAction("重傷或暫停派遣者需要休養。")
    if action["cost"] > state.resources["treasury"]:
        raise InvalidAction("糧餉不足以支付這項安排。")
    assignments = dict(assignments or {})
    if set(assignments) - (active_ids - set(ids)) or any(job not in JOBS for job in assignments.values()):
        raise InvalidAction("留門分工不可重複使用出勤者，且必須是有效的工作。")
    for char in state.active():
        if char.id not in ids:
            job = assignments.setdefault(char.id, "rest")
            if not char.actionable(state.tick) and job != "rest":
                raise InvalidAction(f"{char.name}目前只能休養。")
    return action, [state.character(cid) for cid in ids], assignments


def _chance(state, action, team, bonus=0):
    skill = action.get("skill", "strategy")
    best = max((c.skills[skill] for c in team), default=0)
    teamwork = min(12, 6 * (len(team) - 1))
    fatigue = sum(c.fatigue / 10 + c.injury * 7 for c in team) / max(1, len(team))
    faction = state.factions["商隊"] * 2 if action.get("event_id") in ("escort", "caravan_talk") else 0
    growth = sum(2 for c in team if "果決" in c.development and action["risk"] == "high")
    return max(15, min(95, 35 + best * 8 + teamwork + bonus * 7 + faction + growth
                       - {"low": 0, "medium": 12, "high": 23}[action["risk"]] - fatigue))


def _mission_history(state, team, action, success):
    eid = action["event_id"]
    sources = []
    names = "、".join(c.name for c in team)
    text = f"{names}處理「{EVENTS[eid]['title']}」，" + ("把事情辦成了。" if success else "失手後一起返山。" if len(team) > 1 else "未能辦成，返山重整。")
    for char in team:
        char.last_opportunity = state.tick
        char.neglect_warnings.clear()
        char.leave_intent = False
        char.appearances += 1
        char.duties["missions"] = char.duties.get("missions", 0) + 1
        sources.append(record(state, char, "mission_success" if success else "mission_failure", text, 2 if success else 3, eid).id)
        char.fatigue = min(100, char.fatigue + 18)
        if success:
            milestone(state, char, "first_success", "第一次把受託的差事辦成，回門時有人叫住他道謝。")
            skill = action.get("skill", "strategy")
            key = "success:" + skill
            char.duties[key] = char.duties.get(key, 0) + 1
            if char.duties[key] % 3 == 0:
                char.skills[skill] = min(10, char.skills[skill] + 1)
        else:
            enqueue(state, "failure_request", char.id, sources[-1])
        if action["risk"] == "high":
            record(state, char, "high_risk", "這次冒險出勤，讓大家記住了他在危急時的樣子。", 3, eid)
    if len(team) == 1 and success:
        milestone(state, team[0], "first_solo", "第一次獨自辦成差事，開始相信自己能扛起託付。")
    if len(team) >= 2:
        leader = team[0]
        leader.duties["lead"] = leader.duties.get("lead", 0) + 1
        milestone(state, leader, "first_lead", "第一次帶隊出門，記得在回程重新點齊人數。")
        shared_memory(state, team, text, ["cooperation" if success else "failure"], sources)
        if any(c.stage < leader.stage for c in team[1:]):
            leader.duties["mentoring"] = leader.duties.get("mentoring", 0) + 1
            record(state, leader, "mentoring", f"帶著{team[1].name}走過一趟差事，回來還陪他重新整理經過。", 2, eid)
        relation = leader.relationships[team[1].id]
        if relation["cooperations"] >= 3:
            for char in team:
                partner = next(c for c in team if c.id != char.id)
                milestone(state, char, "partner:" + partner.id, f"和{partner.name}合作多次，已能認出對方遲疑時的神色。", 2)
    if not success and action.get("injury_risk") and action["risk"] in ("medium", "high"):
        injured = state.rng.choice(team)
        severity = 2 if action["risk"] == "high" else 1
        injured.injury = min(2, injured.injury + severity)
        injured.recovery_progress = 0
        wound = record(state, injured, "injury", f"在「{EVENTS[eid]['title']}」負傷，需要留門照料。", 4, eid)
        log(state, f"{injured.name}負傷，" + ("暫時無法出勤。" if injured.injury >= 2 else "仍可行動，但帶傷出勤會更吃力。"), "injury")
        enqueue(state, "injury_request", injured.id, wound.id)
        if len(team) > 1:
            rescuer = next(c for c in team if c.id != injured.id)
            rescue_text = f"{injured.name}負傷，{rescuer.name}將他背回山門。"
            rescue = record(state, rescuer, "rescue", rescue_text, 5, eid)
            received = record(state, injured, "rescued", rescue_text, 4, eid)
            shared_memory(state, [rescuer, injured], rescue_text, ["rescue"], [rescue.id, received.id, wound.id], 5, rescuer.id, injured.id)
            log(state, rescue_text, "person")
    if success:
        for char in team:
            if any(e.kind == "mission_failure" and e.tick < state.tick for e in char.experiences):
                milestone(state, char, "comeback", "曾經失手後再獲託付，這次終於帶回好消息。", 4)
                if "穩重" not in char.development:
                    char.development.append("穩重")
            if char.duties["missions"] >= 4 and action["risk"] == "high" and "果決" not in char.development:
                char.development.append("果決")
    return sources


def resolve_mission(state, action, team):
    memories = eligible_memories(state, [c.id for c in team], action["event_id"])
    bonus = recall(state, max(memories, key=lambda m: m.importance), action["event_id"]) if memories else 0
    if action["method"] == "supported":
        for char in team:
            record(state, char, "supported", "掌門先備妥支援才讓他出發；這一趟有人接應。", 2, action["event_id"])
    success = state.rng.randrange(100) < _chance(state, action, team, bonus)
    event = EVENTS[action["event_id"]]
    state.resources[event["resource"]] += event["reward"] if success else -2
    if action["event_id"] in ("escort", "caravan_talk") and success:
        state.factions["商隊"] = min(5, state.factions["商隊"] + 1)
    if action["event_id"] == "bandits":
        state.factions["烈川堂"] = max(-5, state.factions["烈川堂"] - 1)
    log(state, "、".join(c.name for c in team) + "：" + event["success" if success else "failure"])
    _mission_history(state, team, action, success)


def resolve_chain(state, action, team):
    method = action["method"]
    step = state.chain["step"]
    success = method in ("pay", "ally") or (method in ("investigate", "negotiate") and state.rng.randrange(100) < _chance(state, action, team))
    if method == "investigate" and success:
        state.chain["clues"] += 1
        text = ("車夫記得借車的人，並指出另一個交貨渡口。", "貨棧的人認出送帖人，願意下次到場說明。", "當事人把沿途見聞說清楚，送帖人承認冒用名義。")[step]
    elif method == "negotiate" and success:
        state.factions["商隊"] = min(5, state.factions["商隊"] + 1)
        text = "商隊接受暫緩追償，也願意在下次有消息時先知會山門。"
    elif method == "pay":
        state.resources["reputation"] += 2
        text = "山門先付了貨款，商隊眼前的損失有了著落，冒名的人仍需另查。"
    elif method == "ally":
        state.chain["clues"] += 1
        text = "地方行會派人問明交貨去向，把打聽到的消息帶回山門。"
    elif method == "ignore":
        state.resources["reputation"] -= 4
        state.factions["商隊"] = max(-5, state.factions["商隊"] - 1)
        text = "商隊暫時離去，沒有得到答覆的貨款成了山下的議論。"
    else:
        text = "這趟沒有問到可靠的消息，先前知道的事情仍然保留，日後還能換個方法處理。"
    log(state, text, "chain")
    if team:
        _mission_history(state, team, action, success)
    state.chain["step"] += 1
    state.chain["due"] = state.tick + 4
    state.chain["status"] = "等待後續消息"
    if step == 2:
        state.chain["status"] = "查明冒名者" if state.chain["clues"] >= 2 else "協商暫結，冒名者未明"
        state.resources["reputation"] += 8 if state.chain["clues"] >= 2 else 0
        for char in team:
            record(state, char, "chain_outcome", f"參與假名帖收束：{state.chain['status']}。", 4, action["event_id"])
        log(state, "假名帖：" + state.chain["status"] + "。山門的日子仍繼續。", "chain")


def rest_character(state, char, deliberate=False):
    char.fatigue = max(0, char.fatigue - 22)
    if char.injury:
        char.recovery_progress += 1
        if deliberate:
            record(state, char, "care", "掌門特地讓他留門養傷，派遣牌上空出了他的名字。", 2)
            char.last_opportunity = state.tick
        if char.recovery_progress >= 2:
            char.injury -= 1
            char.recovery_progress = 0
            log(state, f"{char.name}的傷勢減輕了。" if char.injury else f"{char.name}傷癒，能重新走出山門。", "injury")
            if not char.injury:
                milestone(state, char, "recovered", "養傷後重新站穩，記得這段日子誰替自己留了飯。", 2)


def duty(state, char, job):
    char.duties[job] = char.duties.get(job, 0) + 1
    count = char.duties[job]
    if job == "rest":
        rest_character(state, char)
        return
    tired = char.fatigue >= 65
    char.fatigue = min(100, char.fatigue + (5 if job == "train" else 8))
    if job == "guard":
        state.resources["defense"] += 1 if tired else 2
    elif job == "herbs":
        state.resources["treasury"] += max(0, state.facilities["herbs"] - 1) if tired else state.facilities["herbs"]
    elif job == "host":
        state.resources["treasury"] += 1 if tired else 2 + state.facilities["lodge"]
    skill = {"guard": "combat", "herbs": "medicine", "host": "diplomacy", "train": "combat"}[job]
    if count % 3 == 0:
        char.skills[skill] = min(10, char.skills[skill] + 1)
        record(state, char, job, f"長期{JOBS[job]}，如今能熟練地處理這份工作。", 2)
        if job != "train":
            char.last_opportunity = state.tick
    if job == "train" and state.facilities["training"] >= 2 and count % 4 == 0:
        char.skills["strategy"] = min(10, char.skills["strategy"] + 1)


def resolve_personal(state, action, team):
    item = next(p for p in state.personal_queue if p["id"] == action["item_id"])
    eid = item["event_id"]
    char = state.character(item["character_id"])
    if item["source_id"].startswith("m:"):
        memory = next(m for m in state.shared_memories if m.id == item["source_id"])
        bonus = recall(state, memory, eid)
        state.resources["reputation" if eid == "suspicion" else "treasury"] += 2 + bonus * 2
        for member in team:
            record(state, member, "memory_response", "舊事在今日再次被提起，同門因此願意繼續信任與合作。", 3 if memory.importance >= 4 else 2, eid)
        log(state, "大家決定先聽當事人說明，沒有把一次通信當成背叛。" if eid == "suspicion" else "兩人用熟悉的分工完成了這趟普通差事，帶回一筆糧餉。", "person")
    elif eid == "injury_request":
        rest_character(state, char, deliberate=True)
        log(state, f"你替{char.name}備了藥食，讓他安心休養。", "person")
    elif eid == "goal":
        direction = max(("herbs", "train", "lead"), key=lambda key: char.duties.get(key, 0))
        char.goal = {"herbs": "把藥圃管好，接下同門的日常照護", "train": "把自己的經驗教給後來的人", "lead": "讓跟自己出門的人都能平安返山"}[direction]
        record(state, char, "goal", f"主動向掌門提出：{char.goal}。", 3, eid)
        log(state, f"{char.name}說：「我想{char.goal}。」", "person")
    else:
        record(state, char, "second_chance" if eid == "failure_request" else "heard", "掌門聽完他的要求，答應重新安排機會；他願意再等幾旬。", 2, eid)
        char.neglect_warnings.clear()
        char.leave_intent = False
        log(state, f"你與{char.name}談定先整備、再辦事。他把行囊留在門邊，等下一次受託。", "person")
    for member in team:
        member.last_opportunity = state.tick
        member.fatigue = max(0, member.fatigue - 8)
    state.personal_queue.remove(item)


def autonomous_life(state, assignments):
    """Small interactions between actual available people; never invisible missions."""
    available = [c for c in state.active() if c.id in assignments]
    for holder in [c for c in available if c.office and c.actionable(state.tick) and assignments[c.id] != "rest" and c.fatigue < 65]:
        others = [c for c in available if c.id != holder.id]
        if holder.office == "medic":
            patient = next((c for c in others if c.injury and assignments[c.id] == "rest"), None)
            if patient:
                rest_character(state, patient)
                text = f"{holder.name}以藥堂主事的身分替{patient.name}換藥，縮短了休養的時間。"
                a = record(state, holder, "healing", text, 2)
                b = record(state, patient, "cared_by", text, 2)
                shared_memory(state, [holder, patient], text, ["care"], [a.id, b.id])
                log(state, text, "autonomous")
        elif holder.office == "leader":
            junior = next((c for c in others if c.actionable(state.tick) and assignments[c.id] == "train" and c.fatigue < 65), None)
            if junior:
                state.resources["treasury"] += 5
                text = f"{holder.name}主動帶{junior.name}替客舍送貨，普通差事已不用你逐一安排。"
                sources = [record(state, c, "delegated", text, 1).id for c in (holder, junior)]
                for c in (holder, junior):
                    c.last_opportunity = state.tick
                    c.fatigue = min(100, c.fatigue + 7)
                shared_memory(state, [holder, junior], text, ["cooperation"], sources)
                log(state, text, "autonomous")
        elif holder.office == "mentor":
            junior = next((c for c in others if c.actionable(state.tick) and assignments[c.id] == "train"), None)
            if junior:
                duty(state, junior, "train")
                text = f"{holder.name}留下來替{junior.name}拆招，練功時又多走了一步。"
                sources = [record(state, c, "mentoring" if c == holder else "mentored", text, 1).id for c in (holder, junior)]
                shared_memory(state, [holder, junior], text, ["cooperation"], sources)
                log(state, text, "autonomous")
    healthy = [c for c in available if c.actionable(state.tick) and c.fatigue < 65 and assignments[c.id] != "rest"]
    if len(healthy) >= 2 and state.rng.random() < .35:
        pair = state.rng.sample(healthy, 2)
        conflict = state.rng.random() < .2
        text = f"{pair[0].name}與{pair[1].name}" + ("為輪值先後爭了幾句，各自記住了對方不肯退讓的樣子。" if conflict else "做完手邊的事，一起在廊下練了幾招，漸漸熟悉對方的步子。")
        sources = [record(state, c, "conflict" if conflict else "companionship", text, 1).id for c in pair]
        shared_memory(state, pair, text, ["conflict" if conflict else "cooperation"], sources, 1)
        log(state, text, "autonomous")
    for char in state.active():
        gap = state.tick - char.last_opportunity
        if gap >= 8 and not char.neglect_warnings:
            char.neglect_warnings.append(state.tick)
            text = f"{char.name}說自己一直沒被託付差事；再等下去，可能會考慮離山。"
            record(state, char, "neglect_warning", text, 1)
            log(state, text, "warning")
            enqueue(state, "neglect", char.id, str(state.tick))
        elif gap >= 12 and len(char.neglect_warnings) == 1:
            char.neglect_warnings.append(state.tick)
            char.leave_intent = True
            log(state, f"{char.name}第二次提起離山，開始收拾行李。給他實際工作或回應要求，還能挽留。", "warning")
        elif gap >= 16 and len(char.neglect_warnings) >= 2 and char.neglect_warnings[-1] < state.tick:
            char.status = "left"
            text = f"{char.name}等過兩次答覆後，留下門牌離山；他想去找一個能用上自己的地方。"
            record(state, char, "departure", text, 3)
            state.major_outcomes.append({"tick": state.tick, "character_id": char.id, "kind": "left", "warnings": list(char.neglect_warnings)})
            log(state, text, "departure")


def annual_crisis(state):
    strength = state.resources["defense"] + state.resources["reputation"] // 3 + sum(c.skills["combat"] for c in state.active() if c.injury < 2)
    pressure = 52 + min(24, ((state.tick - 1) // 36) * 4) - state.factions["烈川堂"] * 2
    survived = strength >= pressure
    if survived:
        state.resources["defense"] -= 12
        state.resources["treasury"] -= 6
        text = "歲末守山：門人守住了山口。十二月只是這一年留下的里程碑，來年仍有新的日子。"
    else:
        state.ending = "山門失守"
        text = "歲末守山：守備與人手未能擋住壓力，眾人撤離青崖山，這一局門派歷史在此落幕。"
    state.annual_reports.append({"year": state.tick // 36, "tick": state.tick, "survived": survived,
                                 "strength": strength, "pressure": pressure, "text": text})
    for char in state.active():
        record(state, char, "annual_crisis", "與同門共同經歷歲末守山。", 4, "annual")
    log(state, text, "annual")


def resolve_turn(state, action_id, participant_ids, assignments=None, token=None):
    action, team, jobs = validate_plan(state, action_id, participant_ids, assignments, token)
    before = dict(state.resources)
    state.last_result = []
    state.resources["treasury"] -= action["cost"]
    kind = action["kind"]
    if kind == "mission":
        resolve_mission(state, action, team)
    elif kind == "chain":
        resolve_chain(state, action, team)
    elif kind == "personal":
        resolve_personal(state, action, team)
    elif kind == "rest":
        for char in team:
            rest_character(state, char, deliberate=True)
        log(state, "、".join(c.name for c in team) + "留門休養，今日不用趕路。")
    elif kind == "train":
        sources = []
        for char in team:
            duty(state, char, "train")
            char.last_opportunity = state.tick
            sources.append(record(state, char, "practice", "這旬受掌門安排，在練武場專心拆解招式。", 1).id)
        if len(team) == 2:
            team[0].duties["mentoring"] = team[0].duties.get("mentoring", 0) + 1
            record(state, team[0], "mentoring", f"陪{team[1].name}拆招，學著把自己會的本事說明白。", 2)
            shared_memory(state, team, f"{team[0].name}陪{team[1].name}拆招，從站姿開始慢慢練。", ["cooperation"], sources)
        log(state, "、".join(c.name for c in team) + "在練武場度過這一旬。")
    elif kind == "work":
        wages = sum(4 if c.fatigue >= 65 else 7 for c in team)
        state.resources["treasury"] += wages
        sources = []
        for char in team:
            char.fatigue = min(100, char.fatigue + 15)
            char.last_opportunity = state.tick
            sources.append(record(state, char, "work", "下山接了短工，把工錢帶回伙房換米。", 1).id)
        if len(team) == 2:
            shared_memory(state, team, f"{team[0].name}與{team[1].name}一起做短工，靠雙手補上山門糧餉。", ["cooperation"], sources, 1)
        log(state, "、".join(c.name for c in team) + f"帶回 {wages} 糧餉。")
    elif kind == "build":
        facility = action["facility"]
        state.facilities[facility] += 1
        names = "、".join(c.name for c in team)
        for char in team:
            char.last_opportunity = state.tick
            char.fatigue = min(100, char.fatigue + 12)
            record(state, char, "building", f"參與整修{FACILITIES[facility]}，山門的一部分留下了自己的手藝。", 3)
        state.story_flags[f"builder:{facility}"] = [c.id for c in team]
        log(state, f"{names}將{FACILITIES[facility]}修至 {state.facilities[facility]} 級。")
    elif kind == "appoint":
        char = team[0]
        char.office = action["office"]
        char.stage = 3
        char.last_opportunity = state.tick
        record(state, char, "promotion", f"獲任命為{OFFICES[char.office]}，從此替山門承擔一份長久的責任。", 5)
        log(state, f"{char.name}接過{OFFICES[char.office]}的職牌。", "promotion")
    for cid, job in jobs.items():
        duty(state, state.character(cid), job)
    autonomous_life(state, jobs)
    upkeep = max(1, (len(state.active()) + 1) // 2)
    state.resources["treasury"] -= upkeep
    state.resources["defense"] -= 1
    log(state, f"本旬伙食支出 {upkeep} 糧餉；山門日常耗損 1 防備。")
    if state.chain["step"] < 3 and state.tick >= state.chain["due"] + 3:
        state.resources["reputation"] -= 3
        state.factions["商隊"] = max(-5, state.factions["商隊"] - 1)
        state.chain["due"] = state.tick + 4
        log(state, "假名帖一直未獲回應，商隊先離開了；幾旬後仍會再來討說法。", "chain")
    if state.tick % 36 == 0:
        annual_crisis(state)
    state.starvation = state.starvation + 1 if state.resources["treasury"] <= 0 else 0
    if state.starvation == 1:
        log(state, "伙房已無餘糧；若連續三旬沒有糧餉，門人將無法留山。仍可安排短工或客舍接待補糧。", "warning")
    if state.starvation >= 3 or not state.active():
        state.ending = "糧盡散門" if state.starvation >= 3 else "門人散盡"
        log(state, state.ending + "。這座山門暫時留不住眾人。")
    for resource in state.resources:
        state.resources[resource] = max(0, min(999 if resource == "treasury" else 100, state.resources[resource]))
    state.last_changes = {key: state.resources[key] - before[key] for key in before}
    state.decisions.append({"tick": state.tick, "action_id": action_id, "label": action["title"],
                            "participants": list(participant_ids), "assignments": dict(jobs), "changes": dict(state.last_changes)})
    state.scene_history.append({"tick": state.tick, "event_id": action.get("event_id", kind), "text": list(state.last_result)})
    # Requests expire when their cause has been resolved; old requests cannot be farmed.
    state.personal_queue = [p for p in state.personal_queue if state.character(p["character_id"]).status == "active"
        and not (p["event_id"] == "injury_request" and not state.character(p["character_id"]).injury)
        and not (p["event_id"] in ("failure_request", "neglect") and state.character(p["character_id"]).last_opportunity > p["tick"])
        and not (p["source_id"].startswith("m:") and any(m.id == p["source_id"] and m.recalled_by for m in state.shared_memories))]
    state.resolved.add(f"{state.tick}:plan")
    state.phase = "ended" if state.ending else "result"


def next_tick(state, token=None):
    if state.phase != "result" or (token is not None and token != f"{state.tick}:next"):
        raise InvalidAction("請先完成本旬安排；舊頁面不能再次推進時間。")
    state.tick += 1
    prepare_tick(state)


def public_state(state):
    characters = []
    for char in state.characters:
        characters.append({"id": char.id, "name": char.name, "age": char.age, "background": char.background["summary"],
            "personality": char.personality, "signature": char.signature,
            "skills": {SKILLS[k]: v for k, v in char.skills.items()}, "stage": STAGES[char.stage],
            "office": OFFICES.get(char.office, ""), "status": char.status_display(state.tick)[0],
            "actionable": char.actionable(state.tick), "active": char.status == "active", "injury": char.injury,
            "fatigue": char.fatigue, "recent": char.recent, "goal": char.goal, "development": list(char.development),
            "relationships": [{"name": state.character(cid).name, "label": rel["label"]} for cid, rel in char.relationships.items()],
            "experiences": [{"id": e.id, "date": date_label(e.tick), "text": e.text} for e in char.experiences],
            "memories": [{"id": m.id, "date": date_label(m.tick), "text": m.text, "recalled": bool(m.recalled_by)} for m in state.shared_memories if char.id in m.participants]})
    return deepcopy({"version": state.version, "seed": state.seed, "tick": state.tick, "date": date_label(state.tick),
        "phase": state.phase, "resources": {RESOURCES[k]: v for k, v in state.resources.items()},
        "changes": {RESOURCES[k]: v for k, v in state.last_changes.items()}, "characters": characters,
        "facilities": {FACILITIES[k]: v for k, v in state.facilities.items()}, "factions": state.factions,
        "actions": available_actions(state), "last_result": state.last_result, "chain": state.chain,
        "logs": state.logs, "callbacks": state.callback_history, "annual_reports": state.annual_reports,
        "ending": state.ending})


def history_review(state):
    """A qualitative replay based only on things that actually happened."""
    result = []
    for char in state.characters:
        unique = {}
        for exp in sorted(char.experiences, key=lambda e: (-e.importance, e.tick)):
            unique.setdefault(exp.text, exp)
        important = list(unique.values())[:4]
        important.sort(key=lambda e: e.tick)
        result.append({"id": char.id, "name": char.name, "stage": STAGES[char.stage],
                       "story": [f"{date_label(e.tick)}：{e.text}" for e in important] or ["還沒有留下重要經歷。"]})
    return result
