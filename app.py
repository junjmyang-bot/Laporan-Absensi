from pathlib import Path
import os
from datetime import datetime, date

import pytz
import streamlit as st
from dotenv import load_dotenv

import gspread
from google.oauth2.service_account import Credentials

import requests


# =========================
# 0) "이 파일이 있는 폴더"를 기준으로 모든 경로 고정
# =========================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CREDS_PATH = BASE_DIR / "credentials.json"

# .env를 "현재 작업폴더"가 아니라, "이 app.py 폴더"에서 무조건 읽게 함
load_dotenv(dotenv_path=ENV_PATH)


# =========================
# 1) 환경변수 읽기
# =========================
TZ = os.getenv("TZ", "Asia/Jakarta")

# Google Sheet (백업)
SHEET_NAME = os.getenv("GSHEET_NAME", "ABSENSI_REPORT")
TAB_NAME = os.getenv("GSHEET_TAB", "DATA")

# Telegram (메인)
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")


# =========================
# 2) Google Sheet 연결
# =========================
def get_ws():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet(TAB_NAME)
    return ws


# =========================
# 3) Telegram 전송
# =========================
def send_telegram(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False, "❌ .env에 TG_BOT_TOKEN 또는 TG_CHAT_ID가 비어있음"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text}, timeout=20)
        if r.status_code == 200:
            return True, "✅ 텔레그램 전송 성공"
        return False, f"❌ 텔레그램 전송 실패: {r.status_code} / {r.text}"
    except Exception as e:
        return False, f"❌ 텔레그램 전송 예외: {type(e).__name__}: {e}"


# =========================
# 4) UI
# =========================
st.set_page_config(page_title="Laporan Absensi", layout="centered")
st.title("📋 Laporan Absensi")

# ★ 이 표시가 보이면 "텔레그램 버전 app.py"가 실제로 실행 중이라는 뜻
st.warning("✅ TELEGRAM VERSION RUNNING (이 문구가 안 보이면 다른 파일이 실행 중!)")

# 사이드바에 현재 설정 상태를 보여줌(토큰은 전부 노출하지 않음)
with st.sidebar:
    st.header("⚙️ 현재 설정 상태")
    st.write("📁 실행 폴더:", str(BASE_DIR))
    st.write("📄 .env 존재:", ENV_PATH.exists())
    st.write("🔐 credentials.json 존재:", CREDS_PATH.exists())
    st.write("🧾 GSHEET_NAME:", SHEET_NAME)
    st.write("📑 GSHEET_TAB:", TAB_NAME)
    st.write("🤖 TG_CHAT_ID:", TG_CHAT_ID if TG_CHAT_ID else "(비어있음)")
    st.write("🤖 TG_BOT_TOKEN:", ("(있음)" if TG_BOT_TOKEN else "(비어있음)"))

    # 텔레그램 테스트 버튼 (폼 안 누르고도 바로 테스트 가능)
    if st.button("🧪 텔레그램 테스트 보내기"):
        ok, info = send_telegram("✅ TEST: Telegram 연결 테스트 메시지")
        (st.success(info) if ok else st.error(info))


with st.form("absensi_form"):
    col1, col2 = st.columns(2)
    with col1:
        tgl = st.date_input("Tanggal", value=date.today())
    with col2:
        shift = st.selectbox("Shift", ["Shift 1", "Shift 2", "Shift 3"])

    dept = st.selectbox(
        "Departemen",
        ["Steam", "Kupas", "Dry", "Packing", "Gudang", "Washing", "QC", "Maintenance", "Security"],
    )
    reporter = st.text_input("Nama Pelapor (TL/AS/MP)")

    st.write("### Data Karyawan")
    names_text = st.text_area("Daftar Nama (1 baris 1 nama)", height=140)

    status = st.selectbox("Status default", ["Hadir", "Sakit", "Izin", "Alfa", "Libur"])
    note = st.text_input("Catatan (opsional)")

    submitted = st.form_submit_button("✅ Kirim ke Telegram (Backup ke Google Sheet)")


# =========================
# 5) Submit 처리
# =========================
if submitted:
    # 1) 입력 검증
    if not reporter.strip():
        st.error("Nama pelapor wajib diisi.")
        st.stop()

    names = [n.strip() for n in names_text.splitlines() if n.strip()]
    if not names:
        st.error("Daftar nama wajib diisi (minimal 1 nama).")
        st.stop()

    # 2) 시간
    tz = pytz.timezone(TZ)
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    # 3) Telegram 메시지 만들기
    msg = (
        f"📋 ABSENSI\n"
        f"Tanggal: {tgl}\n"
        f"Shift: {shift}\n"
        f"Dept: {dept}\n"
        f"Pelapor: {reporter}\n"
        f"Status: {status}\n"
        f"Nama ({len(names)}): {', '.join(names)}\n"
    )
    if note.strip():
        msg += f"Catatan: {note.strip()}\n"
    msg += f"Waktu: {now}"

    # 4) Telegram 전송(메인)
    ok_tg, info_tg = send_telegram(msg)
    (st.success(info_tg) if ok_tg else st.error(info_tg))

    # 5) Google Sheet 백업(실패해도 OK)
    try:
        if not CREDS_PATH.exists():
            st.warning("Google Sheet 백업 스킵: credentials.json 없음")
        else:
            rows = [[str(tgl), shift, dept, n, status, note, reporter, now] for n in names]
            ws = get_ws()
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            st.info("✅ Google Sheet 백업 저장 완료")
    except Exception as e:
        st.warning(f"⚠️ Google Sheet 백업 실패: {type(e).__name__}: {e}")