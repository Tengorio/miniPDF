import streamlit as st
import os
import tempfile
from pdf2image import convert_from_path
import img2pdf
from PIL import Image
import io
import pandas as pd
from pypdf import PdfReader, PdfWriter
from io import BytesIO
import re

def parse_page_range(range_str, max_pages):
    """
    Convierte un string de rango de páginas en una lista de números de página
    Ejemplo: "1-3,5,7-9" -> [1,2,3,5,7,8,9]
    """
    pages = []
    parts = range_str.split(',')
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            start = int(start.strip())
            end = int(end.strip())
            pages.extend(range(start, min(end, max_pages) + 1))
        else:
            page = int(part)
            if page <= max_pages:
                pages.append(page)
    
    # Eliminar duplicados y ordenar
    return sorted(set(pages))

# def parse_page_range(page_range_str, max_pages):
#     """
#     Parsea un string de rango de páginas y devuelve una lista de números de página.
#     
#     Args:
#         page_range_str: String con el rango (ej: "1-3,5,7-9")
#         max_pages: Número máximo de páginas disponible
#     
#     Returns:
#         Lista de números de página (enteros)
#     """
#     pages = []
#     
#     # Eliminar espacios y dividir por comas
#     parts = page_range_str.replace(" ", "").split(",")
#     
#     for part in parts:
#         if "-" in part:
#             # Rango de páginas (ej: 1-3)
#             start_end = part.split("-")
#             if len(start_end) == 2:
#                 try:
#                     start = int(start_end[0])
#                     end = int(start_end[1])
#                     # Asegurar que esté dentro de los límites
#                     start = max(1, min(start, max_pages))
#                     end = max(1, min(end, max_pages))
#                     if start <= end:
#                         pages.extend(range(start, end + 1))
#                 except ValueError:
#                     continue
#         else:
#             # Página individual
#             try:
#                 page_num = int(part)
#                 if 1 <= page_num <= max_pages:
#                     pages.append(page_num)
#             except ValueError:
#                 continue
#     
#     # Eliminar duplicados y ordenar
#     pages = sorted(set(pages))
#     return pages


def extract_pages(input_pdf_bytes, page_range):
    """Extrae las páginas especificadas de un PDF"""
    reader = PdfReader(BytesIO(input_pdf_bytes))
    writer = PdfWriter()
    
    for page_num in page_range:
        if 0 <= page_num - 1 < len(reader.pages):
            writer.add_page(reader.pages[page_num - 1])
    
    output = BytesIO()
    writer.write(output)
    return output.getvalue()

def extract_pages_2(pdf_bytes, page_range):
    """
    Extrae un rango específico de páginas de un PDF.
    
    Args:
        pdf_bytes: Bytes del PDF original
        page_range: String con el rango de páginas (ej: "1-3,5,7-9")
    
    Returns:
        Bytes del PDF con las páginas extraídas
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()
        
        # Parsear el rango de páginas
        selected_pages = parse_page_range(page_range, len(reader.pages))
        
        # Asegurarnos de que page_num sea entero
        for page_num in selected_pages:
            # Convertir a entero si es necesario
            if isinstance(page_num, str):
                page_num = int(page_num)
            
            # Verificar que el número de página sea válido
            if 0 <= page_num - 1 < len(reader.pages):
                writer.add_page(reader.pages[page_num - 1])
        
        output_bytes = BytesIO()
        writer.write(output_bytes)
        return output_bytes.getvalue()
        
    except Exception as e:
        print(f"Error extrayendo páginas: {e}")
        return None

def merge_pdfs(pdf_bytes_list):
    """Combina múltiples PDFs en uno solo"""
    writer = PdfWriter()
    
    for pdf_bytes in pdf_bytes_list:
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    
    output = BytesIO()
    writer.write(output)
    return output.getvalue()

def detect_text_content(pdf_bytes):
    """
    Detecta si un PDF contiene texto seleccionable
    Returns: (has_text, text_ratio) donde text_ratio es la proporción de páginas con texto
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages_with_text = 0
        total_pages = len(reader.pages)
        
        for page in reader.pages:
            text = page.extract_text().strip()
            if text and len(text) > 10:  # Mínimo 10 caracteres para considerar que tiene texto útil
                pages_with_text += 1
        
        text_ratio = pages_with_text / total_pages if total_pages > 0 else 0
        has_significant_text = text_ratio > 0.5  # Más del 50% de páginas tienen texto
        
        return has_significant_text, text_ratio
        
    except Exception as e:
        st.warning(f"Error detectando texto en PDF: {str(e)}")
        return False, 0.0

def analyze_pdfs_for_compression(file_data):
    """
    Analiza los PDFs para determinar la mejor estrategia de compresión
    """
    analysis_results = []
    
    for data in file_data:
        try:
            # Extraer páginas seleccionadas primero
            pages = parse_page_range(data['page_range'], data['num_pages'])
            if not pages:
                continue
                
            extracted_pdf = extract_pages(data['bytes'], pages)
            has_text, text_ratio = detect_text_content(extracted_pdf)
            size_mb = get_file_size(extracted_pdf)
            
            analysis_results.append({
                'name': data['name'],
                'extracted_pdf': extracted_pdf,
                'has_text': has_text,
                'text_ratio': text_ratio,
                'size_mb': size_mb,
                'pages_selected': len(pages)
            })
            
        except Exception as e:
            st.error(f"Error analizando {data['name']}: {str(e)}")
            continue
    
    return analysis_results

def pdf_to_compressed_pdf(input_pdf_bytes, dpi=100, quality=70):
    """
    Comprime un PDF convirtiendo sus páginas a imágenes JPEG y reconvirtiéndolas a PDF
    
    Args:
        input_pdf_bytes (bytes): Bytes del PDF de entrada
        dpi (int): Resolución DPI para la conversión
        quality (int): Calidad JPEG (1-100)
    
    Returns:
        bytes: PDF comprimido en bytes
    """
    try:
        # Crear archivo temporal para procesamiento
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_input:
            temp_input.write(input_pdf_bytes)
            temp_input_path = temp_input.name
        
        # Convertir PDF a imágenes
        images = convert_from_path(temp_input_path, dpi=dpi)
        
        # Lista para guardar las imágenes temporales
        temp_images = []
        
        # Procesar cada imagen
        for i, img in enumerate(images):
            # Crear archivo temporal para cada imagen
            temp_img = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            img.save(temp_img.name, "JPEG", quality=quality)
            temp_images.append(temp_img.name)
        
        # Convertir imágenes a PDF
        pdf_bytes = img2pdf.convert(temp_images)
        
        # Limpiar archivos temporales
        for img_path in temp_images:
            try:
                os.remove(img_path)
            except:
                pass
        try:
            os.remove(temp_input_path)
        except:
            pass
        
        return pdf_bytes
        
    except Exception as e:
        st.error(f"Error al procesar el PDF: {str(e)}")
        return None

def get_file_size(file_bytes):
    """Obtiene el tamaño del archivo en MB"""
    return len(file_bytes) / (1024 * 1024)

def extract_project_key(filename):
    """
    Extrae la clave de proyecto de un nombre de archivo.
    Ejemplo: "1.CF-2023-G-518_OficioBeneficiario.pdf" -> "CF-2023-G-518"
    """
    # Patrón para buscar claves del tipo: CF-AAAA-X-NNN
    pattern = r'CF-\d{4}-[GI]-\d+'
    match = re.search(pattern, filename)
    return match.group(0) if match else None

def find_common_project_key(filenames):
    """
    Busca una clave de proyecto común en una lista de nombres de archivo.
    """
    keys = []
    for filename in filenames:
        key = extract_project_key(filename)
        if key:
            keys.append(key)
    
    # Si todas las claves son iguales, retorna esa clave
    if keys and all(k == keys[0] for k in keys):
        return keys[0]
    return None

def calculate_combined_size(file_data):
    """Calcula el tamaño del PDF combinado sin comprimir"""
    extracted_pdfs = []
    
    for data in file_data:
        try:
            pages = parse_page_range(data['page_range'], data['num_pages'])
            if not pages:
                continue
                
            extracted_pdf = extract_pages(data['bytes'], pages)
            extracted_pdfs.append(extracted_pdf)
            
        except Exception as e:
            st.error(f"Error procesando {data['name']}: {str(e)}")
            continue
    
    if not extracted_pdfs:
        return 0.0
    
    combined_pdf = merge_pdfs(extracted_pdfs)
    return get_file_size(combined_pdf)

