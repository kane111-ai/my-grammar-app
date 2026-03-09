import streamlit as st
import json
import random
import os
import ast
import re
from datetime import datetime, timedelta

# --- スプレッドシート通信用ライブラリ ---
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

# --- パス設定 ---
BASE_DIR = os.path.dirname(__file__)
PROGRESS_PATH = os.path.join(BASE_DIR, '../progress/user_progress.json') # ローカルバックアップ用
SECRET_PATH = os.path.join(BASE_DIR, '../secret.json')

# --- スタイリング ---
st.markdown("""
<style>
    .main { background-color: #f0f2f6; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; font-weight: bold; transition: 0.2s; }
    .q-card { background-color: #ffffff !important; color: #000000 !important; padding: 30px; border-radius: 20px; border-left: 10px solid #3498db; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 25px; }
    .feedback-correct { background-color: #e8f8f5 !important; color: #0b5345 !important; padding: 25px; border-radius: 15px; border: 2px solid #2ecc71; font-size: 1.1em; font-weight: bold; margin-bottom: 15px; }
    .feedback-wrong { background-color: #fbeee6 !important; color: #78281f !important; padding: 25px; border-radius: 15px; border: 2px solid #e74c3c; font-size: 1.1em; font-weight: bold; margin-bottom: 15px; }
    .stat-label { font-size: 0.9em; color: #7f8c8d; font-weight: bold; }
    .stat-value { font-size: 1.8em; font-weight: bold; color: #3498db; }
</style>
""", unsafe_allow_html=True)

# --- 章分け設定 ---
CHAPTER_MAP = [
    (1, 12, "時制"), (13, 16, "受動態"), (17, 30, "助動詞"), (31, 41, "仮定法"),
    (42, 53, "不定詞"), (54, 58, "動名詞"), (59, 67, "分詞"), (68, 78, "関係詞"),
    (79, 92, "接続詞"), (93, 105, "前置詞"), (106, 117, "比較"), 
    (118, 123, "主語と述語動詞の一致"), (124, 130, "疑問詞"), (131, 134, "否定"), 
    (135, 141, "語順・省略・強調"), (142, 142, "語法"), (143, 176, "動詞の語法"),
    (177, 185, "名詞の語法"), (186, 199, "代名詞の語法"), (200, 211, "形容詞の語法"),
    (212, 219, "副詞の語法")
]

ORDERED_CHAPS_MASTER = [name for _, _, name in CHAPTER_MAP] + ["会話表現", "イディオム", "その他"]

def get_chapter_name(sec):
    try:
        s = int(sec)
        for start, end, name in CHAPTER_MAP:
            if start <= s <= end: return name
        return "イディオム" if s >= 220 else "その他"
    except: return "会話表現"

def get_logical_today_date():
    now = datetime.now()
    if now.hour < 7: return (now - timedelta(days=1)).date()
    return now.date()

today_date = get_logical_today_date()
today_str = str(today_date)

# --- クラウド同期機能 (GSpread) ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    elif os.path.exists(SECRET_PATH):
        creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_PATH, scope)
    else:
        raise Exception("鍵（secret）が見つかりません。")
    return gspread.authorize(creds)

@st.cache_data(ttl=3600)
def load_questions_from_cloud():
    if not GSPREAD_AVAILABLE:
        st.error("スプレッドシート通信ライブラリがありません。")
        return []
    try:
        client = get_gspread_client()
        sheet = client.open("grammar_data")
        ws_q = sheet.worksheet("Questions")
        
        records = ws_q.get_all_values()
        if not records: return []

        start_idx = 1 if records[0] and str(records[0][0]).lower() == 'id' else 0

        q_data = []
        for i, row in enumerate(records[start_idx:]):
            row = row + [''] * max(0, 10 - len(row))

            q_id = int(row[0]) if str(row[0]).isdigit() else (i + 1)
            section = int(row[1]) if str(row[1]).isdigit() else 0
            question = str(row[2]).strip()

            opt_raw = [str(row[3]).strip(), str(row[4]).strip(), str(row[5]).strip(), str(row[6]).strip()]
            options = [opt for opt in opt_raw if opt]

            ans_raw = str(row[7]).strip()
            translation = str(row[8]).strip()
            explanation = str(row[9]).strip()

            if ans_raw in ['1', '2', '3', '4'] and len(options) > 1:
                ans_idx = int(ans_raw) - 1
                correct_answer = options[ans_idx] if 0 <= ans_idx < len(options) else ""
                
                q_data.append({
                    "id": q_id, "section": section, "question": question,
                    "options": options, "answer": ans_idx, "correct_answer": correct_answer,
                    "explanation": explanation, "translation": translation
                })
            else:
                q_data.append({
                    "id": q_id, "section": section, "question": question,
                    "options": [], "answer": ans_raw, "correct_answer": ans_raw,
                    "explanation": explanation, "translation": translation
                })

        return q_data
    except Exception as e:
        st.error(f"問題データの取得に失敗しました: {str(e)}")
        return []

def sync_to_cloud(p_data):
    if not GSPREAD_AVAILABLE: return False, "ライブラリがありません。"
    try:
        client = get_gspread_client()
        sheet = client.open("grammar_data") 
        try: ws_save = sheet.worksheet("SaveData")
        except: ws_save = sheet.add_worksheet(title="SaveData", rows="10", cols="10")
        ws_save.update(range_name='A1', values=[[json.dumps(p_data, ensure_ascii=False)]])
        
        try: ws_hist = sheet.worksheet("History")
        except: ws_hist = sheet.add_worksheet(title="History", rows="1000", cols="5")
        ws_hist.append_row([today_str, p_data["stats"]["today_count"]])
        return True, "クラウドにセーブしました！"
    except Exception as e:
        return False, f"通信エラー: {str(e)}"

def load_progress_from_cloud():
    if not GSPREAD_AVAILABLE: return False, "ライブラリがありません。", {}
    try:
        client = get_gspread_client()
        sheet = client.open("grammar_data")
        ws_save = sheet.worksheet("SaveData")
        val = ws_save.acell('A1').value
        if val:
            cloud_data = json.loads(val)
            save_p(cloud_data)
            return True, "クラウドからデータをロードしました！", cloud_data
        return False, "クラウドにデータがありません。", {}
    except Exception as e:
        return False, f"通信エラー: {str(e)}", {}

def load_progress(cloud_data=None):
    p = cloud_data if cloud_data else {}
    if not p and os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH, 'r', encoding='utf-8') as f: p = json.load(f)
        except: pass

    if "stats" not in p: p["stats"] = {"streak": 0, "last_date": "", "today_count": 0, "history": {}}
    if "history" not in p["stats"]: p["stats"]["history"] = {}
    if "seq_progress" not in p["stats"]: p["stats"]["seq_progress"] = {"ALL": 0}
    if "random_state" not in p["stats"]: p["stats"]["random_state"] = {"queue_ids": [], "idx": 0}
    if "review_list" not in p: p["review_list"] = []
    if "chapter_wrongs" not in p: p["chapter_wrongs"] = []
    
    if "items" not in p:
        items_dict = {}
        for k, v in list(p.items()):
            if k not in ["stats", "items", "chapter_wrongs", "review_list"]:
                items_dict[k] = v
                del p[k]
        p["items"] = items_dict

    # 互換性パッチ
    for qid, item in list(p["items"].items()):
        if "ease" in item:
            old_int = item.get("interval", 1)
            new_lvl = 5 if old_int >= 30 else 4 if old_int >= 15 else 3 if old_int >= 7 else 2 if old_int >= 3 else 1
            p["items"][qid] = {
                "level": new_lvl,
                "wrong_count": 0,
                "next_review": str(item.get("next_review", today_str))[:10],
                "last_tested_date": ""
            }

    return p

def save_p(p):
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=4)

def check_text_answer(user_input, correct_ans):
    u = re.sub(r'\s+', ' ', str(user_input).strip().lower())
    c = re.sub(r'\s+', ' ', str(correct_ans).strip().lower())
    return u == c

# --- オートロード機能 ---
if 'auto_loaded' not in st.session_state:
    st.session_state.auto_loaded = False
    st.session_state.cloud_p_data = {}

if not st.session_state.auto_loaded:
    success, msg, data = load_progress_from_cloud()
    if success:
        st.session_state.cloud_p_data = data
    st.session_state.auto_loaded = True

q_data = load_questions_from_cloud()
p_data = load_progress(st.session_state.cloud_p_data)

if p_data["stats"].get("last_date") != today_str:
    yesterday = str(today_date - timedelta(days=1))
    if p_data["stats"].get("last_date") == yesterday: p_data["stats"]["streak"] += 1
    elif p_data["stats"].get("last_date") == "": p_data["stats"]["streak"] = 1
    else: p_data["stats"]["streak"] = 0
    p_data["stats"]["today_count"] = 0
    p_data["stats"]["last_date"] = today_str
    if today_str not in p_data["stats"]["history"]: p_data["stats"]["history"][today_str] = 0
    save_p(p_data)

if 'view' not in st.session_state: st.session_state.view = "HOME"
if 'queue' not in st.session_state: st.session_state.queue = []
if 'idx' not in st.session_state: st.session_state.idx = 0
if 'ans_flag' not in st.session_state: st.session_state.ans_flag = False
if 'quiz_mode' not in st.session_state: st.session_state.quiz_mode = None
if 'seq_key' not in st.session_state: st.session_state.seq_key = None

def start_quiz(queue, mode, seq_key=None, start_idx=0):
    st.session_state.queue = list(queue)
    st.session_state.quiz_mode = mode
    st.session_state.seq_key = seq_key
    st.session_state.view = "QUIZ"
    st.session_state.idx = start_idx
    st.session_state.ans_flag = False
    st.rerun()

# --- サイドバー ---
with st.sidebar:
    st.title("🚀 Progress")
    st.markdown(f'<div class="stat-label">🔥 連続学習日数</div><div class="stat-value">{p_data["stats"]["streak"]} 日</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="stat-label">✅ 今日の回答数</div><div class="stat-value">{p_data["stats"]["today_count"]} 問</div>', unsafe_allow_html=True)
    
    mastered_count = sum(1 for item in p_data["items"].values() if item.get("level", 0) >= 5)
    st.markdown(f'<div class="stat-label" style="margin-top:10px;">👑 マスター済み</div><div class="stat-value" style="color:#f1c40f;">{mastered_count} 問</div>', unsafe_allow_html=True)

    st.divider()
    
    st.write("☁️ **クラウド同期**")
    if st.button("⬆️ セーブする", type="primary"):
        with st.spinner("通信中..."):
            success, msg = sync_to_cloud(p_data)
            if success: st.success(msg)
            else: st.error(msg)
            
    if st.button("⬇️ ロードする"):
        with st.spinner("通信中..."):
            success, msg, data = load_progress_from_cloud()
            if success: 
                st.session_state.cloud_p_data = data
                st.success(msg)
                st.rerun()
            else: st.error(msg)
            
    if st.button("🔄 問題データを再読み込み"):
        load_questions_from_cloud.clear()
        st.success("スプレッドシートから最新データを再取得しました！")
        st.rerun()
    
    st.divider()
    st.write("📝 **現在の苦手リスト**")
    st.write(f"・総合復習: {len(p_data['review_list'])} 問")
    st.write(f"・章別復習: {len(p_data['chapter_wrongs'])} 問")
    
    st.divider()
    if st.button("🏠 ホームメニューへ"):
        st.session_state.view = "HOME"
        st.rerun()

# --- メイン画面 ---
if st.session_state.view == "HOME":
    st.title("英文法 忘却曲線マスター Pro")

    if not q_data:
        st.warning("⚠️ 問題データが読み込めていません。サイドバーの「🔄 問題データを再読み込み」を押してください。")
        st.stop()

    tab_seq, tab_rand, tab_eb, tab_chap, tab_review, tab_record = st.tabs([
        "📖 順番に解く", "🎲 ランダム", "🧠 エビングハウス", "📚 章別学習", "♻️ 復習", "📅 記録"
    ])

    with tab_seq:
        st.subheader("メイン学習: 全問を順番に進める")
        saved_idx = p_data["stats"]["seq_progress"].get("ALL", 0)
        st.info(f"現在の進捗: 全 {len(q_data)} 問中、{saved_idx} 問目まで完了")
        if st.button(f"🚀 全問を順番に解く (続き: {saved_idx+1}問目〜)", type="primary"):
            queue = sorted(q_data, key=lambda x: x['id'])
            if saved_idx >= len(queue): saved_idx = 0
            start_quiz(queue, mode="GLOBAL_LEARN", seq_key="ALL", start_idx=saved_idx)

    with tab_rand:
        st.subheader("ランダム演習")
        r_state = p_data["stats"]["random_state"]
        if st.button(f"🎲 全問をランダムに解く (続き: {r_state['idx']+1}問目〜)"):
            if not r_state["queue_ids"] or r_state["idx"] >= len(q_data):
                r_state["queue_ids"] = [q['id'] for q in q_data]
                random.shuffle(r_state["queue_ids"])
                r_state["idx"] = 0
                save_p(p_data)
            q_dict = {q['id']: q for q in q_data}
            queue = [q_dict[qid] for qid in r_state["queue_ids"] if qid in q_dict]
            start_quiz(queue, mode="RANDOM_LEARN", seq_key="RANDOM", start_idx=r_state["idx"])

    with tab_eb:
        st.subheader("忘却曲線テスト")
        due = []
        for q in q_data:
            qid = str(q['id'])
            if qid in p_data["items"]:
                item = p_data["items"][qid]
                if item.get("level", 0) > 0 and item.get("next_review", today_str) <= today_str and item.get("last_tested_date") != today_str:
                    due.append(q)

        st.info(f"今日復習すべき問題: {len(due)}問")
        if st.button("🧠 今日の忘却曲線テストを開始"):
            if due: start_quiz(random.sample(due, len(due)), mode="EB")
            else: st.success("明日の朝7時まで、復習する問題はありません。完璧です！")

    with tab_chap:
        st.subheader("章別学習（エビングハウス対象外）")
        chaps_in_data = list(dict.fromkeys(get_chapter_name(q.get('section')) for q in q_data))
        ordered_chaps = sorted(chaps_in_data, key=lambda x: ORDERED_CHAPS_MASTER.index(x) if x in ORDERED_CHAPS_MASTER else 999)
        sel_c = st.selectbox("学習する章を選択してください", ordered_chaps)
        
        col1, col2 = st.columns(2)
        with col1:
            chap_saved_idx = p_data["stats"]["seq_progress"].get(sel_c, 0)
            if st.button(f"📖 この章を順番に解く (続き: {chap_saved_idx+1}問目〜)"):
                queue = sorted([q for q in q_data if get_chapter_name(q.get('section')) == sel_c], key=lambda x: x['id'])
                if chap_saved_idx >= len(queue): chap_saved_idx = 0
                if queue: start_quiz(queue, mode="CHAP_LEARN", seq_key=sel_c, start_idx=chap_saved_idx)
                else: st.warning("この章にはまだ問題がありません。")
        with col2:
            if st.button("🎲 この章をランダムに解く"):
                queue = [q for q in q_data if get_chapter_name(q.get('section')) == sel_c]
                if queue: start_quiz(random.sample(queue, len(queue)), mode="CHAP_LEARN_RANDOM")

    with tab_review:
        st.subheader("間違えた問題の復習テスト")
        wrongs_global = [q for q in q_data if str(q['id']) in p_data["review_list"]]
        wrongs_chap = [q for q in q_data if str(q['id']) in p_data["chapter_wrongs"]]
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**総合の苦手: {len(wrongs_global)} 問**")
            if st.button("🚀 総合の復習テストを開始"):
                if wrongs_global: start_quiz(random.sample(wrongs_global, len(wrongs_global)), mode="GLOBAL_REVIEW")
                else: st.success("総合の苦手リストは空です！")
        with col2:
            st.info(f"**章別学習の苦手: {len(wrongs_chap)} 問**")
            if st.button("📚 章別の復習テストを開始"):
                if wrongs_chap: start_quiz(random.sample(wrongs_chap, len(wrongs_chap)), mode="CHAP_REVIEW")
                else: st.success("章別の苦手リストは空です！")

    with tab_record:
        st.subheader("📅 日々の学習記録")
        history_data = p_data["stats"].get("history", {})
        if history_data:
            sorted_history = dict(sorted(history_data.items()))
            st.bar_chart(sorted_history)

        st.divider()
        st.subheader("⚙️ データの管理")
        if 'confirm_reset' not in st.session_state: st.session_state.confirm_reset = False
        if not st.session_state.confirm_reset:
            if st.button("⚠️ 全データをリセットする"):
                st.session_state.confirm_reset = True
                st.rerun()
        else:
            st.warning("本当にすべての記録をリセットしますか？")
            rc1, rc2 = st.columns(2)
            if rc1.button("はい、完全にリセットします", type="primary"):
                if os.path.exists(PROGRESS_PATH): os.remove(PROGRESS_PATH)
                st.session_state.confirm_reset = False
                st.success("全データをリセットしました。画面をリロードしてください。")
                st.rerun()
            if rc2.button("キャンセル"):
                st.session_state.confirm_reset = False
                st.rerun()

elif st.session_state.view == "QUIZ":
    if st.session_state.idx < len(st.session_state.queue):
        q = st.session_state.queue[st.session_state.idx]
        mode = st.session_state.quiz_mode
        
        if mode == "EB": label = "🧠 忘却曲線テスト"
        elif mode == "GLOBAL_REVIEW": label = "📝 総合復習テスト"
        elif mode == "GLOBAL_LEARN": label = "📖 全問順番に解く"
        elif mode == "RANDOM_LEARN": label = "🎲 全問ランダム (EB対象外)"
        elif mode == "CHAP_REVIEW": label = "♻️ 章別・復習テスト"
        else: label = "📚 章別学習"
        
        # キューの長さは変わらないのでシンプルな進捗計算に戻す
        progress_val = min(1.0, st.session_state.idx / max(1, len(st.session_state.queue)))
        st.progress(progress_val)
        st.caption(f"{label} | {get_chapter_name(q.get('section'))} | ID: {q['id']} ({st.session_state.idx + 1} / {len(st.session_state.queue)})")
        
        st.markdown(f'<div class="q-card"><b>Question:</b><br>{q["question"]}</div>', unsafe_allow_html=True)

        if not st.session_state.ans_flag:
            is_mcq = 'options' in q and isinstance(q['options'], list) and len(q['options']) > 0

            if is_mcq:
                cols = st.columns(2)
                for i, opt in enumerate(q['options']):
                    if cols[i % 2].button(f"{i+1}. {opt}", key=f"opt_{q['id']}_{i}"):
                        st.session_state.ans_flag = True
                        st.session_state.is_correct = (i == q['answer'])
                        st.rerun()
            else:
                user_ans = st.text_input("✍️ 答えを入力してください (例: dead for)", key=f"text_ans_{q['id']}")
                if st.button("回答を送信", type="primary"):
                    if user_ans.strip():
                        st.session_state.ans_flag = True
                        st.session_state.is_correct = check_text_answer(user_ans, q.get('correct_answer', ''))
                        st.rerun()
                    else:
                        st.warning("答えを入力してください。")
            
            st.write("")
            if st.button("🤔 わからない (苦手リストに追加)", type="secondary"):
                st.session_state.ans_flag = True
                st.session_state.is_correct = False
                st.rerun()

        else:
            if st.session_state.is_correct:
                st.markdown('<div class="feedback-correct">⭕ 正解です！素晴らしい！</div>', unsafe_allow_html=True)
            else:
                correct_txt = q['correct_answer']
                st.markdown(f'<div class="feedback-wrong">❌ 不正解...<br>正解: {correct_txt}</div>', unsafe_allow_html=True)
            
            if q.get('translation'):
                st.write(f"**【日本語訳】** {q.get('translation')}")
            
            if q.get('explanation'):
                st.info(f"**【解説】**\n{q.get('explanation')}")
            
            # --- 修正版: エンドレスループ廃止 ＆ 復習タブでエビングハウス開始 ---
            if st.button("次の問題へ ➡️", type="primary"):
                qid = str(q['id'])
                is_correct = st.session_state.is_correct

                if qid not in p_data["items"]:
                    p_data["items"][qid] = {"level": 0, "wrong_count": 0, "next_review": today_str, "last_tested_date": ""}
                
                item = p_data["items"][qid]
                curr_lvl = item.get("level", 0)
                curr_w = item.get("wrong_count", 0)
                intervals = [0, 1, 3, 7, 15, 30, 60, 90]

                if mode == "EB":
                    if is_correct:
                        new_lvl = curr_lvl + 1
                        item['level'] = new_lvl
                        item['next_review'] = str(today_date + timedelta(days=intervals[min(new_lvl, 7)]))
                        item['last_tested_date'] = today_str
                    else:
                        item['level'] = max(1, curr_lvl - 1)
                        item['wrong_count'] = curr_w + 1
                        # 忘却曲線で間違えた場合も、しっかり復習タブ（総合の苦手）に送る
                        if qid not in p_data["review_list"]:
                            p_data["review_list"].append(qid)

                elif mode in ["GLOBAL_LEARN", "CHAP_LEARN", "CHAP_LEARN_RANDOM", "RANDOM_LEARN"]:
                    if is_correct:
                        # 初見で正解したらエビングハウスのレベル1へ
                        if curr_lvl == 0:
                            item['level'] = 1
                            item['next_review'] = str(today_date + timedelta(days=1))
                            item['last_tested_date'] = today_str
                    else:
                        item['wrong_count'] = curr_w + 1
                        # 間違えたらループさせず、それぞれの苦手リストに登録するだけ
                        if mode in ["GLOBAL_LEARN", "RANDOM_LEARN"] and qid not in p_data["review_list"]:
                            p_data["review_list"].append(qid)
                        elif mode in ["CHAP_LEARN", "CHAP_LEARN_RANDOM"] and qid not in p_data["chapter_wrongs"]:
                            p_data["chapter_wrongs"].append(qid)

                elif mode in ["GLOBAL_REVIEW", "CHAP_REVIEW"]:
                    if is_correct:
                        # 復習タブで正解したらリストから除外し、エビングハウスの1歩目（レベル1）をセット
                        if mode == "GLOBAL_REVIEW" and qid in p_data["review_list"]: p_data["review_list"].remove(qid)
                        if mode == "CHAP_REVIEW" and qid in p_data["chapter_wrongs"]: p_data["chapter_wrongs"].remove(qid)
                        
                        item['level'] = 1
                        item['next_review'] = str(today_date + timedelta(days=1))
                        item['last_tested_date'] = today_str
                    else:
                        item['wrong_count'] = curr_w + 1

                # 進捗セーブ
                if mode in ["GLOBAL_LEARN", "CHAP_LEARN"]:
                    p_data["stats"]["seq_progress"][st.session_state.seq_key] = st.session_state.idx + 1
                if mode == "RANDOM_LEARN":
                    p_data["stats"]["random_state"]["idx"] = st.session_state.idx + 1

                p_data["stats"]["today_count"] += 1
                p_data["stats"]["history"][today_str] = p_data["stats"]["today_count"]
                save_p(p_data)
                
                st.session_state.ans_flag = False
                st.session_state.idx += 1
                st.rerun()
    else:
        st.balloons()
        st.success("🎉 おめでとうございます！このセットの学習をすべて完了しました。")
        
        if st.session_state.quiz_mode == "RANDOM_LEARN":
            p_data["stats"]["random_state"]["idx"] = 0
            save_p(p_data)
        elif st.session_state.quiz_mode in ["GLOBAL_LEARN", "CHAP_LEARN"]:
            p_data["stats"]["seq_progress"][st.session_state.seq_key] = 0
            save_p(p_data)

        if st.button("🏠 ホームへ戻る", type="primary"):
            st.session_state.view = "HOME"
            st.rerun()
