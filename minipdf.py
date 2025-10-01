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

# from utilities_minipdf import *
from utilities_minipdf import (
    parse_page_range,
    extract_pages,
    merge_pdfs,
    detect_text_content,
    analyze_pdfs_for_compression,
    pdf_to_compressed_pdf,
    get_file_size,
    extract_project_key,
    find_common_project_key,
    calculate_combined_size
)

def find_split_point(pdf_bytes, max_size_mb):
    """
    Encuentra el punto de división óptimo para dividir un PDF en dos partes
    que pesen menos del tamaño máximo especificado.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    
    # Si el PDF ya es más pequeño que el límite, no necesita división
    original_size = get_file_size(pdf_bytes)
    if original_size <= max_size_mb:
        return total_pages, original_size, original_size
    
    # Buscar el punto de división binariamente
    low, high = 1, total_pages - 1
    
    while low <= high:
        mid = (low + high) // 2
        
        # Extraer primera parte (páginas 1 a mid)
        part1 = extract_pages(pdf_bytes, f"1-{mid}")
        if part1 is None:
            break
        size1 = get_file_size(part1)
        
        # Extraer segunda parte (páginas mid+1 a total_pages)
        part2 = extract_pages(pdf_bytes, f"{mid+1}-{total_pages}")
        if part2 is None:
            break
        size2 = get_file_size(part2)
        
        # Verificar si ambas partes cumplen con el límite
        if size1 <= max_size_mb and size2 <= max_size_mb:
            return mid, size1, size2
        
        # Si alguna parte es demasiado grande, ajustar la búsqueda
        if size1 > max_size_mb:
            high = mid - 1
        else:
            low = mid + 1
    
    # Si no se encuentra un punto ideal, usar la mitad como fallback
    split_point = total_pages // 2
    part1 = extract_pages(pdf_bytes, f"1-{split_point}")
    part2 = extract_pages(pdf_bytes, f"{split_point+1}-{total_pages}")
    
    size1 = get_file_size(part1) if part1 else original_size
    size2 = get_file_size(part2) if part2 else original_size
    
    return split_point, size1, size2

def compress_if_needed(pdf_bytes, max_size_mb, dpi=150, quality=80):
    """
    Comprime un PDF si excede el tamaño máximo, usando los parámetros fijos.
    """
    current_size = get_file_size(pdf_bytes)
    
    if current_size <= max_size_mb:
        return pdf_bytes, current_size, True  # No necesita compresión
    
    # Intentar compresión con parámetros fijos
    compressed_pdf = pdf_to_compressed_pdf(pdf_bytes, dpi=dpi, quality=quality)
    if compressed_pdf:
        compressed_size = get_file_size(compressed_pdf)
        return compressed_pdf, compressed_size, False
    
    return pdf_bytes, current_size, False  # Falló la compresión

def main():
    st.set_page_config(
        page_title="MiniPDF",
        page_icon="📄",
        layout="centered"
    )
    
    # Inicializar estado de sesión para preservar los datos
    if 'pdf_parts' not in st.session_state:
        st.session_state.pdf_parts = None
    if 'uploaded_file_name' not in st.session_state:
        st.session_state.uploaded_file_name = None
    if 'split_point' not in st.session_state:
        st.session_state.split_point = None
    if 'num_pages' not in st.session_state:
        st.session_state.num_pages = None
    
    st.title("📄 MiniPDF")
    
    # Sidebar para configuración
    st.sidebar.header("⚙️ Configuración")
    
    # VALORES FIJOS PARA COMPRESIÓN
    dpi = 150
    quality = 80
    
    max_size_mb = st.sidebar.number_input(
        "Tamaño máximo del archivo resultante (MB)",
        min_value=0.1,
        max_value=100.0,
        value=1.0,
        step=0.1,
        help="El compresor intentará reducir el tamaño hasta este límite"
    )
    
    # Nueva opción para preservar texto
    preserve_text = st.sidebar.checkbox(
        "🔤 Preservar texto seleccionable cuando sea posible",
        value=True,
        help="Mantiene el texto seleccionable si el PDF original lo tiene y el tamaño lo permite"
    )
    
    # Selección de modo de operación
    st.sidebar.header("🔀 Modo de Operación")
    operation_mode = st.sidebar.radio(
        "Selecciona la operación a realizar:",
        ["Dividir PDF en Partes", "Combinar y Comprimir PDFs"]
    )
    
    if operation_mode == "Dividir PDF en Partes":
        st.header("✂️ Subir PDF para dividir en partes")
        st.info(f"Divide un PDF en dos partes que pesen menos de {max_size_mb} MB cada una")
        
        # Uploader para un solo archivo
        uploaded_file = st.file_uploader(
            "Selecciona el archivo PDF a dividir",
            type="pdf",
            help="Sube el PDF que deseas dividir en partes más pequeñas",
            accept_multiple_files=False
        )
        
        # Resetear estado si se sube un nuevo archivo
        if uploaded_file and uploaded_file.name != st.session_state.uploaded_file_name:
            st.session_state.pdf_parts = None
            st.session_state.uploaded_file_name = uploaded_file.name
            st.session_state.split_point = None
            st.session_state.num_pages = None
        
        if uploaded_file:
            # Mostrar información del archivo
            pdf_bytes = uploaded_file.getvalue()
            reader = PdfReader(BytesIO(pdf_bytes))
            num_pages = len(reader.pages)
            file_size = get_file_size(pdf_bytes)
            
            # Guardar en estado de sesión
            st.session_state.num_pages = num_pages
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Archivo", uploaded_file.name)
            col2.metric("Páginas", num_pages)
            col3.metric("Tamaño", f"{file_size:.2f} MB")
            
            # Checkbox para compresión automática
            # comprimir_partes = st.checkbox(
            #     "🔧 Comprimir partes automáticamente si exceden el límite",
            #     value=True,
            #     help="Si está desactivado, solo se dividirá el PDF sin comprimir"
            # )
            
            # Verificar si necesita división
            if file_size <= max_size_mb:
                st.warning(f"ℹ️ El archivo ya pesa {file_size:.2f} MB, que es menor que el límite de {max_size_mb} MB. No necesita división.")
                
                # Ofrecer compresión simple
                if st.button("Comprimir PDF", type="primary"):
                    with st.spinner("Comprimiendo PDF..."):
                        compressed_pdf, compressed_size, no_compression_needed = compress_if_needed(
                            pdf_bytes, max_size_mb, dpi, quality
                        )
                        
                        if not no_compression_needed:
                            st.success(f"✅ PDF comprimido de {file_size:.2f} MB a {compressed_size:.2f} MB")
                            
                            # Generar nombre de archivo
                            original_name = os.path.splitext(uploaded_file.name)[0]
                            output_filename = f"{original_name}_comprimido.pdf"
                            
                            st.download_button(
                                label="📥 Descargar PDF Comprimido",
                                data=compressed_pdf,
                                file_name=output_filename,
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True
                            )
                        else:
                            st.info("El archivo no necesitaba compresión adicional.")
            else:
                # Botón para dividir el PDF
                if st.button("Dividir PDF", type="primary", use_container_width=True):
                    with st.spinner("Analizando y dividiendo el PDF..."):
                        # Encontrar punto de división
                        split_point, size1, size2 = find_split_point(pdf_bytes, max_size_mb)
                        
                        # Extraer las dos partes
                        part1 = extract_pages(pdf_bytes, f"1-{split_point}")
                        part2 = extract_pages(pdf_bytes, f"{split_point+1}-{num_pages}")
                        
                        # Comprimir si el usuario lo eligió
                        # if comprimir_partes:
                        #     part1_final, final_size1, compressed1 = compress_if_needed(part1, max_size_mb, dpi, quality)
                        #     part2_final, final_size2, compressed2 = compress_if_needed(part2, max_size_mb, dpi, quality)
                        # else:
                        part1_final, part2_final = part1, part2
                        final_size1, final_size2 = get_file_size(part1), get_file_size(part2)
                        compressed1 = compressed2 = False
                        
                        # Guardar en estado de sesión
                        st.session_state.pdf_parts = {
                            'part1': part1_final,
                            'part2': part2_final,
                            'size1': final_size1,
                            'size2': final_size2,
                            'compressed1': compressed1,
                            'compressed2': compressed2
                        }
                        st.session_state.split_point = split_point
                
                # Mostrar resultados si ya están en el estado de sesión
                if st.session_state.pdf_parts is not None:
                    st.success("✅ PDF dividido exitosamente!")
                    
                    # Mostrar información de compresión si se aplicó
                    if st.session_state.pdf_parts['compressed1'] or st.session_state.pdf_parts['compressed2']:
                        st.info("ℹ️ Se aplicó compresión a una o ambas partes para cumplir con el límite de tamaño.")
                    
                    # Advertencia si alguna parte aún excede el límite
                    if st.session_state.pdf_parts['size1'] > max_size_mb or st.session_state.pdf_parts['size2'] > max_size_mb:
                        st.warning("⚠️ Una o ambas partes aún exceden el límite de tamaño después de la compresión. Puede intentar con un límite más alto.")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Parte 1")
                        st.metric("Páginas", f"1-{st.session_state.split_point}")
                        st.metric("Tamaño", f"{st.session_state.pdf_parts['size1']:.2f} MB")
                        
                        original_name = os.path.splitext(uploaded_file.name)[0]
                        output_filename1 = f"{original_name}_parte1.pdf"
                        
                        st.download_button(
                            label="📥 Descargar Parte 1",
                            data=st.session_state.pdf_parts['part1'],
                            file_name=output_filename1,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key="download_part1"  # Clave única para este botón
                        )
                    
                    with col2:
                        st.subheader("Parte 2")
                        st.metric("Páginas", f"{st.session_state.split_point+1}-{st.session_state.num_pages}")
                        st.metric("Tamaño", f"{st.session_state.pdf_parts['size2']:.2f} MB")
                        
                        output_filename2 = f"{original_name}_parte2.pdf"
                        
                        st.download_button(
                            label="📥 Descargar Parte 2",
                            data=st.session_state.pdf_parts['part2'],
                            file_name=output_filename2,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key="download_part2"  # Clave única para este botón
                        )
        
        return  # Salir temprano para evitar mostrar la interfaz de combinación
    
    # Área principal (modo original - Combinar y Comprimir)
    st.header("📤 Subir archivos PDF para combinar o comprimir")
    uploaded_files = st.file_uploader(
        "Selecciona uno o varios archivos PDF",
        type="pdf",
        help="Sube los archivos PDF que deseas combinar y comprimir",
        accept_multiple_files=True
    )
    
    # ... (el resto del código original para combinar y comprimir permanece igual)
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

        # Botón para previsualizar el tamaño
        if st.button("📊 Previsualizar tamaño sin comprimir", use_container_width=True):
            with st.spinner("Calculando tamaño estimado..."):
                estimated_size = calculate_combined_size(file_data)
                st.info(f"El tamaño estimado del PDF combinado sin comprimir sería: **{estimated_size:.2f} MB**")
                
                # Mostrar comparación con el límite configurado
                if estimated_size > max_size_mb:
                    st.warning(f"⚠️ El tamaño estimado ({estimated_size:.2f} MB) supera el límite configurado ({max_size_mb} MB). Se necesitará compresión.")
                else:
                    st.success(f"✅ El tamaño estimado ({estimated_size:.2f} MB) está dentro del límite configurado ({max_size_mb} MB).")
        
        filenames = [file.name for file in uploaded_files]
        common_key = find_common_project_key(filenames)
        
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
                            'Texto Seleccionable': "✅ Sí" if result['has_text'] else "❌ No",
                            'Ratio Texto Selecc': f"{result['text_ratio']:.1%}"
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
                    if common_key:
                        output_filename = f"{common_key}_DC.pdf"
                        st.info(f"🔑 Clave de proyecto detectada: {common_key}")
                    elif len(uploaded_files) == 1:
                        # Extraer nombre base sin extensión
                        original_name = os.path.splitext(uploaded_files[0].name)[0]
                        # Intentar extraer clave incluso si es el único archivo
                        single_key = extract_project_key(original_name)
                        if single_key:
                            output_filename = f"{single_key}_DC.pdf"
                            st.info(f"🔑 Clave de proyecto detectada: {single_key}")
                        else:
                            output_filename = f"{original_name}_comprimido.pdf"
                    else:
                        output_filename = "documento_comprimido.pdf"
                    
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
                        # st.info(f"🔧 Comprimiendo con estrategia: {compression_strategy} (máximo {max_size_mb} MB)...")
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
                        if common_key:
                            output_filename = f"{common_key}_DC.pdf"
                            st.info(f"🔑 Clave de proyecto detectada: {common_key}")
                        elif len(uploaded_files) == 1:
                            # Extraer nombre base sin extensión
                            original_name = os.path.splitext(uploaded_files[0].name)[0]
                            # Intentar extraer clave incluso si es el único archivo
                            single_key = extract_project_key(original_name)
                            if single_key:
                                output_filename = f"{single_key}_DC.pdf"
                                st.info(f"🔑 Clave de proyecto detectada: {single_key}")
                            else:
                                output_filename = f"{original_name}_comprimido.pdf"
                        else:
                            output_filename = "documento_comprimido.pdf"
                        
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