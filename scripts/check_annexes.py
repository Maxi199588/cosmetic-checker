#!/usr/bin/env python3
import os
import re
import json
import requests
import io
import xlrd            # pip install xlrd
from openpyxl import load_workbook  # pip install openpyxl
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
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_and_parse_date(url):
    """
    Descarga el XLS (.xls o .xlsx) desde la URL y extrae la fecha combinada en la celda A3.
    Devuelve la fecha 'DD/MM/YYYY' o None.
    """
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    content = r.content

    cell_value = None
    # Intentar con openpyxl (.xlsx)
    if url.lower().endswith('.xlsx'):
        try:
            wb = load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            cell_value = ws.cell(row=3, column=1).value
        except Exception:
            cell_value = None
    # Si no resultó o es .xls, usar xlrd
    if cell_value is None and url.lower().endswith('.xls') or cell_value is None:
        try:
            book = xlrd.open_workbook(file_contents=content)
            sheet = book.sheet_by_index(0)
            cell_value = sheet.cell_value(2, 0)
        except Exception:
            cell_value = None

    if not isinstance(cell_value, str):
        return None
    m = DATE_PATTERN.search(cell_value)
    return m.group(1) if m else None


def download_file(url, dest_path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(r.content)


def commit_and_push(files, message):
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(REPO_NAME)
    for path in files:
        with open(path, "rb") as f:
            content = f.read()
        try:
            existing = repo.get_contents(path, ref=BRANCH)
            repo.update_file(path, message, content, existing.sha, branch=BRANCH)
        except Exception:
            repo.create_file(path, message, content, branch=BRANCH)


def main():
    state = load_state()
    new_state = {}
    to_commit = []

    for anexo in ANNEX_PAGES:
        url = f"{STATIC_BASE_URL}/COSING_Annex_{anexo}_v2.xlsx"
        # También intentar la extensión .xls si no existe .xlsx
        internal_date = fetch_and_parse_date(url)
        if not internal_date:
            # Prueba .xls si .xlsx no funcionó
            url_xls = url[:-1]  # reemplaza xlsx -> xls
            internal_date = fetch_and_parse_date(url_xls)
            url = url_xls

        if not internal_date:
            print(f"[WARN] No pude leer la fecha en Annex {anexo}")
            new_state[anexo] = state.get(anexo)
            continue

        new_state[anexo] = internal_date
        if state.get(anexo) != internal_date:
            print(f"[CHANGE] Annex {anexo}: {state.get(anexo)} -> {internal_date}")
            # Descargar y guardar el fichero correcto
            filename = f"COSING_Annex_{anexo}_v2{'.xls' if url.lower().endswith('.xls') else '.xlsx'}"
            dest = os.path.join(OUTPUT_DIR, filename)
            download_file(url, dest)
            to_commit.append(dest)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        print(f"✅ Committed {len(to_commit)} archivos.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == "__main__":
    main()
