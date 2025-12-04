import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬")

# --- 2. Firebase 연결 (Secrets 사용) ---
# 앱이 실행될 때 한 번만 연결
if not firebase_admin._apps:
    try:
        # st.secrets["firebase_key"]는 아까 설정한 TOML 내용을 딕셔너리로 가져옵니다.
        cred_info = dict(st.secrets["firebase_key"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase 연결 에러: {e}")
        st.stop()

db = firestore.client()

# --- 3. UI 및 사용자 이름 설정 ---
st.title("💬 정동고1-6반 익명 채팅방")

if "username" not in st.session_state:
    st.session_state.username = "익명"

with st.sidebar:
    st.header("설정")
    st.session_state.username = st.text_input("닉네임", st.session_state.username)
    if st.button("🔄 새로고침"):
        st.rerun()
    st.caption("※ 상대방 글을 보려면 새로고침을 누르세요.")

# --- 4. 메시지 가져오기 ---
# 채팅방 이름: 'global_chat' (없으면 자동 생성됨)
chat_ref = db.collection("global_chat")

# 시간순으로 정렬해서 가져오기
docs = chat_ref.order_by("timestamp").stream()

# --- 5. 채팅 화면 그리기 ---
for doc in docs:
    data = doc.to_dict()
    sender_name = data.get("name", "알 수 없음")
    message_text = data.get("message", "")
    
    # 내가 보낸 건 오른쪽("user"), 남이 보낸 건 왼쪽("assistant")
    if sender_name == st.session_state.username:
        with st.chat_message("user"):
            st.write(f"{message_text}")
    else:
        with st.chat_message("assistant"):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

# --- 6. 메시지 전송 로직 ---
# 화면 맨 아래 입력창
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 1. DB에 저장
    chat_ref.add({
        "name": st.session_state.username,
        "message": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    
    # 2. 화면 즉시 갱신 (내 메시지 바로 보이게)
    st.rerun()
