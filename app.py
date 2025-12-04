import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="실시간 채팅", page_icon="💬", layout="wide")

# --- 2. 설정값 ---
MAX_CHAT_MESSAGES = 50
INACTIVE_DAYS_LIMIT = 90
KST = timezone(timedelta(hours=9))

# --- 3. 유틸리티 함수들 ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_custom_avatar(user_id):
    if user_id == "ADMIN_ACCOUNT":
        return "📢"
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

def maintain_chat_history():
    docs = chat_ref.order_by("timestamp").stream()
    doc_list = list(docs)
    if len(doc_list) > MAX_CHAT_MESSAGES:
        delete_count = len(doc_list) - MAX_CHAT_MESSAGES
        for i in range(delete_count):
            doc_list[i].reference.delete()

def clean_inactive_users():
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=INACTIVE_DAYS_LIMIT)
        old_users = users_ref.where("last_login", "<", cutoff_date).stream()
        for user in old_users: user.reference.delete()
    except: pass

def format_time_kst(timestamp):
    if not timestamp: return "-"
    dt_kst = timestamp.astimezone(KST)
    return dt_kst.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후")

# --- 4. Firebase 연결 ---
if not firebase_admin._apps:
    try:
        cred_info = dict(st.secrets["firebase_key"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🔥 Firebase 연결 실패: {e}")
        st.stop()

db = firestore.client()
users_ref = db.collection("users")
chat_ref = db.collection("global_chat")

# --- 5. 세션 초기화 ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "user_nickname" not in st.session_state: st.session_state.user_nickname = ""
if "is_super_admin" not in st.session_state: st.session_state.is_super_admin = False


# ==========================================
# [A] 로그인 화면
# ==========================================
if not st.session_state.logged_in:
    st.title("정동고 익명 채팅방 입장하기")
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    
    with tab1:
        st.subheader("로그인")
        login_id = st.text_input("아이디", key="login_id")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인 하기"):
            if not login_id or not login_pw:
                st.warning("입력해주세요.")
            else:
                if login_id == "admin":
                    if "admin_password" in st.secrets and login_pw == st.secrets["admin_password"]:
                        st.session_state.logged_in = True
                        st.session_state.user_id = "ADMIN_ACCOUNT"
                        st.session_state.user_nickname = "관리자"
                        st.session_state.is_super_admin = True
                        st.success("관리자 모드로 접속합니다.")
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error("관리자 비밀번호가 틀렸습니다.")
                else:
                    doc = users_ref.document(login_id).get()
                    if doc.exists and doc.to_dict()['password'] == hash_password(login_pw):
                        users_ref.document(login_id).update({"last_login": firestore.SERVER_TIMESTAMP})
                        clean_inactive_users()
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_id
                        st.session_state.user_nickname = doc.to_dict()['nickname']
                        st.session_state.is_super_admin = False
                        st.rerun()
                    else: st.error("정보가 틀립니다.")

    with tab2:
        st.subheader("회원가입")
        new_id = st.text_input("아이디", key="new_id")
        new_pw = st.text_input("비밀번호 (영문+숫자 4자 이상)", type="password", key="new_pw")
        new_nick = st.text_input("닉네임", key="new_nick")
        if st.button("회원가입"):
            if new_id.lower() == "admin": st.error("이 아이디는 사용할 수 없습니다.")
            elif len(new_pw) < 4 or not (re.search("[a-zA-Z]", new_pw) and re.search("[0-9]", new_pw)):
                st.error("비밀번호 조건을 확인해주세요.")
            elif users_ref.document(new_id).get().exists: st.error("이미 있는 아이디입니다.")
            else:
                users_ref.document(new_id).set({
                    "password": hash_password(new_pw),
                    "nickname": new_nick,
                    "last_login": firestore.SERVER_TIMESTAMP
                })
                st.success("가입 완료! 로그인해주세요.")

# ==========================================
# [B] 로그인 성공 후
# ==========================================
else:
    # ----------------------------------------------------
    # [B-1] 관리자 전용 화면
    # ----------------------------------------------------
    if st.session_state.is_super_admin:
        st.markdown("""
            <style>
            [data-testid="stAppViewContainer"] { background-color: #FFF9C4; }
            [data-testid="stHeader"] { background-color: #FFF9C4; }
            [data-testid="stSidebar"] { background-color: #FFF59D; }
            </style>
            """, unsafe_allow_html=True)

        st.sidebar.header("🛡️ 관리자 메뉴")
        if st.sidebar.button("🚪 관리자 로그아웃"):
            st.session_state.logged_in = False
            st.session_state.is_super_admin = False
            st.rerun()

        st.title("🛡️ 관리자 통제 센터")
        
        admin_tab1, admin_tab2, admin_tab3 = st.tabs(["📊 통계", "👥 회원 관리", "📢 모니터링"])
        
        with admin_tab1:
            all_users = list(users_ref.stream())
            all_chats = list(chat_ref.stream())
            c1, c2 = st.columns(2)
            c1.metric("총 회원", f"{len(all_users)}명")
            c2.metric("총 메시지", f"{len(all_chats)}개")

        with admin_tab2:
            st.subheader("회원 목록")
            if all_users:
                c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 2, 1.5, 1])
                c1.markdown("**ID**")
                c2.markdown("**닉네임**")
                c3.markdown("**닉네임 변경**")
                c4.markdown("**적용**")
                c5.markdown("**삭제**")
                st.divider()
                for user in all_users:
                    u_data = user.to_dict()
                    u_id = user.id
                    u_nick = u_data.get("nickname", "-")
                    cc1, cc2, cc3, cc4, cc5 = st.columns([1.5, 1.5, 2, 1.5, 1])
                    cc1.text(u_id)
                    cc2.text(u_nick)
                    new_nick_val = cc3.text_input("label", key=f"input_{u_id}", label_visibility="collapsed", placeholder="새 닉네임")
                    
                    if cc4.button("변경", key=f"change_{u_id}"):
                        if new_nick_val:
                            users_ref.document(u_id).update({"nickname": new_nick_val})
                            user_msgs = chat_ref.where("user_id", "==", u_id).stream()
                            for msg in user_msgs: msg.reference.update({"name": new_nick_val})
                            st.toast(f"변경 완료")
                            time.sleep(1)
                            st.rerun()
                    
                    if cc5.button("삭제", key=f"ban_{u_id}", type="primary"):
                        users_ref.document(u_id).delete()
                        st.toast("삭제 완료")
                        time.sleep(1)
                        st.rerun()

        with admin_tab3:
            st.subheader("실시간 모니터링")
            docs = chat_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
            for doc in docs:
                data = doc.to_dict()
                doc_id = doc.id
                name = data.get("name")
                msg = data.get("message")
                is_deleted = data.get("is_deleted", False)
                with st.container(border=True):
                    mc1, mc2 = st.columns([8, 2])
                    with mc1:
                        if is_deleted: st.caption(f"🚫 {msg} (ID: {name})")
                        else: st.write(f"**{name}**: {msg}")
                    with mc2:
                        if not is_deleted:
                            if st.button("삭제", key=f"adm_del_{doc_id}", type="primary"):
                                chat_ref.document(doc_id).update({
                                    "message": "🚫 관리자에 의해 삭제된 글입니다.",
                                    "is_deleted": True
                                })
                                st.rerun()
            st.divider()
            notice_msg = st.text_input("공지 내용")
            if st.button("공지 전송"):
                if notice_msg:
                    chat_ref.add({
                        "user_id": "ADMIN_ACCOUNT",
                        "name": "📢 관리자",
                        "message": notice_msg,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "is_deleted": False
                    })
                    maintain_chat_history()
                    st.rerun()

    # ----------------------------------------------------
    # [B-2] 일반 사용자 화면
    # ----------------------------------------------------
    else:
        # [수정] 버튼 위치를 오른쪽 상단으로 변경 & 크기 고정
        components.html("""
            <script>
                function fixButtonPosition() {
                    const buttons = window.parent.document.querySelectorAll('button');
                    buttons.forEach(btn => {
                        if (btn.innerText.includes('🔄 채팅 새로고침')) {
                            // 1. 강제 고정
                            btn.style.position = 'fixed';
                            
                            // 2. 위치: 오른쪽 위 (헤더 바로 아래)
                            btn.style.top = '70px'; 
                            btn.style.right = '20px';
                            btn.style.bottom = 'auto'; // 하단 위치 해제
                            btn.style.left = 'auto';   // 왼쪽 위치 해제
                            
                            // 3. 스타일: 작고 예쁘게
                            btn.style.width = 'auto';  // [중요] 길게 늘어나는 것 방지!
                            btn.style.minWidth = '0px'; // 최소 너비 해제
                            btn.style.zIndex = '999999';
                            btn.style.backgroundColor = 'white';
                            btn.style.color = '#FF4B4B';
                            btn.style.border = '1px solid #FF4B4B';
                            btn.style.borderRadius = '15px';
                            btn.style.fontWeight = 'bold';
                            btn.style.padding = '5px 12px'; // 안쪽 여백 줄임 (버튼 작게)
                            btn.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)';
                        }
                    });
                }
                // 지속적으로 위치 고정
                setInterval(fixButtonPosition, 500);
            </script>
        """, height=0, width=0)
        
        if st.button("🔄 채팅 새로고침"):
            st.rerun()

        # 사이드바
        with st.sidebar:
            st.header(f"👤 {st.session_state.user_nickname}님")
            with st.expander("닉네임 변경"):
                change_nick = st.text_input("새 닉네임", value=st.session_state.user_nickname)
                if st.button("저장"):
                    if change_nick != st.session_state.user_nickname:
                        clean_nick = change_nick.strip()
                        if clean_nick:
                            users_ref.document(st.session_state.user_id).update({"nickname": clean_nick})
                            my_msgs = chat_ref.where("user_id", "==", st.session_state.user_id).stream()
                            for msg in my_msgs: msg.reference.update({"name": clean_nick})
                            st.session_state.user_nickname = clean_nick
                            st.rerun()
            if st.button("🚪 로그아웃"):
                st.session_state.logged_in = False
                st.rerun()
            st.divider()
            st.caption("문의사항은 관리자에게 연락.")

        # 메인 채팅창
        st.title("💬 정동고 익명 채팅방")
        
        docs = chat_ref.order_by("timestamp").stream()
        chat_exists = False
        
        for doc in docs:
            chat_exists = True
            data = doc.to_dict()
            doc_id = doc.id
            msg_id = data.get("user_id")
            msg_name = data.get("name")
            msg_text = data.get("message")
            msg_time = format_time_kst(data.get("timestamp"))
            is_deleted = data.get("is_deleted", False)
            
            # 1. 관리자 공지
            if msg_id == "ADMIN_ACCOUNT":
                with st.chat_message("admin", avatar="📢"):
                    st.error(f"**[공지] {msg_text}**") 
            
            # 2. 내 메시지
            elif msg_id == st.session_state.user_id:
                with st.chat_message("user"):
                    col_msg, col_del = st.columns([9, 1])
                    with col_msg:
                        if is_deleted:
                            st.markdown(f"<div style='color:#999; font-style:italic;'>{msg_text}</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"{msg_text}")
                        st.caption(f"{msg_time}")
                    with col_del:
                        if not is_deleted:
                            if st.button("🗑️", key=f"my_del_{doc_id}", help="이 글 삭제"):
                                chat_ref.document(doc_id).update({
                                    "message": f"🗑️ {st.session_state.user_nickname}님이 삭제한 글입니다.",
                                    "is_deleted": True
                                })
                                st.rerun()

            # 3. 남 메시지
            else:
                with st.chat_message(msg_name, avatar=get_custom_avatar(msg_id)):
                    if is_deleted:
                        st.markdown(f"<div style='color:#999; font-style:italic;'>{msg_text}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"**{msg_name}**")
                        st.markdown(f"{msg_text}")
                    st.caption(f"{msg_time}")

        if not chat_exists: st.info("대화가 없습니다.")
            
        # 메시지 입력창
        if prompt := st.chat_input("메시지 입력..."):
            chat_ref.add({
                "user_id": st.session_state.user_id,
                "name": st.session_state.user_nickname,
                "message": prompt,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "is_deleted": False
            })
            maintain_chat_history()
            st.rerun()
