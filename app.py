import re
import os
from difflib import SequenceMatcher

import streamlit as st
import pandas as pd
from googleapiclient.discovery import build


# =========================================================
# KONFIGURASI
# =========================================================
THRESHOLD = 0.90  # ambang batas kemiripan untuk fuzzy matching


# =========================================================
# KONEKSI KE GOOGLE DRIVE (pakai Service Account)
# =========================================================
@st.cache_resource
def get_drive_service():
    """
    Pakai API Key saja (bukan service account).
    Syarat: folder Drive sertifikat harus di-set
    "Anyone with the link" (Viewer), karena API key
    hanya bisa membaca resource yang sudah publik.

    API key diambil dari Streamlit secrets:
    - Lokal: .streamlit/secrets.toml -> [general] api_key = "..."
    - Streamlit Cloud: menu App settings > Secrets
    """
    api_key = st.secrets["general"]["api_key"]
    return build("drive", "v3", developerKey=api_key)


def extract_folder_id(drive_link: str) -> str | None:
    """
    Ambil folder ID otomatis dari berbagai format link Google Drive, misal:
    - https://drive.google.com/drive/folders/1AbCDeFGhiJKLmnop?usp=sharing
    - https://drive.google.com/drive/u/0/folders/1AbCDeFGhiJKLmnop
    """
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", drive_link)
    if match:
        return match.group(1)
    # fallback: kalau user cuma paste ID mentahnya saja
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", drive_link.strip()):
        return drive_link.strip()
    return None


def list_files_in_folder(service, folder_id: str):
    files_list = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            )
            .execute()
        )
        files_list.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files_list


def normalize(name: str) -> str:
    name = str(name).strip().lower()
    name = re.sub(r"[.,\-_/\\]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def make_link(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"


def match_certificates(df: pd.DataFrame, drive_files: list):
    name_to_id = {}
    for f in drive_files:
        name_no_ext = os.path.splitext(f["name"])[0]
        name_to_id[normalize(name_no_ext)] = f["id"]

    links, statuses = [], []

    progress = st.progress(0, text="Mencocokkan data...")
    total = len(df)

    for i, full_name in enumerate(df["full_name"]):
        key = normalize(full_name)

        if key in name_to_id:
            file_id = name_to_id[key]
            status = "EXACT"
        else:
            best_score, best_key = 0, None
            for candidate_key in name_to_id:
                score = similarity(key, candidate_key)
                if score > best_score:
                    best_score, best_key = score, candidate_key

            if best_key and best_score >= THRESHOLD:
                file_id = name_to_id[best_key]
                status = f"FUZZY ({best_score:.2f})"
            else:
                file_id = None
                status = "NOT FOUND"

        if file_id:
            links.append(make_link(file_id))
        else:
            links.append("NOT FOUND")

        statuses.append(status)
        progress.progress((i + 1) / total, text=f"Memproses {i + 1}/{total}")

    progress.empty()
    df = df.copy()
    df["link"] = links
    df["match_status"] = statuses
    return df


# =========================================================
# TAMPILAN STREAMLIT
# =========================================================
st.set_page_config(page_title="TautCepat", page_icon="🍀", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --tc-base: #095864;
        --tc-base-light: #14808F;
        --tc-orange: #F4A300;
        --tc-orange-hover: #FFB733;
    }

    .stApp {
        background: linear-gradient(180deg, var(--tc-base) 0%, var(--tc-base-light) 100%);
    }

    .block-container {
        max-width: 1100px;
        padding-top: 2.5rem;
        padding-bottom: 3rem;
    }

    h1 {
        color: #FFFFFF !important;
        text-align: center;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }

    .tc-label {
        text-align: center;
        font-size: 1.25rem;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 0.5rem;
    }

    .tc-caption {
        text-align: center;
        color: #FFFFFF;
        opacity: 0.85;
        font-size: 0.9rem;
        margin-top: -0.4rem;
        margin-bottom: 1.6rem;
    }

    /* Kotak upload file: besar & tombol browse di tengah */
    [data-testid="stFileUploaderDropzone"] {
        background-color: #FFFFFF;
        border: 2.5px dashed var(--tc-orange);
        border-radius: 16px;
        padding: 2rem 1rem;
        display: flex;
        justify-content: center;
        align-items: center;
    }

    [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none;
    }

    [data-testid="stFileUploaderDropzone"] button {
        background-color: var(--tc-orange) !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        border: none !important;
    }

    div[data-testid="stTextInput"] input {
        border-radius: 10px;
        border: 1.5px solid var(--tc-orange);
        padding: 0.7rem;
        text-align: center;
    }

    /* Tombol proses & download: oranye, lebih lebar, benar-benar center */
    div[data-testid="stButton"],
    div[data-testid="stDownloadButton"] {
        display: flex !important;
        justify-content: center !important;
        width: 100%;
    }
    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button {
        width: 70%;
        min-width: 320px;
        background-color: var(--tc-orange);
        color: #FFFFFF;
        font-weight: 800;
        font-size: 1.15rem;
        padding: 0.9rem 0;
        border-radius: 14px;
        border: none;
        box-shadow: 0 6px 16px rgba(244, 163, 0, 0.4);
    }
    div[data-testid="stButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover {
        background-color: var(--tc-orange-hover);
        color: #FFFFFF;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("TautCepat")
st.markdown("<br>", unsafe_allow_html=True)

st.markdown('<div class="tc-label">📁 Upload file Excel (kolom wajib: full_name)</div>', unsafe_allow_html=True)
excel_file = st.file_uploader(
    "Upload file Excel", type=["xlsx", "xls"], label_visibility="collapsed"
)

st.markdown("<br>", unsafe_allow_html=True)

st.markdown('<div class="tc-label">🔗 Tempel link folder Google Drive sertifikat</div>', unsafe_allow_html=True)
drive_link = st.text_input(
    "Link folder Google Drive", label_visibility="collapsed", placeholder="https://drive.google.com/drive/folders/..."
)
st.markdown(
    '<div class="tc-caption">Pastikan folder sudah di-set \'Anyone with the link\' (Viewer) di pengaturan share Google Drive.</div>',
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)
process_clicked = st.button("Proses Sekarang")

st.markdown("<br>", unsafe_allow_html=True)

if process_clicked:
    if not excel_file:
        st.error("Silakan upload file Excel terlebih dahulu.")
    elif not drive_link:
        st.error("Silakan isi link folder Google Drive terlebih dahulu.")
    else:
        folder_id = extract_folder_id(drive_link)
        if not folder_id:
            st.error("Link folder Google Drive tidak valid. Pastikan link berupa link folder, bukan file.")
        else:
            file_ext = excel_file.name.rsplit(".", 1)[-1].lower()
            engine = "xlrd" if file_ext == "xls" else "openpyxl"

            try:
                df = pd.read_excel(excel_file, engine=engine)
            except Exception as e:
                st.error(f"Gagal membaca file Excel: {e}")
                st.stop()

            if "full_name" not in df.columns:
                st.error("Kolom 'full_name' tidak ditemukan di file Excel. Periksa kembali nama kolomnya.")
                st.stop()

            with st.spinner("Menghubungkan ke Google Drive..."):
                service = get_drive_service()
                drive_files = list_files_in_folder(service, folder_id)

            if not drive_files:
                st.warning(
                    "Tidak ada file ditemukan di folder tersebut. "
                    "Pastikan folder sudah di-set 'Anyone with the link' (Viewer) di Google Drive."
                )
                st.stop()

            st.success(f"✅ Ditemukan {len(drive_files)} file sertifikat di folder.")

            result_df = match_certificates(df, drive_files)

            exact = (result_df["match_status"] == "EXACT").sum()
            fuzzy = result_df["match_status"].str.startswith("FUZZY").sum()
            notfound = (result_df["match_status"] == "NOT FOUND").sum()

            col1, col2, col3 = st.columns(3)
            col1.metric("✅ Exact Match", exact)
            col2.metric("⚠️ Fuzzy Match (perlu cek)", fuzzy)
            col3.metric("❌ Tidak Ditemukan", notfound)

            st.dataframe(result_df, use_container_width=True)

            output_name = f"hasil_{excel_file.name.rsplit('.', 1)[0]}.xlsx"
            from io import BytesIO
            buffer = BytesIO()
            result_df.to_excel(buffer, index=False, engine="openpyxl")
            buffer.seek(0)

            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button(
                "⬇️ Download Hasil Excel",
                data=buffer,
                file_name=output_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )