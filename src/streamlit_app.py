import streamlit as st
import json
import random
import os
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
DATA_PATH = os.path.join(BASE_DIR, '../data/questions.json')
PROGRESS_PATH = os.path.join(BASE_DIR, '../progress/user_progress.json')
SECRET_PATH = os.path.join(BASE_DIR, '../secret.json')

# --- スタイリング ---
st.markdown("""
<style>
    .main { background-color: #f0f2f6; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; font-weight: bold; transition: 0.2s; }
    .q-card { background-color: #ffffff !important; color: #000000 !important; padding: 30px; border-radius: 20px; border-left: 10px solid #3498db; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 25px; }
    .feedback-correct { background-color: #e8f8f5 !important; color: #0b5345 !important; padding: 25px; border-radius: 15px; border: 2px solid #2ecc71; font-size: 1.1em; font-weight: bold; }
    .feedback-wrong { background-color: #fbeee6 !important; color: #78281f !important; padding: 25px; border-radius: 15px; border: 2px solid #e74c3c; font-size: 1.1em; font-weight: bold; }
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

def get_next_review(interval):
    now = datetime.now()
    if now.hour < 7: base_date = now.date() - timedelta(days=1)
    else: base_date = now.date()
    next_date = base_date + timedelta(days=interval)
    return datetime(next_date.year, next_date.month, next_date.day, 7, 0, 0).isoformat()

# --- クラウド同期機能（セキュリティ対応版） ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Streamlit Cloud上で動かしている場合（st.secretsから読み込む）
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    # 2. ローカルパソコンで動かしている場合（secret.jsonから読み込む）
    elif os.path.exists(SECRET_PATH):
        creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_PATH, scope)
    else:
        raise Exception("鍵（secret）が見つかりません。")
        
    return gspread.authorize(creds)

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
        today = datetime.now().strftime("%Y-%m-%d")
        ws_hist.append_row([today, p_data["stats"]["today_count"]])
        return True, "クラウドにセーブしました！"
    except Exception as e:
        return False, f"通信エラー: {str(e)}"

def load_from_cloud():
    if not GSPREAD_AVAILABLE: return False, "ライブラリがありません。"
    try:
        client = get_gspread_client()
        sheet = client.open("grammar_data")
        ws_save = sheet.worksheet("SaveData")
        val = ws_save.acell('A1').value
        if val:
            cloud_data = json.loads(val)
            save_p(cloud_data)
            return True, "クラウドからデータをロードしました！"
        return False, "クラウドにデータがありません。"
    except Exception as e:
        return False, f"通信エラー: {str(e)}"

# --- データ管理 ---
def load_all():
    q = []
    p = {}
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, 'r', encoding='utf-8') as f: q = json.load(f)
    if os.path.exists(PROGRESS_PATH):
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

    return q, p

def save_p(p):
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=4)

def sm2_update(ease, interval):
    if interval == 0: interval = 1
    elif interval == 1: interval = 3
    else: interval = round(interval * ease)
    ease = min(3.0, ease + 0.1)
    return ease, interval

# --- ★ オートロード機能（アプリ起動時に1回だけ実行） ★ ---
if 'auto_loaded' not in st.session_state:
    st.session_state.auto_loaded = False

if not st.session_state.auto_loaded:
    load_from_cloud() # 裏側で静かにロードする
    st.session_state.auto_loaded = True

# 初期化
q_data, p_data = load_all()
now = datetime.now()
today_str = now.strftime("%Y-%m-%d")

if p_data["stats"].get("last_date") != today_str:
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
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
    st.session_state.queue = queue
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
    
    st.divider()
    
    st.write("☁️ **クラウド同期**")
    if st.button("⬆️ セーブする", type="primary"):
        with st.spinner("通信中..."):
            success, msg = sync_to_cloud(p_data)
            if success: st.success(msg)
            else: st.error(msg)
            
    if st.button("⬇️ ロードする"):
        with st.spinner("通信中..."):
            success, msg = load_from_cloud()
            if success: 
                st.success(msg)
                st.rerun()
            else: st.error(msg)
    
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
        due = [q for q in q_data if str(q['id']) in p_data["items"] and datetime.fromisoformat(p_data["items"][str(q['id'])]['next_review']) <= now]
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
        
        st.progress((st.session_state.idx) / len(st.session_state.queue))
        st.caption(f"{label} | {get_chapter_name(q.get('section'))} | ID: {q['id']} ({st.session_state.idx + 1} / {len(st.session_state.queue)})")
        
        st.markdown(f'<div class="q-card"><b>Question:</b><br>{q["question"]}</div>', unsafe_allow_html=True)

        if not st.session_state.ans_flag:
            cols = st.columns(2)
            if 'options' in q and q['options']:
                for i, opt in enumerate(q['options']):
                    if cols[i % 2].button(f"{i+1}. {opt}", key=f"opt_{i}"):
                        st.session_state.ans_flag = True
                        st.session_state.is_correct = (i == q['answer'])
                        st.rerun()
            
            if st.button("🤔 わからない (苦手リストに追加)", type="secondary"):
                st.session_state.ans_flag = True
                st.session_state.is_correct = False
                st.rerun()
        else:
            if st.session_state.is_correct:
                st.markdown('<div class="feedback-correct">⭕ 正解です！素晴らしい！</div>', unsafe_allow_html=True)
            else:
                correct_txt = q['options'][q['answer']] if 'options' in q else q.get('correct_answer')
                st.markdown(f'<div class="feedback-wrong">❌ 不正解...<br>正解: {correct_txt}</div>', unsafe_allow_html=True)
            
            st.write(f"**【日本語訳】** {q.get('translation') or q.get('hint_translation')}")
            st.info(f"**【解説】**\n{q['explanation']}")
            
            if st.button("次の問題へ ➡️"):
                qid = str(q['id'])
                is_correct = st.session_state.is_correct

                if mode == "EB":
                    if is_correct:
                        e, i = sm2_update(p_data["items"][qid]['ease'], p_data["items"][qid]['interval'])
                        p_data["items"][qid] = {"ease": e, "interval": i, "next_review": get_next_review(i)}
                    else:
                        if qid in p_data["items"]: del p_data["items"][qid]
                        if qid not in p_data["review_list"]: p_data["review_list"].append(qid)

                elif mode == "GLOBAL_REVIEW":
                    if is_correct:
                        if qid in p_data["review_list"]: p_data["review_list"].remove(qid)
                        p_data["items"][qid] = {"ease": 2.5, "interval": 1, "next_review": get_next_review(1)}

                elif mode == "CHAP_REVIEW":
                    if is_correct:
                        if qid in p_data["chapter_wrongs"]: p_data["chapter_wrongs"].remove(qid)

                elif mode == "RANDOM_LEARN":
                    if not is_correct:
                        if qid not in p_data["review_list"]: p_data["review_list"].append(qid)
                        if qid in p_data["items"]: del p_data["items"][qid]
                    p_data["stats"]["random_state"]["idx"] = st.session_state.idx + 1

                elif mode in ["GLOBAL_LEARN", "CHAP_LEARN", "CHAP_LEARN_RANDOM"]:
                    if is_correct:
                        if mode == "GLOBAL_LEARN":
                            if qid not in p_data["items"] and qid not in p_data["review_list"]:
                                p_data["items"][qid] = {"ease": 2.5, "interval": 1, "next_review": get_next_review(1)}
                    else:
                        if mode == "GLOBAL_LEARN":
                            if qid not in p_data["review_list"]: p_data["review_list"].append(qid)
                        else:
                            if qid not in p_data["chapter_wrongs"]: p_data["chapter_wrongs"].append(qid)
                        if qid in p_data["items"]: del p_data["items"][qid]

                    if mode in ["GLOBAL_LEARN", "CHAP_LEARN"]:
                        p_data["stats"]["seq_progress"][st.session_state.seq_key] = st.session_state.idx + 1

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

        if st.button("ホームへ戻る"):
            st.session_state.view = "HOME"
            st.rerun()