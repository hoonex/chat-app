import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re
import uuid # [NEW] 익명 아이디 생성을 위해 필요
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬", layout="wide")

# --- 2. 설정값 ---
MAX_CHAT_MESSAGES = 50
INACTIVE_DAYS_LIMIT = 90
KST = timezone(timedelta(hours=9))
DEFAULT_DAILY_LIMIT = 0 # [변경] 0이면 무제한

# --- 3. 유틸리티 함수들 ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_custom_avatar(user_id):
    if user_id == "ADMIN_ACCOUNT":
        return "📢"
    hash_object = hashlib.md5(user_id.encode())
    hex_dig = hash_object.hexdigest()
    color_hex = hex_dig[:6]
    svg_code = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
      <rect width="100" height="100" rx="50" fill="#{color_hex}" />
      <text x="50%" y="55%" dominant-baseline="central" text-anchor="middle" font-size="60" fill="white">👤</text>
    </svg>
    """
    b64_svg = base64.b64encode(svg_code.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64_svg}"

def maintain_chat_history():
    docs = chat_ref.order_by("timestamp").stream()
    doc_list = list(docs)
    if len(doc_list) > MAX_CHAT_MESSAGES:
        delete_count = len(doc_list) - MAX_CHAT_MESSAGES
        for i in range(delete_count):
            doc_list[i].reference.delete()

def clean_inactive_users():
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=INACTIVE_DAYS_LIMIT)
        old_users = users_ref.where("last_login", "<", cutoff_date).stream()
        for user in old_users: user.reference.delete()
    except: pass

def format_time_kst(timestamp):
    if not timestamp: return "-"
    dt_kst = timestamp.astimezone(KST)
    return dt_kst.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후")

def get_system_config():
    doc = system_ref.document("config").get()
    if doc.exists:
        return doc.to_dict()
    else:
        default_config = {"is_locked": False, "banned_words": ""}
        system_ref.document("config").set(default_config)
        return default_config

def filter_message(text, banned_words_str):
    if not banned_words_str: return text
    words = [w.strip() for w in banned_words_str.split(",") if w.strip()]
    for word in words:
        if word in text: text = text.replace(word, "*" * len(word))
    return text

# 시간 제한 체크 (0이면 무제한)
def check_time_limit(user_id):
    if user_id == "ADMIN_ACCOUNT":
        return True, 0, 0
        
    user_ref = users_ref.document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return True, 0, 0

    data = user_doc.to_dict()
    daily_limit = data.get("daily_limit", 0) # 기본값 0 (무제한)
    used_minutes = data.get("used_minutes", 0)
    last_active_ts = data.get("last_active_ts")
    last_date_str = data.get("last_date_str")
    
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")
    
    if last_date_str != today_str:
        used_minutes = 0
        last_date_str = today_str
        
    added_time = 0
    if last_active_ts:
        last_active = last_active_ts.astimezone(KST)
        diff = (now - last_active).total_seconds() / 60
        if diff < 10: 
            added_time = diff
            
    new_used = used_minutes + added_time
    
    user_ref.update({
        "used_minutes": new_used,
        "last_active_ts": firestore.SERVER_TIMESTAMP,
        "last_date_str": last_date_str
    })
    
    # [수정] limit가 0보다 클 때만 체크 (0은 무제한)
    if daily_limit > 0 and new_used > daily_limit:
        return False, int(new_used), daily_limit 
        
    return True, int(new_used), daily_limit

# --- 4. Firebase 연결 ---
if not firebase_admin._apps:
    try:
        cred_info = dict(st.secrets["firebase_key"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 Firebase 연결 실패: {e}")
        st.stop()

db = firestore.client()
users_ref = db.collection("users")
chat_ref = db.collection("global_chat")
system_ref = db.collection("system")

# --- 5. 세션 초기화 ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "user_nickname" not in st.session_state: st.session_state.user_nickname = ""
if "is_super_admin" not in st.session_state: st.session_state.is_super_admin = False


# ==========================================
# [A] 로그인 화면
# ==========================================
if not st.session_state.logged_in:
    st.title("정동고 익명 채팅방 입장하기")
    
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    with tab1:
        st.subheader("로그인")
        login_id = st.text_input("아이디", key="login_id")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인 하기"):
            if not login_id or not login_pw:
                st.warning("입력해주세요.")
            else:
                if login_id == "admin":
                    if "admin_password" in st.secrets and login_pw == st.secrets["admin_password"]:
                        st.session_state.logged_in = True
                        st.session_state.user_id = "ADMIN_ACCOUNT"
                        st.session_state.user_nickname = "관리자"
                        st.session_state.is_super_admin = True
                        st.success("관리자 모드로 접속합니다.")
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error("관리자 비밀번호가 틀렸습니다.")
                else:
                    doc = users_ref.document(login_id).get()
                    if doc.exists and doc.to_dict()['password'] == hash_password(login_pw):
                        users_ref.document(login_id).update({
                            "last_login": firestore.SERVER_TIMESTAMP,
                            "last_active_ts": firestore.SERVER_TIMESTAMP
                        })
                        clean_inactive_users()
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_id
                        st.session_state.user_nickname = doc.to_dict()['nickname']
                        st.session_state.is_super_admin = False
                        st.rerun()
                    else: st.error("정보가 틀립니다.")

        # [NEW] 익명 입장 버튼 (로그인 탭 하단)
        st.markdown("---")
        if st.button("🕵️ 익명으로 바로 입장하기", type="primary", use_container_width=True):
            # 익명 계정 생성 (guest_랜덤ID)
            random_suffix = str(uuid.uuid4())[:6]
            guest_id = f"guest_{random_suffix}"
            guest_nick = f"익명_{random_suffix}"
            
            # DB에 게스트 정보 저장 (그래야 관리자가 시간제한 걸 수 있음)
            users_ref.document(guest_id).set({
                "password": "GUEST_NO_PASSWORD", # 비밀번호 없음
                "nickname": guest_nick,
                "last_login": firestore.SERVER_TIMESTAMP,
                "last_active_ts": firestore.SERVER_TIMESTAMP,
                "daily_limit": 0, # 무제한 기본
                "used_minutes": 0,
                "last_date_str": datetime.now(KST).strftime("%Y-%m-%d"),
                "is_guest": True # 게스트 표시
            })
            
            st.session_state.logged_in = True
            st.session_state.user_id = guest_id
            st.session_state.user_nickname = guest_nick
            st.session_state.is_super_admin = False
            st.success(f"임시 닉네임 '{guest_nick}'으로 입장합니다.")
            time.sleep(0.5)
            st.rerun()

    with tab2:
        st.subheader("회원가입")
        new_id = st.text_input("아이디", key="new_id")
        new_pw = st.text_input("비밀번호 (영문+숫자 4자 이상)", type="password", key="new_pw")
        new_nick = st.text_input("닉네임", key="new_nick")
        if st.button("회원가입"):
            if new_id.lower() == "admin": st.error("이 아이디는 사용할 수 없습니다.")
            elif new_id.startswith("guest_"): st.error("guest_로 시작하는 아이디는 만들 수 없습니다.")
            elif len(new_pw) < 4 or not (re.search("[a-zA-Z]", new_pw) and re.search("[0-9]", new_pw)):
                st.error("비밀번호 조건을 확인해주세요.")
            elif users_ref.document(new_id).get().exists: st.error("이미 있는 아이디입니다.")
            else:
                users_ref.document(new_id).set({
                    "password": hash_password(new_pw),
                    "nickname": new_nick,
                    "last_login": firestore.SERVER_TIMESTAMP,
                    "daily_limit": 0, # 무제한 기본
                    "used_minutes": 0,
                    "last_date_str": datetime.now(KST).strftime("%Y-%m-%d")
                })
                st.success("가입 완료! 로그인해주세요.")

# ==========================================
# [B] 로그인 성공 후
# ==========================================
else:
    sys_config = get_system_config()
    is_chat_locked = sys_config.get("is_locked", False)
    banned_words = sys_config.get("banned_words", "")

    is_allowed = True
    used_min = 0
    limit_min = 0
    
    if not st.session_state.is_super_admin:
        is_allowed, used_min, limit_min = check_time_limit(st.session_state.user_id)

    # ----------------------------------------------------
    # [B-1] 관리자 전용 화면
    # ----------------------------------------------------
    if st.session_state.is_super_admin:
        st.markdown("""
            <style>
            [data-testid="stAppViewContainer"] { background-color: #FFF9C4; }
            [data-testid="stHeader"] { background-color: #FFF9C4; }
            [data-testid="stSidebar"] { background-color: #FFF59D; }
            </style>
            """, unsafe_allow_html=True)

        st.sidebar.header("🛡️ 관리자 메뉴")
        if st.sidebar.button("🔄 관리자 페이지 새로고침"):
            st.rerun()
        st.sidebar.divider()
        if st.sidebar.button("🚪 관리자 로그아웃"):
            st.session_state.logged_in = False
            st.session_state.is_super_admin = False
            st.rerun()

        st.title("🛡️ 관리자 통제 센터")
        
        admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs(["📊 통계", "👥 회원 관리", "📢 모니터링", "⚙️ 시스템 설정"])
        
        with admin_tab1:
            all_users = list(users_ref.stream())
            all_chats = list(chat_ref.stream())
            c1, c2 = st.columns(2)
            c1.metric("총 회원", f"{len(all_users)}명")
            c2.metric("총 메시지", f"{len(all_chats)}개")

        with admin_tab2:
            st.subheader("회원 목록 및 시간 제한 (0=무제한)")
            if all_users:
                c1, c2, c3, c4, c5, c6 = st.columns([1.5, 1.5, 1.5, 1.5, 1, 1])
                c1.markdown("**ID**")
                c2.markdown("**닉네임**")
                c3.markdown("**사용 / 제한**")
                c4.markdown("**제한(분) 설정**")
                c5.markdown("**적용**")
                c6.markdown("**관리**")
                st.divider()
                
                for user in all_users:
                    u_data = user.to_dict()
                    u_id = user.id
                    u_nick = u_data.get("nickname", "-")
                    u_limit = u_data.get("daily_limit", 0) # 기본 0
                    u_used = u_data.get("used_minutes", 0)
                    
                    cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([1.5, 1.5, 1.5, 1.5, 1, 1])
                    cc1.text(u_id)
                    cc2.text(u_nick)
                    
                    # 사용량 텍스트
                    limit_str = "무제한" if u_limit == 0 else f"{u_limit}분"
                    usage_text = f"{int(u_used)}분 / {limit_str}"
                    
                    # 초과 시 빨간색
                    if u_limit > 0 and u_used > u_limit:
                        cc3.error(usage_text)
                    else:
                        cc3.text(usage_text)
                    
                    # 제한 설정 입력 (0 = 무제한)
                    new_limit = cc4.number_input("limit", min_value=0, value=u_limit, key=f"limit_{u_id}", label_visibility="collapsed")
                    
                    if cc5.button("저장", key=f"save_{u_id}"):
                        users_ref.document(u_id).update({"daily_limit": new_limit})
                        st.toast(f"설정 완료: {new_limit}분 (0=무제한)")
                        time.sleep(1)
                        st.rerun()
                    
                    if cc6.button("삭제", key=f"ban_{u_id}", type="primary"):
                        users_ref.document(u_id).delete()
                        st.toast("삭제 완료")
                        time.sleep(1)
                        st.rerun()

        with admin_tab3:
            st.subheader("실시간 모니터링")
            if st.button("🗑️ 채팅방 기록 전체 삭제 (초기화)", type="primary"):
                docs = chat_ref.stream()
                for doc in docs: doc.reference.delete()
                st.success("삭제 완료")
                time.sleep(1)
                st.rerun()
            st.divider()
            docs = chat_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
            for doc in docs:
                data = doc.to_dict()
                doc_id = doc.id
                name = data.get("name")
                msg = data.get("message")
                is_deleted = data.get("is_deleted", False)
                time_str = format_time_kst(data.get("timestamp"))
                with st.container(border=True):
                    mc1, mc2 = st.columns([8, 2])
                    with mc1:
                        if is_deleted: st.caption(f"🚫 [삭제됨] {name}: {msg}")
                        else: 
                            st.write(f"**{name}**: {msg}")
                            st.caption(time_str)
                    with mc2:
                        if not is_deleted:
                            if st.button("삭제", key=f"adm_del_{doc_id}", type="primary"):
                                chat_ref.document(doc_id).update({"is_deleted": True})
                                st.rerun()
            st.divider()
            notice_msg = st.text_input("공지 내용")
            if st.button("공지 전송"):
                if notice_msg:
                    chat_ref.add({
                        "user_id": "ADMIN_ACCOUNT",
                        "name": "📢 관리자",
                        "message": notice_msg,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "is_deleted": False
                    })
                    maintain_chat_history()
                    st.rerun()

        with admin_tab4:
            st.subheader("⚙️ 시스템 설정")
            st.markdown("### 1. 채팅방 얼리기")
            lock_status = st.toggle("채팅방 얼리기", value=is_chat_locked)
            if lock_status != is_chat_locked:
                system_ref.document("config").update({"is_locked": lock_status})
                st.rerun()
            st.divider()
            st.markdown("### 2. 금칙어 관리")
            st.caption("쉼표(,)로 구분")
            new_banned_words = st.text_area("금칙어 목록", value=banned_words, height=150)
            if st.button("금칙어 저장"):
                system_ref.document("config").update({"banned_words": new_banned_words})
                st.success("저장됨")
                time.sleep(1)
                st.rerun()

    # ----------------------------------------------------
    # [B-2] 일반 사용자 화면
    # ----------------------------------------------------
    else:
        # 시간 초과 체크
        if not is_allowed:
            st.error("⏳ 일일 이용 시간이 초과되었습니다.")
            st.info(f"오늘은 {used_min}분을 사용하셨습니다.")
            st.warning("내일 다시 접속해주세요!")
            if st.button("🚪 로그아웃"):
                st.session_state.logged_in = False
                st.rerun()
            st.stop()

        components.html("""
            <script>
                function fixButtonPosition() {
                    const buttons = window.parent.document.querySelectorAll('button');
                    buttons.forEach(btn => {
                        if (btn.innerText.includes('🔄 채팅 새로고침')) {
                            btn.style.position = 'fixed';
                            btn.style.top = '70px'; 
                            btn.style.right = '20px';
                            btn.style.bottom = 'auto'; 
                            btn.style.left = 'auto';   
                            btn.style.width = 'auto'; 
                            btn.style.minWidth = '0px';
                            btn.style.zIndex = '999999';
                            btn.style.backgroundColor = 'white';
                            btn.style.color = '#FF4B4B';
                            btn.style.border = '1px solid #FF4B4B';
                            btn.style.borderRadius = '15px';
                            btn.style.fontWeight = 'bold';
                            btn.style.padding = '5px 12px';
                            btn.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
                        }
                    });
                }
                setInterval(fixButtonPosition, 500);
            </script>
        """, height=0, width=0)
        
        if st.button("🔄 채팅 새로고침"):
            st.rerun()

        with st.sidebar:
            st.header(f"👤 {st.session_state.user_nickname}님")
            
            # 남은 시간 표시
            if limit_min == 0:
                st.info(f"⏳ 사용: {used_min}분 (무제한)")
            else:
                st.info(f"⏳ 사용: {used_min}분 / {limit_min}분")
                
            with st.expander("닉네임 변경"):
                change_nick = st.text_input("새 닉네임", value=st.session_state.user_nickname)
                if st.button("저장"):
                    if change_nick != st.session_state.user_nickname:
                        clean_nick = change_nick.strip()
                        if clean_nick:
                            users_ref.document(st.session_state.user_id).update({"nickname": clean_nick})
                            my_msgs = chat_ref.where("user_id", "==", st.session_state.user_id).stream()
                            for msg in my_msgs: msg.reference.update({"name": clean_nick})
                            st.session_state.user_nickname = clean_nick
                            st.rerun()
            if st.button("🚪 로그아웃"):
                st.session_state.logged_in = False
                st.rerun()
            st.divider()
            st.caption("문의사항은 관리자에게 연락.")

        st.title("💬 정동고 익명 채팅방")
        
        if is_chat_locked:
            st.error("🔒 현재 관리자가 채팅방을 얼렸습니다.")

        docs = chat_ref.order_by("timestamp").stream()
        chat_exists = False
        
        for doc in docs:
            chat_exists = True
            data = doc.to_dict()
            doc_id = doc.id
            msg_id = data.get("user_id")
            msg_name = data.get("name")
            msg_text = data.get("message")
            msg_time = format_time_kst(data.get("timestamp"))
            is_deleted = data.get("is_deleted", False)
            
            if is_deleted:
                if msg_id == "ADMIN_ACCOUNT":
                    display_text = "🚫 관리자에 의해 삭제된 공지입니다."
                elif msg_text == "🚫 관리자에 의해 삭제된 글입니다.":
                    display_text = "🚫 관리자에 의해 삭제된 글입니다."
                else:
                    display_text = f"🗑️ {msg_name}님이 삭제한 글입니다."
                
                text_html = f"""<div style='color:#888;font-style:italic;'>{display_text}</div>
                                <div style='display:block;text-align:right;font-size:0.7em;color:grey;'>{msg_time}</div>"""
            else:
                text_html = f"""{msg_text}<div style='display:block;text-align:right;font-size:0.7em;color:grey;'>{msg_time}</div>"""
            
            if msg_id == "ADMIN_ACCOUNT":
                with st.chat_message("admin", avatar="📢"):
                    if is_deleted: st.markdown(text_html, unsafe_allow_html=True)
                    else: st.error(f"**[공지] {msg_text}**") 
            
            elif msg_id == st.session_state.user_id:
                with st.chat_message("user"):
                    col_msg, col_del = st.columns([9, 1])
                    with col_msg: st.markdown(text_html, unsafe_allow_html=True)
                    with col_del:
                        if not is_deleted:
                            if st.button("🗑️", key=f"my_del_{doc_id}", help="삭제"):
                                chat_ref.document(doc_id).update({"is_deleted": True})
                                st.rerun()

            else:
                with st.chat_message(msg_name, avatar=get_custom_avatar(msg_id)):
                    if not is_deleted: st.markdown(f"**{msg_name}**")
                    st.markdown(text_html, unsafe_allow_html=True)

        if not chat_exists: st.info("대화가 없습니다.")
            
        if prompt := st.chat_input("메시지 입력...", disabled=is_chat_locked):
            filtered_msg = filter_message(prompt, banned_words)
            chat_ref.add({
                "user_id": st.session_state.user_id,
                "name": st.session_state.user_nickname,
                "message": filtered_msg,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "is_deleted": False
            })
            maintain_chat_history()
            st.rerun()
