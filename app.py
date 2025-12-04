import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
import uuid
import hashlib
import base64

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬")

# --- 2. 아바타 생성 함수 ---
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
chat_ref = db.collection("global_chat")

# --- 4. 사이드바 (계정 설정) ---
with st.sidebar:
    st.header("👤 계정 설정")
    
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    
    input_id = st.text_input("고유 ID (복구용)", value=st.session_state.user_id)
    
    # [수정된 부분] 에러가 나던 로그인 버튼 로직을 안전하게 변경
    if st.button("🆔 이 ID로 로그인"):
        st.session_state.user_id = input_id.strip()
        
        # [해결책] DB에서는 order_by를 뺍니다. (인덱스 에러 방지)
        # 그냥 해당 ID로 쓴 글을 다 가져온 뒤, 파이썬에서 최신순을 찾습니다.
        docs = chat_ref.where("user_id", "==", st.session_state.user_id).stream()
        
        found_name = None
        latest_time = None

        # 파이썬 반복문으로 가장 최신 글의 닉네임을 찾음
        for doc in docs:
            data = doc.to_dict()
            msg_time = data.get("timestamp")
            
            # 시간이 없거나(None), 더 최신이면 갱신
            if latest_time is None or (msg_time and msg_time > latest_time):
                latest_time = msg_time
                found_name = data.get("name")
            
        if found_name:
            st.session_state.user_nickname = found_name
            st.success(f"'{found_name}'님 환영합니다!")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("이 ID로 작성된 대화가 없거나 찾을 수 없습니다.")

    st.divider()

    if "user_nickname" not in st.session_state:
        st.session_state.user_nickname = "익명"

    new_nickname = st.text_input("닉네임", value=st.session_state.user_nickname)
    if new_nickname != st.session_state.user_nickname:
        st.session_state.user_nickname = new_nickname
        st.rerun()

    MY_NAME = st.session_state.user_nickname.strip()
    if not MY_NAME:
        MY_NAME = "익명"
    
    st.caption(f"ID: ...{st.session_state.user_id[-6:]}")
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

# --- 5. 메인 채팅 화면 ---
st.title("💬 정동고 익명 채팅방")

# 전체 채팅 목록은 시간순 정렬이 필요하므로 그대로 둡니다. 
# (단순 정렬만 하는 건 인덱스 없이도 잘 됩니다)
docs = chat_ref.order_by("timestamp").stream()
chat_exists = False

for doc in docs:
    chat_exists = True
    data = doc.to_dict()
    
    sender_name = str(data.get("name", "알 수 없음"))
    message_text = data.get("message", "")
    sender_id = data.get("user_id", "")
    
    if sender_id == st.session_state.user_id:
        with st.chat_message("user"):
            st.write(message_text)
    else:
        seed = sender_id if sender_id else sender_name
        custom_icon_url = get_custom_avatar(seed)
        
        with st.chat_message(sender_name, avatar=custom_icon_url):
            st.markdown(f"**{sender_name}**")
            st.write(message_text)

if not chat_exists:
    st.info("첫 메시지를 남겨보세요!")

# --- 6. 메시지 전송 ---
if prompt := st.chat_input("메시지 입력..."):
    chat_ref.add({
        "name": MY_NAME,
        "message": prompt,
        "user_id": st.session_state.user_id,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    st.rerun()
