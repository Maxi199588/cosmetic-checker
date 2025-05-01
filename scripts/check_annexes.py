#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import io
import pandas as pd
import hashlib
from github import Github

# —— CONFIGURACIÓN ——
API_BASE_URL = "https://api.tech.ec.europa.eu/cosing20/1.0/api/annexes"
ANNEX_PAGES = ["II", "III", "IV", "V", "VI"]
STATE_FILE = "annexes_state.json"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "Maxi199588/cosmetic-checker"
BRANCH = "main"
OUTPUT_DIR = "RESTRICCIONES"

# Patrón para extraer fecha "DD/MM/YYYY"
DATE_PATTERNS = [
    re.compile(r"Last update:\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Update[d]?:?\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Date:?\s*(\d{2}/\d{2}/\d{4})")
]


def load_state():
    """Carga el estado anterior del archivo STATE_FILE."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    """Guarda el estado actual en el archivo STATE_FILE."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def download_annex(annex):
    """Descarga un anexo usando la URL de API directa."""
    url = f"{API_BASE_URL}/{annex}/export-xls"
    print(f"\n--- Descargando Annex {annex} ---")
    print(f"URL: {url}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "*/*"
        }
        
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Extraer información importante de las cabeceras
        content_type = response.headers.get('Content-Type', '')
        content_disp = response.headers.get('Content-Disposition', '')
        last_modified = response.headers.get('Last-Modified', '')
        
        print(f"Respuesta exitosa. Status: {response.status_code}")
        print(f"Content-Type: {content_type}")
        print(f"Content-Disposition: {content_disp}")
        print(f"Last-Modified: {last_modified}")
        
        # Verificar que es un archivo Excel
        if 'application/vnd.ms-excel' in content_type or 'excel' in content_type.lower():
            # Guardar el archivo
            temp_file = f"temp_annex_{annex}.xls"
            
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Archivo descargado como {temp_file}")
            
            # Extraer fecha de last-modified si está disponible
            if last_modified:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(last_modified)
                    last_mod_date = dt.strftime('%d/%m/%Y')
                    print(f"Fecha de última modificación: {last_mod_date} (del encabezado HTTP)")
                    
                    # También intentamos extraer fecha del contenido del archivo
                    file_date = extract_date_from_excel(temp_file)
                    
                    # Preferir la fecha del archivo si está disponible, sino usar la del encabezado
                    if file_date:
                        print(f"Usando fecha encontrada en el archivo: {file_date}")
                        return temp_file, file_date
                    else:
                        print(f"Usando fecha del encabezado Last-Modified: {last_mod_date}")
                        return temp_file, last_mod_date
                except Exception as e:
                    print(f"Error al parsear fecha Last-Modified: {e}")
            
            # Si no pudimos extraer fecha del encabezado, intentamos del archivo
            file_date = extract_date_from_excel(temp_file)
            if file_date:
                return temp_file, file_date
            
            # Si todo falla, usamos un hash del contenido como identificador de "versión"
            file_hash = calculate_file_hash(temp_file)
            print(f"No se pudo determinar fecha. Usando hash como identificador: {file_hash[:8]}")
            return temp_file, f"hash-{file_hash[:8]}"
        
        else:
            print(f"¡El contenido descargado no es un archivo Excel! Tipo: {content_type}")
            # Guardar el contenido para diagnóstico
            with open(f"invalid_content_{annex}.bin", 'wb') as f:
                f.write(response.content)
            print(f"Contenido guardado para diagnóstico en invalid_content_{annex}.bin")
            return None, None
    
    except Exception as e:
        print(f"Error al descargar anexo {annex}: {e}")
        return None, None


def calculate_file_hash(file_path):
    """Calcula un hash MD5 del contenido del archivo."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()


def extract_date_from_excel(file_path):
    """Extrae la fecha de actualización de un archivo Excel."""
    try:
        # Detectar el tipo de archivo (siempre debería ser .xls en este caso)
        engine = 'xlrd'
            
        print(f"Leyendo {file_path} con {engine}...")
        try:
            df = pd.read_excel(file_path, engine=engine, header=None)
        except Exception as e1:
            print(f"Error con {engine}: {e1}")
            try:
                # Intentar con openpyxl como alternativa
                print("Intentando con openpyxl...")
                df = pd.read_excel(file_path, engine='openpyxl', header=None)
            except Exception as e2:
                print(f"Error con openpyxl: {e2}")
                return None
        
        print(f"Archivo leído con éxito. Filas: {len(df)}")
        
        # Buscar la fecha en las primeras 15 filas
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                try:
                    val = df.iloc[idx, col]
                    if isinstance(val, str):
                        print(f"Fila {idx+1}, Col {col+1}: {val}")
                        # Probar todos los patrones de fecha
                        for pattern in DATE_PATTERNS:
                            m = pattern.search(val)
                            if m:
                                date = m.group(1)
                                print(f"¡Fecha encontrada!: {date} en fila {idx+1}, columna {col+1}")
                                return date
                except Exception as e:
                    pass
        
        # Buscar cualquier celda que parezca una fecha
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                try:
                    val = df.iloc[idx, col]
                    if isinstance(val, pd.Timestamp) or (hasattr(val, 'strftime')):
                        date_str = val.strftime('%d/%m/%Y')
                        print(f"¡Fecha encontrada (Timestamp)!: {date_str} en fila {idx+1}, columna {col+1}")
                        return date_str
                except:
                    pass
        
        print("No se encontró ninguna fecha en el formato esperado.")
        return None
    
    except Exception as e:
        print(f"Error general al procesar el archivo Excel: {e}")
        return None


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
        return False


def commit_and_push(files, message):
    """Realiza un commit de los archivos al repositorio GitHub."""
    if not GITHUB_TOKEN:
        print("⚠️ No se ha proporcionado GITHUB_TOKEN. No se realizará el commit.")
        return
        
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
    """Función principal del script."""
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
        print(f"openpyxl instalado")
    except ImportError:
        print("⚠️ openpyxl no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "openpyxl"])

    for annex in ANNEX_PAGES:
        print(f"\n{'='*50}")
        print(f"Procesando ANNEX {annex}")
        print(f"{'='*50}")
        
        # Descargar archivo con la API directa
        downloaded_file, date = download_annex(annex)
        
        if downloaded_file and date:
            print(f"Versión identificada: {date}")
            
            new_state[annex] = date
            if state.get(annex) != date:
                print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {date}")
                # Preparar archivo para commit
                filename = f"COSING_Annex_{annex}_v2.xlsx"
                dest = os.path.join(OUTPUT_DIR, filename)
                
                # Conversión a .xlsx
                success = convert_xls_to_xlsx(downloaded_file, dest)
                if not success:
                    print(f"⚠️ No se pudo convertir a .xlsx. Usaremos el .xls original.")
                    # Copiar el archivo tal cual
                    import shutil
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(downloaded_file, dest.replace('.xlsx', '.xls'))
                    dest = dest.replace('.xlsx', '.xls')
                
                to_commit.append(dest)
            
            # Limpiar archivo temporal
            try:
                os.remove(downloaded_file)
            except:
                pass
        else:
            print(f"[WARN] No pude descargar el archivo para Annex {annex}")
            new_state[annex] = state.get(annex)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        print(f"✅ Committed {len(to_commit)} archivos.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
