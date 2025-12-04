import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import time
import hashlib
import base64
import re
from datetime import datetime, timedelta, timezone

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
    # 관리자일 경우 특별한 아이콘 리턴
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
# [A] 로그인 화면 (일반 / 관리자 분기점)
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
                # [관리자 로그인 로직]
                # 아이디가 'admin'이면 DB 안 보고 Secrets의 비번과 대조
                if login_id == "admin":
                    if "admin_password" in st.secrets and login_pw == st.secrets["admin_password"]:
                        st.session_state.logged_in = True
                        st.session_state.user_id = "ADMIN_ACCOUNT"
                        st.session_state.user_nickname = "관리자"
                        st.session_state.is_super_admin = True # 관리자 플래그 ON
                        st.success("관리자 모드로 접속합니다.")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("관리자 비밀번호가 틀렸습니다.")
                
                # [일반 유저 로그인 로직]
                else:
                    doc = users_ref.document(login_id).get()
                    if doc.exists and doc.to_dict()['password'] == hash_password(login_pw):
                        users_ref.document(login_id).update({"last_login": firestore.SERVER_TIMESTAMP})
                        clean_inactive_users()
                        st.session_state.logged_in = True
                        st.session_state.user_id = login_id
                        st.session_state.user_nickname = doc.to_dict()['nickname']
                        st.session_state.is_super_admin = False # 일반 유저
                        st.rerun()
                    else: st.error("정보가 틀립니다.")

    with tab2:
        st.subheader("회원가입")
        new_id = st.text_input("아이디", key="new_id")
        new_pw = st.text_input("비밀번호 (영문+숫자 4자 이상)", type="password", key="new_pw")
        new_nick = st.text_input("닉네임", key="new_nick")
        if st.button("회원가입"):
            # admin 아이디는 생성 불가
            if new_id.lower() == "admin":
                st.error("이 아이디는 사용할 수 없습니다.")
            elif len(new_pw) < 4 or not (re.search("[a-zA-Z]", new_pw) and re.search("[0-9]", new_pw)):
                st.error("비밀번호 조건을 확인해주세요.")
            elif users_ref.document(new_id).get().exists:
                st.error("이미 있는 아이디입니다.")
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
    # [B-1] 관리자 전용 화면 (Super Admin)
    # ----------------------------------------------------
    if st.session_state.is_super_admin:
        st.sidebar.header("🛡️ 관리자 메뉴")
        st.sidebar.info("현재 'admin' 계정으로 접속 중입니다.")
        
        if st.sidebar.button("🚪 관리자 로그아웃"):
            st.session_state.logged_in = False
            st.session_state.is_super_admin = False
            st.rerun()

        st.title("관리자 통제 센터")
        
        # 탭 구성: 대시보드(통계) / 회원관리 / 채팅모니터링(공지)
        admin_tab1, admin_tab2, admin_tab3 = st.tabs(["📊 현황 통계", "👥 회원 관리", "📢 모니터링 & 공지"])
        
        # --- 1. 통계 탭 ---
        with admin_tab1:
            all_users = list(users_ref.stream())
            all_chats = list(chat_ref.stream())
            
            col1, col2 = st.columns(2)
            col1.metric("총 회원 수", f"{len(all_users)}명")
            col2.metric("누적 메시지 수", f"{len(all_chats)}개")
            
            st.divider()
            st.write("💡 **시스템 상태:** 정상 가동 중")
            st.caption(f"최대 메시지 저장 제한: {MAX_CHAT_MESSAGES}개")
            st.caption(f"미접속 삭제 기준: {INACTIVE_DAYS_LIMIT}일")

        # --- 2. 회원 관리 탭 ---
        with admin_tab2:
            st.subheader("회원 목록")
            if not all_users:
                st.info("가입된 회원이 없습니다.")
            else:
                # 헤더
                c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
                c1.markdown("**ID**")
                c2.markdown("**닉네임**")
                c3.markdown("**마지막 접속**")
                c4.markdown("**추방**")
                st.divider()
                
                for user in all_users:
                    u_data = user.to_dict()
                    u_id = user.id
                    u_nick = u_data.get("nickname", "-")
                    u_last = u_data.get("last_login")
                    
                    cc1, cc2, cc3, cc4 = st.columns([2, 2, 3, 1])
                    cc1.text(u_id)
                    cc2.text(u_nick)
                    cc3.text(format_time_kst(u_last))
                    
                    if cc4.button("삭제", key=f"ban_{u_id}", type="primary"):
                        users_ref.document(u_id).delete()
                        st.toast(f"사용자 {u_id}를 삭제했습니다.")
                        time.sleep(1)
                        st.rerun()
            
            st.divider()
            if st.button("전체 회원 초기화 (복구 불가)"):
                for u in all_users: u.reference.delete()
                st.success("모든 회원이 삭제되었습니다.")
                st.rerun()

        # --- 3. 모니터링 & 공지 탭 ---
        with admin_tab3:
            st.subheader("💬 실시간 모니터링")
            
            # 채팅 기록 초기화 버튼
            if st.button("🗑️ 채팅방 청소 (기록 삭제)"):
                docs = chat_ref.stream()
                for doc in docs: doc.reference.delete()
                st.success("채팅방이 깨끗해졌습니다.")
                st.rerun()

            st.divider()
            
            # 채팅 내역 보여주기 (읽기 전용 느낌)
            chat_container = st.container(height=400)
            docs = chat_ref.order_by("timestamp").stream()
            with chat_container:
                for doc in docs:
                    data = doc.to_dict()
                    name = data.get("name")
                    msg = data.get("message")
                    time_str = format_time_kst(data.get("timestamp"))
                    st.text(f"[{time_str}] {name}: {msg}")

            st.divider()
            
            # [특별 기능] 공지사항 보내기
            st.subheader("📢 전체 공지 보내기")
            notice_msg = st.text_input("공지할 내용을 입력하세요", placeholder="예: 서버 점검 예정입니다.")
            
            if st.button("공지 전송"):
                if notice_msg:
                    chat_ref.add({
                        "user_id": "ADMIN_ACCOUNT", # 특수 ID
                        "name": "📢 관리자",       # 특수 이름
                        "message": notice_msg,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    maintain_chat_history()
                    st.success("공지가 전송되었습니다!")
                    st.rerun()

    # ----------------------------------------------------
    # [B-2] 일반 사용자 화면
    # ----------------------------------------------------
    else:
        # 사이드바 (일반 유저용)
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
        col1, col2 = st.columns([3, 1])
        with col1: st.title("💬 정동고 익명 채팅방")
        with col2: 
            if st.button("🔄 채팅 새로고침"): st.rerun()
        
        docs = chat_ref.order_by("timestamp").stream()
        chat_exists = False
        
        for doc in docs:
            chat_exists = True
            data = doc.to_dict()
            msg_id = data.get("user_id")
            msg_name = data.get("name")
            msg_text = data.get("message")
            msg_time = format_time_kst(data.get("timestamp"))
            
            text_html = f"""{msg_text}<div style='display:block;text-align:right;font-size:0.7em;color:grey;'>{msg_time}</div>"""
            
            # [관리자 공지사항 특별 처리]
            if msg_id == "ADMIN_ACCOUNT":
                # 빨간색 경고창 스타일로 표시
                with st.chat_message("admin", avatar="📢"):
                    st.error(f"**[공지] {msg_text}**") 
                    # error 박스를 쓰면 빨간색으로 강조됨
            
            # 내 메시지
            elif msg_id == st.session_state.user_id:
                with st.chat_message("user"): st.markdown(text_html, unsafe_allow_html=True)
            
            # 남 메시지
            else:
                with st.chat_message(msg_name, avatar=get_custom_avatar(msg_id)):
                    st.markdown(f"**{msg_name}**")
                    st.markdown(text_html, unsafe_allow_html=True)
                    
        if not chat_exists: st.info("대화가 없습니다.")
            
        if prompt := st.chat_input("메시지 입력..."):
            chat_ref.add({
                "user_id": st.session_state.user_id,
                "name": st.session_state.user_nickname,
                "message": prompt,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            maintain_chat_history()
            st.rerun()
