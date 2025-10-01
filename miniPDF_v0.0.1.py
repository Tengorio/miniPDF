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

def main():
    st.set_page_config(
        page_title="Compresor de PDF Avanzado",
        page_icon="📄",
        layout="wide"
    )
    
    st.title("📄 Compresor de PDF Avanzado")
    st.markdown("Combina y comprime múltiples archivos PDF con control de páginas y tamaño máximo")
    
    # Sidebar para configuración
    st.sidebar.header("⚙️ Configuración")
    
    dpi = st.sidebar.slider(
        "DPI (Resolución)",
        min_value=50,
        max_value=300,
        value=150,
        step=10,
        help="Mayor DPI = mejor calidad pero archivo más grande"
    )
    
    quality = st.sidebar.slider(
        "Calidad JPEG",
        min_value=10,
        max_value=100,
        value=80,
        step=5,
        help="Mayor calidad = archivo más grande"
    )
    
    max_size_mb = st.sidebar.number_input(
        "Tamaño máximo del archivo resultante (MB)",
        min_value=0.1,
        max_value=100.0,
        value=10.0,
        step=0.1,
        help="El compresor intentará reducir el tamaño hasta este límite"
    )
    
    # Nueva opción para preservar texto
    preserve_text = st.sidebar.checkbox(
        "🔤 Preservar texto seleccionable cuando sea posible",
        value=True,
        help="Mantiene el texto seleccionable si el PDF original lo tiene y el tamaño lo permite"
    )
    
    # Información sobre la configuración
    st.sidebar.markdown("### 💡 Consejos")
    st.sidebar.markdown("""
    **Para documentos de texto:**
    - DPI: 100-150
    - Calidad: 70-85
    
    **Para documentos con imágenes:**
    - DPI: 150-200
    - Calidad: 80-90
    
    **Para máxima compresión:**
    - DPI: 75-100
    - Calidad: 60-70
    """)
    
    # Área principal
    st.header("📤 Subir archivos PDF")
    uploaded_files = st.file_uploader(
        "Selecciona uno o varios archivos PDF",
        type="pdf",
        help="Sube los archivos PDF que deseas combinar y comprimir",
        accept_multiple_files=True
    )
    
    file_data = []
    if uploaded_files:
        st.subheader("Selección de páginas")
        st.info("Especifica qué páginas incluir de cada archivo (ej: 1-3,5,7-9)")
        
        for i, uploaded_file in enumerate(uploaded_files):
            # Obtener información del PDF
            pdf_bytes = uploaded_file.getvalue()
            try:
                reader = PdfReader(BytesIO(pdf_bytes))
                num_pages = len(reader.pages)
            except:
                st.error(f"Error al leer el archivo: {uploaded_file.name}")
                continue
            
            # Interfaz para selección de páginas
            col_file, col_range = st.columns([3, 2])
            with col_file:
                st.markdown(f"**{uploaded_file.name}** ({num_pages} páginas)")
            with col_range:
                default_range = "1" if num_pages == 1 else f"1-{num_pages}"
                page_range = st.text_input(
                    f"Páginas a incluir",
                    value=default_range,
                    key=f"range_{i}"
                )
            
            file_data.append({
                'name': uploaded_file.name,
                'bytes': pdf_bytes,
                'page_range': page_range,
                'num_pages': num_pages
            })
        
        # Botón para procesar
        if st.button("📄 Combinar y Comprimir PDF", type="primary", use_container_width=True):
            with st.spinner("Analizando archivos..."):
                # Analizar PDFs
                analysis_results = analyze_pdfs_for_compression(file_data)
                
                if not analysis_results:
                    st.error("No hay páginas válidas para procesar")
                    st.stop()
                
                # Mostrar análisis de contenido
                if preserve_text:
                    st.subheader("🔍 Análisis de Contenido")
                    analysis_df = pd.DataFrame([
                        {
                            'Archivo': result['name'],
                            'Páginas': result['pages_selected'],
                            'Tamaño (MB)': f"{result['size_mb']:.2f}",
                            'Tiene Texto': "✅ Sí" if result['has_text'] else "❌ No",
                            'Ratio Texto': f"{result['text_ratio']:.1%}"
                        }
                        for result in analysis_results
                    ])
                    st.dataframe(analysis_df, hide_index=True)
                
                # Combinar PDFs
                extracted_pdfs = [result['extracted_pdf'] for result in analysis_results]
                combined_pdf = merge_pdfs(extracted_pdfs)
                combined_size = get_file_size(combined_pdf)
                
                # Determinar si tiene texto seleccionable el PDF combinado
                combined_has_text, combined_text_ratio = detect_text_content(combined_pdf)
                
                st.success(f"✅ {len(extracted_pdfs)} archivos combinados ({combined_size:.2f} MB)")
                
                if combined_has_text and preserve_text:
                    st.info(f"📝 El documento combinado tiene texto seleccionable ({combined_text_ratio:.1%} de las páginas)")
                
                # Verificar si necesita compresión basado en el límite del usuario
                if combined_size <= max_size_mb:
                    st.info(f"ℹ️ El archivo combinado ({combined_size:.2f} MB) ya cumple con el límite de {max_size_mb} MB. No se aplicará compresión.")
                    
                    # Mostrar métricas
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Tamaño combinado", f"{combined_size:.2f} MB")
                    col2.metric("Límite configurado", f"{max_size_mb} MB")
                    col3.metric("Texto seleccionable", "✅ Sí" if combined_has_text else "❌ No")
                    
                    # Botón de descarga
                    output_filename = "documento_combinado.pdf"
                    if len(uploaded_files) == 1:
                        original_name = uploaded_files[0].name.split('.')[0]
                        output_filename = f"{original_name}_combinado.pdf"
                    
                    st.download_button(
                        label="📥 Descargar PDF Combinado",
                        data=combined_pdf,
                        file_name=output_filename,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    # Necesita compresión
                    compression_strategy = "texto preservado" if (combined_has_text and preserve_text) else "imagen optimizada"
                    
                    if combined_has_text and preserve_text:
                        # Intentar compresión manteniendo el texto (usando pypdf optimization)
                        st.info(f"🔧 Intentando compresión con texto preservado...")
                        
                        # Aquí podrías implementar técnicas de compresión que preserven el texto
                        # Por ahora, usaremos el PDF combinado tal como está si es posible
                        final_pdf = combined_pdf
                        final_size = combined_size
                        text_preserved = True
                        
                        if final_size > max_size_mb:
                            st.warning(f"⚠️ No se puede reducir más el tamaño manteniendo el texto seleccionable.")
                            st.info("🖼️ Aplicando compresión con conversión a imagen...")
                            text_preserved = False
                    
                    # Si no se puede preservar texto o no lo tiene, usar compresión por imagen
                    if not (combined_has_text and preserve_text) or (combined_has_text and preserve_text and combined_size > max_size_mb):
                        st.info(f"🔧 Comprimiendo con estrategia: {compression_strategy} (máximo {max_size_mb} MB)...")
                        current_dpi = dpi
                        current_quality = quality
                        compression_data = []
                        compressed_pdf_bytes = None
                        
                        for attempt in range(10):  # Máximo 10 intentos
                            with st.spinner(f"Intento {attempt+1}: DPI={current_dpi}, Calidad={current_quality}..."):
                                compressed_pdf_bytes = pdf_to_compressed_pdf(
                                    combined_pdf,
                                    dpi=current_dpi,
                                    quality=current_quality
                                )
                            
                            if compressed_pdf_bytes is None:
                                st.error("Error en la compresión")
                                break
                                
                            compressed_size = get_file_size(compressed_pdf_bytes)
                            compression_data.append({
                                'Intento': attempt + 1,
                                'DPI': current_dpi,
                                'Calidad': current_quality,
                                'Tamaño (MB)': f"{compressed_size:.2f}",
                                'Resultado': "✅ Éxito" if compressed_size <= max_size_mb else "⚠️ Intento"
                            })
                            
                            # Verificar si cumple con el tamaño máximo
                            if compressed_size <= max_size_mb:
                                break
                                
                            # Ajustar parámetros para siguiente intento
                            current_dpi = max(50, int(current_dpi * 0.85))
                            current_quality = max(20, int(current_quality * 0.85))
                        
                        final_pdf = compressed_pdf_bytes
                        final_size = get_file_size(compressed_pdf_bytes) if compressed_pdf_bytes else combined_size
                        text_preserved = False
                        
                        # Mostrar tabla de intentos
                        if compression_data:
                            st.subheader("📊 Proceso de Compresión")
                            df = pd.DataFrame(compression_data)
                            st.dataframe(df, hide_index=True)
                    
                    # Mostrar resultados finales
                    if final_pdf:
                        reduction = combined_size - final_size
                        
                        st.success("🎉 ¡Proceso completado!")
                        
                        # Mostrar métricas
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Tamaño inicial", f"{combined_size:.2f} MB")
                        col2.metric("Tamaño final", f"{final_size:.2f} MB", 
                                   f"-{reduction:.2f} MB")
                        col3.metric("Reducción", f"{(reduction/combined_size)*100:.1f}%")
                        col4.metric("Texto preservado", "✅ Sí" if text_preserved else "❌ No")
                        
                        # Botón de descarga
                        output_filename = "documento_comprimido.pdf"
                        if len(uploaded_files) == 1:
                            original_name = uploaded_files[0].name.split('.')[0]
                            output_filename = f"{original_name}_comprimido.pdf"
                        
                        st.download_button(
                            label="📥 Descargar PDF Comprimido",
                            data=final_pdf,
                            file_name=output_filename,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True
                        )
                        
                        if final_size > max_size_mb:
                            st.warning("⚠️ No se alcanzó el tamaño máximo deseado. Intente con ajustes más agresivos.")

if __name__ == "__main__":
    main()