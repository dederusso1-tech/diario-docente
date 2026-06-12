import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Diário Docente - CIEP 205", page_icon="🏫")

st.title("🏫 Diário Docente - CIEP 205")
st.subheader("Fechamento de Bimestre — Conselho de Classe")

arquivo_enviado = st.file_uploader("Importe a planilha .csv da SEEDUC abaixo:", type=["csv"])

if arquivo_enviado is not None:
    try:
        # Lê o arquivo pulando linhas com erro de colunas (como cabeçalhos extras)
        df_notas = pd.read_csv(arquivo_enviado, sep=",", on_bad_lines='skip', encoding="utf-8-sig")
        st.success("✅ Arquivo processado com sucesso!")
        
        # Mostra uma prévia dos dados na tela
        st.dataframe(df_notas.head(10))
        
        # Cria o arquivo Excel na memória para download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_notas.to_excel(writer, index=False, sheet_name="Fechamento_Bimestre")
        
        st.download_button(
            label="📊 Baixar Planilha Consolidada para o Excel",
            data=output.getvalue(),
            file_name="Consolidado_Bimestre_CIEP_205.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
else:
    st.info("Nenhum estudante matriculado nesta visualização. Importe a planilha acima para gerar o Excel.")

st.markdown("---")
st.caption("Desenvolvido para gerenciamento interno • CIEP 205 Frei Agostinho Fíncias")
