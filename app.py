import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re
from datetime import datetime, timedelta, timezone

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬")

# --- 2. 설정값 ---
MAX_CHAT_MESSAGES = 50  # 최대 메시지 저장 개수
INACTIVE_DAYS_LIMIT = 90 # 미접속 계정 삭제 기준일

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
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "user_nickname" not in st.session_state:
    st.session_state.user_nickname = ""

# ==========================================
# [A] 로그인 전 화면
# ==========================================
if not st.session_state.logged_in:
    st.title("🔒 입장하기")
    
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    with tab1:
        st.subheader("로그인")
        login_id = st.text_input("아이디", key="login_id")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        
        if st.button("로그인 하기"):
            if not login_id or not login_pw:
                st.warning("아이디와 비밀번호를 입력하세요.")
            else:
                doc = users_ref.document(login_id).get()
                if doc.exists:
                    user_data = doc.to_dict()
                    if user_data['password'] == hash_password(login_pw):
                        users_ref.document(login_id).update({
                            "last_login": firestore.SERVER_TIMESTAMP
                        })
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_id
                        st.session_state.user_nickname = user_data['nickname']
                        st.success(f"{user_data['nickname']}님 환영합니다!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("비밀번호가 틀렸습니다.")
                else:
                    st.error("존재하지 않는 아이디입니다.")

    with tab2:
        st.subheader("새 계정 만들기")
        new_id = st.text_input("아이디 (자유롭게 입력)", key="new_id")
        new_pw = st.text_input("비밀번호 (영문+숫자 4자 이상)", type="password", key="new_pw")
        new_nick = st.text_input("사용할 닉네임", key="new_nick")
        
        if st.button("회원가입"):
            if not new_id:
                st.error("아이디를 입력해주세요.")
            elif len(new_pw) < 4:
                st.error("비밀번호는 최소 4글자 이상이어야 합니다.")
            elif not re.search("[a-zA-Z]", new_pw) or not re.search("[0-9]", new_pw):
                st.error("비밀번호는 영문자와 숫자를 꼭 섞어서 만들어주세요.")
            elif not new_nick:
                st.error("닉네임을 입력해주세요.")
            else:
                if users_ref.document(new_id).get().exists:
                    st.error("이미 사용 중인 아이디입니다.")
                else:
                    users_ref.document(new_id).set({
                        "password": hash_password(new_pw),
                        "nickname": new_nick,
                        "last_login": firestore.SERVER_TIMESTAMP
                    })
                    st.success("회원가입 성공! 로그인 탭에서 로그인해주세요.")

# ==========================================
# [B] 로그인 후 화면
# ==========================================
else:
    with st.sidebar:
        st.header(f"👤 {st.session_state.user_nickname}님")
        # [삭제됨] 여기에 있던 새로고침 버튼 삭제함
        
        st.divider()
        
        with st.expander("닉네임 변경"):
            change_nick = st.text_input("새 닉네임", value=st.session_state.user_nickname)
            if st.button("저장"):
                if change_nick != st.session_state.user_nickname:
                    clean_nick = change_nick.strip()
                    if clean_nick:
                        with st.spinner("업데이트 중..."):
                            users_ref.document(st.session_state.user_id).update({"nickname": clean_nick})
                            my_msgs = chat_ref.where("user_id", "==", st.session_state.user_id).stream()
                            for msg in my_msgs:
                                msg.reference.update({"name": clean_nick})
                            st.session_state.user_nickname = clean_nick
                            st.success("완료!")
                            time.sleep(1)
                            st.rerun()
        
        st.divider()
        if st.button("🚪 로그아웃"):
            st.session_state.logged_in = False
            st.rerun()

        st.divider()
        
        with st.expander("🛠 관리자 메뉴"):
            admin_pw = st.text_input("관리자 암호", type="password")
            is_admin = ("admin_password" in st.secrets and admin_pw == st.secrets["admin_password"])
            
            if st.button("🗑️ 채팅 전체 삭제"):
                if is_admin:
                    with st.spinner("삭제 중..."):
                        docs = chat_ref.stream()
                        for doc in docs: doc.reference.delete()
                    st.success("완료")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("암호 오류")
            
            if st.button("계정 전체 삭제"):
                if is_admin:
                    with st.spinner("계정 삭제 중..."):
                        users = users_ref.stream()
                        for user in users: user.reference.delete()
                    st.success("완료")
                    st.session_state.logged_in = False
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("암호 오류")

            if st.button(f"💤 미접속 계정 정리 ({INACTIVE_DAYS_LIMIT}일)"):
                if is_admin:
                    with st.spinner("검색 중..."):
                        cutoff_date = datetime.now(timezone.utc) - timedelta(days=INACTIVE_DAYS_LIMIT)
                        old_users = users_ref.where("last_login", "<", cutoff_date).stream()
                        count = 0
                        for user in old_users:
                            user.reference.delete()
                            count += 1
                    st.success(f"{count}개 계정 삭제 완료")
                else:
                    st.error("암호 오류")

    # --- 메인 채팅창 ---
    # [수정됨] 오른쪽 위에 '채팅 새로고침' 버튼 크게 배치
    col1, col2 = st.columns([3, 1]) # 비율 조절해서 버튼 공간 확보
    with col1:
        st.title("💬 정동고 익명 채팅방")
    with col2:
        # 여기에 글자를 넣었습니다!
        if st.button("🔄 채팅 새로고침"): 
            st.rerun()
    
    docs = chat_ref.order_by("timestamp").stream()
    chat_exists = False
    
    for doc in docs:
        chat_exists = True
        data = doc.to_dict()
        msg_sender_id = data.get("user_id")
        msg_name = data.get("name")
        msg_text = data.get("message")
        
        if msg_sender_id == st.session_state.user_id:
            with st.chat_message("user"):
                st.write(msg_text)
        else:
            custom_avatar = get_custom_avatar(msg_sender_id)
            with st.chat_message(msg_name, avatar=custom_avatar):
                st.markdown(f"**{msg_name}**")
                st.write(msg_text)
                
    if not chat_exists:
        st.info("대화가 없습니다.")
        
    if prompt := st.chat_input("메시지 입력..."):
        chat_ref.add({
            "user_id": st.session_state.user_id,
            "name": st.session_state.user_nickname,
            "message": prompt,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        maintain_chat_history()
        st.rerun()
