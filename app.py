import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time

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
    
    # [수정 1] 이름을 입력받을 때 공백 제거 (.strip())
    # key를 지정해서 입력 값을 안전하게 잡습니다.
    if "username" not in st.session_state:
        st.session_state.username = "익명"
        
    input_name = st.text_input("닉네임", value=st.session_state.username)
    # 입력된 이름의 앞뒤 공백을 자동으로 삭제해서 저장
    st.session_state.username = input_name.strip()
    
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

# 메시지 가져오기
docs = chat_ref.order_by("timestamp").stream()

empty_check = True

for doc in docs:
    empty_check = False
    data = doc.to_dict()
    sender_name = data.get("name", "알 수 없음")
    message_text = data.get("message", "")
    
    # [수정 2] 보낸 사람 이름도 혹시 모르니 공백 제거해서 비교
    if sender_name.strip() == st.session_state.username:
        # 🟢 나 (오른쪽)
        with st.chat_message("user"):
            st.write(message_text)
    else:
        # 🔴 남 (왼쪽) - 예쁜 아이콘 적용
        icon_url = f"https://ui-avatars.com/api/?name={sender_name}&background=random&color=fff"
        with st.chat_message(sender_name, avatar=icon_url):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if empty_check:
    st.info("첫 메시지를 남겨보세요!")

# --- 5. 메시지 전송 ---
if prompt := st.chat_input("메시지 입력..."):
    # [수정 3] 메시지 보낼 때도 내 이름을 확실하게 공백 제거해서 보냄
    current_name = st.session_state.username
    if not current_name: # 이름이 비어있으면 '익명'으로 강제 설정
        current_name = "익명"
        
    chat_ref.add({
        "name": current_name,
        "message": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    st.rerun()
