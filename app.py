import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# 1. Firebase 연결 (Streamlit 비밀공간에서 키를 가져옴)
if not firebase_admin._apps:
    # st.secrets에 저장된 키 정보를 딕셔너리로 가져옴
    cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

st.title("🔥 내 첫 채팅앱")

# 2. 메시지 전송 기능
if prompt := st.chat_input("메시지 입력"):
    doc_ref = db.collection("chats").document()
    doc_ref.set({
        "message": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

# 3. 메시지 화면에 보여주기
docs = db.collection("chats").order_by("timestamp").stream()

for doc in docs:
    data = doc.to_dict()
    with st.chat_message("user"):
        st.write(data["message"])

if st.button("새로고침"):
    st.rerun()