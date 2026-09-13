"""Local Streamlit presentation; hidden data never enters a display component."""
import secrets
from uuid import uuid4

import streamlit as st

from game_runtime import load_current_engine

APP_VERSION = "0.6"
st.set_page_config(page_title="危門十二月", page_icon="⛰️", layout="wide")
# Refresh an earlier process before binding functions from the game modules.
try:
    load_current_engine(APP_VERSION)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

from investigation import checkpoint_view, resolve_deduction

from feedback import DEFAULT_PATH, save_feedback, survey_options
from game_engine import (InvalidAction, begin_month, current_event, emergency_rest,
                         ending_view, legal_actions, new_game, night_view, public_option,
                         public_state, resolve_day, resolve_night, start_night)
from game_engine import resolve_case_action
from case_engine import legal_case_actions

def restart():
    for key in list(st.session_state):
        if key != "seed_input":
            del st.session_state[key]


def start_new_game():
    previous = st.session_state.get("game")
    seed = int(st.session_state.get("seed_input", getattr(previous, "seed", 42)))
    state = new_game(seed)
    restart()
    st.session_state.game = state
    st.session_state.response_id = str(uuid4())


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
        draw_evidence_board(view)
        st.header("掌門札記")
        st.caption(f"本局種子：{view['seed']}")
        with st.expander("人物與異常", expanded=False):
            st.caption("只記錄新的言行或事實；沒有新變化便不新增。重大警示若有後續進展，會另記一筆。")
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
        with st.expander("已知往事"):
            for flag in view["flags"] or ["尚無已公開事項。"]:
                st.write(flag)
        st.button("重新開始", on_click=restart)
        st.caption("單局保留在目前瀏覽器工作階段；重新整理連線或關閉伺服器可能重置。")


def draw_cards(view):
    columns = st.columns(2)
    for index, char in enumerate(view["characters"]):
        column = columns[index % 2]
        with column, st.container(border=True):
            st.subheader(char["name"])
            st.caption(f"{char['age']} 歲 · {char['role']}專長 · {char['personality']}")
            st.write(" · ".join(f"{k} {v}" for k, v in char["skills"].items()))
            st.markdown(f"**{char['physical']}**")
            st.write(char["signature"])
            with st.expander("人物小傳與近況"):
                st.write("小傳：" + char["background"])
                when = f"（第 {char['recent_month']} 月）" if char["recent_month"] else ""
                st.write("近況" + when + "：" + char["recent"])
                if char["experiences"]:
                    st.write("已知經歷：")
                    for experience in char["experiences"]:
                        st.write("• " + experience)


def draw_resources(view):
    st.subheader(f"第 {view['month']} 月 · {view['chapter']}")
    for col, (name, value) in zip(st.columns(3), view["resources"].items()):
        col.metric(name, value)


def draw_event_scene(view):
    event = view["event"]
    st.header(event["title"])
    st.markdown("**事件人物：" + event["npc_identity"] + "**")
    st.write(event["description"])
    if view['case_question']:
        question = view['case_question']
        st.info('核心問題：' + question['text'])
        st.caption('查明程度：' + {'open':'尚待核查', 'partial':'部分查明', 'resolved':'本題已有依據'}[question['status']])
        with st.expander('目前已知／尚未確認', expanded=True):
            st.markdown('**目前已知**')
            for fact in question['known_facts'] or ['尚無已核實材料；人物的主張請見證據板「人物說法」。']:
                st.write(fact)
            st.markdown('**尚未確認**')
            for part in question['unresolved_parts'] or ['本題必要核對已完成；其他問題仍各自保留缺口。']:
                st.write(part)
    else:
        st.info("目前疑點：" + event["current_question"])
    if event["callbacks"]:
        with st.expander("與本月有關的前事"):
            for callback in event["callbacks"]:
                st.write(callback["text"])


def draw_character_opinions(view):
    st.subheader("四名弟子的判斷")
    columns = st.columns(2)
    for index, char in enumerate(view["characters"]):
        with columns[index % 2], st.container(border=True):
            st.markdown("### " + char["name"])
            st.write(f"{char['role']}專長 · {char['personality']}")
            status = f"狀態：{char['status_label']} · {char['actionable_label']}"
            if char["status_level"] in ("danger", "unavailable"):
                st.warning(status)
            else:
                st.write(status)
            st.markdown("**判斷**")
            st.write(char["thought"])
            if char["dialogue"]:
                st.markdown("**他說**")
                st.write("「" + char["dialogue"] + "」")
            with st.expander("能力、背景與判斷範圍"):
                st.write(" · ".join(f"{k} {v}" for k,v in char["skills"].items()))
                st.write("小傳：" + char["background"])
                when = f"（第 {char['recent_month']} 月）" if char["recent_month"] else ""
                st.write("近況" + when + "：" + char["recent"])
                for experience in char["experiences"]:
                    st.write("• " + experience)
                st.write("較熟悉：" + char["reliable_domain"])
                st.write("需另找人核對：" + char["blind_spot"])


def draw_evidence_board(view):
    board = view["evidence_board"]
    st.subheader("證據板")
    for key, label in (("confirmed","已證實"),("pending","待核實"),("claims","人物說法"),("excluded","排除事項")):
        with st.expander(f"{label} · {len(board[key])}", expanded=key == "confirmed"):
            if not board[key]:
                st.write("目前沒有這類記錄。")
            for item in board[key]:
                st.markdown("**" + item["title"] + "**")
                if key == "excluded":
                    st.write("與已核實資料不符：" + "、".join(item["sources"]))
                else:
                    st.write(item["text"])
                    st.caption(f"第 {item['month']} 月 · 來源：{item['source']}")


def draw_investigation_options(state, view):
    options = {o["id"]:o for o in view["investigations"]}
    st.subheader("決定查什麼")
    focus_id = st.radio("本月調查方向", list(options), index=None,
                        format_func=lambda key:options[key]["label"] + ("（已有記錄）" if options[key]["already_known"] else ""),
                        key=f"focus_{state.month}")
    if focus_id is not None:
        option=options[focus_id]
        st.write(option["hint"])
        st.caption(f"調查成本 {option['cost']} 糧餉 · 建議{option['skill']}")
    return focus_id


def draw_dispatch_selector(state, view, option, focus_id):
    available = {c["id"]:c for c in view["characters"] if c["actionable"]}
    def name(cid):
        c=available[cid]
        return f"{c['name']}｜{c['role']}｜{c['status_label']}｜{c['actionable_label']}"
    members=st.multiselect("派遣弟子（確認前可更換）", list(available), format_func=name,
                           max_selections=option["count"],key=f"team_{view['month']}_{option['id']}")
    valid=focus_id is not None and any(o["id"] == option["id"] and set(ids)==set(members) for o,ids in legal_actions(state,focus_id))
    if focus_id is not None:
        focus=next(o for o in view["investigations"] if o["id"]==focus_id)
        st.write(f"本次總成本：{option['cost'] + focus['cost']} 糧餉（門務 {option['cost']}＋調查 {focus['cost']}）")
        if not legal_actions(state,focus_id):
            st.warning("此調查搭配目前的人手或糧餉無法執行，可改選其他方向或只處理門務。")
    if st.button("確認派遣",type="primary",disabled=not valid,key="confirm_day"):
        run_action(resolve_day,state,option["id"],members,f"{view['month']}:day",focus_id)


def draw_day(state, view):
    draw_event_scene(view)
    draw_character_opinions(view)
    if view['causal_case']:
        draw_case_actions(state, view)
        return
    focus_id=draw_investigation_options(state,view)
    st.subheader("安排門務與派遣")
    if not legal_actions(state):
        st.warning("目前沒有可執行的門務方案，需要留門休整。")
        if st.button("全員留門休整",key="rest"):
            run_action(emergency_rest,state)
        return
    options={o["id"]:o for o in view["event"]["options"]}
    option_id=st.radio("選擇本月方案",list(options),format_func=lambda key:options[key]["label"],key=f"plan_{view['month']}")
    option=options[option_id]
    st.write(option["hint"])
    st.write(f"門務成本 {option['cost']} · 建議{option['skill']} · 派遣 {option['count']} 人")
    if option["risk"] == "致命風險":
        st.error("致命風險：可能造成弟子死亡")
    else:
        st.write("風險："+option["risk"])
    draw_dispatch_selector(state,view,option,focus_id)


def draw_case_actions(state, view):
    st.subheader('你打算怎麼處理這件事？')
    legal = legal_case_actions(state)
    if not legal:
        st.warning('目前人手無法出勤，先留門休整並保留待查事項。')
        if st.button('全員留門休整', key='rest'):
            run_action(emergency_rest, state)
        return
    options = {a['id']: a for a in view['case_actions']}
    for option in options.values():
        with st.container(border=True):
            st.markdown('**' + option['label'] + '**')
            st.write('回答：' + option['question_part'])
            st.write(option['description'])
            st.caption(f"成本 {option['cost']} 糧餉 · 建議{option['skill']} · {option['count']} 人 · 風險{option['risk']}")
            st.write(option['hint'])
            if option['already_known']:
                st.caption('這項材料已有記錄；再查不會重複加入證據。')
    action_id = st.radio('選擇處理方法', list(options), index=None,
                         format_func=lambda aid: options[aid]['label'], key=f'case_action_{state.month}')
    if action_id is None:
        st.button('確認派遣', disabled=True, key='confirm_day')
        return
    option = options[action_id]
    available = {c['id']: c for c in view['characters'] if c['actionable']}
    team = st.multiselect('派遣弟子（確認前可更換）', list(available),
        format_func=lambda cid: f"{available[cid]['name']}｜{available[cid]['role']}｜{available[cid]['status_label']}｜可派遣",
        max_selections=option['count'], key=f"team_{state.month}_{action_id}")
    valid = any(a.id == action_id and set(ids) == set(team) for a, ids in legal)
    st.write(f"本次總成本：{option['cost']} 糧餉")
    if st.button('確認派遣', disabled=not valid, type='primary', key='confirm_day'):
        run_action(resolve_case_action, state, action_id, team, f'{state.month}:day')


def draw_deduction_checkpoint(state, view):
    if view['causal_case']:
        draw_event_scene(view)
        draw_character_opinions(view)
    checkpoint=checkpoint_view(state)
    st.header({4:"初步假說",8:"證據交叉",11:"最後證據鏈"}[state.month])
    st.write(checkpoint["question"])
    evidence={e["id"]:e for e in checkpoint["evidence"]}
    chosen=[]
    hypothesis=None
    if state.month == 4:
        hypotheses={h["id"]:h["label"] for h in checkpoint["hypotheses"]}
        hypothesis=st.radio("目前的假說",list(hypotheses),index=None,format_func=lambda h:hypotheses[h],key="hypothesis_4")
        valid=hypothesis is not None
    elif state.month == 8:
        chosen=st.multiselect("選兩份已取得的證據",list(evidence),format_func=lambda cid:evidence[cid]["title"],max_selections=2,key="evidence_pair_8")
        defer=st.checkbox("目前證據不足，保留判斷",key="deduction_defer_8")
        valid=defer or len(chosen)==2
        if defer:
            chosen=[]
    else:
        for slot,label in (("document","原件／文件"),("physical","現場／物證"),("witness","人證／佐證")):
            ids=[cid for cid,e in evidence.items() if e["type"]==slot]
            cid=st.selectbox(label,ids,index=None,format_func=lambda cid:evidence[cid]["title"],key="chain_"+slot)
            if cid:
                chosen.append(cid)
        defer=st.checkbox("證據鏈尚未完整，只提出已知部分",key="deduction_defer_11")
        valid=defer or len(chosen)==3
        if defer and not view['causal_case']:
            chosen=[]
    st.caption("只可使用已取得資料。判斷失誤不會立即結束遊戲，也不會刪除證據。")
    if st.button("提出推理",disabled=not valid,type="primary",key="confirm_deduction"):
        run_action(resolve_deduction,state,hypothesis,chosen,f"{state.month}:deduction")


def draw_night(state, view):
    scene = night_view(state)
    st.header("夜間 · " + {"personal_scene": scene["name"], "relationship_scene": "同門之間", "mainline_scene": "追查舊事", "quiet_scene": "歇一口氣", "group_scene": "留下來的人"}[scene["kind"]])
    st.subheader(scene["title"])
    if scene["context"]:
        st.write(scene["context"])
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
    if end['mystery_axis']:
        st.info('案件：' + {'complete':'完整證據鏈', 'partial':'部分查明', 'unresolved':'尚未查明'}[end['mystery_axis']]
                + ' · 門派：' + {'stable':'穩定', 'weakened':'受損', 'collapsed':'覆滅'}[end['sect_axis']])
        st.write(end['reason'])
    st.write(end["final_scene"])
    with st.expander("這一局的謎底與未解之處", expanded=True):
        st.write(end["mystery_reveal"])
        for callback in end["callbacks"]:
            st.write(callback)
        for callback in end["personal_callbacks"]:
            st.write(callback)
    st.subheader("四名弟子的去向")
    for char in end["characters"]:
        with st.expander(char["name"], expanded=True):
            st.write(char["epilogue"])
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
        st.info("假名帖主線：先看核心問題與四名弟子的看法，選一種處理方法並派遣；晚上回應當日後果。第四、八、十一月由劇情人物要求你提出推理，夜間再討論其影響。種子 4 可體驗此線。")
        st.number_input("遊戲種子", min_value=0, max_value=2**32 - 1, value=42, step=1, key="seed_input")
        st.button("隨機種子", on_click=random_seed)
        st.button("開始新遊戲", type="primary", key="start", on_click=start_new_game)
        return
    state = st.session_state.game
    if getattr(state, "version", "") != APP_VERSION:
        st.info("這局在更新前開始。新版需要重新選擇案件行動與排列證據，請開始新局；舊情報不會自動變成已查證資料。")
        st.button("開始新版遊戲", type="primary", key="start_current_version", on_click=start_new_game)
        return
    view = public_state(state)
    draw_sidebar(view)
    draw_resources(view)
    if view["phase"] == "day":
        for text in view["last_result"]:
            st.info(text)
        draw_day(state, view)
    elif view["phase"] == "deduction":
        draw_deduction_checkpoint(state, view)
    elif view["phase"] == "night":
        draw_night(state, view)
    elif view["phase"] in ("day_result", "night_result", "deduction_result"):
        st.header("本階段結果")
        for line in view["last_result"]:
            st.write(line)
        st.caption("新的言行或事實，可在側邊欄「掌門札記」查看。")
        if view["phase"] == "day_result" or (view['causal_case'] and view['phase'] == 'deduction_result'):
            if st.button("進入夜間互動", key="next_phase", type="primary"):
                run_action(start_night, state)
        elif st.button("進入本月推理" if not view['causal_case'] and view["phase"] == "night_result" and view["month"] in (4,8,11) else "前往斷劍臺" if view["month"] == 11 else "進入下一月", key="next_month", type="primary"):
            run_action(begin_month, state)
    else:
        draw_ending(state)
    if view["phase"] != "day":
        with st.expander("門內眾人", expanded=False):
            draw_cards(view)


if __name__ == "__main__":
    main()
