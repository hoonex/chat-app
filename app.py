import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re
from datetime import datetime, timedelta, timezone
import pandas as pd # 👈 [추가] 표(DataFrame) 처리를 위해 필요

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬", layout="wide") 
# layout="wide"로 변경하여 관리자 화면을 넓게 씁니다.

# --- 2. 설정값 ---
MAX_CHAT_MESSAGES = 50
INACTIVE_DAYS_LIMIT = 90
KST = timezone(timedelta(hours=9))

# --- 3. 유틸리티 함수들 ---

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_custom_avatar(user_id):
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
        for user in old_users:
            user.reference.delete()
    except:
        pass

def format_time_kst(timestamp):
    if not timestamp: return "-"
    dt_kst = timestamp.astimezone(KST)
    return dt_kst.strftime("%Y-%m-%d %p %I:%M").replace("AM", "오전").replace("PM", "오후")

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

# --- 5. 세션 초기화 ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "user_nickname" not in st.session_state: st.session_state.user_nickname = ""
if "is_admin_mode" not in st.session_state: st.session_state.is_admin_mode = False

# ==========================================
# [사이드바] 공통 메뉴 & 관리자 스위치
# ==========================================
with st.sidebar:
    if st.session_state.logged_in:
        st.header(f"👤 {st.session_state.user_nickname}님")
        
        # 닉네임 변경 등 기존 기능들...
        with st.expander("내 정보 수정"):
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
            st.session_state.is_admin_mode = False
            st.rerun()
            
    st.divider()
    
    # [핵심] 관리자 모드 진입 스위치
    st.subheader("🛡️ 관리자")
    admin_pw_input = st.text_input("관리자 암호", type="password")
    
    # 암호가 맞으면 관리자 모드 체크박스 활성화
    is_correct_admin = ("admin_password" in st.secrets and admin_pw_input == st.secrets["admin_password"])
    
    if is_correct_admin:
        # 체크박스로 모드 전환
        st.session_state.is_admin_mode = st.checkbox("관리자 대시보드 열기", value=st.session_state.is_admin_mode)
    else:
        if admin_pw_input:
            st.error("암호가 틀렸습니다.")
        st.session_state.is_admin_mode = False

# ==========================================
# [A] 관리자 대시보드 (관리자 모드 ON일 때)
# ==========================================
if st.session_state.is_admin_mode:
    st.title("🛡️ 관리자 대시보드")
    st.info("여기서는 회원 목록을 확인하고 개별적으로 관리할 수 있습니다.")
    
    tab_users, tab_chat = st.tabs(["👥 회원 관리", "💬 채팅 데이터 관리"])
    
    # --- 1. 회원 관리 탭 ---
    with tab_users:
        # 모든 회원 가져오기
        all_users = list(users_ref.stream())
        
        if not all_users:
            st.warning("가입된 회원이 없습니다.")
        else:
            st.metric("총 회원 수", f"{len(all_users)}명")
            
            # 표 헤더
            col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
            col1.markdown("**아이디**")
            col2.markdown("**닉네임**")
            col3.markdown("**마지막 접속**")
            col4.markdown("**관리**")
            st.divider()
            
            # 회원 리스트 출력
            for user in all_users:
                u_data = user.to_dict()
                u_id = user.id
                u_nick = u_data.get("nickname", "-")
                u_last = u_data.get("last_login")
                
                c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
                
                c1.text(u_id)
                c2.text(u_nick)
                c3.text(format_time_kst(u_last))
                
                # 삭제 버튼 (각 회원마다 고유 키 부여)
                if c4.button("삭제", key=f"del_{u_id}", type="primary"):
                    # DB에서 삭제
                    users_ref.document(u_id).delete()
                    st.toast(f"'{u_nick}'({u_id}) 계정을 삭제했습니다.")
                    time.sleep(1)
                    st.rerun()
            
            st.divider()
            if st.button("전체 회원 일괄 삭제"):
                for u in all_users:
                    u.reference.delete()
                st.success("모든 회원이 삭제되었습니다.")
                st.rerun()

    # --- 2. 채팅 데이터 관리 탭 ---
    with tab_chat:
        st.write("채팅방 데이터를 강제로 초기화할 수 있습니다.")
        if st.button("🗑️ 채팅 기록 전체 삭제"):
            docs = chat_ref.stream()
            for doc in docs: doc.reference.delete()
            st.success("채팅방이 초기화되었습니다.")

# ==========================================
# [B] 일반 사용자 화면 (로그인 전/후)
# ==========================================
else:
    # 1. 로그인 전
    if not st.session_state.logged_in:
        st.title("정동고 익명 채팅방 입장하기")
        tab1, tab2 = st.tabs(["로그인", "회원가입"])
        
        with tab1:
            st.subheader("로그인")
            login_id = st.text_input("아이디", key="login_id")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw")
            if st.button("로그인 하기"):
                if not login_id or not login_pw: st.warning("입력해주세요.")
                else:
                    doc = users_ref.document(login_id).get()
                    if doc.exists and doc.to_dict()['password'] == hash_password(login_pw):
                        users_ref.document(login_id).update({"last_login": firestore.SERVER_TIMESTAMP})
                        clean_inactive_users()
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_id
                        st.session_state.user_nickname = doc.to_dict()['nickname']
                        st.rerun()
                    else: st.error("정보가 틀립니다.")

        with tab2:
            st.subheader("회원가입")
            new_id = st.text_input("아이디", key="new_id")
            new_pw = st.text_input("비밀번호 (영문+숫자 4자 이상)", type="password", key="new_pw")
            new_nick = st.text_input("닉네임", key="new_nick")
            if st.button("회원가입"):
                if len(new_pw) < 4 or not (re.search("[a-zA-Z]", new_pw) and re.search("[0-9]", new_pw)):
                    st.error("비밀번호 조건을 확인해주세요.")
                elif users_ref.document(new_id).get().exists:
                    st.error("이미 있는 아이디입니다.")
                else:
                    users_ref.document(new_id).set({
                        "password": hash_password(new_pw),
                        "nickname": new_nick,
                        "last_login": firestore.SERVER_TIMESTAMP
                    })
                    st.success("가입 완료! 로그인해주세요.")

    # 2. 로그인 후 (채팅 화면)
    else:
        # 메인 채팅창
        col1, col2 = st.columns([3, 1])
        with col1: st.title("💬 정동고 익명 채팅방")
        with col2: 
            if st.button("🔄 채팅 새로고침"): st.rerun()
        
        docs = chat_ref.order_by("timestamp").stream()
        chat_exists = False
        
        for doc in docs:
            chat_exists = True
            data = doc.to_dict()
            msg_id = data.get("user_id")
            msg_name = data.get("name")
            msg_text = data.get("message")
            msg_time = format_time_kst(data.get("timestamp"))
            
            text_html = f"""{msg_text}<div style='display:block;text-align:right;font-size:0.7em;color:grey;'>{msg_time}</div>"""
            
            if msg_id == st.session_state.user_id:
                with st.chat_message("user"): st.markdown(text_html, unsafe_allow_html=True)
            else:
                with st.chat_message(msg_name, avatar=get_custom_avatar(msg_id)):
                    st.markdown(f"**{msg_name}**")
                    st.markdown(text_html, unsafe_allow_html=True)
                    
        if not chat_exists: st.info("대화가 없습니다.")
            
        if prompt := st.chat_input("메시지 입력..."):
            chat_ref.add({
                "user_id": st.session_state.user_id,
                "name": st.session_state.user_nickname,
                "message": prompt,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            maintain_chat_history()
            st.rerun()
