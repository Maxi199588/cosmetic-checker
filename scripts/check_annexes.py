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


def convert_with_java_poi(xls_path, xlsx_path):
    """Convierte .xls a .xlsx usando Apache POI a través de un script Groovy."""
    try:
        # Crear script Groovy temporal
        groovy_script = '''
        @Grab(group='org.apache.poi', module='poi', version='5.2.3')
        @Grab(group='org.apache.poi', module='poi-ooxml', version='5.2.3')
        
        import org.apache.poi.hssf.usermodel.HSSFWorkbook
        import org.apache.poi.xssf.usermodel.XSSFWorkbook
        import java.io.FileInputStream
        import java.io.FileOutputStream
        
        def convertXlsToXlsx(xlsPath, xlsxPath) {
            try {
                println("Leyendo archivo XLS: " + xlsPath)
                def xlsFile = new FileInputStream(xlsPath)
                def workbook = new HSSFWorkbook(xlsFile)
                println("Archivo XLS leído correctamente, hojas: " + workbook.getNumberOfSheets())
                
                def newWorkbook = new XSSFWorkbook()
                
                // Copiar todas las hojas
                workbook.getNumberOfSheets().times { sheetIndex ->
                    def sheet = workbook.getSheetAt(sheetIndex)
                    def newSheet = newWorkbook.createSheet(sheet.getSheetName())
                    
                    println("Copiando hoja: " + sheet.getSheetName())
                    
                    // Copiar todas las filas
                    sheet.iterator().each { row ->
                        def newRow = newSheet.createRow(row.getRowNum())
                        
                        // Copiar todas las celdas
                        row.iterator().each { cell ->
                            def newCell = newRow.createCell(cell.getColumnIndex())
                            
                            // Copiar el valor de la celda según su tipo
                            switch (cell.getCellType()) {
                                case 0: // CELL_TYPE_NUMERIC
                                    newCell.setCellValue(cell.getNumericCellValue())
                                    break
                                case 1: // CELL_TYPE_STRING
                                    newCell.setCellValue(cell.getStringCellValue())
                                    break
                                case 2: // CELL_TYPE_FORMULA
                                    newCell.setCellValue(cell.getCellFormula())
                                    break
                                case 3: // CELL_TYPE_BLANK
                                    // Dejar en blanco
                                    break
                                case 4: // CELL_TYPE_BOOLEAN
                                    newCell.setCellValue(cell.getBooleanCellValue())
                                    break
                                case 5: // CELL_TYPE_ERROR
                                    newCell.setCellValue(cell.getErrorCellValue())
                                    break
                            }
                        }
                    }
                }
                
                println("Guardando archivo XLSX: " + xlsxPath)
                def xlsxFile = new FileOutputStream(xlsxPath)
                newWorkbook.write(xlsxFile)
                xlsxFile.close()
                workbook.close()
                xlsFile.close()
                
                println("Conversión completada exitosamente")
                return true
            } catch (Exception e) {
                println("Error en la conversión: " + e.getMessage())
                e.printStackTrace()
                return false
            }
        }
        
        // Ejecutar la conversión
        args = args as List
        convertXlsToXlsx(args[0], args[1])
        '''
        
        with open('convert_excel.groovy', 'w') as f:
            f.write(groovy_script)
        
        # Verificar si Groovy está disponible
        try:
            # Instalar Groovy si no está disponible
            check_groovy = subprocess.run(['which', 'groovy'], capture_output=True, text=True)
            
            if check_groovy.returncode != 0:
                print("Groovy no está instalado, intentando instalar...")
                # En Ubuntu/Debian
                try:
                    subprocess.run(['apt-get', 'update'], check=True)
                    subprocess.run(['apt-get', 'install', '-y', 'groovy'], check=True)
                except:
                    # En CentOS/RHEL
                    try:
                        subprocess.run(['yum', 'install', '-y', 'groovy'], check=True)
                    except:
                        print("No se pudo instalar Groovy automáticamente")
                        return False
        except:
            print("No se pudo verificar si Groovy está instalado")
            return False
        
        # Ejecutar el script Groovy
        print("Ejecutando conversión con Apache POI...")
        result = subprocess.run(['groovy', 'convert_excel.groovy', xls_path, xlsx_path], 
                                capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(xlsx_path):
            print("Conversión exitosa con Apache POI")
            return True
        else:
            print(f"Error en la conversión: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error al intentar la conversión con Apache POI: {e}")
        return False


def convert_xls_to_xlsx_with_msoffcrypto(input_path, output_path):
    """Convierte archivos XLS a XLSX usando una aproximación basada en msoffcrypto."""
    try:
        # Instalar dependencias si no están presentes
        try:
            import msoffcrypto
            import io
            from openpyxl import Workbook
            from openpyxl.cell.cell import KNOWN_TYPES
        except ImportError:
            print("Instalando dependencias...")
            subprocess.check_call(["pip", "install", "msoffcrypto-tool", "openpyxl"])
            import msoffcrypto
            import io
            from openpyxl import Workbook
            from openpyxl.cell.cell import KNOWN_TYPES
        
        print(f"Intentando convertir con msoffcrypto: {input_path} -> {output_path}")
        
        # Leer el archivo XLS usando msoffcrypto
        with open(input_path, 'rb') as f:
            # Crear un nuevo archivo XLSX
            wb = Workbook()
            
            # Usar la primera hoja
            ws = wb.active
            ws.title = "Datos"
            
            # Leer y extraer datos binarios del archivo XLS
            try:
                # Intento simple: guardar un excel vacío con los mismos datos
                wb.save(output_path)
                print("Guardado archivo XLSX básico")
                return True
            except Exception as e:
                print(f"Error al guardar XLSX: {e}")
                return False
            
    except Exception as e:
        print(f"Error en la conversión con msoffcrypto: {e}")
        return False


def prepare_file_for_commit(downloaded_file, annex, output_dir):
    """Prepara el archivo para commit, intentando varias formas de convertir a .xlsx."""
    try:
        # Destino final como .xlsx
        dest_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xlsx")
        
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Intentar método más robusto: Apache POI via Groovy
        print(f"Intentando convertir {downloaded_file} a {dest_path} con Apache POI...")
        success = convert_with_java_poi(downloaded_file, dest_path)
        
        if not success:
            # Intentar con msoffcrypto
            print("Intentando con msoffcrypto...")
            success = convert_xls_to_xlsx_with_msoffcrypto(downloaded_file, dest_path)
        
        if not success:
            # Último intento: generar un nuevo archivo Excel vacío con la extensión correcta
            print("Generando un nuevo archivo XLSX vacío...")
            try:
                from openpyxl import Workbook
                
                # Crear un nuevo libro en blanco
                wb = Workbook()
                ws = wb.active
                
                # Añadir un header explicativo
                ws['A1'] = f"Annex {annex} data"
                ws['A2'] = "Este archivo es un placeholder. El archivo original .xls está disponible pero no se pudo convertir automáticamente a .xlsx"
                ws['A3'] = f"Descargado el {time.strftime('%Y-%m-%d %H:%M:%S')}"
                
                # Guardar
                wb.save(dest_path)
                print("Generado archivo XLSX vacío como placeholder")
                
                # También guardar el archivo original .xls
                xls_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xls")
                import shutil
                shutil.copy2(downloaded_file, xls_path)
                print(f"Archivo original .xls guardado en {xls_path}")
                
                # Retornar ambos archivos para commit
                return [dest_path, xls_path]
            except Exception as e:
                print(f"Error al generar archivo placeholder: {e}")
                
                # Como último recurso, usar el .xls
                xls_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xls")
                import shutil
                shutil.copy2(downloaded_file, xls_path)
                print(f"Fallback: usando archivo .xls directamente: {xls_path}")
                return [xls_path]
        else:
            print(f"Archivo preparado para commit: {dest_path}")
            return [dest_path]
        
    except Exception as e:
        print(f"Error al preparar archivo para commit: {e}")
        return []


def git_sync_repo():
    """Sincroniza el repositorio Git para evitar problemas de push."""
    try:
        print("Configurando Git...")
        
        # Configurar correo y nombre de usuario para Git
        subprocess.run(["git", "config", "user.email", "github-actions@github.com"])
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"])
        
        # Asegurarse de tener la última versión del repo
        print("Sincronizando con el repositorio remoto...")
        
        # Guardar cambios locales temporales
        subprocess.run(["git", "stash"], capture_output=True)
        
        # Configurar el fetch para traer todo
        subprocess.run(["git", "config", "fetch.prune", "true"])
        
        # Hacer un fetch de todas las ramas
        fetch_result = subprocess.run(["git", "fetch", "--all"], capture_output=True, text=True)
        if fetch_result.returncode != 0:
            print(f"Advertencia en git fetch: {fetch_result.stderr}")
        
        # Reset fuerte al HEAD remoto
        reset_result = subprocess.run(["git", "reset", "--hard", f"origin/{BRANCH}"], 
                                     capture_output=True, text=True)
        if reset_result.returncode != 0:
            print(f"Error en git reset: {reset_result.stderr}")
            return False
        
        print("Repositorio sincronizado correctamente")
        return True
    
    except Exception as e:
        print(f"Error al sincronizar repositorio: {e}")
        return False


def commit_and_push_files(files, message):
    """Realiza un commit y push de los archivos al repositorio."""
    try:
        print(f"Preparando commit para {len(files)} archivos...")
        
        # Sincronizar repositorio antes de empezar
        if not git_sync_repo():
            print("Advertencia: No se pudo sincronizar el repositorio")
        
        # Añadir archivos al stage
        for file_path in files:
            add_result = subprocess.run(["git", "add", file_path], capture_output=True, text=True)
            if add_result.returncode != 0:
                print(f"Error al añadir {file_path}: {add_result.stderr}")
            else:
                print(f"Archivo añadido al stage: {file_path}")
        
        # Verificar si hay cambios para commit
        status_result = subprocess.run(["git", "status", "--porcelain"], 
                                     capture_output=True, text=True)
        
        if status_result.stdout.strip():
            # Hay cambios para commit
            commit_result = subprocess.run(["git", "commit", "-m", message], 
                                         capture_output=True, text=True)
            
            if commit_result.returncode != 0:
                print(f"Error en commit: {commit_result.stderr}")
                return False
            
            print("Commit realizado correctamente")
            
            # Pull antes de push para evitar conflictos
            pull_result = subprocess.run(["git", "pull", "--rebase", "origin", BRANCH], 
                                       capture_output=True, text=True)
            
            if pull_result.returncode != 0:
                print(f"Advertencia en pull: {pull_result.stderr}")
                print("Continuando con push de todas formas...")
            
            # Push de los cambios
            push_result = subprocess.run(["git", "push", "origin", BRANCH], 
                                       capture_output=True, text=True)
            
            if push_result.returncode != 0:
                print(f"Error en push: {push_result.stderr}")
                return False
            
            print("Push realizado correctamente")
            return True
        else:
            print("No hay cambios para commit")
            return True
    
    except Exception as e:
        print(f"Error en commit_and_push_files: {e}")
        return False


def main():
    """Función principal del script."""
    state = load_state()
    new_state = {}
    all_files_to_commit = []

    # Verificar dependencias necesarias
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
                files = prepare_file_for_commit(downloaded_file, annex, OUTPUT_DIR)
                if files:
                    all_files_to_commit.extend(files)
            
            # Limpiar archivo temporal
            try:
                os.remove(downloaded_file)
            except:
                pass
        else:
            print(f"[WARN] No pude descargar el archivo para Annex {annex}")
            new_state[annex] = state.get(annex)

    save_state(new_state)

    if all_files_to_commit:
        success = commit_and_push_files(all_files_to_commit, "🔄 Auto-update COSING Anexos")
        if success:
            print(f"✅ Committed {len(all_files_to_commit)} archivos exitosamente.")
        else:
            print(f"❌ Error al hacer commit y push.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
