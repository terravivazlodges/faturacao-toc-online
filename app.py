import streamlit as st
import pandas as pd
import re
import io

# Configuração da página
st.set_page_config(
    page_title="Faturação Automática — TOC Online", 
    page_icon="🧾", 
    layout="centered"
)

st.markdown("""
    <style>
    .info-box {
        background-color: #0e1117;
        border: 1px solid #262730;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🧾 Portal de Faturação — TOC Online")
st.write("Automação de extração de reservas do **Smoobu** (com datas de estadia nas **Observações**), ordenadas cronologicamente.")

uploaded_file = st.file_uploader("Carregue o ficheiro de reservas do Smoobu (.xlsx ou .csv)", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        # Identificar se é Excel ou CSV e efetuar a leitura
        filename = uploaded_file.name.lower()
        if filename.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8-sig')
        
        # 1. ORDENAÇÃO CRONOLÓGICA por Chegada e Partida
        df['Chegada_DT'] = pd.to_datetime(df['Chegada'], format='%d-%m-%y', errors='coerce')
        df['Partida_DT'] = pd.to_datetime(df['Partida'], format='%d-%m-%y', errors='coerce')
        df = df.sort_values(by=['Chegada_DT', 'Partida_DT'], ascending=[True, True]).reset_index(drop=True)
        
        # Limpeza e conversão do Preço Bruto
        df['Preço_Bruto'] = df['Preço'].astype(str).str.replace('€','', regex=False).str.replace(',','.', regex=False).str.strip().astype(float)
        
        def extrair_taxa_turistica(row):
            notas = str(row.get('Notas', ''))
            preco_txt = str(row.get('Preço', ''))
            detalhes = str(row.get('Detalhes de preço', ''))
            
            texto_agrupado = f"{notas} {preco_txt} {detalhes}"
            
            # 1. Pesquisa por "Other Fees - EUR X" (comum em reservas Airbnb)
            match_other_fees = re.search(r'Other Fees\s*-\s*EUR\s*(\d+[\.,]?\d*)', texto_agrupado, re.IGNORECASE)
            if match_other_fees:
                try:
                    return float(match_other_fees.group(1).replace(',', '.'))
                except:
                    pass

            # 2. Pesquisa por imposto municipal no formato Booking/OTA (ex: "imposto municipal - EUR 12")
            match_imposto = re.search(r'(?:imposto municipal|taxa turistica|city tax)\s*-\s*EUR\s*(\d+[\.,]?\d*)', texto_agrupado, re.IGNORECASE)
            if match_imposto:
                try:
                    return float(match_imposto.group(1).replace(',', '.'))
                except:
                    pass
            
            # 3. Pesquisa geral por menções em euros perto de termos fiscais/municipais
            match_geral = re.search(r'(\d+[\.,]?\d*)\s*(?:€|EUR)', texto_agrupado, re.IGNORECASE)
            if match_geral and any(termo in texto_agrupado.lower() for termo in ['turistica', 'municipal', 'tx', 'imposto', 'city tax']):
                try:
                    return float(match_geral.group(1).replace(',', '.'))
                except:
                    pass
                    
            return 0.0

        # Aplicação da extração da taxa turística
        df['Taxa_Turistica'] = df.apply(extrair_taxa_turistica, axis=1)
        
        # Cálculo do valor do alojamento sem IVA (4% Açores) deduzindo a taxa turística
        df['Preco_Alojamento_Sem_IVA'] = ((df['Preço_Bruto'] - df['Taxa_Turistica']) / 1.04).round(2)

        linhas_toc = []

        for _, row in df.iterrows():
            data_doc = row['Chegada']
            data_partida = row['Partida']
            cliente = str(row['Hóspede']) if pd.notna(row['Hóspede']) else 'Consumidor Final'
            alojamento_nome = str(row['Alojamento'])
            portal = str(row['Portal']) if pd.notna(row['Portal']) else 'Direto'
            
            # Mapeamento do código de artigo segundo o alojamento
            aloj_upper = alojamento_nome.upper()
            if any(k in aloj_upper for k in ['PORTO', 'BAY', 'VILLA']):
                codigo_artigo = 'AL-PB'
            elif any(k in aloj_upper for k in ['SUITE', 'BLUE', 'GREEN', 'GARDEN']):
                codigo_artigo = 'AL-RC'
            else:
                codigo_artigo = 'AL-CB'
            
            # Descrição limpa do alojamento
            descricao_alojamento = f"Alojamento Local - {alojamento_nome}"
            
            # Observações enriquecidas com o período da estadia
            observacoes_texto = f"Reserva Smoobu / {portal} — Estadia de {data_doc} a {data_partida}"
            
            # Linha 1: Alojamento Local (4% IVA)
            linhas_toc.append({
                'Tipo_Documento': 'FR',
                'Data_Documento': data_doc,
                'Cliente_Nome': cliente,
                'Cliente_NIF': '999999990',
                'Codigo_Artigo': codigo_artigo,
                'Descricao': descricao_alojamento,
                'Quantidade': 1.0,
                'Preco_Unitario': row['Preco_Alojamento_Sem_IVA'],
                'Taxa_IVA': 4.0,
                'Observacoes': observacoes_texto
            })
            
            # Linha 2: Taxa Turística / Imposto Municipal (Obrigatória por reserva)
            taxa_turistica = row['Taxa_Turistica']
            linhas_toc.append({
                'Tipo_Documento': 'FR',
                'Data_Documento': data_doc,
                'Cliente_Nome': cliente,
                'Cliente_NIF': '999999990',
                'Codigo_Artigo': 'TTUR',
                'Descricao': 'Taxa Turística',
                'Quantidade': 1.0,
                'Preco_Unitario': taxa_turistica,
                'Taxa_IVA': 0.0,
                'Observacoes': f"Taxa turística / Other Fees — Estadia de {data_doc} a {data_partida}" if taxa_turistica > 0 else f"Isento / Sem taxa turística — Estadia de {data_doc} a {data_partida}"
            })

        df_toc = pd.DataFrame(linhas_toc)

        st.success(f"✅ Ficheiro processado com sucesso! Geradas {len(df_toc)} linhas com as datas de estadia integradas nas observações.")

        st.subheader("📋 Tabela de Apoio e Validação Prévia")
        st.dataframe(df_toc, use_container_width=True)

        # Botões de Download em CSV e Excel
        col1, col2 = st.columns(2)
        
        with col1:
            csv_toc = df_toc.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button(
                label="📥 Descarregar em formato CSV",
                data=csv_toc,
                file_name="faturacao_toc_online.csv",
                mime="text/csv"
            )
            
        with col2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_toc.to_excel(writer, index=False, sheet_name='Faturacao')
            excel_data = output.getvalue()
            
            st.download_button(
                label="📊 Descarregar em formato Excel (.xlsx)",
                data=excel_data,
                file_name="faturacao_toc_online.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o ficheiro: {e}")
else:
    st.info("💡 Por favor, carregue o ficheiro Excel (.xlsx) ou CSV de reservas do Smoobu.")
