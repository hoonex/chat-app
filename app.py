import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re
import uuid
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬", layout="wide")

# --- 2. 설정값 ---
MAX_CHAT_MESSAGES = 50
KST = timezone(timedelta(hours=9))

# --- 3. 유틸리티 함수들 ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# [색상 기능] 아바타 생성 시 색상 반영
def get_custom_avatar(user_id, specific_color=None):
    if user_id == "ADMIN_ACCOUNT":
        return "📢"
    
    if specific_color:
        color_hex = specific_color.replace("#", "")
    else:
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
# [색상] 세션 초기화
if "user_color" not in st.session_state: st.session_state.user_color = "#000000"


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
                        # 로그인 시간만 업데이트 (시간 제한 로직 삭제됨)
                        users_ref.document(login_id).update({
                            "last_login": firestore.SERVER_TIMESTAMP
                        })
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_id
                        st.session_state.user_nickname = doc.to_dict()['nickname']
                        st.session_state.is_super_admin = False
                        st.rerun()
                    else: st.error("정보가 틀립니다.")

        st.markdown("---")
        if st.button("🕵️ 익명으로 바로 입장하기", type="primary", use_container_width=True):
            random_suffix = str(uuid.uuid4())[:6]
            guest_id = f"guest_{random_suffix}"
            guest_nick = f"익명_{random_suffix}"
            
            users_ref.document(guest_id).set({
                "password": "GUEST_NO_PASSWORD",
                "nickname": guest_nick,
                "last_login": firestore.SERVER_TIMESTAMP,
                "is_guest": True
            })
            
            st.session_state.logged_in = True
            st.session_state.user_id = guest_id
            st.session_state.user_nickname = guest_nick
            st.session_state.is_super_admin = False
            st.success(f"'{guest_nick}'으로 입장합니다.")
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
                    "last_login": firestore.SERVER_TIMESTAMP
                })
                st.success("가입 완료! 로그인해주세요.")

# ==========================================
# [B] 로그인 성공 후
# ==========================================
else:
    sys_config = get_system_config()
    is_chat_locked = sys_config.get("is_locked", False)
    banned_words = sys_config.get("banned_words", "")

    # [수정] 시간 체크 로직(check_time_limit) 완전히 삭제함.
    # 이제 무조건 이용 가능합니다.

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
            st.subheader("회원 목록")
            if all_users:
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.markdown("**ID**")
                c2.markdown("**닉네임**")
                c3.markdown("**관리**")
                st.divider()
                
                for user in all_users:
                    u_data = user.to_dict()
                    u_id = user.id
                    u_nick = u_data.get("nickname", "-")
                    
                    cc1, cc2, cc3 = st.columns([2, 2, 1])
                    cc1.text(u_id)
                    cc2.text(u_nick)
                    
                    if cc3.button("추방", key=f"ban_{u_id}", type="primary"):
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
                # [색상] 관리자 화면에서도 보존된 색상 확인
                msg_color = data.get("color", "#000000")

                with st.container(border=True):
                    mc1, mc2 = st.columns([8, 2])
                    with mc1:
                        if is_deleted: st.caption(f"🚫 [삭제됨] {name}: {msg}")
                        else: 
                            # 색상 적용
                            st.markdown(f"<span style='color:{msg_color}; font-weight:bold;'>{name}</span>: {msg}", unsafe_allow_html=True)
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
                        "is_deleted": False,
                        "color": "#FF0000"
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
        # [수정] 여기에 있던 "if not is_allowed: ..." 블록을 완전히 삭제했습니다.
        # 이제 시간 초과 검사를 하지 않습니다.

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
            
            # --- [기능] 사이드바 색상 변경 (메시지 보낼때 이 색이 박제됨) ---
            st.divider()
            st.subheader("🎨 프로필 색상")
            
            # 현재 세션 스테이트의 색상을 기본값으로 사용
            chosen_color = st.color_picker("색상 선택", st.session_state.user_color)
            
            if chosen_color != st.session_state.user_color:
                st.session_state.user_color = chosen_color
                st.rerun()
                
            st.divider()
            # ---------------------------------------------------------------
                
            with st.expander("닉네임 변경"):
                if st.session_state.user_id.startswith("guest_"):
                    st.caption("🚫 익명 사용자는 닉네임을 변경할 수 없습니다.")
                else:
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
            
            # --- [기능] 저장된 메시지 색상 불러오기 ---
            msg_color = data.get("color", "#000000")
            
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
                # [색상] 상대방 메시지 표시할 때 저장된 색상 적용
                with st.chat_message(msg_name, avatar=get_custom_avatar(msg_id, msg_color)):
                    if not is_deleted: 
                        st.markdown(f"<span style='color:{msg_color}; font-weight:bold;'>{msg_name}</span>", unsafe_allow_html=True)
                    st.markdown(text_html, unsafe_allow_html=True)

        if not chat_exists: st.info("대화가 없습니다.")
            
        if prompt := st.chat_input("메시지 입력...", disabled=is_chat_locked):
            filtered_msg = filter_message(prompt, banned_words)
            
            # --- [기능] 메시지 저장 시 현재 내 색상(user_color)을 같이 저장 ---
            chat_ref.add({
                "user_id": st.session_state.user_id,
                "name": st.session_state.user_nickname,
                "message": filtered_msg,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "is_deleted": False,
                "color": st.session_state.user_color 
            })
            
            maintain_chat_history()
            st.rerun()
