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
        # Secrets에 저장된 Firebase 키 정보를 가져옴
        cred_info = dict(st.secrets["firebase_key"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 Firebase 연결 실패: {e}")
        st.stop()

db = firestore.client()
chat_ref = db.collection("global_chat") # 채팅방 이름

# --- 3. 사이드바 (설정 & 관리자 메뉴) ---
with st.sidebar:
    st.header("👤 내 정보")
    # 사용자 이름 설정
    if "username" not in st.session_state:
        st.session_state.username = "익명"
    st.session_state.username = st.text_input("닉네임", st.session_state.username)
    
    st.divider() # 구분선
    
    st.header("🛠 관리자 메뉴")
    # 관리자 암호 입력창 (비밀번호처럼 가려짐)
    admin_input = st.text_input("관리자 암호", type="password", key="admin_pwd")
    
    # 채팅 기록 삭제 버튼
    if st.button("🗑️ 채팅 기록 삭제 (초기화)"):
        # Secrets에 저장된 'admin_password'와 입력한 암호 비교
        if "admin_password" in st.secrets and admin_input == st.secrets["admin_password"]:
            with st.spinner("기록을 지우는 중입니다..."):
                # DB의 모든 메시지 삭제
                docs = chat_ref.stream()
                for doc in docs:
                    doc.reference.delete()
                
            st.success("채팅방이 깨끗하게 초기화되었습니다! ✨")
            time.sleep(1)
            st.rerun() # 화면 새로고침
        else:
            if "admin_password" not in st.secrets:
                st.error("설정 오류: Secrets에 'admin_password'가 없습니다.")
            else:
                st.error("암호가 틀렸습니다! 🚫")
            
    st.divider()
    if st.button("🔄 새로고침"):
        st.rerun()

# --- 4. 메인 채팅 화면 ---
st.title("정동고 익명 채팅방")

# 메시지 가져오기
docs = chat_ref.order_by("timestamp").stream()

empty_check = True

for doc in docs:
    empty_check = False
    data = doc.to_dict()
    sender_name = data.get("name", "알 수 없음")
    message_text = data.get("message", "")
    
    # 1. 내가 보낸 메시지 (오른쪽)
    if sender_name == st.session_state.username:
        # 내 건 그냥 'user' 아이콘(사람 모양) 쓰거나, 내 이름 넣어도 됨
        with st.chat_message("user"): 
            st.write(message_text)
            
    # 2. 남이 보낸 메시지 (왼쪽)
    else:
        with st.chat_message(sender_name): 
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if empty_check:
    st.info("아직 대화 내용이 없습니다. 첫 메시지를 남겨보세요!")

# --- 5. 메시지 전송 로직 ---
if prompt := st.chat_input("메시지를 입력하세요..."):
    # DB에 저장
    chat_ref.add({
        "name": st.session_state.username,
        "message": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    # 전송 후 즉시 화면 갱신
    st.rerun()
