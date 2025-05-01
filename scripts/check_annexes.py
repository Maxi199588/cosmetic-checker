#!/usr/bin/env python3
import os
import re
import json
import requests
import io
import pandas as pd
from github import Github

# —— CONFIGURACIÓN ——
STATIC_BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing/assets/data"
ANNEX_PAGES     = ["II", "III", "IV", "V", "VI"]
STATE_FILE      = "annexes_state.json"
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN")
REPO_NAME       = "Maxi199588/cosmetic-checker"
BRANCH          = "main"
OUTPUT_DIR      = "RESTRICCIONES"

# Patrón para extraer fecha "DD/MM/YYYY"
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
    Descarga el archivo y busca la fecha de actualización.
    """
    print(f"Descargando {url}...")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        
        # Guardar temporalmente el archivo para inspeccionarlo
        temp_file = "temp_annex.xls"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        
        print(f"Archivo descargado, tamaño: {len(r.content)} bytes")
        
        # Intentar leer con engine='xlrd' explícitamente para .xls
        if url.endswith('.xls'):
            try:
                print("Intentando leer con xlrd...")
                df = pd.read_excel(temp_file, engine='xlrd', header=None)
                print(f"¡Éxito! Leído con xlrd. Filas: {len(df)}")
            except Exception as e:
                print(f"Error con xlrd: {e}")
                # Intentar con otro método: openpyxl
                try:
                    print("Intentando leer con openpyxl...")
                    df = pd.read_excel(temp_file, engine='openpyxl', header=None)
                    print(f"¡Éxito! Leído con openpyxl. Filas: {len(df)}")
                except Exception as e:
                    print(f"Error con openpyxl: {e}")
                    return None
        else:
            # Para .xlsx, usar openpyxl
            try:
                print("Intentando leer con openpyxl...")
                df = pd.read_excel(temp_file, engine='openpyxl', header=None)
                print(f"¡Éxito! Leído con openpyxl. Filas: {len(df)}")
            except Exception as e:
                print(f"Error con openpyxl: {e}")
                return None
        
        # Buscar la fecha en las primeras 15 filas
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                val = df.iloc[idx, col]
                if isinstance(val, str):
                    print(f"Fila {idx+1}, Col {col+1}: {val}")
                    # Probar todos los patrones de fecha
                    for pattern in DATE_PATTERNS:
                        m = pattern.search(val)
                        if m:
                            date = m.group(1)
                            print(f"¡Fecha encontrada!: {date} en fila {idx+1}, columna {col+1}")
                            os.remove(temp_file)  # Limpiar
                            return date
        
        # Si llegamos aquí, no encontramos la fecha
        print("No se encontró ninguna fecha en el formato esperado.")
        
        # Último intento: buscar cualquier celda que parezca una fecha
        print("Buscando celdas con formato de fecha...")
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                val = df.iloc[idx, col]
                if isinstance(val, pd.Timestamp) or (isinstance(val, str) and '/' in val):
                    date_str = str(val)
                    print(f"Posible fecha en Fila {idx+1}, Col {col+1}: {date_str}")
                    # Intentar extraer DD/MM/YYYY
                    date_match = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', date_str)
                    if date_match:
                        date = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
                        print(f"¡Fecha encontrada en formato alternativo!: {date}")
                        os.remove(temp_file)  # Limpiar
                        return date
        
        os.remove(temp_file)  # Limpiar
        return None
        
    except Exception as e:
        print(f"Error general al procesar {url}: {e}")
        if os.path.exists("temp_annex.xls"):
            os.remove("temp_annex.xls")
        return None


def download_file(url, dest_path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(r.content)
    return dest_path


def convert_xls_to_xlsx(xls_path, xlsx_path):
    """Convierte archivo .xls a .xlsx con manejo de errores específico."""
    try:
        # Leer con xlrd explícitamente para .xls
        df = pd.read_excel(xls_path, engine='xlrd')
        df.to_excel(xlsx_path, index=False)
        print(f"Convertido {xls_path} a {xlsx_path}")
        return True
    except Exception as e:
        print(f"Error al convertir {xls_path} a {xlsx_path}: {e}")
        # Intento alternativo
        try:
            import subprocess
            # Intentar con libreoffice si está disponible
            cmd = ['libreoffice', '--headless', '--convert-to', 'xlsx', '--outdir', 
                   os.path.dirname(xlsx_path), xls_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("Convertido usando LibreOffice")
                return True
        except Exception as sub_e:
            print(f"Error en conversión alternativa: {sub_e}")
        return False


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

    # Verificar dependencias necesarias
    try:
        import xlrd
        print(f"xlrd version: {xlrd.__version__}")
    except ImportError:
        print("⚠️ xlrd no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "xlrd"])
    
    try:
        import openpyxl
        print(f"openpyxl version: {openpyxl.__version__}")
    except ImportError:
        print("⚠️ openpyxl no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "openpyxl"])

    for annex in ANNEX_PAGES:
        date = None
        chosen_url = None
        
        # Probar las variantes de URL
        urls_to_try = [
            f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2.xlsx",
            f"{STATIC_BASE_URL}/COSING_Annex_{annex}_v2.xls",
            # No incluimos el "6" ya que era solo en tu caso local
        ]
        
        for url in urls_to_try:
            try:
                print(f"\n--- Procesando Annex {annex} ({url}) ---")
                d = fetch_and_parse_date(url)
                if d:
                    date = d
                    chosen_url = url
                    break
            except Exception as e:
                print(f"Error procesando {url}: {e}")
        
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
            
            if chosen_url.endswith('.xls'):
                tmp = download_file(chosen_url, os.path.join(OUTPUT_DIR, f"COSING_Annex_{annex}_v2.xls"))
                # Conversión mejorada
                success = convert_xls_to_xlsx(tmp, dest)
                if not success:
                    print(f"⚠️ No se pudo convertir {tmp} a .xlsx. Usaremos el .xls original.")
                    dest = tmp
                else:
                    os.remove(tmp)  # Eliminar .xls temporal si la conversión fue exitosa
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
