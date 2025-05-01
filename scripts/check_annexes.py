#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import io
import pandas as pd
from github import Github

# —— CONFIGURACIÓN ——
BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing"
API_URL = f"{BASE_URL}/api"
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


def inspect_content(file_path):
    """Inspecciona el contenido del archivo para ver qué tipo de archivo es realmente."""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(20)  # Leer los primeros 20 bytes para inspeccionar
            
        # Detectar firmas de archivo comunes
        if header.startswith(b'PK\x03\x04'):
            print("El archivo parece ser un archivo ZIP/XLSX válido")
            return "xlsx"
        elif header.startswith(b'\xD0\xCF\x11\xE0'):
            print("El archivo parece ser un archivo OLE/XLS válido")
            return "xls"
        elif header.startswith(b'<!DOCTYPE') or header.startswith(b'<html'):
            print("El archivo parece ser HTML, no un Excel")
            
            # Leer para diagnóstico
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1000)  # Leer hasta 1000 caracteres para diagnóstico
            print(f"Contenido HTML (primeros 1000 caracteres):\n{content}")
            
            return "html"
        else:
            print(f"Tipo de archivo desconocido. Primeros bytes: {header}")
            return "unknown"
    except Exception as e:
        print(f"Error al inspeccionar el archivo: {e}")
        return "error"


def attempt_download_with_session(annex):
    """Intenta descargar el anexo utilizando una sesión para mantener cookies."""
    print(f"\n--- Intentando descarga con sesión para Annex {annex} ---")
    
    session = requests.Session()
    
    # Cabeceras para simular un navegador real
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    
    session.headers.update(headers)
    
    # 1. Primer visitar la página principal para obtener cookies
    main_url = f"{BASE_URL}/reference/annexes/list/{annex}"
    try:
        print(f"Visitando la página principal: {main_url}")
        r = session.get(main_url, timeout=30)
        r.raise_for_status()
        
        # 2. Buscar el token CSRF o cualquier otro parámetro necesario
        csrf_token = None
        csrf_pattern = re.compile(r'name="csrf_token" value="([^"]+)"')
        match = csrf_pattern.search(r.text)
        if match:
            csrf_token = match.group(1)
            print(f"Token CSRF encontrado: {csrf_token}")
        
        # 3. Intentar diferentes URLs de descarga
        download_endpoints = [
            f"{BASE_URL}/reference/annexes/download/{annex}",
            f"{BASE_URL}/reference/annexes/list/{annex}/download",
            f"{API_URL}/annex/{annex}/download",
            f"{API_URL}/annexes/{annex}/download"
        ]
        
        for endpoint in download_endpoints:
            try:
                print(f"Intentando descarga desde: {endpoint}")
                # Si tenemos un token CSRF, lo incluimos en la solicitud
                if csrf_token:
                    data = {"csrf_token": csrf_token}
                    r = session.post(endpoint, data=data, timeout=30, stream=True)
                else:
                    r = session.get(endpoint, timeout=30, stream=True)
                
                if r.status_code == 200:
                    content_type = r.headers.get('Content-Type', '')
                    content_disp = r.headers.get('Content-Disposition', '')
                    
                    print(f"Respuesta exitosa. Content-Type: {content_type}")
                    print(f"Content-Disposition: {content_disp}")
                    
                    # Determinar la extensión del archivo por la disposición del contenido
                    filename = f"temp_annex_{annex}.xlsx"
                    if 'filename=' in content_disp:
                        match = re.search(r'filename=(?:"([^"]+)"|([^;]+))', content_disp)
                        if match:
                            original_filename = match.group(1) or match.group(2)
                            print(f"Nombre de archivo original: {original_filename}")
                            
                            # Usar la extensión del archivo original si está disponible
                            if original_filename.lower().endswith('.xls'):
                                filename = f"temp_annex_{annex}.xls"
                            elif original_filename.lower().endswith('.xlsx'):
                                filename = f"temp_annex_{annex}.xlsx"
                    elif '.xls' in content_type.lower() and '.xlsx' not in content_type.lower():
                        filename = f"temp_annex_{annex}.xls"
                    
                    # Guardar el archivo
                    with open(filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print(f"Archivo descargado como {filename}")
                    
                    # Verificar qué tipo de archivo es realmente
                    file_type = inspect_content(filename)
                    
                    if file_type in ['xlsx', 'xls']:
                        return filename
                    else:
                        print(f"El archivo descargado no es un Excel válido (es {file_type})")
                        # Renombrar para depuración
                        debug_file = f"invalid_{annex}_{file_type}.bin"
                        os.rename(filename, debug_file)
                        print(f"Archivo renombrado a {debug_file} para depuración")
            
            except Exception as e:
                print(f"Error al intentar {endpoint}: {e}")
        
        # 4. Intentar descargar desde URLs directas
        direct_urls = [
            f"{BASE_URL}/assets/data/Annex_{annex}_OFFICIAL.xlsx",
            f"{BASE_URL}/assets/data/Annex_{annex.upper()}_OFFICIAL.xlsx",
            f"{BASE_URL}/assets/data/Annex_{annex}.xlsx",
            f"{BASE_URL}/assets/data/Annex_{annex}.xls",
            f"{BASE_URL}/assets/data/COSING_Annex_{annex}.xlsx",
            f"{BASE_URL}/assets/data/COSING_Annex_{annex}.xls",
            f"{BASE_URL}/assets/data/COSING_Annex_{annex}_v2.xlsx",
            f"{BASE_URL}/assets/data/COSING_Annex_{annex}_v2.xls"
        ]
        
        for direct_url in direct_urls:
            try:
                print(f"Intentando URL directa: {direct_url}")
                r = session.get(direct_url, timeout=30, stream=True)
                
                if r.status_code == 200:
                    filename = f"temp_annex_{annex}.xlsx" if direct_url.endswith('.xlsx') else f"temp_annex_{annex}.xls"
                    
                    with open(filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print(f"Archivo descargado como {filename}")
                    
                    # Verificar qué tipo de archivo es realmente
                    file_type = inspect_content(filename)
                    
                    if file_type in ['xlsx', 'xls']:
                        return filename
                    else:
                        print(f"El archivo descargado no es un Excel válido (es {file_type})")
                        # Renombrar para depuración
                        debug_file = f"invalid_{annex}_{file_type}.bin"
                        os.rename(filename, debug_file)
                        print(f"Archivo renombrado a {debug_file} para depuración")
            
            except Exception as e:
                print(f"Error al intentar {direct_url}: {e}")
    
    except Exception as e:
        print(f"Error durante la sesión: {e}")
    
    return None


def download_annex_alternate_formats(annex):
    """Intenta descargar formatos alternativos del anexo."""
    print(f"\n--- Probando formatos alternativos para Annex {annex} ---")
    
    # Probar con nombres de archivo alternativos y en diferentes subcarpetas
    alternative_urls = [
        f"{BASE_URL}/assets/documents/annexes/annex_{annex.lower()}.xlsx",
        f"{BASE_URL}/assets/documents/annex_{annex.lower()}.xlsx",
        f"{BASE_URL}/assets/files/annex_{annex}.xlsx",
        f"{BASE_URL}/docs/annex_{annex}.xlsx",
        f"{BASE_URL}/documents/annex_{annex}.xlsx",
        # Versiones en PDF por si acaso
        f"{BASE_URL}/assets/data/Annex_{annex}.pdf",
        f"{BASE_URL}/assets/data/COSING_Annex_{annex}.pdf",
        f"{BASE_URL}/reference/annexes/pdf/{annex}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    for url in alternative_urls:
        try:
            print(f"Probando: {url}")
            r = requests.head(url, headers=headers, timeout=10)
            
            if r.status_code == 200:
                print(f"¡URL exitosa!: {url}")
                r = requests.get(url, headers=headers, timeout=30, stream=True)
                
                # Determinar la extensión basada en la URL
                ext = url.split('.')[-1].lower() if '.' in url else 'xlsx'
                filename = f"temp_annex_{annex}.{ext}"
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"Archivo descargado como {filename}")
                
                # Si es un PDF, no podemos extraer la fecha directamente
                if ext == 'pdf':
                    print("Archivo PDF descargado. No se puede extraer fecha automáticamente.")
                    return None
                
                # Verificar qué tipo de archivo es realmente
                file_type = inspect_content(filename)
                
                if file_type in ['xlsx', 'xls']:
                    return filename
        
        except Exception as e:
            print(f"Error al probar {url}: {e}")
    
    return None


def extract_date_from_excel(file_path):
    """Extrae la fecha de actualización de un archivo Excel."""
    try:
        # Verificar primero qué tipo de archivo es realmente
        file_type = inspect_content(file_path)
        
        if file_type not in ['xlsx', 'xls']:
            print(f"El archivo no es un Excel válido ({file_type})")
            return None
        
        # Detectar el tipo de archivo por la extensión
        if file_path.endswith('.xlsx'):
            engine = 'openpyxl'
        else:
            engine = 'xlrd'
            
        print(f"Leyendo {file_path} con {engine}...")
        try:
            df = pd.read_excel(file_path, engine=engine, header=None)
        except Exception as e1:
            print(f"Error con {engine}: {e1}")
            # Intentar con el otro motor
            try:
                alternate_engine = 'xlrd' if engine == 'openpyxl' else 'openpyxl'
                print(f"Intentando con {alternate_engine}...")
                df = pd.read_excel(file_path, engine=alternate_engine, header=None)
            except Exception as e2:
                print(f"Error con {alternate_engine}: {e2}")
                # Último intento con opciones adicionales
                try:
                    print("Último intento con opciones adicionales...")
                    if engine == 'xlrd':
                        # Para xlrd
                        import xlrd
                        xls = xlrd.open_workbook(file_path, logfile=open(os.devnull, 'w'))
                        sheet = xls.sheet_by_index(0)
                        # Convertir a dataframe
                        data = []
                        for i in range(sheet.nrows):
                            row = []
                            for j in range(sheet.ncols):
                                row.append(sheet.cell_value(i, j))
                            data.append(row)
                        df = pd.DataFrame(data)
                    else:
                        # Para openpyxl
                        from openpyxl import load_workbook
                        wb = load_workbook(file_path, read_only=True, data_only=True)
                        sheet = wb.active
                        # Convertir a dataframe
                        data = []
                        for row in sheet.rows:
                            data.append([cell.value for cell in row])
                        df = pd.DataFrame(data)
                except Exception as e3:
                    print(f"Todos los intentos fallaron: {e3}")
                    return None
        
        print(f"Archivo leído con éxito. Filas: {len(df)}, Columnas: {len(df.columns)}")
        
        # Imprimir las primeras filas para diagnóstico
        print("Primeras filas del archivo:")
        for i in range(min(10, len(df))):
            row_values = []
            for j in range(min(5, len(df.columns))):
                try:
                    val = df.iloc[i, j]
                    row_values.append(str(val)[:50])  # Limitar a 50 caracteres para legibilidad
                except:
                    row_values.append("ERROR")
            print(f"Fila {i+1}: {' | '.join(row_values)}")
        
        # Buscar la fecha en las primeras 15 filas
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                try:
                    val = df.iloc[idx, col]
                    if isinstance(val, str):
                        # Probar todos los patrones de fecha
                        for pattern in DATE_PATTERNS:
                            m = pattern.search(val)
                            if m:
                                date = m.group(1)
                                print(f"¡Fecha encontrada!: {date} en fila {idx+1}, columna {col+1}")
                                return date
                except Exception as e:
                    print(f"Error al leer celda ({idx}, {col}): {e}")
        
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
        print(f"openpyxl version: {openpyxl.__VERSION__}" if hasattr(openpyxl, '__VERSION__') else f"openpyxl instalado")
    except ImportError:
        print("⚠️ openpyxl no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "openpyxl"])

    for annex in ANNEX_PAGES:
        print(f"\n{'='*50}")
        print(f"Procesando ANNEX {annex}")
        print(f"{'='*50}")
        
        # Intentar descargar con sesión (simulando un navegador)
        downloaded_file = attempt_download_with_session(annex)
        
        # Si falla, probar con formatos alternativos
        if not downloaded_file:
            downloaded_file = download_annex_alternate_formats(annex)
        
        if downloaded_file:
            # Extraer fecha del archivo
            date = extract_date_from_excel(downloaded_file)
            
            if date:
                print(f"Fecha encontrada: {date}")
                
                new_state[annex] = date
                if state.get(annex) != date:
                    print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {date}")
                    # Preparar archivo para commit
                    filename = f"COSING_Annex_{annex}_v2.xlsx"
                    dest = os.path.join(OUTPUT_DIR, filename)
                    
                    if downloaded_file.endswith('.xls'):
                        # Conversión a .xlsx
                        success = convert_xls_to_xlsx(downloaded_file, dest)
                        if not success:
                            print(f"⚠️ No se pudo convertir a .xlsx. Usaremos el .xls original.")
                            # Copiar el archivo tal cual
                            import shutil
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(downloaded_file, dest.replace('.xlsx', '.xls'))
                            dest = dest.replace('.xlsx', '.xls')
                    else:
                        # Copiar el archivo tal cual
                        import shutil
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(downloaded_file, dest)
                    
                    to_commit.append(dest)
                
                # Limpiar archivo temporal
                try:
                    os.remove(downloaded_file)
                except:
                    pass
            else:
                print(f"[WARN] No pude leer la fecha en Annex {annex}")
                new_state[annex] = state.get(annex)
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
