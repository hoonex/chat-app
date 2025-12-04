import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
import urllib.parse

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

# --- 3. 사이드바 (내 정보 설정) ---
with st.sidebar:
    st.header("👤 내 정보")
    
    # [핵심 수정 1] Streamlit 자체 'key' 기능을 사용하여 입력 즉시 동기화
    # 사용자가 입력하자마자 'st.session_state.user_nickname'에 저장됩니다.
    if "user_nickname" not in st.session_state:
        st.session_state.user_nickname = "익명"

    # text_input이 변하면 자동으로 세션값이 바뀝니다.
    st.text_input("닉네임", key="user_nickname")
    
    # 비교를 위해 확실하게 공백을 제거한 '내 이름' 변수를 만듭니다.
    MY_NAME = st.session_state.user_nickname.strip()
    
    # 이름이 비어있으면 '익명'으로 처리
    if not MY_NAME:
        MY_NAME = "익명"

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

# --- 4. 메인 채팅 화면 ---
st.title("💬 정동고 익명 채팅방")

# DB에서 메시지 가져오기
docs = chat_ref.order_by("timestamp").stream()

# 메시지가 없는 경우 처리
chat_exists = False

for doc in docs:
    chat_exists = True
    data = doc.to_dict()
    
    # DB에 저장된 이름 (문자열로 변환 후 공백 제거)
    sender_name = str(data.get("name", "알 수 없음")).strip()
    message_text = data.get("message", "")
    
    # [핵심 수정 2] 여기서 MY_NAME(내 현재 닉네임)과 DB 이름(sender_name)을 비교
    # 둘 다 공백을 제거했으므로 글자만 같으면 무조건 True가 나옵니다.
    if sender_name == MY_NAME:
        # ✅ 나 (오른쪽, 기본 아이콘)
        with st.chat_message("user"):
            st.write(message_text)
    else:
        # 🔴 남 (왼쪽, DiceBear 아이콘)
        safe_name = urllib.parse.quote(sender_name)
        icon_url = f"https://api.dicebear.com/9.x/initials/svg?seed={safe_name}"
        
        with st.chat_message(sender_name, avatar=icon_url):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if not chat_exists:
    st.info("첫 메시지를 남겨보세요!")

# --- 5. 메시지 전송 ---
if prompt := st.chat_input("메시지 입력..."):
    # [핵심 수정 3] 보낼 때도 위에서 확정한 'MY_NAME'을 그대로 사용
    chat_ref.add({
        "name": MY_NAME,
        "message": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    # 전송 후 즉시 화면 다시 그리기
    st.rerun()
