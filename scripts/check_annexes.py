#!/usr/bin/env python3
import os
import re
import json
import requests
import io
import pandas as pd            # pip install pandas
from github import Github      # pip install PyGithub

# —— CONFIGURACIÓN ——
STATIC_BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing/assets/data"
ANNEX_PAGES     = ["II", "III", "IV", "V", "VI"]
STATE_FILE      = "annexes_state.json"
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN")
REPO_NAME       = "Maxi199588/cosmetic-checker"
BRANCH          = "main"
OUTPUT_DIR      = "RESTRICCIONES"

# Patrón para extraer fecha "DD/MM/YYYY"
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
    Descarga el archivo (xls o xlsx) y usa pandas para leer filas A3 y A4,
    extrayendo la fecha interna en formato DD/MM/YYYY.
    """
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    # Leer con pandas sin importar la extensión
    df = pd.read_excel(io.BytesIO(r.content), header=None, nrows=5)
    for idx in (2, 3):  # fila 3 y 4
        val = df.iloc[idx, 0]
        if isinstance(val, str):
            m = DATE_PATTERN.search(val)
            if m:
                return m.group(1)
    return None


def download_file(url, dest_path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(r.content)
    return dest_path


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
        date = None
        chosen_url = None
        # probar xlsx y xls
        for ext in ('.xlsx', '.xls'):
            url = f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2{ext}"
            try:
                d = fetch_and_parse_date(url)
            except Exception:
                d = None
            if d:
                date = d
                chosen_url = url
                break

        if not date:
            print(f"[WARN] No pude leer la fecha en Annex {annex}")
            new_state[annex] = state.get(annex)
            continue

        new_state[annex] = date
        if state.get(annex) != date:
            print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {date}")
            # descarga y añade al commit
            filename = f"COSING_Annex_{annex}_v2.xlsx"
            dest = os.path.join(OUTPUT_DIR, filename)
            # si URL es .xls, descargar y convertir
            if chosen_url.endswith('.xls'):
                tmp = download_file(chosen_url, dest.replace('.xlsx','.xls'))
                # usar pandas para convertir
                df = pd.read_excel(tmp, engine='xlrd')
                df.to_excel(dest, index=False)
                os.remove(tmp)
            else:
                download_file(chosen_url, dest)
            to_commit.append(dest)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        print(f"✅ Committed {len(to_commit)} archivos.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
