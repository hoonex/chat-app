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

# --- 2. 아바타 생성 함수 (외부 사이트 안 씀!) ---
def get_custom_avatar(user_id):
    """
    User ID를 넣으면 그 ID에 맞는 고유한 배경색을 가진 
    '👤' 아이콘 이미지 주소(Data URL)를 만들어줍니다.
    """
    # 1. ID를 해시(암호화)해서 고유한 6자리 색상코드(Hex) 추출
    hash_object = hashlib.md5(user_id.encode())
    hex_dig = hash_object.hexdigest()
    color_hex = hex_dig[:6] # 앞에서 6자리만 따서 색상으로 씀

    # 2. SVG 이미지 코드 생성 (배경색 + 👤 이모지)
    # rx="50"은 둥근 원을 의미합니다.
    svg_code = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
      <rect width="100" height="100" rx="50" fill="#{color_hex}" />
      <text x="50%" y="55%" dominant-baseline="central" text-anchor="middle" font-size="60" fill="white">👤</text>
    </svg>
    """
    
    # 3. 브라우저가 읽을 수 있게 Base64로 인코딩
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
    
    # ID 생성 및 관리
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    
    # ID 복구 기능
    input_id = st.text_input("고유 ID (복구용)", value=st.session_state.user_id)
    
    if st.button("🆔 이 ID로 로그인"):
        st.session_state.user_id = input_id.strip()
        
        # 닉네임 불러오기
        recent_msg = chat_ref.where("user_id", "==", st.session_state.user_id)\
                             .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                             .limit(1).stream()
        
        found_name = None
        for doc in recent_msg:
            found_name = doc.to_dict().get("name")
            
        if found_name:
            st.session_state.user_nickname = found_name
            st.success(f"'{found_name}'님 환영합니다!")
            time.sleep(1)
            st.rerun()
        else:
            st.warning("새로운 ID입니다.")

    st.divider()

    # 닉네임 설정
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
    
    # 관리자 메뉴
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

docs = chat_ref.order_by("timestamp").stream()
chat_exists = False

for doc in docs:
    chat_exists = True
    data = doc.to_dict()
    
    sender_name = str(data.get("name", "알 수 없음"))
    message_text = data.get("message", "")
    sender_id = data.get("user_id", "")
    
    # 1. 내 글 (오른쪽)
    if sender_id == st.session_state.user_id:
        with st.chat_message("user"):
            st.write(message_text)
            
    # 2. 남의 글 (왼쪽)
    else:
        # [핵심] 우리가 만든 함수로 아바타 이미지 생성
        # sender_id가 있으면 그걸로 색깔 만듦. 없으면(옛날글) 이름으로 만듦.
        seed = sender_id if sender_id else sender_name
        
        # 여기서 '👤 + 랜덤 배경색' 이미지가 만들어짐
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
