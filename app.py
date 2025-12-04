import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
import urllib.parse

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬")

# --- 2. Firebase 연결 ---
if not firebase_admin._apps:
    try:
        cred_info = dict(st.secrets["firebase_key"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 Firebase 연결 실패: {e}")
        st.stop()

db = firestore.client()
chat_ref = db.collection("global_chat")

# --- 3. 사이드바 (설정) ---
with st.sidebar:
    st.header("👤 내 정보")
    
    # [핵심 수정 1] 세션 상태 대신 입력창 값을 실시간 변수로 받습니다.
    # 초기값 설정 (처음 켤 때만 적용)
    if "init_name" not in st.session_state:
        st.session_state.init_name = "익명"
    
    # 입력창을 만들고 바로 변수에 담습니다.
    raw_name = st.text_input("닉네임", value=st.session_state.init_name)
    
    # [핵심 수정 2] 무조건 공백을 제거하고 '현재 이름'으로 확정합니다.
    # 이제부터 이 변수(USER_NAME)가 법입니다.
    USER_NAME = raw_name.strip()
    if not USER_NAME:
        USER_NAME = "익명"
        
    # 나중에 다시 켰을 때 기억하기 위해 세션에 저장
    st.session_state.init_name = USER_NAME
    
    st.divider()
    
    st.header("🛠 관리자 메뉴")
    admin_input = st.text_input("관리자 암호", type="password", key="admin_pwd")
    
    if st.button("🗑️ 채팅 기록 삭제"):
        if "admin_password" in st.secrets and admin_input == st.secrets["admin_password"]:
            with st.spinner("청소 중..."):
                docs = chat_ref.stream()
                for doc in docs:
                    doc.reference.delete()
            st.success("초기화 완료!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("암호가 틀렸습니다!")
            
    st.divider()
    if st.button("🔄 새로고침"):
        st.rerun()

# --- 4. 메인 채팅 화면 ---
st.title("💬 정동고 익명 채팅방")

docs = chat_ref.order_by("timestamp").stream()
empty_check = True

for doc in docs:
    empty_check = False
    data = doc.to_dict()
    sender_name = data.get("name", "알 수 없음")
    message_text = data.get("message", "")
    
    # [핵심 수정 3] 비교할 때 위에서 만든 USER_NAME 변수를 씁니다.
    # 보낸 사람 이름도 공백 제거해서 비교
    if sender_name.strip() == USER_NAME:
        # 🟢 나 (오른쪽)
        with st.chat_message("user"):
            st.write(message_text)
    else:
        # 🔴 남 (왼쪽)
        safe_name = urllib.parse.quote(sender_name.strip())
        icon_url = f"https://api.dicebear.com/9.x/initials/svg?seed={safe_name}"
        
        with st.chat_message(sender_name, avatar=icon_url):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if empty_check:
    st.info("첫 메시지를 남겨보세요!")

# --- 5. 메시지 전송 ---
if prompt := st.chat_input("메시지 입력..."):
    # [핵심 수정 4] 메시지를 보낼 때도 무조건 USER_NAME 변수를 씁니다.
    # 이렇게 하면 비교하는 이름과 저장하는 이름이 100% 똑같을 수밖에 없습니다.
    chat_ref.add({
        "name": USER_NAME,
        "message": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    st.rerun()
