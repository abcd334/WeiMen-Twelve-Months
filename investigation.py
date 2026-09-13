"""Case evidence and player deductions. No Streamlit, no hidden-random judgments."""
from copy import deepcopy
from data_loader import load_story_data
from models import SKILLS


def thread_for(state):
    return next(t for t in load_story_data()["threads"] if t["id"] == state.main_thread)


def graph_for(state):
    thread = thread_for(state)
    return {n["id"]: n for n in [*thread["evidence_graph"], thread["cross_lead"]]}


def case_scene(state):
    return thread_for(state).get("monthly_scenes", {}).get(str(state.month), {})


def investigation_options(state):
    thread = thread_for(state)
    if thread.get('engine') == 'causal_v06':
        return []
    options = deepcopy(thread["investigations"])
    options += [
        {"id":"hear_claim", "label":"找經手人，留下原話", "targets":[state.main_thread+"_claim"], "cost":0, "skill":"diplomacy", "stable":True, "hint":"只記人物說法，尚不能列為已證實。"},
        {"id":"hear_external", "label":"聽取外部聯絡的說明", "targets":[state.main_thread+"_external_claim"], "cost":0, "skill":"diplomacy", "stable":True, "hint":"來往、內容與背叛意圖必須分開查，說明不直接證明清白或有罪。"},
    ]
    scene = case_scene(state)
    if scene.get("focus_ids"):
        options = [o for o in options if o["id"] in scene["focus_ids"]]
    if state.month >= 9 and any(n["id"] == thread["cross_lead"]["id"] for n in state.leads):
        options.append(deepcopy(thread["cross_followup"]))
    if state.month in (10, 11):
        for path in thread["recovery_paths"]:
            if path["evidence_id"] not in state.evidence:
                options.append({"id":path["focus_id"], "label":path["label"], "targets":[path["evidence_id"]], "cost":2, "skill":"diplomacy", "stable":True, "recovery":True, "hint":"改查封存副本或第二位見證人；門務失敗不會取消這項補證。"})
        missing = [cid for cid in thread["required_clues"] if cid not in state.evidence]
        if missing:
            options.append({"id":"recover_chain", "label":"逐項補查尚缺的文件、物證與見證", "targets":missing, "cost":4, "skill":"diplomacy", "stable":True, "recovery":True, "hint":"用一整班工走完仍缺的補查管道，支出 4 糧餉；保留已取得證據。"})
    for option in options:
        option["already_known"] = all(cid in state.evidence or any(n["id"] == cid for n in state.leads + state.claims) for cid in option["targets"])
    return [{"id":"none", "label":"本月只處理門務", "cost":0,"skill":"strategy","targets":[], "hint":"不另查案件，也不會自動取得下一份證據。", "stable":True, "already_known":False}, *options]


def public_investigations(state):
    return [{"id":o["id"], "label":o["label"], "cost":o["cost"], "skill":SKILLS[o["skill"]], "hint":o["hint"], "already_known":o["already_known"]} for o in investigation_options(state)]


def store_item(state, node, source, focus_id=""):
    from game_engine import record_fact
    kind = node["kind"]
    target = state.evidence if kind == "evidence" else state.claims if kind == "claim" else state.leads
    if (node["id"] in target if isinstance(target, dict) else any(n["id"] == node["id"] for n in target)):
        return None
    item = {k: node[k] for k in ("id", "title", "text", "type", "thread_id")}
    item.update(month=state.month, source=source, focus_id=focus_id)
    if state.main_thread == 'false_cards':
        item.update(action_id=focus_id, episode_id=state.current_episode_id,
                    question_id=state.current_question_id)
    label = {"evidence":"已證實", "lead":"待核實", "claim":"人物說法"}[kind]
    item["fact_id"] = record_fact(state, label + "：" + item["text"], "intel" if kind == "evidence" else kind, source)
    if kind == "evidence":
        state.evidence[node["id"]] = item
        state.intel[node["id"]] = item["text"]
        state.clue_metadata[node["id"]] = {"thread_id":state.main_thread,"clue_type":node["type"],"text":item["text"]}
        state.leads[:] = [n for n in state.leads if n["id"] != "pending:" + node["id"]]
    else:
        target.append(item)
    return item["fact_id"]


def resolve_investigation(state, focus, team, mission_success, option_id):
    from game_engine import add_callback, contact_unavailable, record_fact
    if focus["id"] == "none":
        return []
    blocked = (state.main_thread == "old_letters" and not focus.get("recovery") and contact_unavailable(state))
    witness_refused = state.main_thread == "false_cards" and state.month == 5 and focus["id"] == "confront_witness" and option_id != "verify_witness"
    # The verification itself is explicit and deterministic. A reliable copied
    # record/recovery is not lost merely because the accompanying chores failed.
    effective_skill = max(c.skills[focus["skill"]] for c in team)
    verified = not blocked and not witness_refused and (focus["stable"] or mission_success or effective_skill >= 4)
    if state.main_thread == "false_cards" and state.month == 5 and option_id == "verify_witness" and not blocked:
        verified = True
    graph = graph_for(state)
    facts = []
    for cid in focus["targets"]:
        if cid in state.evidence:
            continue
        node = graph[cid]
        if node["kind"] != "evidence" or verified:
            fid = store_item(state, node, "、".join(c.name for c in team) + "／" + focus["label"], focus["id"])
        else:
            pending = {**node,"id":"pending:"+cid,"kind":"lead","type":"lead", "text":"尚未完成「"+node["title"]+"」的核對。" + ("原聯絡管道暫時無法交件，可於後段改查封存留底。" if blocked else "這次未接上來源，之後仍可再查或從補證管道取得。")}
            fid = store_item(state, pending, focus["label"], focus["id"])
        if fid:
            facts.append(fid)
            text = next(f["text"] for f in state.facts if f["id"] == fid)
            state.last_result.append(text)
            add_callback(state, fid, "你當時選擇「"+focus["label"]+"」，留下的查證結果是："+text)
    state.investigation_history.append({"month":state.month,"focus_id":focus["id"],"label":focus["label"],"verified":verified,"fact_ids":facts})
    if witness_refused:
        fid = record_fact(state, "證人不願替公開指控作保。要取得核對證詞，仍須安排看過原件的見證人。", "lead", "witness")
        facts.append(fid)
        state.last_result.append(state.facts[-1]["text"])
    return facts


def evidence_board(state):
    graph, thread = graph_for(state), thread_for(state)
    excluded = {}
    labels = {h["id"]:h["label"] for h in thread["hypotheses"]}
    for cid, item in state.evidence.items():
        for hypothesis in graph[cid]["contradicts"]:
            excluded.setdefault(hypothesis, {"title":labels[hypothesis],"sources":[]})["sources"].append(item["title"])
    return {"confirmed":deepcopy(list(state.evidence.values())), "pending":deepcopy(state.leads), "claims":deepcopy(state.claims), "excluded":list(excluded.values())}


def checkpoint_view(state):
    from game_engine import InvalidAction
    if state.phase != "deduction":
        raise InvalidAction("現在不是推理階段。")
    checkpoint = next(c for c in thread_for(state)["deduction_checkpoints"] if c["month"] == state.month)
    return {**checkpoint, "hypotheses":deepcopy(thread_for(state)["hypotheses"]) if state.month == 4 else [],
            "evidence":[{k: v for k,v in e.items() if k in ("id","title","text","type","month","source")} for e in state.evidence.values()]}


def chain_complete(state):
    thread = thread_for(state)
    required = set(thread["required_clues"])
    return (required <= state.evidence.keys() and any(h["month"] == 11 and h["accepted"] and required <= set(h["evidence_ids"]) for h in state.deduction_history))


def resolve_deduction(state, hypothesis=None, evidence_ids=(), token=None):
    from game_engine import InvalidAction, record_fact, record_decision, add_callback
    expected = f"{state.month}:deduction"
    if state.phase != "deduction" or expected in state.resolved or (token is not None and token != expected):
        raise InvalidAction("此推理已結算，或頁面已過期。")
    thread, graph = thread_for(state), graph_for(state)
    causal = thread.get('engine') == 'causal_v06'
    if causal:
        import case_engine
        episode = case_engine.current_episode(state)
        if episode['kind'] != 'deduction':
            raise InvalidAction('本月事件沒有要求推理答覆。')
        before = case_engine.snapshot(state)
    evidence_ids = list(evidence_ids)
    if state.month != 4 and hypothesis is not None:
        raise InvalidAction("本次請選證據，不接受假說代替證據。")
    if len(set(evidence_ids)) != len(evidence_ids) or any(cid not in state.evidence for cid in evidence_ids):
        raise InvalidAction("只能使用自己已取得的證據，且不能重複選同一份。")
    if state.month == 4:
        if hypothesis not in {h["id"] for h in thread["hypotheses"]} or evidence_ids:
            raise InvalidAction("請選擇本次提供的一項假說。")
        supported = any(hypothesis in graph[cid]["supports"] for cid in state.evidence)
        accepted = hypothesis == "uncertain" or (hypothesis == thread["correct_hypothesis"] and supported)
        label = next(h["label"] for h in thread["hypotheses"] if h["id"] == hypothesis)
        text = "暫列假說：「"+label+"」。" + ("先保留查證空間，後面仍須核對原件與其他來源。" if accepted else "現有資料還不足以支持這個判斷，後續要多花時間澄清；補證入口仍保留。")
        state.hypotheses["working"] = hypothesis
    elif state.month == 8:
        if len(evidence_ids) not in (0,2):
            raise InvalidAction("請選兩份證據，或明確保留為證據不足。")
        accepted = any(set(pair) == set(evidence_ids) for pair in thread["cross_pairs"])
        label = "交叉核對：" + "、".join(state.evidence[cid]["title"] for cid in evidence_ids) if evidence_ids else "目前無法交叉核對"
        text = label + ("。兩份不同來源可以接上，已打開追問交付者的方向。" if accepted else "。仍不足以證明兩份資料指向同一件事；既有證據保留，下一步可重新追問來源。")
        if causal and accepted:
            index = next(i for i, pair in enumerate(thread['cross_pairs']) if set(pair) == set(evidence_ids))
            text += thread['cross_reasons'][index]
    elif state.month == 11:
        if len(evidence_ids) not in ((0, 1, 2, 3) if causal else (0,3)):
            raise InvalidAction("請選文件、物證、見證各一份，或保留為證據鏈不足。")
        slots = [state.evidence[cid]["type"] for cid in evidence_ids]
        accepted = set(thread["required_clues"]) <= set(evidence_ids) and slots == ["document","physical","witness"]
        label = "最終證據鏈：" + " → ".join(state.evidence[cid]["title"] for cid in evidence_ids) if evidence_ids else "保留未完整的證據鏈"
        text = label + ("。三個環節的來源接得上，明日可以完整說明案件。" if accepted else "。仍有來源或交叉關係未接上；可以守山，但目前只能提出已核實的部分。")
    else:
        raise InvalidAction("本月沒有推理節點。")
    state.resolved.add(expected)
    # An unsupported inference costs reputation, never survival resources or an
    # immediate irreversible character outcome. Evidence remains append-only.
    if not accepted and (hypothesis or evidence_ids):
        loss = min(2, state.resources["reputation"])
        state.resources["reputation"] = max(0, state.resources["reputation"] - 2)
        text += f"（江湖聲望 -{loss}，案件資料仍保留。）"
    facts = [record_fact(state, text, "deduction", expected)]
    if state.month == 8 and accepted:
        fid = store_item(state, thread["cross_lead"], "第八月交叉核對")
        if fid:
            facts.append(fid)
    row = {"month":state.month,"hypothesis":hypothesis,"evidence_ids":evidence_ids,"accepted":accepted,"text":text,"fact_ids":facts}
    state.deduction_history.append(row)
    record_decision(state, label, facts, True)
    if state.month < 11 and not causal:
        add_callback(state, facts[0], text, due=state.month+1)
    state.last_result = [text]
    state.phase = "deduction_result"
    if causal:
        action_id = case_engine.current_episode(state)['action_ids'][0]
        state.resolved.add(f'{state.month}:day')
        state.last_participants = []
        case_engine.capture_day(state, action_id, [], accepted and hypothesis != 'uncertain',
                                before, facts, deduction=row)
