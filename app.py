"""v0.7 Streamlit UI: people, assignments and remembered history."""
import secrets
import importlib
from uuid import uuid4

import streamlit as st
import game_runtime

APP_VERSION = "0.7"
st.set_page_config(page_title="危門 · 山門歲月", page_icon="⛰️", layout="wide")
try:
    # Cloud can rerun this entrypoint while the v0.6 launcher stays imported.
    # Refresh the launcher before asking it to select an engine it never knew.
    if not callable(getattr(game_runtime, "load_sect_engine", None)):
        importlib.invalidate_caches()
        importlib.reload(game_runtime)
    engine = game_runtime.load_current_engine(APP_VERSION)
except (ImportError, RuntimeError) as exc:
    st.error(str(exc))
    st.stop()

from sect_models import JOBS, date_label
from models import SKILLS, RISK_NAMES
import sect_feedback
import sect_save


def restart():
    for key in list(st.session_state):
        if key != "seed_input":
            del st.session_state[key]


def start_new_game():
    previous = st.session_state.get("game")
    seed = int(st.session_state.get("seed_input", getattr(previous, "seed", 42)))
    current = engine.new_game(seed)
    restart()
    st.session_state.game = current
    st.session_state.response_id = str(uuid4())


def random_seed():
    st.session_state.seed_input = secrets.randbelow(2**32)


def draw_save(state=None):
    with st.expander("本機存檔／讀檔"):
        st.caption("下載 JSON 保存進度；日後可讀回。存檔需使用相同版本規則，最多支援 1000 旬。")
        if state is not None:
            try:
                payload = sect_save.export_save(state)
            except ValueError as exc:
                st.info(str(exc))
            else:
                st.download_button("下載這局存檔", payload, file_name=f"weimen_v07_{state.seed}_{state.tick}.json", mime="application/json", key="download_save")
        uploaded = st.file_uploader("選擇 v0.7 存檔", type=["json"], key="save_file")
        if st.button("讀取並切換至此存檔", disabled=uploaded is None, key="load_save"):
            try:
                restored = sect_save.import_save(uploaded.getvalue())
            except ValueError as exc:
                st.error(str(exc))
            else:
                restart()
                st.session_state.game = restored
                st.session_state.response_id = str(uuid4())
                st.rerun()


def run_action(fn, *args):
    try:
        fn(*args)
    except (engine.InvalidAction, ValueError) as exc:
        st.error(str(exc))
    else:
        # Prune controls for completed turns in this open-ended campaign.
        for key in list(st.session_state):
            if key.startswith(("action_", "team_", "job_")):
                del st.session_state[key]
        st.rerun()


def draw_people(view):
    columns = st.columns(2)
    for index, char in enumerate(view["characters"]):
        with columns[index % 2], st.container(border=True):
            st.subheader(char["name"])
            st.caption(f"{char['age']} 歲 · {char['background']} · {char['personality']}")
            st.write(f"**{char['stage']}**" + (f" · {char['office']}" if char["office"] else "") + f" · {char['status']}")
            st.write(" · ".join(f"{k} {v}" for k, v in char["skills"].items()))
            st.caption(char["signature"])
            st.write(char["recent"])
            if char["goal"]:
                st.info("想走的方向：" + char["goal"])
            if char["development"]:
                st.write("經歷留下的變化：" + "、".join(char["development"]))
            with st.expander("人際與共同記憶"):
                for relation in char["relationships"]:
                    st.write(relation["name"] + " · " + relation["label"])
                for memory in reversed(char["memories"][-12:]):
                    st.write(f"{memory['date']} · {memory['text']}" + ("（後來又被提起）" if memory["recalled"] else ""))
                if not char["memories"]:
                    st.caption("尚未一起經歷事情。")
            with st.expander("人物經歷"):
                for exp in reversed(char["experiences"]):
                    st.write(f"{exp['date']} · {exp['text']}")


def draw_planning(state, view):
    st.subheader("這一旬，把事情交給誰？")
    st.caption("選一項主要安排，再分配其他門人的留門工作。第一位出勤者帶隊；同旬每人只有一份安排。")
    by_id = {a["id"]: a for a in view["actions"]}
    pending = [a for a in view["actions"] if a["kind"] in ("personal", "appoint")]
    if pending:
        st.info("有人在等你回應：" + "；".join(a["title"] for a in pending[:4]) + (f"；另有 {len(pending) - 4} 件，可在下方選單查看。" if len(pending) > 4 else "。"))
    else:
        st.caption("門人今日沒有特別的請求，你可以自行安排外勤與門務。")
    action_id = st.selectbox("本旬要處理的事", list(by_id), format_func=lambda aid: by_id[aid]["title"], key=f"action_{view['tick']}")
    action = by_id[action_id]
    st.write(action["description"])
    st.caption(f"花費 {action['cost']} 糧餉 · 風險：{RISK_NAMES[action['risk']]} · 人數 {action['minimum']}～{action['maximum']}" +
               (f" · 適合{SKILLS[action['skill']]}專長" if action.get("skill") else ""))
    if action["risk"] != "low" and action.get("injury_risk"):
        st.warning("失手可能負傷；高風險失敗可能重傷。同行者能在危急時接應，備妥支援也能降低風險。")
    elif action["risk"] != "low":
        st.caption("這項風險影響辦事成果；交涉或查問失利不會直接造成負傷。")
    if action["kind"] == "appoint":
        st.info("職務效果在留門工作時生效；安排休養、外勤或過度疲憊時暫停。")
    people = {c["id"]: c for c in view["characters"]}
    eligible = [c["id"] for c in view["characters"] if c["active"] and (action.get("allow_injured") or c["actionable"])]
    required = action.get("required", [])
    if required:
        eligible = required
    team = st.multiselect("參與門人（第一位帶隊）", eligible, default=required,
        format_func=lambda cid: f"{people[cid]['name']}｜{people[cid]['status']}｜" + " · ".join(f"{key}{value}" for key, value in people[cid]["skills"].items()),
        key=f"team_{view['tick']}_{action_id}", disabled=bool(required) or action["maximum"] == 0,
        max_selections=action["maximum"] or None)
    jobs = {}
    with st.expander("留門分工", expanded=True):
        st.caption("休養減輕傷疲；守山增加防備；藥圃與客舍補充糧餉；修煉累積本事。疲勞達 65 時，工作收穫會減少，請輪替休息。")
        remaining = [c for c in view["characters"] if c["active"] and c["id"] not in team]
        columns = st.columns(2)
        for index, char in enumerate(remaining):
            with columns[index % 2]:
                options = list(JOBS) if char["actionable"] else ["rest"]
                default = "rest" if char["fatigue"] >= 45 or char["injury"] or not char["actionable"] else ("host", "guard", "herbs", "train")[index % 4]
                jobs[char["id"]] = st.selectbox(f"{char['name']} · {char['status']} · 疲勞 {char['fatigue']}", options,
                    index=options.index(default), format_func=lambda key: JOBS[key], key=f"job_{view['tick']}_{action_id}_{char['id']}")
    st.caption(f"本旬另需 {max(1, (sum(c['active'] for c in view['characters']) + 1) // 2)} 糧餉伙食及 1 防備維護耗損。")
    try:
        engine.validate_plan(state, action_id, team, jobs)
        valid = True
    except engine.InvalidAction as exc:
        valid = False
        st.info(str(exc))
    if st.button("確定安排，度過這一旬", type="primary", key="confirm_turn", disabled=not valid):
        run_action(engine.resolve_turn, state, action_id, team, jobs, f"{view['tick']}:plan")


def draw_review(state):
    if len(state.decisions) < 24 and state.phase != "ended":
        return
    with st.expander("回看這一局 · 你最記得誰？", expanded=len(state.decisions) == 24 or state.phase == "ended"):
        st.write("先不用看數字：這一局你最記得誰？為什麼？如果重新開始，同一批人會不會變得不同？")
        st.caption("這是第一段山門歲月的回看，可以填完後繼續遊玩。回答只保存在本機。")
        if st.session_state.get("survey_saved"):
            st.success("這局的回看已保存。")
        else:
            with st.form("history_feedback"):
                who = st.selectbox("你最記得誰？", [c.name for c in state.characters] + ["沒有特別記得的人"], key="memorable")
                why = st.text_area("因為發生過什麼？", max_chars=2000, key="reason")
                replay = st.radio("再玩一局，同一批人可能不一樣嗎？", ["可能很不一樣", "也許", "感覺差不多"], key="replay")
                submitted = st.form_submit_button("保存這局的感受")
            if submitted:
                try:
                    response_id = st.session_state.get("response_id") or str(uuid4())
                    st.session_state.response_id = response_id
                    sect_feedback.save_feedback(state, who, why, replay, response_id)
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
                else:
                    st.session_state.survey_saved = True
                    st.rerun()
        for char in engine.history_review(state):
            st.markdown(f"**{char['name']} · {char['stage']}**")
            for line in char["story"]:
                st.write(line)


def main():
    st.title("危門 · 山門歲月")
    st.caption("六名普通門人，一座山門；誰會被記住，要由往後的日子決定。 · v0.7")
    if "game" not in st.session_state:
        st.write("你接下青崖門的門務。山下有要辦的差事，山上有漏雨的屋舍，也有人等著第一次獨自出門。每旬安排誰出勤、誰照顧山門、誰安心養傷；日後再遇到事情，同門會記起曾經一起走過的路。")
        st.info("先玩 24 旬，看看你會記得誰。每月三旬，跨年後仍可繼續；十二月是年度危機。")
        st.number_input("遊戲種子", min_value=0, max_value=2**32 - 1, value=42, step=1, key="seed_input")
        st.button("隨機種子", on_click=random_seed)
        st.button("開始新遊戲", type="primary", key="start", on_click=start_new_game)
        draw_save()
        return
    state = st.session_state.game
    if getattr(state, "version", "") != APP_VERSION:
        st.info("這局使用舊版月份與案件規則。v0.7 改為六人門派與旬制經營，需要以原種子另開新局。")
        st.button("開始新版遊戲", type="primary", key="start_current_version", on_click=start_new_game)
        return
    view = engine.public_state(state)
    with st.sidebar:
        st.header("青崖門")
        st.write(view["date"])
        st.caption(f"種子 {view['seed']} · 已完成 {len(state.decisions)} 次決策")
        for label, level in view["facilities"].items():
            st.write(f"{label} · {level} 級")
        st.caption("二級藥圃＋長期醫療工作可任藥堂主事；二級客舍＋帶隊經歷可任外務領隊；二級練武場＋帶新人可任教習。人物也需累積為核心人物。")
        st.write("假名帖：" + view["chain"]["status"])
        for faction, relation in view["factions"].items():
            st.write(f"{faction}：" + ("友好" if relation > 0 else "緊張" if relation < 0 else "平常往來"))
        draw_save(state)
        st.button("重新開始", on_click=restart)
        st.caption("離開前可下載存檔，避免連線中斷後失去進度。")
    st.subheader(view["date"])
    for column, (label, value) in zip(st.columns(3), view["resources"].items()):
        column.metric(label, value, delta=view["changes"].get(label) if view["phase"] != "planning" else None)
    if (view["tick"] - 1) % 36 >= 30 and view["phase"] != "ended":
        st.warning("歲末守山將在十二月下旬到來。山門防備、聲望、能行動的門人武力及與烈川堂的關係，都會影響能否守住山口。")
    planning, people, history = st.tabs(["本旬安排", "門人與共同歷史", "山門記事"])
    with planning:
        if view["phase"] == "planning":
            draw_planning(state, view)
        else:
            st.subheader("這旬發生的事" if view["phase"] == "result" else view["ending"])
            for line in view["last_result"]:
                st.write(line)
            if view["phase"] == "result" and st.button("進入下一旬", type="primary", key="next_tick"):
                run_action(engine.next_tick, state, f"{view['tick']}:next")
        draw_review(state)
    with people:
        draw_people(view)
    with history:
        st.subheader("山門記得的事")
        for entry in reversed(view["logs"]):
            st.write(f"{date_label(entry['tick'])} · {entry['text']}")
        if not view["logs"]:
            st.caption("這座山門的故事還未開始。")


if __name__ == "__main__":
    main()
