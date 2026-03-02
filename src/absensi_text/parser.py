import re

def parse_attendance_text(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines()]
    full = "\n".join(lines)

    def pick(pattern, default=""):
        m = re.search(pattern, full, flags=re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else default

    def pick_int_from_str(s: str, default=0):
        nums = re.findall(r"\d+", s or "")
        return int(nums[0]) if nums else default

    def pick_int(pattern, default=0):
        return pick_int_from_str(pick(pattern, ""), default)

    # ---------- 기본 ----------
    tanggal = pick(r"tanggal\s*[:\-]\s*(.+)")
    jam_masuk = pick(r"jam\s*masuk\s*[:\-]\s*([0-9]{1,2}:[0-9]{2})")
    jam_pulang = pick(r"jam\s*pulang\s*[:\-]\s*([0-9]{1,2}:[0-9]{2})")

    # "Nama MP / Shift : uyun (Shift 2)"
    mp_name = pick(r"nama\s*mp\s*/\s*shift\s*:\s*([^\(\n]+)")
    shift = pick_int(r"\(\s*shift\s*(\d+)\s*\)", 0) or pick_int(r"shift\s*[:\-]?\s*(\d+)", 0)

    main_tl = pick(r"main\s*tl\s*[:\-]\s*(.+)")
    tl_lain_raw = pick(r"tl\s*lain\s*[:\-]\s*(.+)")
    tl_lain = [x.strip() for x in re.split(r"[,/;|]", tl_lain_raw) if x.strip()]

    # ---------- Total / Masuk / Training ----------
    # Total : 43 pax + 3 tr
    total_kupas = 0
    total_tr = 0
    m_total = re.search(r"total\s*[:\-]\s*(\d+)\s*pax(?:\s*\+\s*(\d+)\s*tr)?", full, flags=re.IGNORECASE)
    if m_total:
        total_kupas = int(m_total.group(1))
        total_tr = int(m_total.group(2) or 0)

    masuk_kupas = 0
    masuk_tr = 0

    # Masuk : 40 pax (+ optional tr)
    m_masuk = re.search(r"masuk\s*[:\-]\s*(\d+)\s*pax(?:\s*\+\s*(\d+)\s*tr)?", full, flags=re.IGNORECASE)
    if m_masuk:
        masuk_kupas = int(m_masuk.group(1))
        masuk_tr = int(m_masuk.group(2) or 0)

    # Training : 3 tr  (별도 라인일 때)
    m_tr = re.search(r"training\s*[:\-]\s*(\d+)\s*tr", full, flags=re.IGNORECASE)
    if m_tr:
        masuk_tr = int(m_tr.group(1))

    # ---------- Role breakdown ----------
    # -> TL : 1 (Total masuk) / 1 (Total Orang di team)
    role_breakdown = {}
    role_map = {"TL": "TL", "AST": "AST", "AJ": "AJ", "BIASA": "BIASA", "TRAINING": "TRAINING"}
    role_pat = re.compile(r"(?:->\s*)?([A-Za-z]+)\s*:\s*(\d+)\s*.*?/\s*(\d+)", re.IGNORECASE)
    for ln in lines:
        mm = role_pat.search(ln)
        if not mm:
            continue
        role_raw = mm.group(1).strip().upper()
        role = role_map.get(role_raw)
        if not role:
            continue
        role_breakdown[role] = {"masuk": int(mm.group(2)), "total": int(mm.group(3))}

    # ---------- Telat ----------
    telat_total = 0
    m_telat = re.search(r"telat\s*[:\-]?\s*(\d+)\s*(?:pax|org|orang)?", full, flags=re.IGNORECASE)
    if m_telat:
        telat_total = int(m_telat.group(1))

    # telat detail line example:
    # -> Lain-lain : 1 pax (Eka puji /biasa/bangun terlambat)
    telat_details = []
    telat_line_pat = re.compile(r"->\s*([^:]+)\s*:\s*(\d+)\s*(?:pax|org|orang)?\s*(?:\((.+)\))?", re.IGNORECASE)

    in_telat = False
    for ln in lines:
        low = ln.lower()
        if low.startswith("5.") or "telat" in low and low.startswith("5"):
            in_telat = True
            continue
        if in_telat and (low.startswith("6.") or "tidak masuk" in low):
            in_telat = False

        if in_telat:
            mm = telat_line_pat.search(ln)
            if mm:
                category = mm.group(1).strip()
                count = int(mm.group(2))
                blob = (mm.group(3) or "").strip()
                person = {}
                # (Name / role / reason)
                if blob:
                    parts = [p.strip() for p in blob.split("/") if p.strip()]
                    person = {
                        "name": parts[0] if len(parts) > 0 else "",
                        "role": parts[1] if len(parts) > 1 else "",
                        "reason": parts[2] if len(parts) > 2 else "",
                    }
                telat_details.append({"category": category, "count": count, "person": person})

    # ---------- Tidak Masuk ----------
    tidak_masuk_total = 0
    m_tm = re.search(r"tidak\s*masuk\s*[:\-]\s*(\d+)\s*(?:pax|org|orang)?", full, flags=re.IGNORECASE)
    if m_tm:
        tidak_masuk_total = int(m_tm.group(1))

    # breakdown lines: -> Ijin : 1 pax
    tidak_masuk_breakdown = {"Ijin": 0, "Sakit": 0, "Libur": 0, "Lain-lain": 0}
    tidak_masuk_people = []  # list of {category, name, role, reason}

    in_tidak_masuk = False
    current_cat = None

    bd_pat = re.compile(r"->\s*([A-Za-z\-\s]+)\s*:\s*(\d+)\s*(?:pax|org|orang)?", re.IGNORECASE)
    person_pat = re.compile(r"^\(\s*(.+?)\s*\)\s*$")  # ( deny / biasa / menjaga bapak sakit)

    for ln in lines:
        low = ln.lower()
        if low.startswith("6.") or low.startswith("6 "):
            in_tidak_masuk = True
            current_cat = None
            continue
        if in_tidak_masuk and (low.startswith("7.") or "tanpa keterangan" in low):
            in_tidak_masuk = False
            current_cat = None

        if not in_tidak_masuk:
            continue

        mm_bd = bd_pat.search(ln)
        if mm_bd:
            cat_raw = mm_bd.group(1).strip()
            cat_key = cat_raw.title()
            if cat_key.lower().startswith("ijin"):
                cat_key = "Ijin"
            elif cat_key.lower().startswith("sakit"):
                cat_key = "Sakit"
            elif cat_key.lower().startswith("libur"):
                cat_key = "Libur"
            else:
                cat_key = "Lain-lain"
            tidak_masuk_breakdown[cat_key] = int(mm_bd.group(2))
            current_cat = cat_key
            continue

        mm_p = person_pat.match(ln)
        if mm_p and current_cat:
            blob = mm_p.group(1)
            parts = [p.strip() for p in blob.split("/") if p.strip()]
            tidak_masuk_people.append({
                "category": current_cat,
                "name": parts[0] if len(parts) > 0 else "",
                "role": parts[1] if len(parts) > 1 else "",
                "reason": parts[2] if len(parts) > 2 else "",
            })

    # ---------- Tanpa keterangan / Resign (일단 카운트만) ----------
    tanpa_keterangan_total = 0
    resign_total = 0
    m_tk = re.search(r"tanpa\s*keterangan\s*[:\-]\s*(\d+)", full, flags=re.IGNORECASE)
    if m_tk:
        tanpa_keterangan_total = int(m_tk.group(1))
    m_rs = re.search(r"resign\s*[:\-]\s*(\d+)", full, flags=re.IGNORECASE)
    if m_rs:
        resign_total = int(m_rs.group(1))

    return {
        "report_type": "A. Laporan Absensi Team",
        "tanggal": tanggal,
        "mp_name": mp_name,
        "shift": shift,
        "main_tl": main_tl,
        "tl_lain": tl_lain,

        "total_kupas_member": total_kupas,
        "total_training": total_tr,
        "masuk_kupas_member": masuk_kupas,
        "masuk_training": masuk_tr,

        "role_breakdown": role_breakdown,

        "jam_masuk": jam_masuk,
        "jam_pulang": jam_pulang,

        "telat_total": telat_total,
        "telat_details": telat_details,

        "tidak_masuk_total": tidak_masuk_total,
        "tidak_masuk_breakdown": tidak_masuk_breakdown,
        "tidak_masuk_people": tidak_masuk_people,

        "tanpa_keterangan_total": tanpa_keterangan_total,
        "resign_total": resign_total,
    }