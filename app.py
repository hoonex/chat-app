import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬")

# --- 2. 유틸리티 함수들 ---

# (1) 비밀번호 암호화
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# (2) 아바타 생성 (ID 기반 고유 색상)
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

# --- 3. Firebase 연결 ---
if not firebase_admin._apps:
    try:
        cred_info = dict(st.secrets["firebase_key"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 Firebase 연결 실패: {e}")
        st.stop()

db = firestore.client()
users_ref = db.collection("users")       # 회원 정보
chat_ref = db.collection("global_chat")  # 채팅 내용

# --- 4. 세션 상태 초기화 ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "user_nickname" not in st.session_state:
    st.session_state.user_nickname = ""

# ==========================================
# [A] 로그인 전 화면 (로그인 / 회원가입)
# ==========================================
if not st.session_state.logged_in:
    st.title("🔒 입장하기")
    
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    # --- 탭 1: 로그인 ---
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

    # --- 탭 2: 회원가입 ---
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
                        "nickname": new_nick
                    })
                    st.success("회원가입 성공! 로그인 탭에서 로그인해주세요.")

# ==========================================
# [B] 로그인 후 화면 (채팅방)
# ==========================================
else:
    # --- 사이드바 ---
    with st.sidebar:
        st.header(f"👤 {st.session_state.user_nickname}님")
        st.caption(f"ID: {st.session_state.user_id}")
        
        # [✨추가됨] 채팅 새로고침 버튼 (가장 잘 보이는 곳에 배치)
        if st.button("🔄 채팅 새로고침", type="primary"):
            st.rerun()
            
        st.divider()
        
        # 닉네임 변경
        st.subheader("닉네임 변경")
        change_nick = st.text_input("새 닉네임", value=st.session_state.user_nickname)
        
        if st.button("변경 저장"):
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
            if st.button("채팅방 초기화"):
                if "admin_password" in st.secrets and admin_pw == st.secrets["admin_password"]:
                    docs = chat_ref.stream()
                    for doc in docs:
                        doc.reference.delete()
                    st.success("초기화 완료")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("암호 오류")

    # --- 메인 채팅창 ---
    # 제목 옆에 작은 새로고침 팁 추가
    col1, col2 = st.columns([5, 1])
    with col1:
        st.title("💬 정동고 익명 채팅방")
    with col2:
        # 화면 오른쪽 위에도 작은 새로고침 버튼 추가
        if st.button("🔄", help="새로고침"):
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
        st.info("대화가 없습니다. 첫 메시지를 보내보세요!")
        
    if prompt := st.chat_input("메시지 입력..."):
        chat_ref.add({
            "user_id": st.session_state.user_id,
            "name": st.session_state.user_nickname,
            "message": prompt,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        st.rerun()
