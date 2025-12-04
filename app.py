import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
import uuid # 고유 ID 생성 도구

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
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

# --- 4. 사이드바 (내 정보 설정) ---
with st.sidebar:
    st.header("👤 내 정보")
    
    if "user_nickname" not in st.session_state:
        st.session_state.user_nickname = "익명"

    st.text_input("닉네임", key="user_nickname")
    
    MY_NAME = st.session_state.user_nickname.strip()
    if not MY_NAME:
        MY_NAME = "익명"

    # 디버깅용 (내 ID 확인)
    st.caption(f"내 고유 ID: ...{st.session_state.user_id[-6:]}") 

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
    sender_id = data.get("user_id", "") # 작성자의 고유 ID
    
    # 1. 고유 ID로 '나'와 '남'을 구분 (이름이 같아도 ID 다르면 남)
    if sender_id == st.session_state.user_id:
        # ✅ 나 (오른쪽)
        with st.chat_message("user"):
            st.write(message_text)
    else:
        # 🔴 남 (왼쪽)
        
        # [핵심 수정] 아이콘을 만들 때 '이름'이 아니라 'ID'를 넣습니다!
        # 이제 이름이 똑같은 '익명'이라도 ID가 다르면 서로 다른 얼굴이 나옵니다.
        
        # ID가 없으면(옛날 글) 이름 사용, 있으면 ID 사용
        seed_value = sender_id if sender_id else sender_name
        
        # 스타일을 'adventurer'(캐릭터)로 변경 -> 구분이 더 확실함
        icon_url = f"https://api.dicebear.com/9.x/adventurer/svg?seed={seed_value}"
        
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
        "user_id": st.session_state.user_id, # 내 ID 포함 전송
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    st.rerun()
