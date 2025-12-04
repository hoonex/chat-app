import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
import urllib.parse
import uuid

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

# --- 3. 사이드바 (로그인 및 설정) ---
with st.sidebar:
    st.header("👤 계정 설정")
    
    # 1. 고유 ID 관리 (랜덤 생성 or 직접 입력)
    # 세션에 ID가 없으면 새로 만듭니다.
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    
    # [핵심 기능] ID 입력창 (기본값은 현재 ID)
    # 사용자가 예전 ID를 여기에 붙여넣을 수 있습니다.
    input_id = st.text_input("고유 ID (복구용)", value=st.session_state.user_id)
    
    # [핵심 기능] ID 변경 및 닉네임 복구 버튼
    if st.button("🆔 이 ID로 로그인 (닉네임 복구)"):
        st.session_state.user_id = input_id.strip() # 입력한 ID를 내 ID로 확정
        
        # DB에서 이 ID로 쓴 가장 최근 메시지를 찾습니다.
        recent_msg = chat_ref.where("user_id", "==", st.session_state.user_id)\
                             .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                             .limit(1).stream()
        
        found_name = None
        for doc in recent_msg:
            found_name = doc.to_dict().get("name")
            
        if found_name:
            st.session_state.user_nickname = found_name
            st.success(f"환영합니다! '{found_name}'님으로 복구되었습니다.")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("이 ID로 작성된 대화 기록이 없습니다. (새 계정)")

    st.divider()

    # 2. 닉네임 설정
    if "user_nickname" not in st.session_state:
        st.session_state.user_nickname = "익명"

    # 복구된 닉네임이 있으면 그게 뜨고, 아니면 입력 가능
    new_nickname = st.text_input("닉네임", value=st.session_state.user_nickname)
    if new_nickname != st.session_state.user_nickname:
        st.session_state.user_nickname = new_nickname
        st.rerun() # 닉네임 바꾸면 즉시 반영

    MY_NAME = st.session_state.user_nickname.strip()
    if not MY_NAME:
        MY_NAME = "익명"
    
    st.info(f"현재 접속 ID: ...{st.session_state.user_id[-6:]}")

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
chat_exists = False

for doc in docs:
    chat_exists = True
    data = doc.to_dict()
    
    sender_name = str(data.get("name", "알 수 없음"))
    message_text = data.get("message", "")
    sender_id = data.get("user_id", "")
    
    # 1. 고유 ID로 나/남 구분
    if sender_id == st.session_state.user_id:
        # ✅ 나 (오른쪽)
        with st.chat_message("user"):
            st.write(message_text)
    else:
        # 🔴 남 (왼쪽)
        
        # [수정 요청] 다시 '글자(initials)' 아이콘으로 변경
        # 하지만 seed에 'ID'를 넣어서 색깔은 사람마다 고유하게 유지
        seed_value = sender_id if sender_id else sender_name
        
        # initials 스타일 사용
        icon_url = f"https://api.dicebear.com/9.x/initials/svg?seed={seed_value}"
        
        with st.chat_message(sender_name, avatar=icon_url):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if not chat_exists:
    st.info("첫 메시지를 남겨보세요!")

# --- 5. 메시지 전송 ---
if prompt := st.chat_input("메시지 입력..."):
    chat_ref.add({
        "name": MY_NAME,
        "message": prompt,
        "user_id": st.session_state.user_id, # 내 ID 저장
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    st.rerun()
