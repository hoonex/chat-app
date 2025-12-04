import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
import urllib.parse
import uuid # 👈 [추가] 고유한 주민등록번호(ID)를 만드는 도구

# --- 1. 페이지 기본 설정 ---
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

# --- 3. 사용자 고유 ID(지문) 생성 ---
# 브라우저를 껐다 켜기 전까지 유지되는 나만의 고유번호
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

# --- 4. 사이드바 (내 정보 설정) ---
with st.sidebar:
    st.header("👤 내 정보")
    
    # 닉네임 설정
    if "user_nickname" not in st.session_state:
        st.session_state.user_nickname = "익명"

    st.text_input("닉네임", key="user_nickname")
    
    # 이름 공백 제거
    MY_NAME = st.session_state.user_nickname.strip()
    if not MY_NAME:
        MY_NAME = "익명"

    st.caption(f"내 고유 ID: ...{st.session_state.user_id[-6:]}") # 디버깅용(끝 6자리만 표시)

    st.divider()
    
    st.header("🛠 관리자 메뉴")
    admin_input = st.text_input("관리자 암호", type="password", key="admin_pwd")
    
    if st.button("🗑️ 채팅 기록 삭제"):
        if "admin_password" in st.secrets and admin_input == st.secrets["admin_password"]:
            with st.spinner("삭제 중..."):
                docs = chat_ref.stream()
                for doc in docs:
                    doc.reference.delete()
            st.success("삭제 완료!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("암호가 틀렸습니다!")
            
    st.divider()
    if st.button("🔄 새로고침"):
        st.rerun()

# --- 5. 메인 채팅 화면 ---
st.title("💬 정동고 익명 채팅방")

docs = chat_ref.order_by("timestamp").stream()
chat_exists = False

for doc in docs:
    chat_exists = True
    data = doc.to_dict()
    
    sender_name = str(data.get("name", "알 수 없음"))
    message_text = data.get("message", "")
    sender_id = data.get("user_id", "") # 저장된 작성자의 고유 ID 꺼내기
    
    # [핵심 수정] 닉네임이 아니라 '고유 ID'가 같은지 비교합니다.
    # 이름이 "익명"으로 똑같아도, ID가 다르면 남(왼쪽)으로 뜹니다.
    if sender_id == st.session_state.user_id:
        # ✅ 나 (오른쪽)
        with st.chat_message("user"):
            st.write(message_text)
    else:
        # 🔴 남 (왼쪽)
        # 이름이 같아도 남이면 왼쪽에 예쁜 아이콘으로 뜹니다.
        safe_name = urllib.parse.quote(sender_name)
        icon_url = f"https://api.dicebear.com/9.x/initials/svg?seed={safe_name}"
        
        with st.chat_message(sender_name, avatar=icon_url):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if not chat_exists:
    st.info("첫 메시지를 남겨보세요!")

# --- 6. 메시지 전송 ---
if prompt := st.chat_input("메시지 입력..."):
    chat_ref.add({
        "name": MY_NAME,
        "message": prompt,
        "user_id": st.session_state.user_id, # [중요] 내 지문(ID)을 같이 찍어서 보냄
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    st.rerun()
