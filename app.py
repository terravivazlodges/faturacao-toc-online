import streamlit as st
import pandas as pd
import re

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
st.write("Automação de extração de reservas do **Smoobu** (Excel ou CSV) organizadas **cronologicamente** para emissão de faturas no **TOC Online**.")

uploaded_file = st.file_uploader("Carregue o ficheiro de reservas do Smoobu (.xlsx ou .csv)", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        # Identificar se é Excel ou CSV e efetuar a leitura
        filename = uploaded_file.name.lower()
        if filename.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8-sig')
        
        # 1. ORDENAÇÃO CRONOLÓGICA por Chegada (Check-in) e Partida (Check-out)
        df['Chegada_DT'] = pd.to_datetime(df['Chegada'], format='%d-%m-%y', errors='coerce')
        df['Partida_DT'] = pd.to_datetime(df['Partida'], format='%d-%m-%y', errors='coerce')
        
        # Ordenar primeiramente pela data de chegada e em seguida pela data de partida
        df = df.sort_values(by=['Chegada_DT', 'Partida_DT'], ascending=[True, True]).reset_index(drop=True)
        
        # Limpeza e conversão do Preço Bruto
        df['Preço_Bruto'] = df['Preço'].astype(str).str.replace('€','', regex=False).str.replace(',','.', regex=False).str.strip().astype(float)
        
        def extrair_taxa_turistica(row):
            notas = str(row.get('Notas', ''))
            preco_txt = str(row.get('Preço', ''))
            detalhes = str(row.get('Detalhes de preço', ''))
            
            texto_agrupado = f"{notas} {preco_txt} {detalhes}"
            
            # Pesquisa por imposto municipal no formato Booking/OTA (ex: "imposto municipal - EUR 12")
            match_imposto = re.search(r'(?:imposto municipal|taxa turistica|city tax)\s*-\s*EUR\s*(\d+[\.,]?\d*)', texto_agrupado, re.IGNORECASE)
            if match_imposto:
                try:
                    return float(match_imposto.group(1).replace(',', '.'))
                except:
                    pass
            
            # Pesquisa por menções em euros perto de termos fiscais/municipais
            match_geral = re.search(r'(\d+[\.,]?\d*)\s*(?:€|EUR)', texto_agrupado, re.IGNORECASE)
            if match_geral and any(termo in texto_agrupado.lower() for termo in ['turistica', 'municipal', 'tx', 'imposto', 'city tax']):
                try:
                    return float(match_geral.group(1).replace(',', '.'))
                except:
                    pass
                    
            return 0.0

        # Aplicação da extração da taxa turística / imposto municipal
        df['Taxa_Turistica'] = df.apply(extrair_taxa_turistica, axis=1)
        
        # Cálculo do valor do alojamento sem IVA (4% Açores)
        df['Preco_Alojamento_Sem_IVA'] = ((df['Preço_Bruto'] - df['Taxa_Turistica']) / 1.04).round(2)

        linhas_toc = []

        for _, row in df.iterrows():
            data_doc = row['Chegada']
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
            
            # Linha 1: Alojamento Local (4% IVA)
            linhas_toc.append({
                'Tipo_Documento': 'FR',
                'Data_Documento': data_doc,
                'Cliente_Nome': cliente,
                'Cliente_NIF': '999999990',
                'Codigo_Artigo': codigo_artigo,
                'Descricao': f'Alojamento Local - {alojamento_nome}',
                'Quantidade': 1.0,
                'Preco_Unitario': row['Preco_Alojamento_Sem_IVA'],
                'Taxa_IVA': 4.0,
                'Observacoes': f'Reserva Smoobu / {portal}'
            })
            
            # Linha 2: Taxa Turística / Imposto Municipal (0% IVA com código TTUR, caso exista)
            taxa_turistica = row['Taxa_Turistica']
            if taxa_turistica > 0:
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
                    'Observacoes': 'Taxa turística / imposto municipal recolhido'
                })

        df_toc = pd.DataFrame(linhas_toc)

        st.success(f"✅ Ficheiro processado e ordenado cronologicamente com sucesso! Geradas {len(df_toc)} linhas para {len(df)} reservas.")

        st.subheader("📋 Tabela de Apoio e Validação Prévia (Ordenada por Data)")
        st.dataframe(df_toc, use_container_width=True)

        csv_toc = df_toc.to_csv(index=False, sep=';', encoding='utf-8-sig')

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Descarregar Ficheiro de Importação (TOC Online)",
            data=csv_toc,
            file_name="faturacao_toc_online.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o ficheiro: {e}")
else:
    st.info("💡 Por favor, carregue o ficheiro Excel (.xlsx) ou CSV de reservas do Smoobu.")
