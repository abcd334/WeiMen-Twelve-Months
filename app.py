"""Local Streamlit presentation; hidden data never enters a display component."""
import secrets
from uuid import uuid4

import streamlit as st

from feedback import DEFAULT_PATH, save_feedback, survey_options
from game_engine import (InvalidAction, begin_month, current_event, emergency_rest,
                         ending_view, legal_actions, new_game, night_view, public_option,
                         public_state, resolve_day, resolve_night, start_night)

st.set_page_config(page_title="危門十二月", page_icon="⛰️", layout="wide")


def restart():
    for key in list(st.session_state):
        if key != "seed_input":
            del st.session_state[key]


def random_seed():
    st.session_state.seed_input = secrets.randbelow(2**32)


def run_action(action, *args):
    try:
        action(*args)
    except (InvalidAction, ValueError) as exc:
        st.error(str(exc))
    else:
        st.rerun()


def draw_sidebar(view):
    names = {c["id"]: c["name"] for c in view["characters"]}
    with st.sidebar:
        st.header("青崖門手記")
        st.caption(f"本局種子：{view['seed']}")
        with st.expander("觀察札記", expanded=False):
            st.caption("可核對事實是已觀察到的依據；言行觀察仍需比對；日常片段只記性格與情境。")
            if not view["observations"]:
                st.write("尚未留下觀察。")
            for cue in reversed(view["observations"]):
                st.markdown(f"**第 {cue['month']} 月 · {names[cue['character_id']]} · {cue['kind']}**")
                st.write(cue["text"])
        with st.expander("已知情報"):
            for text in view["intel"] or ["尚未取得可核對的敵方情報。"]:
                st.write(text)
        with st.expander("事件紀錄"):
            for log in reversed(view["logs"]):
                st.write(f"第 {log['month']} 月：{log['text']}")
        with st.expander("已公開狀態旗標"):
            for flag in view["flags"] or ["尚無已公開事項。"]:
                st.write(flag)
        st.button("重新開始", on_click=restart)
        st.caption("單局保留在目前瀏覽器工作階段；重新整理連線或關閉伺服器可能重置。")


def draw_cards(view):
    for column, char in zip(st.columns(4), view["characters"]):
        with column, st.container(border=True):
            st.subheader(char["name"])
            st.caption(f"{char['age']} 歲 · {char['role']}專長 · {char['personality']}")
            st.write(" · ".join(f"{k} {v}" for k, v in char["skills"].items()))
            st.markdown(f"**{char['physical']}**")
            st.write(char["signature"])
            with st.expander("人物小傳與近況"):
                st.write(char["background"])
                st.write(char["recent"])
                for experience in char["experiences"]:
                    st.caption(experience)


def draw_day(state, view):
    event = view["event"]
    st.header(event["title"])
    st.write(event["description"])
    for column, option in zip(st.columns(3), event["options"]):
        with column, st.container(border=True):
            st.markdown(f"**{option['label']}**")
            st.write(option["hint"])
            st.caption(f"糧餉成本 {option['cost']} · 建議{option['skill']} · 派遣 {option['count']} 人")
            if option["risk"] == "致命風險":
                st.error("致命風險：可能造成弟子死亡")
            else:
                st.write("風險：" + option["risk"])
            st.caption("可能影響：" + "、".join(option["affected_resources"]))
            st.caption("可能有延遲後果" if option["delayed"] else "無預設延遲後果")
    if not legal_actions(state):
        st.warning("目前沒有符合人數、傷勢與糧餉要求的派遣。須留門休整，承擔失去處理時機的代價。")
        if st.button("全員留門休整", key="rest"):
            run_action(emergency_rest, state)
        return
    options = {o["id"]: o for o in event["options"]}
    option_id = st.radio("選擇本月方案", list(options), format_func=lambda key: options[key]["label"],
                         key=f"plan_{view['month']}")
    option = options[option_id]
    available = {c["id"]: c for c in view["characters"] if c["actionable"]}
    members = st.multiselect("派遣弟子（確認前可更換）", list(available),
                             format_func=lambda cid: available[cid]["name"],
                             max_selections=option["count"], key=f"team_{view['month']}_{option_id}")
    preview = public_option(state, next(o for o in current_event(state)["options"] if o["id"] == option_id), members)
    for hint in preview["extra_hints"]:
        st.info(hint)
    valid = len(members) == option["count"] and option["cost"] <= view["resources"]["糧餉"]
    st.caption("確認後立即結算一次；未派遣者將有機會在次月休養。")
    if st.button("確認派遣", type="primary", disabled=not valid, key="confirm_day"):
        run_action(resolve_day, state, option_id, members, f"{view['month']}:day")


def draw_night(state, view):
    scene = night_view(state)
    st.header("夜間人物互動 · " + scene["name"])
    st.write(scene["text"])
    choices = {c["id"]: c for c in scene["choices"]}
    for choice in choices.values():
        st.markdown(f"**{choice['label']}** · 糧餉成本 {choice['cost']}")
        st.write(choice["hint"])
        st.caption("取捨：" + "／".join(choice["tradeoffs"]))
    choice_id = st.radio("固定回應", list(choices), format_func=lambda key: choices[key]["label"], key=f"night_{view['month']}")
    if st.button("確認回應", type="primary", key="confirm_night",
                 disabled=choices[choice_id]["cost"] > view["resources"]["糧餉"]):
        run_action(resolve_night, state, choice_id, f"{view['month']}:night")


def draw_ending(state):
    end = ending_view(state)
    st.header("青崖門結局 · " + end["ending"])
    st.write(end["reason"])
    st.subheader("四名弟子的去向")
    for char in end["characters"]:
        with st.expander(char["name"] + " · " + char["fate"], expanded=True):
            st.markdown("**人物心跡（結局後解鎖）**")
            st.write(char["heart"])
            for cue in char["warnings"]:
                st.write(f"事前警示 · 第 {cue['month']} 月：{cue['text']}")
            if char["risk_notice"]:
                st.write("派遣前風險提示：" + char["risk_notice"])
    st.subheader("關鍵決策因果回放")
    for item in end["replay"]:
        st.write(item["text"])
    with st.expander("可選填 · 本機遊戲後問卷"):
        st.caption("只保存於這台電腦的 feedback/responses.jsonl，不上傳。全部為固定選項。")
        if st.session_state.get("survey_saved"):
            st.success("問卷已保存，謝謝你留下這局的感受。")
        else:
            options = survey_options(state)
            labels = {"memorable": "你最記得哪一名弟子？", "habit": "你記得最明顯的性格或習慣是什麼？",
                      "hardest": "哪一次派遣或人物選擇最難決定？", "unfair": "哪一個重大結果讓你覺得事前完全沒有合理線索？",
                      "replay": "換一個種子，你是否願意再玩一局？"}
            with st.form("survey"):
                answers = {key: st.selectbox(labels[key], values, key="survey_" + key) for key, values in options.items()}
                submit = st.form_submit_button("保存問卷")
            if submit:
                try:
                    save_feedback(state, answers, st.session_state.response_id, DEFAULT_PATH)
                except (OSError, ValueError) as exc:
                    st.error("問卷未能保存：" + str(exc))
                else:
                    st.session_state.survey_saved = True
                    st.rerun()


def main():
    st.title("危門十二月")
    st.caption("十二個月，四名弟子，一座不能輕易放棄的山門。")
    if "game" not in st.session_state:
        st.write("前任掌門失蹤，青崖門糧餉短缺。烈川堂送來戰帖，十二個月後將在斷劍臺決定青崖山的歸屬。你被推舉為代理掌門，必須與四名各懷心事的弟子一起度過危局。")
        st.info("每月白天選方案、派弟子，夜間回應人物需求。請留意傷疲、公開背景與觀察札記；選擇的代價可能要數月後才顯現。")
        st.number_input("遊戲種子", min_value=0, max_value=2**32 - 1, value=42, step=1, key="seed_input")
        st.button("隨機種子", on_click=random_seed)
        if st.button("開始新遊戲", type="primary", key="start"):
            st.session_state.game = new_game(int(st.session_state.seed_input))
            st.session_state.response_id = str(uuid4())
            st.rerun()
        return
    state = st.session_state.game
    view = public_state(state)
    draw_sidebar(view)
    phase = {"day": "白天 · 門派事件", "day_result": "白天 · 結算", "night": "夜間 · 人物互動",
             "night_result": "夜間 · 結算", "ended": "結局"}[view["phase"]]
    st.subheader(f"第 {view['month']} 月／十二月 · {phase}")
    for col, (name, value) in zip(st.columns(3), view["resources"].items()):
        col.metric(name, value)
    draw_cards(view)
    st.divider()
    if view["phase"] == "day":
        for text in view["last_result"]:
            st.info(text)
        draw_day(state, view)
    elif view["phase"] == "night":
        draw_night(state, view)
    elif view["phase"] in ("day_result", "night_result"):
        st.header("本階段結果")
        for line in view["last_result"]:
            st.write(line)
        st.caption("新的言行已寫入側邊欄「觀察札記」。")
        if view["phase"] == "day_result":
            if st.button("進入夜間互動", key="next_phase", type="primary"):
                run_action(start_night, state)
        elif st.button("前往斷劍臺" if view["month"] == 11 else "進入下一月", key="next_month", type="primary"):
            run_action(begin_month, state)
    else:
        draw_ending(state)


if __name__ == "__main__":
    main()
