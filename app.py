import datetime as dt
import os
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from dotenv import load_dotenv

from src.absensi_text.parser import parse_attendance_text

load_dotenv()
st.set_page_config(page_title="Laporan Absensi", layout="wide")


DEPARTMENTS = ["Steam", "Gudang", "Kupas", "Dry", "Packing", "Cuci"]
ROLE_UNIVERSE = ["TL", "AS", "AST", "AJ", "Biasa", "Training"]
ROLE_DEFAULT_ENABLED = ["TL", "AST", "Biasa", "Training"]
ROLE_KEY_MAP = {
    "TL": "TL",
    "AS": "AS",
    "AST": "AST",
    "AJ": "AJ",
    "Biasa": "BIASA",
    "Training": "TR",
}

TELAT_REASONS = ["sepeda dipakai", "sakit", "lain-lain"]
TIDAK_MASUK_REASONS = ["ijin", "sakit", "libur", "lain-lain"]
SEND_COOLDOWN_SECONDS = 60
REPORT_TIMEZONE = os.getenv("REPORT_TIMEZONE", "Asia/Jakarta")
# Runtime in-memory store: sender -> last successful send time.
# Works across sessions in the same Streamlit process.
LAST_SEND_AT_BY_SENDER: dict[str, dt.datetime] = {}


def send_telegram_message(text: str) -> tuple[bool, str]:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TG_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TG_CHAT_ID", "")

    if not bot_token or not chat_id:
        return False, "Telegram env belum lengkap. Cek TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, data=payload, timeout=20)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        if not data.get("ok"):
            return False, f"Telegram error: {str(data)[:200]}"
        return True, "Kirim ke Telegram berhasil."
    except Exception as e:
        return False, f"Gagal kirim: {type(e).__name__}: {e}"


def get_sender_cooldown_error(sender_name: str, cooldown_seconds: int = SEND_COOLDOWN_SECONDS) -> str:
    sender = (sender_name or "").strip().lower()
    if not sender:
        return "Nama pelapor wajib diisi untuk batas kirim 1 menit."

    last_sent_at = LAST_SEND_AT_BY_SENDER.get(sender)
    if not last_sent_at:
        return ""

    now = dt.datetime.now()
    elapsed = (now - last_sent_at).total_seconds()
    remain = int(cooldown_seconds - elapsed)
    if remain > 0:
        return f"Batas kirim aktif untuk '{sender_name.strip()}'. Coba lagi {remain} detik."
    return ""


def get_report_timestamp() -> str:
    try:
        now = dt.datetime.now(ZoneInfo(REPORT_TIMEZONE))
    except Exception:
        now = dt.datetime.now()
    return now.strftime("%d / %b / %Y %H:%M:%S %Z")


def _init_list_state(key: str):
    if key not in st.session_state:
        st.session_state[key] = []
    if f"{key}__counter" not in st.session_state:
        st.session_state[f"{key}__counter"] = 0


def add_row(key: str, default: dict):
    st.session_state[f"{key}__counter"] += 1
    row_id = st.session_state[f"{key}__counter"]
    st.session_state[key].append({"_id": row_id, **default})


def delete_row(key: str, row_id: int):
    st.session_state[key] = [r for r in st.session_state[key] if r.get("_id") != row_id]


def fmt_delta(base: int, breakdown: int) -> str:
    if base == breakdown:
        return "ok"
    diff = breakdown - base
    return f"lebih {diff}" if diff > 0 else f"kurang {abs(diff)}"


def _first_role(enabled_roles: list[str]) -> str:
    if enabled_roles:
        return enabled_roles[0]
    return "TL"


def _build_role_breakdown_from_state(enabled_roles: list[str]) -> dict:
    role_breakdown = {}
    for role in enabled_roles:
        key = ROLE_KEY_MAP[role]
        role_breakdown[f"{key}_total"] = int(st.session_state.get(f"f_{key.lower()}_total", 0))
        role_breakdown[f"{key}_masuk"] = int(st.session_state.get(f"f_{key.lower()}_masuk", 0))
    return role_breakdown


def validate_role_breakdown(
    base_total_kupas: int,
    base_total_tr: int,
    base_masuk_kupas: int,
    base_masuk_tr: int,
    role_breakdown: dict,
    enabled_roles: list[str],
) -> list[str]:
    errs = []

    if base_masuk_kupas > base_total_kupas:
        errs.append(f"Invalid: Masuk Kupas({base_masuk_kupas}) > Total Kupas({base_total_kupas})")
    if base_masuk_tr > base_total_tr:
        errs.append(f"Invalid: Masuk Training({base_masuk_tr}) > Total Training({base_total_tr})")

    breakdown_kupas_total = 0
    breakdown_kupas_masuk = 0
    breakdown_tr_total = 0
    breakdown_tr_masuk = 0

    for role in enabled_roles:
        key = ROLE_KEY_MAP[role]
        total = int(role_breakdown.get(f"{key}_total", 0))
        masuk = int(role_breakdown.get(f"{key}_masuk", 0))
        if masuk > total:
            errs.append(f"Invalid: {role} masuk({masuk}) > {role} total({total})")

        if role == "Training":
            breakdown_tr_total += total
            breakdown_tr_masuk += masuk
        else:
            breakdown_kupas_total += total
            breakdown_kupas_masuk += masuk

    if base_total_kupas != breakdown_kupas_total:
        errs.append(
            f"Total Kupas mismatch: Base={base_total_kupas}, Breakdown={breakdown_kupas_total} ({fmt_delta(base_total_kupas, breakdown_kupas_total)})"
        )
    if base_masuk_kupas != breakdown_kupas_masuk:
        errs.append(
            f"Masuk Kupas mismatch: Base={base_masuk_kupas}, Breakdown={breakdown_kupas_masuk} ({fmt_delta(base_masuk_kupas, breakdown_kupas_masuk)})"
        )

    if "Training" in enabled_roles:
        if base_total_tr != breakdown_tr_total:
            errs.append(
                f"Total Training mismatch: Base={base_total_tr}, Breakdown={breakdown_tr_total} ({fmt_delta(base_total_tr, breakdown_tr_total)})"
            )
        if base_masuk_tr != breakdown_tr_masuk:
            errs.append(
                f"Masuk Training mismatch: Base={base_masuk_tr}, Breakdown={breakdown_tr_masuk} ({fmt_delta(base_masuk_tr, breakdown_tr_masuk)})"
            )
    else:
        if base_total_tr != 0:
            errs.append(f"Training disabled: Total Training(BASE) harus 0, sekarang {base_total_tr}")
        if base_masuk_tr != 0:
            errs.append(f"Training disabled: Masuk Training(BASE) harus 0, sekarang {base_masuk_tr}")

    return errs


def validate_rows(section_name: str, rows: list[dict], required_fields: list[str], enabled_roles: list[str]) -> list[str]:
    errs = []
    for i, r in enumerate(rows, start=1):
        missing = [f for f in required_fields if not str(r.get(f, "")).strip()]
        if missing:
            errs.append(f"{section_name}: baris #{i} belum lengkap (wajib: {', '.join(missing)})")
            continue

        jabatan = (r.get("jabatan") or "").strip()
        if jabatan and jabatan not in enabled_roles:
            errs.append(f"{section_name}: baris #{i} jabatan '{jabatan}' tidak ada di enabled roles")
    return errs


def _detail_name(r: dict, include_eta: bool) -> str:
    nama = (r.get("nama") or "").strip()
    jabatan = (r.get("jabatan") or "").strip()
    ket = (r.get("ket") or "").strip()
    eta = (r.get("eta") or "").strip()

    parts = [nama]
    if jabatan:
        parts.append(jabatan)
    if ket:
        parts.append(ket)
    if include_eta and eta:
        parts.append(eta)
    return " - ".join([p for p in parts if p])


def aggregate_telat(telat_rows: list[dict]) -> dict:
    buckets = {k: [] for k in TELAT_REASONS}
    for r in telat_rows:
        reason = (r.get("reason") or "").strip()
        if reason not in buckets:
            reason = "lain-lain"
        buckets[reason].append(_detail_name(r, include_eta=True))

    return {
        "total": len(telat_rows),
        "sepeda": len(buckets["sepeda dipakai"]),
        "sepeda_detail": [x for x in buckets["sepeda dipakai"] if x],
        "sakit": len(buckets["sakit"]),
        "sakit_detail": [x for x in buckets["sakit"] if x],
        "lain_lain": len(buckets["lain-lain"]),
        "lain_lain_detail": [x for x in buckets["lain-lain"] if x],
    }


def aggregate_tidak_masuk(rows: list[dict]) -> dict:
    buckets = {k: [] for k in TIDAK_MASUK_REASONS}
    for r in rows:
        reason = (r.get("reason") or "").strip()
        if reason not in buckets:
            reason = "lain-lain"
        buckets[reason].append(_detail_name(r, include_eta=False))

    return {
        "total": len(rows),
        "ijin": len(buckets["ijin"]),
        "ijin_detail": [x for x in buckets["ijin"] if x],
        "sakit": len(buckets["sakit"]),
        "sakit_detail": [x for x in buckets["sakit"] if x],
        "libur": len(buckets["libur"]),
        "libur_detail": [x for x in buckets["libur"] if x],
        "lain_lain": len(buckets["lain-lain"]),
        "lain_lain_detail": [x for x in buckets["lain-lain"] if x],
    }


def _append_vertical_detail(lines: list[str], details: list[str]):
    if not details:
        return
    if len(details) == 1:
        lines.append(f"   ({details[0]})")
        return

    for idx, d in enumerate(details):
        if idx == 0:
            lines.append(f"   ({d}")
        elif idx == len(details) - 1:
            lines.append(f"   - {d})")
        else:
            lines.append(f"   - {d}")


def build_laporan_absensi_team_message(form: dict) -> str:
    role = form["role_breakdown"]
    enabled_roles = form["enabled_roles"]

    telat = form["telat"]
    tm = form["tidak_masuk"]
    tk_rows = form["tanpa_keterangan_rows"]
    resign_rows = form["resign_rows"]

    lines = []
    lines.append("A. Laporan Absensi Team")
    lines.append("-> Durasi Lapor : 1 kali (Waktu Mulai Kerja)")
    lines.append("")
    lines.append(f"Tanggal : {form['tanggal']}")
    lines.append(f"Waktu Lapor : {form['waktu_lapor']}")
    lines.append("")
    lines.append(f"0. Department : {form['department']}")
    lines.append("")
    lines.append(f"1. Nama QC / Shift : {form['qc_name']} ({form['shift']})")
    lines.append(f"-> Main TL : {form['main_tl'] if form['main_tl'] else '-'}")
    lines.append(f"-> TL lain : {form['tl_lain'] if form['tl_lain'] else '-'}")
    lines.append("")
    lines.append(f"2. Total : {form['total_kupas']} pax + {form['total_tr']} tr")
    lines.append(f"-> Masuk : {form['masuk_kupas']} pax")
    lines.append(f"-> Training : {form['masuk_tr']} tr")
    lines.append("")
    lines.append("2-1. Detail Total Pax")
    for role_name in enabled_roles:
        key = ROLE_KEY_MAP[role_name]
        lines.append(
            f"-> {role_name} : {role.get(f'{key}_masuk', 0)} (Total masuk) / {role.get(f'{key}_total', 0)} (Total Orang di team)"
        )
    lines.append("")
    lines.append(f"3. Jam Masuk : {form['jam_masuk']}")
    lines.append(f"4. Jam Pulang : {form['jam_pulang']}")
    lines.append("")

    lines.append(f"5. Telat : {telat['total']} pax")
    lines.append(f"-> Sepeda Dipakai : {telat['sepeda']} pax")
    _append_vertical_detail(lines, telat["sepeda_detail"])
    lines.append(f"-> Sakit : {telat['sakit']} pax")
    _append_vertical_detail(lines, telat["sakit_detail"])
    lines.append(f"-> Lain-lain : {telat['lain_lain']} pax")
    _append_vertical_detail(lines, telat["lain_lain_detail"])
    lines.append("")

    lines.append(f"6. Tidak Masuk : {tm['total']} pax")
    lines.append(f"-> Ijin : {tm['ijin']} pax")
    _append_vertical_detail(lines, tm["ijin_detail"])
    lines.append(f"-> Sakit : {tm['sakit']} pax")
    _append_vertical_detail(lines, tm["sakit_detail"])
    lines.append(f"-> Libur : {tm['libur']} pax")
    _append_vertical_detail(lines, tm["libur_detail"])
    lines.append(f"-> Lain-lain : {tm['lain_lain']} pax")
    _append_vertical_detail(lines, tm["lain_lain_detail"])
    lines.append("")

    lines.append(f"7. Tanpa Keterangan : {len(tk_rows)} pax")
    if tk_rows:
        details = [f"{r['nama'].strip()} - {r['jabatan']}" for r in tk_rows if r.get("nama") and r.get("jabatan")]
        _append_vertical_detail(lines, details)
    lines.append("")

    lines.append(f"8. Resign : {len(resign_rows)} pax")
    if resign_rows:
        details = [
            f"{r['nama'].strip()} - {r['jabatan']} - notif: {str(r.get('notif', 'No')).strip()}"
            for r in resign_rows
            if r.get("nama") and r.get("jabatan")
        ]
        _append_vertical_detail(lines, details)

    return "\n".join(lines)


st.title("Laporan Absensi (TL Input -> Telegram Auto Send)")
st.caption("Input dibuat cepat untuk TL, output Telegram tetap format laporan legacy.")

tab1, tab2 = st.tabs(["TL Input Form", "Paste & Parse (debug)"])

with tab1:
    _init_list_state("telat_rows")
    _init_list_state("tidak_masuk_rows")
    _init_list_state("tanpa_keterangan_rows")
    _init_list_state("resign_rows")

    top1, top2, top3, top4 = st.columns(4)
    with top1:
        tanggal = st.date_input("Tanggal", value=dt.date.today(), key="f_tanggal").strftime("%d / %b / %Y")
    with top2:
        department = st.selectbox("Department", DEPARTMENTS, key="f_department")
    with top3:
        shift = st.selectbox("Shift", ["Shift 1", "Shift 2", "Shift 3", "Shift 4", "Shift 5", "tengah"], key="f_shift")
    with top4:
        qc_name = st.text_input("Nama QC", value="", key="f_qc")

    c1, c2, c3 = st.columns(3)
    with c1:
        main_tl = st.text_input("Main TL", value="", key="f_main_tl")
    with c2:
        tl_lain = st.text_input("TL lain (comma)", value="", key="f_tl_lain")
    with c3:
        sender_name = st.text_input("Nama Pelapor", value="", key="f_sender_name")

    enabled_roles = st.multiselect(
        "Enabled Roles (untuk breakdown + pilihan jabatan input)",
        ROLE_UNIVERSE,
        default=ROLE_DEFAULT_ENABLED,
        key="f_enabled_roles",
    )
    if not enabled_roles:
        st.error("Minimal pilih 1 role agar input jabatan tidak kosong.")

    st.markdown("### 2) Total & Masuk (BASE)")
    training_enabled = "Training" in enabled_roles
    if training_enabled:
        t1, t2, t3, t4 = st.columns(4)
        with t1:
            total_kupas = int(st.number_input("Total Kupas (pax)", min_value=0, value=0, step=1, key="f_total_kupas"))
        with t2:
            total_tr = int(st.number_input("Total Training (tr)", min_value=0, value=0, step=1, key="f_total_tr"))
        with t3:
            masuk_kupas = int(st.number_input("Masuk Kupas (pax)", min_value=0, value=0, step=1, key="f_masuk_kupas"))
        with t4:
            masuk_tr = int(st.number_input("Masuk Training (tr)", min_value=0, value=0, step=1, key="f_masuk_tr"))
    else:
        t1, t2 = st.columns(2)
        with t1:
            total_kupas = int(st.number_input("Total Kupas (pax)", min_value=0, value=0, step=1, key="f_total_kupas"))
        with t2:
            masuk_kupas = int(st.number_input("Masuk Kupas (pax)", min_value=0, value=0, step=1, key="f_masuk_kupas"))
        st.session_state["f_total_tr"] = 0
        st.session_state["f_masuk_tr"] = 0
        total_tr = 0
        masuk_tr = 0
        st.caption("Training tidak diaktifkan, jadi Total Training dan Masuk Training otomatis 0.")

    st.markdown("### 2-1) Role Breakdown (Masuk / Total) - wajib match dengan BASE")
    if enabled_roles:
        rb_cols = st.columns(min(4, len(enabled_roles)))
        for idx, role_name in enumerate(enabled_roles):
            key = ROLE_KEY_MAP[role_name]
            col = rb_cols[idx % len(rb_cols)]
            with col:
                st.number_input(
                    f"{role_name} total",
                    min_value=0,
                    value=int(st.session_state.get(f"f_{key.lower()}_total", 0)),
                    step=1,
                    key=f"f_{key.lower()}_total",
                )
                st.number_input(
                    f"{role_name} masuk",
                    min_value=0,
                    value=int(st.session_state.get(f"f_{key.lower()}_masuk", 0)),
                    step=1,
                    key=f"f_{key.lower()}_masuk",
                )

    role_breakdown = _build_role_breakdown_from_state(enabled_roles)
    role_errors = []
    if enabled_roles:
        role_errors = validate_role_breakdown(
            total_kupas,
            total_tr,
            masuk_kupas,
            masuk_tr,
            role_breakdown,
            enabled_roles,
        )
    else:
        role_errors = ["Enabled roles kosong."]

    if role_errors:
        st.error("Role breakdown belum valid:")
        for e in role_errors:
            st.write(f"- {e}")
    else:
        st.success("Role breakdown valid.")

    st.markdown("### 3-4) Jam Kerja")
    j1, j2 = st.columns(2)
    with j1:
        jam_masuk = st.text_input("Jam Masuk (HH:MM)", value="20:00", key="f_jam_masuk")
    with j2:
        jam_pulang = st.text_input("Jam Pulang (HH:MM)", value="06:30", key="f_jam_pulang")
    st.caption("Waktu Lapor dicatat otomatis saat kirim (server time), tidak bisa diinput manual.")

    default_role = _first_role(enabled_roles)

    st.markdown("### 5) Telat")
    btns = st.columns(3)
    if btns[0].button("+ Sepeda", key="btn_add_telat_sepeda"):
        add_row("telat_rows", {"nama": "", "jabatan": default_role, "eta": "", "reason": "sepeda dipakai", "ket": ""})
    if btns[1].button("+ Sakit", key="btn_add_telat_sakit"):
        add_row("telat_rows", {"nama": "", "jabatan": default_role, "eta": "", "reason": "sakit", "ket": ""})
    if btns[2].button("+ Lain-lain", key="btn_add_telat_other"):
        add_row("telat_rows", {"nama": "", "jabatan": default_role, "eta": "", "reason": "lain-lain", "ket": ""})

    telat_agg_preview = aggregate_telat(st.session_state["telat_rows"])
    st.write(
        f"Telat total: **{telat_agg_preview['total']} pax** | "
        f"Sepeda: **{telat_agg_preview['sepeda']}** | "
        f"Sakit: **{telat_agg_preview['sakit']}** | "
        f"Lain-lain: **{telat_agg_preview['lain_lain']}**"
    )

    for r in list(st.session_state["telat_rows"]):
        cols = st.columns([2.4, 1.3, 1.2, 1.8, 2.1, 0.7])
        with cols[0]:
            r["nama"] = st.text_input("Nama", value=r.get("nama", ""), key=f"telat_nama_{r['_id']}")
        with cols[1]:
            role_options = enabled_roles if enabled_roles else ["TL"]
            current_role = r.get("jabatan") if r.get("jabatan") in role_options else role_options[0]
            r["jabatan"] = st.selectbox(
                "Jabatan",
                role_options,
                index=role_options.index(current_role),
                key=f"telat_jabatan_{r['_id']}",
            )
        with cols[2]:
            r["eta"] = st.text_input("ETA (HH:MM)", value=r.get("eta", ""), key=f"telat_eta_{r['_id']}")
        with cols[3]:
            r["reason"] = st.selectbox(
                "Alasan",
                TELAT_REASONS,
                index=TELAT_REASONS.index(r.get("reason")) if r.get("reason") in TELAT_REASONS else 0,
                key=f"telat_reason_{r['_id']}",
            )
        with cols[4]:
            r["ket"] = st.text_input("Keterangan (opsional)", value=r.get("ket", ""), key=f"telat_ket_{r['_id']}")
        with cols[5]:
            if st.button("Hapus", key=f"telat_del_{r['_id']}"):
                delete_row("telat_rows", r["_id"])
                st.rerun()

    telat_errors = validate_rows("Telat", st.session_state["telat_rows"], ["nama", "jabatan", "eta", "reason"], enabled_roles)
    if telat_errors:
        st.error("Data Telat belum lengkap:")
        for e in telat_errors:
            st.write(f"- {e}")

    st.markdown("### 6) Tidak Masuk")
    btn_tm = st.columns(4)
    if btn_tm[0].button("+ Ijin", key="btn_add_tm_ijin"):
        add_row("tidak_masuk_rows", {"nama": "", "jabatan": default_role, "reason": "ijin", "ket": ""})
    if btn_tm[1].button("+ Sakit", key="btn_add_tm_sakit"):
        add_row("tidak_masuk_rows", {"nama": "", "jabatan": default_role, "reason": "sakit", "ket": ""})
    if btn_tm[2].button("+ Libur", key="btn_add_tm_libur"):
        add_row("tidak_masuk_rows", {"nama": "", "jabatan": default_role, "reason": "libur", "ket": ""})
    if btn_tm[3].button("+ Lain-lain", key="btn_add_tm_other"):
        add_row("tidak_masuk_rows", {"nama": "", "jabatan": default_role, "reason": "lain-lain", "ket": ""})

    tm_agg_preview = aggregate_tidak_masuk(st.session_state["tidak_masuk_rows"])
    st.write(
        f"Tidak masuk total: **{tm_agg_preview['total']} pax** | "
        f"Ijin: **{tm_agg_preview['ijin']}** | "
        f"Sakit: **{tm_agg_preview['sakit']}** | "
        f"Libur: **{tm_agg_preview['libur']}** | "
        f"Lain-lain: **{tm_agg_preview['lain_lain']}**"
    )

    for r in list(st.session_state["tidak_masuk_rows"]):
        cols = st.columns([2.5, 1.4, 1.8, 2.4, 0.7])
        with cols[0]:
            r["nama"] = st.text_input("Nama", value=r.get("nama", ""), key=f"tm_nama_{r['_id']}")
        with cols[1]:
            role_options = enabled_roles if enabled_roles else ["TL"]
            current_role = r.get("jabatan") if r.get("jabatan") in role_options else role_options[0]
            r["jabatan"] = st.selectbox(
                "Jabatan",
                role_options,
                index=role_options.index(current_role),
                key=f"tm_jabatan_{r['_id']}",
            )
        with cols[2]:
            r["reason"] = st.selectbox(
                "Alasan",
                TIDAK_MASUK_REASONS,
                index=TIDAK_MASUK_REASONS.index(r.get("reason")) if r.get("reason") in TIDAK_MASUK_REASONS else 0,
                key=f"tm_reason_{r['_id']}",
            )
        with cols[3]:
            r["ket"] = st.text_input("Keterangan (opsional)", value=r.get("ket", ""), key=f"tm_ket_{r['_id']}")
        with cols[4]:
            if st.button("Hapus", key=f"tm_del_{r['_id']}"):
                delete_row("tidak_masuk_rows", r["_id"])
                st.rerun()

    tm_errors = validate_rows("Tidak Masuk", st.session_state["tidak_masuk_rows"], ["nama", "jabatan", "reason"], enabled_roles)
    if tm_errors:
        st.error("Data Tidak Masuk belum lengkap:")
        for e in tm_errors:
            st.write(f"- {e}")

    st.markdown("### 7) Tanpa Keterangan")
    st.write(f"Total Tanpa Keterangan: **{len(st.session_state['tanpa_keterangan_rows'])} pax**")
    if st.button("+ Tambah Tanpa Keterangan", key="btn_add_tk"):
        add_row("tanpa_keterangan_rows", {"nama": "", "jabatan": default_role})

    for r in list(st.session_state["tanpa_keterangan_rows"]):
        cols = st.columns([3.0, 2.0, 0.7])
        with cols[0]:
            r["nama"] = st.text_input("Nama", value=r.get("nama", ""), key=f"tk_nama_{r['_id']}")
        with cols[1]:
            role_options = enabled_roles if enabled_roles else ["TL"]
            current_role = r.get("jabatan") if r.get("jabatan") in role_options else role_options[0]
            r["jabatan"] = st.selectbox(
                "Jabatan",
                role_options,
                index=role_options.index(current_role),
                key=f"tk_jabatan_{r['_id']}",
            )
        with cols[2]:
            if st.button("Hapus", key=f"tk_del_{r['_id']}"):
                delete_row("tanpa_keterangan_rows", r["_id"])
                st.rerun()

    tk_errors = validate_rows(
        "Tanpa Keterangan",
        st.session_state["tanpa_keterangan_rows"],
        ["nama", "jabatan"],
        enabled_roles,
    )
    if tk_errors:
        st.error("Data Tanpa Keterangan belum lengkap:")
        for e in tk_errors:
            st.write(f"- {e}")

    st.markdown("### 8) Resign")
    st.write(f"Total Resign: **{len(st.session_state['resign_rows'])} pax**")
    if st.button("+ Tambah Resign", key="btn_add_rs"):
        add_row("resign_rows", {"nama": "", "jabatan": default_role, "notif": "No"})

    for r in list(st.session_state["resign_rows"]):
        cols = st.columns([2.6, 1.7, 1.6, 0.7])
        with cols[0]:
            r["nama"] = st.text_input("Nama", value=r.get("nama", ""), key=f"rs_nama_{r['_id']}")
        with cols[1]:
            role_options = enabled_roles if enabled_roles else ["TL"]
            current_role = r.get("jabatan") if r.get("jabatan") in role_options else role_options[0]
            r["jabatan"] = st.selectbox(
                "Jabatan",
                role_options,
                index=role_options.index(current_role),
                key=f"rs_jabatan_{r['_id']}",
            )
        with cols[2]:
            notif_options = ["Yes", "No"]
            current_notif = r.get("notif") if r.get("notif") in notif_options else "No"
            r["notif"] = st.selectbox(
                "Sudah kasih notif?",
                notif_options,
                index=notif_options.index(current_notif),
                key=f"rs_notif_{r['_id']}",
            )
        with cols[3]:
            if st.button("Hapus", key=f"rs_del_{r['_id']}"):
                delete_row("resign_rows", r["_id"])
                st.rerun()

    rs_errors = validate_rows("Resign", st.session_state["resign_rows"], ["nama", "jabatan"], enabled_roles)
    if rs_errors:
        st.error("Data Resign belum lengkap:")
        for e in rs_errors:
            st.write(f"- {e}")

    telat_agg = aggregate_telat(st.session_state["telat_rows"])
    tm_agg = aggregate_tidak_masuk(st.session_state["tidak_masuk_rows"])

    all_errors = []
    all_errors.extend(role_errors)
    all_errors.extend(telat_errors)
    all_errors.extend(tm_errors)
    all_errors.extend(tk_errors)
    all_errors.extend(rs_errors)

    cooldown_error = get_sender_cooldown_error(sender_name)
    if cooldown_error:
        all_errors.append(cooldown_error)

    form = {
        "tanggal": tanggal,
        "department": department,
        "qc_name": qc_name.strip(),
        "shift": shift,
        "main_tl": main_tl.strip(),
        "tl_lain": tl_lain.strip(),
        "total_kupas": total_kupas,
        "total_tr": total_tr,
        "masuk_kupas": masuk_kupas,
        "masuk_tr": masuk_tr,
        "enabled_roles": enabled_roles,
        "role_breakdown": role_breakdown,
        "jam_masuk": jam_masuk.strip(),
        "jam_pulang": jam_pulang.strip(),
        "telat": telat_agg,
        "tidak_masuk": tm_agg,
        "tanpa_keterangan_rows": [
            {"nama": r.get("nama", "").strip(), "jabatan": r.get("jabatan", "")}
            for r in st.session_state["tanpa_keterangan_rows"]
        ],
        "resign_rows": [
            {
                "nama": r.get("nama", "").strip(),
                "jabatan": r.get("jabatan", ""),
                "notif": r.get("notif", "No"),
            }
            for r in st.session_state["resign_rows"]
        ],
    }

    preview_form = {**form, "waktu_lapor": get_report_timestamp()}
    message = build_laporan_absensi_team_message(preview_form)

    st.divider()
    st.subheader("Preview (Telegram message)")
    st.code(message)

    can_submit = len(all_errors) == 0
    if not can_submit:
        st.warning("Submit dinonaktifkan karena masih ada error validasi di form.")
        if cooldown_error:
            st.error(cooldown_error)

    if st.button("Send to Telegram", key="f_send_btn", disabled=not can_submit):
        send_form = {**form, "waktu_lapor": get_report_timestamp()}
        send_message = build_laporan_absensi_team_message(send_form)
        ok, info = send_telegram_message(send_message)
        if ok:
            LAST_SEND_AT_BY_SENDER[sender_name.strip().lower()] = dt.datetime.now()
            st.success(info)
        else:
            st.error(info)

with tab2:
    st.subheader("Paste & Parse (Debug)")
    text = st.text_area("Telegram Report (Paste Here)", height=350, key="dbg_text")
    if st.button("Parse & Show (Debug)", key="dbg_btn"):
        result = parse_attendance_text(text)
        st.json(result)
