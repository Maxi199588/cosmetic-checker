#!/usr/bin/env python3
import os
import re
import json
import requests
import io
import xlrd            # pip install xlrd
from openpyxl import load_workbook  # pip install openpyxl
import pandas as pd                 # pip install pandas
from github import Github            # pip install PyGithub

# —— CONFIGURACIÓN ——
STATIC_BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing/assets/data"
ANNEX_PAGES     = ["II", "III", "IV", "V", "VI"]  # Annex I no dispone de XLS
STATE_FILE      = "annexes_state.json"
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN")
REPO_NAME       = "Maxi199588/cosmetic-checker"  # usuario/repo
BRANCH          = "main"
OUTPUT_DIR      = "RESTRICCIONES"

# Expresión para extraer la fecha interna "Last update: DD/MM/YYYY"
DATE_PATTERN = re.compile(r"Last update:\s*(\d{2}/\d{2}/\d{4})")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, "r", encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_and_parse_date(url):
    """
    Descarga el XLS (.xls o .xlsx) desde la URL y extrae la fecha combinada en las celdas A3 o A4.
    Devuelve la fecha 'DD/MM/YYYY' o None.
    """
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content = resp.content

    cell_value = None
    # Intentar .xlsx con openpyxl
    if url.lower().endswith('.xlsx'):
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            # Celdas A3 y A4
            for row in (3, 4):
                val = ws.cell(row=row, column=1).value
                if isinstance(val, str) and DATE_PATTERN.search(val):
                    cell_value = val
                    break
        except Exception:
            cell_value = None
    # Intentar .xls con xlrd si no se obtuvo
    if cell_value is None:
        try:
            book = xlrd.open_workbook(file_contents=content)
            sheet = book.sheet_by_index(0)
            # Filas 3 (idx2) y 4 (idx3)
            for idx in (2, 3):
                val = sheet.cell_value(idx, 0)
                if isinstance(val, str) and DATE_PATTERN.search(val):
                    cell_value = val
                    break
        except Exception:
            cell_value = None

    if not isinstance(cell_value, str):
        return None
    m = DATE_PATTERN.search(cell_value)
    return m.group(1) if m else None


def download_file(url, dest_path):(url, dest_path):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(resp.content)


def convert_xls_to_xlsx(xls_path):
    df = pd.read_excel(xls_path, engine='xlrd')
    xlsx_path = xls_path[:-4] + '.xlsx'
    df.to_excel(xlsx_path, index=False, engine='openpyxl')
    os.remove(xls_path)
    return xlsx_path


def commit_and_push(files, message):
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(REPO_NAME)
    for file_path in files:
        content = open(file_path, 'rb').read()
        try:
            existing = repo.get_contents(file_path, ref=BRANCH)
            repo.update_file(file_path, message, content, existing.sha, branch=BRANCH)
        except Exception:
            repo.create_file(file_path, message, content, branch=BRANCH)


def main():
    state = load_state()
    new_state = {}
    to_commit = []

    for annex in ANNEX_PAGES:
        urls = [
            f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2.xlsx",
            f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2.xls"
        ]
        internal_date = None
        chosen_url = None
        for url in urls:
            date = fetch_and_parse_date(url)
            if date:
                internal_date = date
                chosen_url = url
                break

        if not internal_date:
            print(f"[WARN] No pude leer la fecha en Annex {annex}")
            new_state[annex] = state.get(annex)
            continue

        new_state[annex] = internal_date
        if state.get(annex) != internal_date:
            print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {internal_date}")
            ext = '.xls' if chosen_url.endswith('.xls') else '.xlsx'
            filename = f"COSING_Annex_{annex}_v2{ext}"
            dest = os.path.join(OUTPUT_DIR, filename)
            download_file(chosen_url, dest)

            # Si .xls, convertir
            if ext == '.xls':
                converted = convert_xls_to_xlsx(dest)
                to_commit.append(converted)
            else:
                to_commit.append(dest)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        print(f"✅ Committed {len(to_commit)} archivos.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
