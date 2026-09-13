"""Load and validate authored JSON; no UI dependency or network access."""
import json
import re
from functools import lru_cache
from pathlib import Path

from models import SKILLS, RESOURCES

DATA_DIR = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=1)
def load_story_data():
    with (DATA_DIR / "story_threads.json").open(encoding="utf-8") as stream:
        data = json.load(stream)
    validate_story_data(data)
    return data


def validate_views(event):
    assert set(event["character_views"]) == set(SKILLS), "Four role opinions required"
    assert event["npc_identity"] and event["current_question"]
    assert isinstance(event["investigation_options"], list)
    for variants in event["character_views"].values():
        assert len({v["dialogue"] for v in variants}) >= 2, "Two authored dialogue variants required"
        for view in variants:
            assert view["thought"] and view["dialogue"]
            assert 1 <= len(re.findall(r"[。！？]", view["dialogue"])) <= 2, "Dialogue must contain 1–2 sentences"


def validate_story_data(data):
    assert {t["id"] for t in data["threads"]} == {"old_road", "false_cards", "old_letters"}
    for thread in data["threads"]:
        if thread.get("engine") == "causal_v06":
            from case_engine import validate_case_thread
            validate_case_thread(thread)
            continue
        assert set(thread["required_clues"]) <= thread["clues"].keys()
        assert all(c["thread_id"] == thread["id"] for c in thread["clues"].values())
        nodes = {n["id"]: n for n in thread["evidence_graph"]}
        assert len(nodes) == len(thread["evidence_graph"])
        critical = {n["id"] for n in nodes.values() if n["critical"]}
        assert len(critical) == 3 and critical == set(thread["required_clues"])
        assert {nodes[cid]["type"] for cid in critical} == {"document", "physical", "witness"}
        assert 2 <= sum(n["kind"] == "evidence" and not n["critical"] for n in nodes.values()) <= 4
        assert 2 <= sum(n["kind"] == "lead" for n in nodes.values()) <= 3
        assert 1 <= sum(n["kind"] == "claim" for n in nodes.values()) <= 2
        hypotheses = {h["id"] for h in thread["hypotheses"]}
        assert len(hypotheses) == 4 and {"uncertain", thread["correct_hypothesis"]} <= hypotheses
        focuses = [*thread["investigations"], thread["cross_followup"]]
        focus_ids = {f["id"] for f in focuses}
        assert len(focus_ids) == len(focuses)
        for n in nodes.values():
            assert n["thread_id"] == thread["id"] and n["text"] and n["title"]
            assert set(n["requires"]) <= focus_ids
            assert set(n["supports"]) | set(n["contradicts"]) <= hypotheses
            if n["kind"] != "evidence":
                assert not n["critical"] and not n["supports"]
        for focus in focuses:
            assert focus["targets"] and set(focus["targets"]) <= nodes.keys()
            assert focus["cost"] >= 0 and focus["skill"] in SKILLS
            assert isinstance(focus["stable"], bool)
            assert all(focus["id"] in nodes[cid]["requires"] for cid in focus["targets"])
        assert {p["evidence_id"] for p in thread["recovery_paths"]} == critical, "Every critical clue needs a recovery path"
        assert all(10 in p["months"] for p in thread["recovery_paths"])
        assert [c["month"] for c in thread["deduction_checkpoints"]] == [4, 8, 11]
        for pair in thread["cross_pairs"]:
            assert len(set(pair)) == 2 and all(nodes[cid]["kind"] == "evidence" for cid in pair)
        for scene in thread.get("monthly_scenes", {}).values():
            validate_views(scene)
            assert set(scene["focus_ids"]) <= focus_ids | {"hear_claim", "hear_external"}
            for option in scene.get("options", []):
                assert option["skill"] in SKILLS and option["count"] in (1, 2)
                assert option["cost"] >= 0 and not option["intel"]
                for outcome in ("success", "failure"):
                    assert set(option[outcome]) <= RESOURCES.keys()
                    assert all(len(v) == 2 and v[0] <= v[1] for v in option[outcome].values())
                    assert len(set(option[outcome + "_narratives"])) >= 2


def validate_data(characters, missions, personal):
    banned = ("有了進展", "未能如期完成", "這次的安排已落實", "同行者帶回了具體阻礙與損失", "下回仍得先看清局面", "把今日經過逐項寫下，請你核對")
    authored = json.dumps([characters, missions, personal], ensure_ascii=False)
    assert not any(phrase in authored for phrase in banned), "Generic narrative placeholder"
    events = missions["events"]
    assert len({e["id"] for e in events}) == len(events), "Duplicate event IDs"
    assert len([e for e in events if not e.get("fixed_month")]) >= 16
    assert {e["fixed_month"] for e in events if e.get("fixed_month")} == {1, 4, 8, 12}
    arc_ids = {a["id"] for a in personal["arcs"]}
    assert len(arc_ids) >= 6
    tags = {tag for bg in characters["backgrounds"] for tag in bg["tags"]}
    assert len(characters["signatures"]) >= 4
    assert set(characters["role_judgments"]) == set(SKILLS)
    assert all(r["reliable_domain"] and r["blind_spot"] for r in characters["role_judgments"].values())
    for secret in characters["secrets"]:
        assert set(secret["requires"]) <= tags
        assert secret["arc"] is None or secret["arc"] in arc_ids
    for event in events:
        validate_views(event)
        assert 80 <= len(event["scene_opening"]) <= 180, event["id"]
        assert event["concrete_detail"] and event["callback_fact"]
        assert len(event["options"]) == (0 if event.get("fixed_month") == 12 else 3)
        assert len({o["id"] for o in event["options"]}) == len(event["options"])
        for option in event["options"]:
            for key in ("success_narratives", "failure_narratives"):
                assert len(set(option[key])) >= 2
                assert all(len(text) >= 45 for text in option[key])
            assert option["skill"] in SKILLS and option["count"] in (1, 2)
            assert option["risk"] in ("low", "medium", "high", "lethal")
            assert option["cost"] >= 0
            assert set(option["intel"]) <= missions["intel"].keys()
            assert set(option["flags"]) <= missions["flags"].keys()
            assert set(option["background_modifiers"]) <= tags
            for outcome in ("success", "failure"):
                assert set(option[outcome]) <= RESOURCES.keys()
                assert all(len(v) == 2 and v[0] <= v[1] for v in option[outcome].values())
            if option["risk"] == "lethal":
                assert "致命風險" in option["visible_hint"]
    for arc in personal["arcs"]:
        assert len(set(arc["resolutions"].values())) >= 2
        assert len(arc["stages"]) == 3 and 2 <= len(arc["choices"]) <= 3
        assert len({tuple(c["tradeoffs"]) for c in arc["choices"]}) >= 2
        assert all(len(c["tradeoffs"]) >= 2 for c in arc["choices"])
    patterns = [json.dumps([(c["effects"], c["psych"], c["reaction"]) for c in arc["choices"]], sort_keys=True) for arc in personal["arcs"]]
    assert len(set(patterns)) == len(patterns), "Personal arcs share identical mechanics and reactions"


@lru_cache(maxsize=1)
def load_data():
    values = []
    for filename in ("character_templates.json", "mission_events.json", "personal_events.json"):
        with (DATA_DIR / filename).open(encoding="utf-8") as stream:
            values.append(json.load(stream))
    validate_data(*values)
    return tuple(values)
