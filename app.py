import streamlit as st
import pandas as pd
import io

# Configuração da página para telemóvel
st.set_page_config(page_title="CIEP 205 - Diário", page_icon="🏫", layout="centered")

st.title("🏫 Diário Docente - CIEP 205")
st.subheader("Painel do Conselho de Classe")
st.write("Baixe o arquivo `.csv` do sistema e envie aqui para gerar o Excel.")

# Caixa para o professor selecionar o arquivo pelo telemóvel ou PC
arquivo_enviado = st.file_uploader("Selecione o arquivo Diário de Classe (.csv)", type=["csv"])

if arquivo_enviado is not None:
    try:
        # Lê os dados enviados com o separador correto de ponto e vírgula
        df_notas = pd.read_csv(arquivo_enviado, sep=",", encoding="utf-8-sig")
        
        st.success("✅ Arquivo processado com sucesso!")
        
        # Cria o arquivo Excel na memória do servidor
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_notas.to_excel(writer, index=False, sheet_name="Fechamento_Bimestre")
        buffer.seek(0)
        
        # Botão para o professor descarregar o Excel formatado
        st.download_button(
            label="📥 Baixar Excel para o Conselho",
            data=buffer,
            file_name="Consolidado_Bimestre_CIEP_205.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
    except Exception as e:
        st.error(f"❌ Erro ao ler o arquivo: {e}")

st.caption("Desenvolvido para automação da gestão escolar do CIEP 205 Frei Agostinho Fíncias.")
