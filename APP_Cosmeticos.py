import streamlit as st
import pandas as pd
import re
import os
import requests
import time
import json
from io import BytesIO
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
)
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

# -----------------------------------------------------------
# FUNCIÓN PARA GENERAR REPORTE PDF
# -----------------------------------------------------------
def generar_reporte_pdf(resultados):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1*inch, rightMargin=1*inch,
        topMargin=1*inch, bottomMargin=1*inch
    )
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    h2     = styles['Heading2']
    h3     = styles['Heading3']
    bold   = ParagraphStyle(name='Bold', parent=normal, fontName='Helvetica-Bold')

    elementos = []
    # Título
    elementos.append(Paragraph(
        "Reporte de Búsqueda de CAS en Anexos de Restricciones",
        styles['Title']
    ))
    elementos.append(Spacer(1, 12))

    primera = True
    for cas_num, res in resultados.items():
        # salto de página entre cada CAS, excepto antes del primero
        if not primera:
            elementos.append(PageBreak())
        primera = False

        # Encabezado CAS
        elementos.append(Paragraph(f"CAS: {cas_num}", h2))
        elementos.append(Spacer(1, 6))

        if not res["encontrado"]:
            elementos.append(Paragraph("No encontrado en ningún anexo.", normal))
            elementos.append(Spacer(1, 12))
            continue

        # Para cada anexo donde se encontró
        for anexo in res["anexos"]:
            elementos.append(Paragraph(anexo['nombre'], h3))
            elementos.append(Spacer(1, 4))

            df = anexo['data'].reset_index(drop=True)
            # Por cada fila del DataFrame
            for _, row in df.iterrows():
                # Para cada par columna→valor
                for col, val in row.items():
                    texto = f"<b>{col}:</b> {'' if pd.isna(val) else val}"
                    elementos.append(Paragraph(texto, normal))
                    elementos.append(Spacer(1, 2))
                # separación entre filas
                elementos.append(Spacer(1, 6))

    # Construir el PDF
    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# -----------------------------------------------------------
# FUNCIÓN PARA CARGAR TODOS LOS ARCHIVOS
# -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data():
    is_cloud = os.environ.get('STREAMLIT_SHARING', '') == 'true'
    base_path = "." if is_cloud else os.path.dirname(os.path.abspath(__file__))
    restr_path = os.path.join(base_path, "RESTRICCIONES")
    cas_path   = os.path.join(base_path, "CAS", "COSING_Ingredients-Fragrance Inventory_v2.xlsx")

    info_carga = []

    # Carga de Annexes II a VI
    def load_annex(name, filename, skip):
        df = pd.DataFrame()
        path = os.path.join(restr_path, filename)
        try:
            df = pd.read_excel(path, skiprows=skip, header=0, engine="openpyxl")
            df.columns = df.columns.str.strip()
            info_carga.append(f"✅ {name}: {len(df)} filas")
        except Exception as e:
            info_carga.append(f"❌ Error {name}: {e}")
        return df

    annex_ii  = load_annex("Annex II",  "COSING_Annex_II_v2.xlsx", 7)
    annex_iii = load_annex("Annex III", "COSING_Annex_III_v2.xlsx",7)
    annex_iv  = load_annex("Annex IV",  "COSING_Annex_IV_v2.xlsx", 7)
    annex_v   = load_annex("Annex V",   "COSING_Annex_V_v2.xlsx",  7)
    annex_vi  = load_annex("Annex VI",  "COSING_Annex_VI_v2.xlsx", 7)

    # Carga de MERCOSUR Prohibidas (fila 6 → skiprows=5)
    mercosur = pd.DataFrame()
    try:
        path = os.path.join(restr_path, "07 MERCOSUR_062_2014_PROHIBIDAS.xlsx")
        mercosur = pd.read_excel(path, skiprows=5, header=0, engine="openpyxl")
        mercosur.columns = mercosur.columns.str.strip()
        info_carga.append(f"✅ MERCOSUR Prohibidas: {len(mercosur)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error MERCOSUR Prohibidas: {e}")

    # Carga de la base CAS
    cas_db = pd.DataFrame()
    try:
        cas_db = pd.read_excel(cas_path, skiprows=7, header=0, engine="openpyxl")
        cas_db.columns = cas_db.columns.str.strip()
        if "INCI name" in cas_db.columns:
            cas_db.rename(columns={"INCI name": "Ingredient"}, inplace=True)
        info_carga.append(f"✅ Base CAS: {len(cas_db)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error Base CAS: {e}")

    return annex_ii, annex_iii, annex_iv, annex_v, annex_vi, mercosur, cas_db, info_carga

# -----------------------------------------------------------
# FUNCIÓN PARA BÚSQUEDA EN PUBCHEM POR CAS
# -----------------------------------------------------------
def buscar_cas_en_pubchem(cas_number):
    """
    Busca un número CAS en PubChem y devuelve información relevante.
    """
    try:
        # Primero, buscar el CAS para obtener el CompoundID (CID)
        search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas_number}/cids/JSON"
        response = requests.get(search_url)
        
        if response.status_code != 200:
            return {
                'encontrado': False,
                'error': f"Error en la búsqueda: Código {response.status_code}",
                'mensaje': "No se encontró el CAS en PubChem"
            }
        
        data = response.json()
        
        if 'IdentifierList' not in data or 'CID' not in data['IdentifierList'] or not data['IdentifierList']['CID']:
            return {
                'encontrado': False,
                'error': "No se encontró un CID válido",
                'mensaje': "PubChem no tiene registros para este número CAS"
            }
        
        # Obtener el CID
        cid = data['IdentifierList']['CID'][0]
        
        # Obtener información detallada usando el CID
        info_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,IUPACName,InChIKey,CanonicalSMILES/JSON"
        info_response = requests.get(info_url)
        
        if info_response.status_code != 200:
            return {
                'encontrado': True,
                'cid': cid,
                'error': f"Error obteniendo detalles: Código {info_response.status_code}",
                'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
            }
        
        info_data = info_response.json()
        properties = info_data['PropertyTable']['Properties'][0]
        
        # Obtener sinónimos
        synonyms_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
        synonyms_response = requests.get(synonyms_url)
        
        synonyms = []
        if synonyms_response.status_code == 200:
            synonyms_data = synonyms_response.json()
            if 'InformationList' in synonyms_data and 'Information' in synonyms_data['InformationList']:
                synonyms = synonyms_data['InformationList']['Information'][0].get('Synonym', [])
                # Limitar a máximo 10 sinónimos para no sobrecargar la UI
                synonyms = synonyms[:10] if len(synonyms) > 10 else synonyms
        
        return {
            'encontrado': True,
            'cid': cid,
            'nombre_iupac': properties.get('IUPACName', 'No disponible'),
            'formula': properties.get('MolecularFormula', 'No disponible'),
            'peso_molecular': properties.get('MolecularWeight', 'No disponible'),
            'inchikey': properties.get('InChIKey', 'No disponible'),
            'smiles': properties.get('CanonicalSMILES', 'No disponible'),
            'sinonimos': synonyms,
            'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        }
    
    except Exception as e:
        return {
            'encontrado': False,
            'error': str(e),
            'mensaje': "Error al conectar con PubChem"
        }

# -----------------------------------------------------------
# FUNCIÓN PARA BÚSQUEDA EN PUBCHEM POR NOMBRE DE INGREDIENTE
# -----------------------------------------------------------
def buscar_ingrediente_en_pubchem(nombre_ingrediente):
    """
    Busca un ingrediente por nombre en PubChem y devuelve información relevante.
    """
    try:
        # Primero, buscar el nombre para obtener el CompoundID (CID)
        search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{nombre_ingrediente}/cids/JSON"
        response = requests.get(search_url)
        
        if response.status_code != 200:
            return {
                'encontrado': False,
                'error': f"Error en la búsqueda: Código {response.status_code}",
                'mensaje': f"No se encontró '{nombre_ingrediente}' en PubChem",
                'input': nombre_ingrediente
            }
        
        data = response.json()
        
        if 'IdentifierList' not in data or 'CID' not in data['IdentifierList'] or not data['IdentifierList']['CID']:
            return {
                'encontrado': False,
                'error': "No se encontró un CID válido",
                'mensaje': f"PubChem no tiene registros para '{nombre_ingrediente}'",
                'input': nombre_ingrediente
            }
        
        # Obtener el CID
        cid = data['IdentifierList']['CID'][0]
        
        # Obtener información detallada usando el CID
        info_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,IUPACName,InChIKey,CanonicalSMILES/JSON"
        info_response = requests.get(info_url)
        
        if info_response.status_code != 200:
            return {
                'encontrado': True,
                'cid': cid,
                'input': nombre_ingrediente,
                'error': f"Error obteniendo detalles: Código {info_response.status_code}",
                'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
            }
        
        info_data = info_response.json()
        properties = info_data['PropertyTable']['Properties'][0]
        
        # Obtener sinónimos
        synonyms_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
        synonyms_response = requests.get(synonyms_url)
        
        synonyms = []
        if synonyms_response.status_code == 200:
            synonyms_data = synonyms_response.json()
            if 'InformationList' in synonyms_data and 'Information' in synonyms_data['InformationList']:
                synonyms = synonyms_data['InformationList']['Information'][0].get('Synonym', [])
                # Limitar a máximo 10 sinónimos para no sobrecargar la UI
                synonyms = synonyms[:10] if len(synonyms) > 10 else synonyms
        
        # Intentar obtener el número CAS
        cas_number = None
        if synonyms:
            # Buscar patrones como "CAS-xxxxx" o "xxxxx-xx-x" (formato CAS común)
            cas_pattern = re.compile(r'(?:CAS[ -]+)?(\d{1,7}-\d{2}-\d{1})')
            for syn in synonyms:
                cas_match = cas_pattern.search(syn)
                if cas_match:
                    cas_number = cas_match.group(1)
                    break
        
        return {
            'encontrado': True,
            'cid': cid,
            'input': nombre_ingrediente,
            'nombre_iupac': properties.get('IUPACName', 'No disponible'),
            'formula': properties.get('MolecularFormula', 'No disponible'),
            'peso_molecular': properties.get('MolecularWeight', 'No disponible'),
            'inchikey': properties.get('InChIKey', 'No disponible'),
            'smiles': properties.get('CanonicalSMILES', 'No disponible'),
            'sinonimos': synonyms,
            'cas_number': cas_number,
            'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        }
    
    except Exception as e:
        return {
            'encontrado': False,
            'error': str(e),
            'mensaje': f"Error al conectar con PubChem para '{nombre_ingrediente}'",
            'input': nombre_ingrediente
        }

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR MÚLTIPLES ELEMENTOS EN PUBCHEM
# -----------------------------------------------------------
def buscar_lista_en_pubchem(lista, por_cas=True):
    """
    Busca múltiples números CAS o nombres de ingredientes en PubChem con un retraso para evitar sobrecargar la API.
    """
    resultados = {}
    
    for i, elemento in enumerate(lista):
        if i > 0:  # Añadir delay entre peticiones excepto para la primera
            time.sleep(1)  # 1 segundo de retraso para respetar límites de la API
        
        if por_cas:
            mensaje = f"Buscando CAS {elemento} en PubChem..."
            resultado = buscar_cas_en_pubchem(elemento)
        else:
            mensaje = f"Buscando ingrediente '{elemento}' en PubChem..."
            resultado = buscar_ingrediente_en_pubchem(elemento)
        
        with st.spinner(mensaje):
            resultados[elemento] = resultado
    
    return resultados

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR CAS EN RESTRICCIONES
# -----------------------------------------------------------
def buscar_cas_en_restricciones(cas_list, mostrar_info=False):
    resultados = {}
    
    for cas_number in cas_list:
        resultados[cas_number] = {"encontrado": False, "anexos": []}
        
        if mostrar_info:
            st.markdown(f"### Buscando CAS: {cas_number}")
        
        # Caso especial para 51-84-3
        if cas_number == "51-84-3":
            if mostrar_info:
                st.write("Buscando específicamente en Annex II, columna 'CAS Number'...")
            
            if 'CAS Number' in annex_ii.columns:
                # Búsqueda por contenido en lugar de coincidencia exacta
                matches = annex_ii[annex_ii['CAS Number'].astype(str).str.contains(cas_number, case=False, na=False)]
                
                if not matches.empty:
                    if mostrar_info:
                        st.success(f"✅ ENCONTRADO en Annex II por búsqueda de contenido")
                        st.dataframe(matches)
                    
                    resultados[cas_number]["encontrado"] = True
                    resultados[cas_number]["anexos"].append({
                        "nombre": "Annex II",
                        "data": matches
                    })
                    continue  # Ir al siguiente CAS
                
                # Iteración fila por fila
                if mostrar_info:
                    st.write("Intentando búsqueda manual fila por fila...")
                
                encontrado = False
                for idx, row in annex_ii.iterrows():
                    try:
                        cas_valor = str(row['CAS Number']).strip()
                        if cas_number in cas_valor or cas_valor == "51843" or '51-84-3' in cas_valor:
                            if mostrar_info:
                                st.success(f"✅ ENCONTRADO en Annex II, fila {idx}")
                                st.dataframe(annex_ii.loc[[idx]])
                            
                            resultados[cas_number]["encontrado"] = True
                            resultados[cas_number]["anexos"].append({
                                "nombre": "Annex II",
                                "data": annex_ii.loc[[idx]]
                            })
                            encontrado = True
                            break
                    except:
                        pass
                
                if encontrado:
                    continue  # Ir al siguiente CAS
        
        # Búsqueda general en todos los anexos
        if mostrar_info:
            st.write(f"Buscando {cas_number} en todos los anexos...")
        
        encontrado_en_alguno = False
        
        for nombre_annex, df_annex in annex_data.items():
            if df_annex.empty:
                continue
            
            # Buscar columnas CAS
            cas_columns = [col for col in df_annex.columns if 'cas' in col.lower()]
            
            if not cas_columns:
                continue
            
            for cas_column in cas_columns:
                if mostrar_info:
                    st.write(f"Buscando en {nombre_annex}, columna '{cas_column}'...")
                
                # Cambio clave: Búsqueda por contenido en lugar de coincidencia exacta
                matches = df_annex[df_annex[cas_column].astype(str).str.contains(cas_number, case=False, na=False)]
                if not matches.empty:
                    if mostrar_info:
                        st.success(f"✅ ENCONTRADO en {nombre_annex}, columna '{cas_column}'")
                        st.dataframe(matches)
                    
                    resultados[cas_number]["encontrado"] = True
                    resultados[cas_number]["anexos"].append({
                        "nombre": nombre_annex,
                        "data": matches
                    })
                    encontrado_en_alguno = True
                    break
            
            # Si ya lo encontramos en este anexo, pasamos al siguiente
            if encontrado_en_alguno:
                break
        
        if not encontrado_en_alguno and mostrar_info:
            st.warning(f"❌ No se encontró el CAS {cas_number} en ningún anexo")
        
        if mostrar_info:
            st.markdown("---")  # Separador entre resultados de CAS
    
    return resultados

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR INGREDIENTES POR NOMBRE
# -----------------------------------------------------------
def buscar_ingredientes_por_nombre(ingredientes, exact=False):
    resultados_formula = []
    
    # Determinar la columna de nombre en la base de datos CAS
    columna_nombre = None
    if "Ingredient" in cas_db.columns:
        columna_nombre = "Ingredient"
    elif "Name" in cas_db.columns:
        columna_nombre = "Name"
    
    if not columna_nombre:
        st.error("La base de datos CAS no tiene una columna identificable para el nombre del ingrediente.")
        return pd.DataFrame()
    
    # Buscar cada ingrediente según el modo (exacto o aproximado)
    for ing in ingredientes:
        if exact:
            # Comparación exacta (ignorando mayúsculas y espacios adicionales)
            mask = cas_db[columna_nombre].astype(str).str.lower().str.strip() == ing.lower().strip()
            df_ing = cas_db[mask]
            if df_ing.empty:
                # Si no se encuentra, crear una fila indicando "No encontrado"
                df_not_found = pd.DataFrame({
                    "Búsqueda": [ing],
                    columna_nombre: [ing],
                    "Resultado": ["No encontrado"]
                })
                resultados_formula.append(df_not_found)
            else:
                df_ing = df_ing.copy()
                df_ing["Búsqueda"] = ing
                resultados_formula.append(df_ing)
        else:
            # Búsqueda aproximada: se buscan coincidencias parciales
            mask = cas_db[columna_nombre].astype(str).str.contains(ing, case=False, na=False)
            df_ing = cas_db[mask]
            if not df_ing.empty:
                df_ing = df_ing.copy()
                df_ing["Búsqueda"] = ing
                resultados_formula.append(df_ing)
            else:
                # También se puede agregar una fila "No encontrado" en modo aproximado
                df_not_found = pd.DataFrame({
                    "Búsqueda": [ing],
                    columna_nombre: [ing],
                    "Resultado": ["No encontrado"]
                })
                resultados_formula.append(df_not_found)
    
    if resultados_formula:
        return pd.concat(resultados_formula, ignore_index=True)
    else:
        return pd.DataFrame()

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR INGREDIENTES EN ANEXOS
# -----------------------------------------------------------
def buscar_ingredientes_en_anexos(ingredientes):
    resultados_anexos = {}
    
    for nombre_annex, df_annex in annex_data.items():
        if df_annex.empty or "Name" not in df_annex.columns:
            continue
        
        resultados_annex = pd.DataFrame()
        for ing in ingredientes:
            res = df_annex[df_annex["Name"].astype(str).str.contains(ing, case=False, na=False)]
            if not res.empty:
                res = res.copy()
                res["Búsqueda"] = ing
                resultados_annex = pd.concat([resultados_annex, res], ignore_index=True)
        
        if not resultados_annex.empty:
            resultados_anexos[nombre_annex] = resultados_annex
    
    return resultados_anexos

# -----------------------------------------------------------
# FUNCIÓN PARA MOSTRAR INFORMACIÓN DE PUBCHEM
# -----------------------------------------------------------
def mostrar_info_pubchem(pubchem_data):
    """
    Muestra la información de PubChem de forma organizada.
    """
    if pubchem_data['encontrado']:
        st.success("✅ Información encontrada en PubChem")
        
        input_value = pubchem_data.get('input', 'No disponible')
        
        # Información básica
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Búsqueda por:**", input_value)
            st.write("**Nombre IUPAC:**", pubchem_data.get('nombre_iupac', 'No disponible'))
            st.write("**Fórmula molecular:**", pubchem_data.get('formula', 'No disponible'))
            st.write("**Peso molecular:**", pubchem_data.get('peso_molecular', 'No disponible'))
        
        with col2:
            st.write("**CompoundID (CID):**", pubchem_data.get('cid', 'No disponible'))
            st.write("**InChIKey:**", pubchem_data.get('inchikey', 'No disponible'))
            
            # Mostrar CAS si está disponible
            if 'cas_number' in pubchem_data and pubchem_data['cas_number']:
                st.write("**Número CAS encontrado:**", pubchem_data['cas_number'])
            
            st.write("**SMILES:**", pubchem_data.get('smiles', 'No disponible'))
        
        # Sinónimos
        if 'sinonimos' in pubchem_data and pubchem_data['sinonimos']:
            with st.expander("Ver sinónimos"):
                for sinonimo in pubchem_data['sinonimos']:
                    st.write(f"• {sinonimo}")
        
        # Enlace a PubChem
        st.markdown(f"[Ver ficha completa en PubChem]({pubchem_data['url']})")
    else:
        st.warning("❌ No se encontró información en PubChem")
        if 'mensaje' in pubchem_data:
            st.write(pubchem_data['mensaje'])
        if 'error' in pubchem_data:
            st.write("Error:", pubchem_data['error'])

# -----------------------------------------------------------
# CARGA DE DATOS
# -----------------------------------------------------------
annex_ii, annex_iii, annex_iv, annex_v, annex_vi, mercosur, cas_db, info_carga = load_data()
annex_data = {
    "Annex II": annex_ii,
    "Annex III": annex_iii,
    "Annex IV": annex_iv,
    "Annex V": annex_v,
    "Annex VI": annex_vi,
    "MERCOSUR Prohibidas": mercosur
}

# -----------------------------------------------------------
# INTERFAZ PRINCIPAL
# -----------------------------------------------------------
st.title("Cosmetic Ingredient Checker")
st.write("""
Esta aplicación permite:
- Buscar en la base de datos de números CAS.
- Consultar en los listados de sustancias permitidas o prohibidas (anexos COSING y MERCOSUR).
- Revisar fórmulas completas (lista de ingredientes) y extraer la información asociada.
- Consultar información en PubChem.
""")

modo_busqueda = st.sidebar.selectbox(
    "Seleccione el método de búsqueda",
    [
        "Búsqueda por fórmula de ingredientes",
        "Búsqueda en restricciones por CAS",
        "Búsqueda en PubChem"
    ]
)

# -----------------------------------------------------------
# 1) Búsqueda por fórmula de ingredientes (con cas_column dinámico)
# -----------------------------------------------------------
if modo_busqueda == "Búsqueda por fórmula de ingredientes":
    st.header("Búsqueda por fórmula de ingredientes")
    formula_input = st.text_area("Ingredientes (separados por comas o líneas):")
    tipo_busqueda = st.radio("Tipo de búsqueda", ["Aproximada", "Exacta"])

    if st.button("Buscar Fórmula"):
        ingredientes = [i.strip() for i in re.split(r'[\n,]+', formula_input) if i.strip()]
        df_res = buscar_ingredientes_por_nombre(ingredientes, exact=(tipo_busqueda == "Exacta"))
        st.session_state["df_formula"] = df_res

    if "df_formula" in st.session_state:
        df = st.session_state["df_formula"]

        # 1) Detectar columna de CAS de forma dinámica
        cas_column = next((c for c in df.columns if 'cas' in c.lower()), None)

        if not df.empty and cas_column:
            # 2) Preparar tabla editable
            df_edit = df.copy()
            df_edit["Seleccionar"] = False
            cols = ["Seleccionar"] + [c for c in df_edit.columns if c != "Seleccionar"]
            df_edit = df_edit[cols]

            df_editado = st.data_editor(
                df_edit,
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn(label="Seleccionar")
                },
                use_container_width=True,
                key="editor_formula"
            )

            # 3) Botón que ahora usa la misma función de búsqueda manual
            if st.button("Buscar seleccionados en restricciones"):
                seleccionadas = df_editado[df_editado["Seleccionar"] == True]
                # Limpiar y extraer sólo strings no nulos
                cas_sel = [str(x).strip() for x in seleccionadas[cas_column] if pd.notna(x)]

                if not cas_sel:
                    st.warning("Selecciona al menos un CAS válido para buscar.")
                else:
                    # Ejecuta la misma búsqueda que en la rama manual
                    resultados = buscar_cas_en_restricciones(cas_sel, mostrar_info=False)

                    # Mostrar resultados idénticos a la búsqueda manual
                    st.subheader("Resultados en listados de restricciones")
                    for cas_n, res in resultados.items():
                        if res["encontrado"]:
                            st.markdown(f"### CAS {cas_n}")
                            for anexo in res["anexos"]:
                                st.write(f"**{anexo['nombre']}**")
                                st.dataframe(anexo["data"])
                                st.markdown("---")
                        else:
                            st.warning(f"⚠️ {cas_n} no encontrado en ningún anexo")

                    # Ofrecer descarga de PDF
                    pdf = generar_reporte_pdf(resultados)
                    st.download_button(
                        "📥 Descargar reporte en PDF",
                        data=pdf,
                        file_name="reporte_cas_restricciones.pdf",
                        mime="application/pdf"
                    )
        else:
            st.info("No se encontraron coincidencias en la base CAS o no hay columna CAS detectada.")

# ------------------------------------------------------------------------
# 2) Búsqueda en restricciones por CAS
# ------------------------------------------------------------------------
elif modo_busqueda == "Búsqueda en restricciones por CAS":
    st.header("Búsqueda en listados de restricciones por CAS")
    mostrar_info = st.checkbox("Mostrar información de carga", False)
    cas_input = st.text_area("Ingrese números CAS (uno por línea):")
    if st.button("Buscar CAS en restricciones"):
        cas_list = [x.strip() for x in re.split(r'[\n,;]+', cas_input) if x.strip()]
        if cas_list:
            if mostrar_info:
                st.write("".join(f"- {l}\n" for l in info_carga))
            resultados = buscar_cas_en_restricciones(cas_list, mostrar_info=False)
            st.subheader("Resultados")
            for cas_n, res in resultados.items():
                if res["encontrado"]:
                    st.markdown(f"### CAS {cas_n}")
                    for anexo in res["anexos"]:
                        st.write(f"**{anexo['nombre']}**")
                        st.dataframe(anexo["data"])
                        st.markdown("---")
                else:
                    st.warning(f"⚠️ {cas_n} no encontrado")

# ------------------------------------------------------------------------
# 3) Búsqueda en PubChem
# ------------------------------------------------------------------------
else:
    st.header("Búsqueda en PubChem")
    modo = st.radio("Buscar por:", ["Número CAS", "Nombre de ingrediente"])
    prompt = st.text_area("Ingrese valores (uno por línea):")
    if st.button("Buscar en PubChem"):
        items = [x.strip() for x in re.split(r'[\n,;]+', prompt) if x.strip()]
        if items:
            resultados = buscar_lista_en_pubchem(items, por_cas=(modo=="Número CAS"))
            for item, data in resultados.items():
                st.markdown(f"### {item}")
                mostrar_info_pubchem(data)
                st.markdown("---")
