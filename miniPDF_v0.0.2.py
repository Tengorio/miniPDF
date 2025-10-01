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
import zipfile

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


def main():
    st.set_page_config(
        page_title="Compresor de PDF Avanzado",
        page_icon="📄",
        layout="centered"
    )
    
    # Crear pestañas para separar funcionalidades
    tab1, tab2 = st.tabs(["📄 Combinar/Comprimir PDF", "🔖 Separador CLC"])
    
    with tab1:
        st.title("📄 Combina, Separa y Comprime archivos PDF")
    
        # Sidebar para configuración
        st.sidebar.header("⚙️ Configuración")

        # VALORES FIJOS PARA COMPRESIÓN (eliminados los sliders)
        dpi = 150      # Valor fijo en lugar de slider
        quality = 80   # Valor fijo en lugar de slider

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
    
    with tab2:
        st.title("🔖 Separador CLC")
        st.info("Sube un PDF multipágina y un Excel con ID_PROYECTO y Página para separar y renombrar automáticamente")
        
        # Subir archivos para el módulo CLC
        clc_pdf = st.file_uploader("Subir PDF para separar", type="pdf", key="clc_pdf")
        clc_excel = st.file_uploader("Subir archivo Excel (columnas: ID_PROYECTO, Página)", type=["xlsx", "xls"], key="clc_excel")
        
        if clc_pdf and clc_excel:
            try:
                # Leer el archivo Excel
                df = pd.read_excel(clc_excel)
                
                # Validar columnas
                if 'ID_PROYECTO' not in df.columns or 'Página' not in df.columns:
                    st.error("El archivo Excel debe contener las columnas 'ID_PROYECTO' y 'Página'")
                    return
                
                # Leer el PDF
                pdf_bytes = clc_pdf.read()
                pdf_reader = PdfReader(BytesIO(pdf_bytes))
                total_pages = len(pdf_reader.pages)
                
                st.success(f"PDF cargado con {total_pages} páginas")
                st.dataframe(df)
                
                # Procesar cada entrada del Excel
                output_files = {}
                
                for index, row in df.iterrows():
                    proyecto = str(row['ID_PROYECTO'])
                    paginas = str(row['Página'])
                    
                    # Parsear rango de páginas
                    paginas_seleccionadas = parse_page_range(paginas, total_pages)
                    
                    if not paginas_seleccionadas:
                        st.warning(f"Fila {index+1}: Rango de páginas inválido '{paginas}' - omitiendo")
                        continue
                    
                    # Extraer páginas del PDF
                    output_pdf = extract_pages(pdf_bytes, paginas_seleccionadas)
                    
                    # Guardar con nombre del proyecto
                    if proyecto in output_files:
                        # Si el proyecto ya existe, añadir número secuencial
                        base_name = proyecto
                        counter = 1
                        while f"{base_name}_{counter}" in output_files:
                            counter += 1
                        proyecto = f"{base_name}_{counter}"
                    
                    output_files[proyecto] = output_pdf
                
                # Crear ZIP con todos los archivos
                if output_files:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for proyecto, pdf_data in output_files.items():
                            zip_file.writestr(f"{proyecto}.pdf", pdf_data)
                    
                    zip_buffer.seek(0)
                    
                    st.success(f"Se crearon {len(output_files)} archivos PDF")
                    
                    # Botón de descarga
                    st.download_button(
                        label="📥 Descargar todos los PDFs separados (ZIP)",
                        data=zip_buffer,
                        file_name="documentos_separados.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    
                    # Mostrar previsualización de archivos generados
                    with st.expander("Ver listado de archivos generados"):
                        for proyecto in output_files.keys():
                            st.write(f"- {proyecto}.pdf")
                else:
                    st.warning("No se generaron archivos. Verifique los rangos de páginas en el Excel.")
                    
            except Exception as e:
                st.error(f"Error al procesar los archivos: {str(e)}")

if __name__ == "__main__":
    main()