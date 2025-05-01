#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import io
import hashlib
import subprocess
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
                    return temp_file, last_mod_date
                except Exception as e:
                    print(f"Error al parsear fecha Last-Modified: {e}")
            
            # Si no pudimos extraer fecha del encabezado, usamos un hash
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


def convert_xls_to_xlsx_with_pyexcel(xls_path, xlsx_path):
    """Convierte archivo .xls a .xlsx usando pyexcel."""
    try:
        print(f"Intentando convertir {xls_path} a {xlsx_path} con pyexcel...")
        
        # Intentar instalar pyexcel si no está instalado
        try:
            import pyexcel
            import pyexcel_xls
            import pyexcel_xlsx
        except ImportError:
            print("Instalando pyexcel y módulos necesarios...")
            subprocess.check_call(["pip", "install", "pyexcel", "pyexcel-xls", "pyexcel-xlsx"])
            import pyexcel
            import pyexcel_xls
            import pyexcel_xlsx
        
        # Cargar y guardar con pyexcel
        pyexcel.save_book_as(file_name=xls_path, dest_file_name=xlsx_path)
        print(f"Conversión exitosa con pyexcel")
        return True
    except Exception as e:
        print(f"Error con pyexcel: {e}")
        
        # Intento alternativo con LibreOffice si está disponible
        try:
            print("Intentando convertir con LibreOffice...")
            # Comprobar si LibreOffice está disponible
            which_result = subprocess.run(["which", "libreoffice"], capture_output=True, text=True)
            
            if which_result.returncode == 0:
                # Usar LibreOffice para la conversión
                cmd = ['libreoffice', '--headless', '--convert-to', 'xlsx', '--outdir', 
                       os.path.dirname(xlsx_path), xls_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("Conversión exitosa con LibreOffice")
                    # Renombrar el archivo si es necesario
                    source_name = os.path.basename(xls_path).replace('.xls', '.xlsx')
                    source_path = os.path.join(os.path.dirname(xlsx_path), source_name)
                    if source_path != xlsx_path and os.path.exists(source_path):
                        os.rename(source_path, xlsx_path)
                    return True
                else:
                    print(f"Error en LibreOffice: {result.stderr}")
            else:
                print("LibreOffice no está disponible")
        except Exception as e2:
            print(f"Error con LibreOffice: {e2}")
        
        # Último intento: Simplemente cambiar la extensión del archivo
        try:
            print("Último intento: copia directa y cambio de extensión...")
            import shutil
            shutil.copy2(xls_path, xlsx_path)
            print("Archivo copiado y extensión cambiada")
            return True
        except Exception as e3:
            print(f"Error en el último intento: {e3}")
        
        return False


def prepare_file_for_commit(downloaded_file, annex, output_dir):
    """Prepara el archivo para commit, convirtiendo de .xls a .xlsx."""
    try:
        # Destino final como .xlsx
        dest_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xlsx")
        
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Intentar convertir de .xls a .xlsx
        success = convert_xls_to_xlsx_with_pyexcel(downloaded_file, dest_path)
        
        if success:
            print(f"Archivo preparado para commit: {dest_path}")
            return dest_path
        else:
            print(f"No se pudo convertir a .xlsx. Usando .xls como fallback.")
            # Como fallback, usar el archivo .xls original
            fallback_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xls")
            import shutil
            shutil.copy2(downloaded_file, fallback_path)
            return fallback_path
    
    except Exception as e:
        print(f"Error al preparar archivo para commit: {e}")
        return None


def git_pull_before_push():
    """Realiza un git pull antes de intentar hacer push."""
    try:
        print("Ejecutando git pull para actualizar el repositorio local...")
        
        # Configurar correo y nombre de usuario para Git
        subprocess.run(["git", "config", "user.email", "github-actions@github.com"])
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"])
        
        # Intentar hacer pull
        result = subprocess.run(["git", "pull", "--rebase", "origin", BRANCH], 
                                capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Git pull exitoso")
            return True
        else:
            print(f"Error en git pull: {result.stderr}")
            # Si hay conflictos, intentar abortar el rebase
            subprocess.run(["git", "rebase", "--abort"])
            # Intentar hacer un pull normal
            result = subprocess.run(["git", "pull", "origin", BRANCH], 
                                    capture_output=True, text=True)
            if result.returncode == 0:
                print("Git pull alternativo exitoso")
                return True
            else:
                print(f"Error en git pull alternativo: {result.stderr}")
                return False
    
    except Exception as e:
        print(f"Error al ejecutar git pull: {e}")
        return False


def commit_and_push(files, message):
    """Realiza un commit de los archivos al repositorio GitHub."""
    if not GITHUB_TOKEN:
        print("⚠️ No se ha proporcionado GITHUB_TOKEN. No se realizará el commit.")
        return False
    
    try:
        # Primero intentar hacerlo con PyGithub
        try:
            gh = Github(GITHUB_TOKEN)
            repo = gh.get_repo(REPO_NAME)
            
            for file_path in files:
                if not os.path.exists(file_path):
                    print(f"⚠️ Archivo no encontrado: {file_path}")
                    continue
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                try:
                    # Verificar si el archivo ya existe
                    try:
                        existing = repo.get_contents(file_path, ref=BRANCH)
                        repo.update_file(file_path, message, content, existing.sha, branch=BRANCH)
                        print(f"Archivo actualizado: {file_path}")
                    except:
                        # Si no existe, crearlo
                        repo.create_file(file_path, message, content, branch=BRANCH)
                        print(f"Archivo creado: {file_path}")
                except Exception as e:
                    print(f"Error al subir {file_path}: {e}")
            
            return True
        
        except Exception as e:
            print(f"Error con PyGithub: {e}")
            print("Intentando con comandos git directos...")
            
            # Si falla, intentar con comandos git directos
            # Primero hacer pull
            if not git_pull_before_push():
                print("No se pudo actualizar el repositorio. Intentando continuar...")
            
            # Añadir archivos
            for file_path in files:
                subprocess.run(["git", "add", file_path])
            
            # Commit
            subprocess.run(["git", "commit", "-m", message])
            
            # Push
            push_result = subprocess.run(["git", "push", "origin", BRANCH], 
                                        capture_output=True, text=True)
            
            if push_result.returncode == 0:
                print("Push exitoso con git directo")
                return True
            else:
                print(f"Error en git push: {push_result.stderr}")
                return False
    
    except Exception as e:
        print(f"Error general en commit_and_push: {e}")
        return False


def main():
    """Función principal del script."""
    state = load_state()
    new_state = {}
    to_commit = []

    # Verificar dependencias necesarias
    try:
        import xlrd
        print(f"xlrd version: {xlrd.__VERSION__}")
    except (ImportError, AttributeError):
        try:
            import xlrd
            print(f"xlrd instalado")
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
                
                # Preparar archivo para commit (convirtiendo a .xlsx)
                dest_path = prepare_file_for_commit(downloaded_file, annex, OUTPUT_DIR)
                if dest_path:
                    to_commit.append(dest_path)
            
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
        success = commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        if success:
            print(f"✅ Committed {len(to_commit)} archivos exitosamente.")
        else:
            print(f"❌ Error al hacer commit y push.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
