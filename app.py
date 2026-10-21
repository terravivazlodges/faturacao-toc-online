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
st.write("Automação de extração de reservas do **Smoobu** para emissão de faturas no **TOC Online** com atribuição correta de códigos de artigos.")

uploaded_file = st.file_uploader("Carregue o ficheiro CSV de reservas (.csv) do Smoobu", type="csv")

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file, sep=';', encoding='utf-8-sig')
        
        df['Preço_Bruto'] = df['Preço'].astype(str).str.replace('€','', regex=False).str.replace(',','.', regex=False).str.strip().astype(float)
        
        def extrair_taxa_turistica(nota):
            if pd.isna(nota):
                return 0.0
            match = re.search(r'(\d+)\s*€', str(nota))
            if match and ('turistica' in str(nota).lower() or 'tx' in str(nota).lower()):
                return float(match.group(1))
            return 0.0

        df['Taxa_Turistica'] = df['Notas'].apply(extrair_taxa_turistica)
        df['Preco_Alojamento_Sem_IVA'] = ((df['Preço_Bruto'] - df['Taxa_Turistica']) / 1.04).round(2)

        linhas_toc = []

        for _, row in df.iterrows():
            data_doc = row['Chegada']
            cliente = str(row['Hóspede']) if pd.notna(row['Hóspede']) else 'Consumidor Final'
            alojamento_nome = str(row['Alojamento'])
            portal = str(row['Portal']) if pd.notna(row['Portal']) else 'Direto'
            
            # Determinar o código de artigo correto com base no nome do alojamento
            aloj_upper = alojamento_nome.upper()
            if any(k in aloj_upper for k in ['PORTO', 'BAY', 'VILLA']):
                codigo_artigo = 'AL-PB'
            elif any(k in aloj_upper for k in ['SUITE', 'BLUE', 'GREEN', 'GARDEN']):
                codigo_artigo = 'AL-RC'
            else:
                codigo_artigo = 'AL-CB' # Casa da Baía / Ribeira por omissão
            
            # Linha 1: Alojamento Local
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
            
            # Linha 2: Taxa Turística (se aplicável)
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
                    'Observacoes': 'Taxa Turística recolhida'
                })

        df_toc = pd.DataFrame(linhas_toc)

        st.success(f"✅ Ficheiro processado com sucesso! Geradas {len(df_toc)} linhas de faturação para {len(df)} reservas.")

        st.subheader("📋 Tabela de Apoio e Validação Prévia")
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
    st.info("💡 Por favor, carregue o ficheiro CSV de reservas do Smoobu.")
