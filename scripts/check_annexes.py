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

# Multiple date patterns to try
DATE_PATTERNS = [
    re.compile(r"Last update:\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Update[d]?:?\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Date:?\s*(\d{2}/\d{2}/\d{4})")
]


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
    Descarga el archivo (xls o xlsx) y usa pandas para buscar la fecha
    en varios formatos y ubicaciones.
    """
    print(f"Descargando {url}...")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    
    try:
        # Leer con pandas sin importar la extensión
        df = pd.read_excel(io.BytesIO(r.content), header=None, nrows=10)
        
        # Debugging: imprimir primeras filas para entender la estructura
        print("Primeras filas del archivo:")
        for i in range(min(10, len(df))):
            print(f"Fila {i+1}: {df.iloc[i, 0]}")
        
        # Buscar en más filas (las 10 primeras)
        for idx in range(10):
            for col in range(min(3, len(df.columns))):  # Buscar en las primeras 3 columnas
                val = df.iloc[idx, col]
                if isinstance(val, str):
                    # Probar todos los patrones de fecha
                    for pattern in DATE_PATTERNS:
                        m = pattern.search(val)
                        if m:
                            date = m.group(1)
                            print(f"¡Fecha encontrada!: {date} en fila {idx+1}, columna {col+1}")
                            return date
        
        # Si aún no encontramos, intentar otro enfoque
        # A veces la fecha puede estar en celdas combinadas o headers
        if 'xlrd' not in str(type(df)):
            # Si estamos usando openpyxl, intentar leer las propiedades del documento
            try:
                buffer = io.BytesIO(r.content)
                from openpyxl import load_workbook
                wb = load_workbook(buffer)
                sheet = wb.active
                
                # Buscar en merged cells
                for merged_cell in sheet.merged_cells.ranges:
                    val = sheet.cell(merged_cell.min_row, merged_cell.min_col).value
                    if isinstance(val, str):
                        for pattern in DATE_PATTERNS:
                            m = pattern.search(val)
                            if m:
                                date = m.group(1)
                                print(f"¡Fecha encontrada en celda combinada!: {date}")
                                return date
            except Exception as e:
                print(f"Error al intentar leer celdas combinadas: {e}")
                
    except Exception as e:
        print(f"Error al leer el archivo: {e}")
    
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
        
        # Probar primero .xlsx y luego .xls
        for ext in ('.xlsx', '.xls'):
            url = f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2{ext}"
            try:
                print(f"\n--- Procesando Annex {annex} ({ext}) ---")
                d = fetch_and_parse_date(url)
                if d:
                    date = d
                    chosen_url = url
                    break
            except Exception as e:
                print(f"Error procesando {url}: {e}")
        
        if not date:
            # Si no se encontró fecha en ninguna extensión, intentar con otro nombre de archivo
            # A veces hay variaciones como espacios o números de versión
            try:
                url = f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2 6.xls"
                print(f"\n--- Intentando formato alternativo: {url} ---")
                d = fetch_and_parse_date(url)
                if d:
                    date = d
                    chosen_url = url
            except Exception as e:
                print(f"Error con formato alternativo: {e}")

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
