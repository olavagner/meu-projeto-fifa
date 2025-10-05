from __future__ import annotations
import streamlit as st
from datetime import datetime, timedelta
import hashlib
import json
import os
import pytz
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import logging
from typing import Optional
import time
from collections import defaultdict
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import qrcode
from io import BytesIO
import base64
import threading

# ==============================================
# CONFIGURAÇÕES INICIAIS
# ==============================================

# Configurações de diretório e arquivos
DATA_DIR = Path("auth_data")
DATA_DIR.mkdir(exist_ok=True)

KEYS_FILE = DATA_DIR / "keys.json"
USAGE_FILE = DATA_DIR / "usage.json"
SALES_FILE = DATA_DIR / "sales.json"

# Configurações de pagamento PIX
PIX_CPF = "01905990065"  # Seu CPF como chave PIX
WHATSAPP_NUM = "5549991663166"  # Seu WhatsApp com código do país
WHATSAPP_MSG = "Olá! Envio comprovante do FIFAlgorithm"

# Configuração de log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes para scraping
URL_AO_VIVO = "https://www.aceodds.com/pt/bet365-transmissao-ao-vivo.html"
URL_RESULTADOS = "https://www.fifastats.net/resultados"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}
COMPETICOES_PERMITIDAS = {
    "E-soccer - H2H GG League - 8 minutos de jogo",
    "Esoccer Battle Volta - 6 Minutos de Jogo",
    "E-soccer - GT Leagues - 12 mins de jogo",
    "E-soccer - Battle - 8 minutos de jogo",
}

# Variáveis globais para controle de atualização
UPDATE_INTERVAL = 300  # 5 minutos em segundos (atualização automática)
MANUAL_UPDATE_DURATION = 3600  # 60 minutos em segundos (duração do boost manual)
last_update_time = time.time()
manual_update_active_until = 0  # Timestamp até quando o boost manual está ativo

# Controle de thread
update_thread_started = False


# ==============================================
# FUNÇÕES AUXILIARES (DEFINIR PRIMEIRO)
# ==============================================

def calcular_estatisticas_jogador(df: pd.DataFrame, jogador: str, liga: str) -> dict:
    """Calcula estatísticas de um jogador em uma liga específica"""
    zeros = {
        "jogos_total": 0, "gols_marcados": 0, "gols_sofridos": 0,
        "gols_marcados_ht": 0, "gols_sofridos_ht": 0,
        "over_05_ht_hits": 0, "over_15_ht_hits": 0, "over_25_ht_hits": 0, "btts_ht_hits": 0,
        "over_05_ft_hits": 0, "over_15_ft_hits": 0, "over_25_ft_hits": 0, "over_35_ft_hits": 0,
        "over_45_ft_hits": 0, "over_55_ft_hits": 0, "over_65_ft_hits": 0, "btts_ft_hits": 0
    }
    if df.empty:
        return zeros.copy()

    jm = df[(df["Mandante"] == jogador) & (df["Liga"] == liga)]
    jv = df[(df["Visitante"] == jogador) & (df["Liga"] == liga)]

    s = zeros.copy()
    s["jogos_total"] = len(jm) + len(jv)

    def acum(jogo, casa: bool):
        gf_ft, ga_ft = (
            (jogo["Mandante FT"], jogo["Visitante FT"]) if casa
            else (jogo["Visitante FT"], jogo["Mandante FT"])
        )
        gf_ht, ga_ht = (
            (jogo["Mandante HT"], jogo["Visitante HT"]) if casa
            else (jogo["Visitante HT"], jogo["Mandante HT"])
        )
        s["gols_marcados"] += gf_ft
        s["gols_sofridos"] += ga_ft
        s["gols_marcados_ht"] += gf_ht
        s["gols_sofridos_ht"] += ga_ht

        total_ht = jogo["Total HT"]
        s["over_05_ht_hits"] += 1 if total_ht > 0 else 0
        s["over_15_ht_hits"] += 1 if total_ht > 1 else 0
        s["over_25_ht_hits"] += 1 if total_ht > 2 else 0
        s["btts_ht_hits"] += 1 if (gf_ht > 0 and ga_ht > 0) else 0

        total_ft = jogo["Total FT"]
        s["over_05_ft_hits"] += 1 if total_ft > 0 else 0
        s["over_15_ft_hits"] += 1 if total_ft > 1 else 0
        s["over_25_ft_hits"] += 1 if total_ft > 2 else 0
        s["over_35_ft_hits"] += 1 if total_ft > 3 else 0
        s["over_45_ft_hits"] += 1 if total_ft > 4 else 0
        s["over_55_ft_hits"] += 1 if total_ft > 5 else 0
        s["over_65_ft_hits"] += 1 if total_ft > 6 else 0
        s["btts_ft_hits"] += 1 if (gf_ft > 0 and ga_ft > 0) else 0

    for _, jogo in jm.iterrows():
        acum(jogo, True)
    for _, jogo in jv.iterrows():
        acum(jogo, False)

    return s


def cor_icon(h_m, t_m, h_v, t_v) -> str:
    """Retorna um ícone de cor com base nos percentuais de acerto"""
    pct_m = h_m / t_m if t_m else 0
    pct_v = h_v / t_v if t_v else 0
    if pct_m >= 0.70 and pct_v >= 0.70:
        return "🟢"
    if pct_m >= 0.60 and pct_v >= 0.60:
        return "🟡"
    return "🔴"


def format_stats(h_m, t_m, h_v, t_v) -> str:
    """Formata estatísticas com ícones de cor"""
    icon = cor_icon(h_m, t_m, h_v, t_v)
    return f"{icon} {h_m}/{t_m}\n{h_v}/{t_v}"


def format_gols_ht_com_icone_para_display(gols_ht_media: float) -> str:
    """Formata a média de gols HT com ícone de cor"""
    if gols_ht_media >= 2.75:
        return f"🟢 {gols_ht_media:.2f}"
    elif 2.62 <= gols_ht_media <= 2.74:
        return f"🟡 {gols_ht_media:.2f}"
    return f"⚪ {gols_ht_media:.2f}"


def sugerir_over_ht(media_gols_ht: float) -> str:
    """Sugere um mercado Over HT com base na média de gols HT"""
    if media_gols_ht >= 2.75:
        return "Over 2.5 HT"
    elif media_gols_ht >= 2.20:
        return "Over 1.5 HT"
    elif media_gols_ht >= 1.70:
        return "Over 0.5 HT"
    else:
        return "Sem Entrada"


def sugerir_over_ft(media_gols_ft: float) -> str:
    """Retorna a sugestão para Over FT com base na média de gols FT"""
    if media_gols_ft >= 6.70:
        return "Over 5.5 FT"
    elif media_gols_ft >= 5.70:
        return "Over 4.5 FT"
    elif media_gols_ft >= 4.50:
        return "Over 3.5 FT"
    elif media_gols_ft >= 3.45:
        return "Over 2.5 FT"
    elif media_gols_ft >= 2.40:
        return "Over 1.5 FT"
    elif media_gols_ft >= 2.00:
        return "Over 0.5 FT"
    else:
        return "Sem Entrada"


# ==============================================
# SISTEMA DE ATUALIZAÇÃO MELHORADO
# ==============================================

def start_auto_update():
    """Inicia a thread de atualização automática apenas uma vez"""
    global update_thread_started

    if not update_thread_started:
        def update_loop():
            while True:
                current_time = time.time()
                # Verifica se é hora de atualizar (automático OU manual ativo)
                if (current_time - last_update_time >= UPDATE_INTERVAL or
                        (manual_update_active_until > 0 and current_time <= manual_update_active_until and
                         current_time - last_update_time >= 60)):  # 1 min durante boost manual

                    if st.session_state.get("authenticated", False):
                        st.session_state["force_update"] = True
                        try:
                            st.rerun()
                        except:
                            pass
                time.sleep(30)  # Verifica a cada 30 segundos

        update_thread = threading.Thread(target=update_loop, daemon=True)
        update_thread.start()
        update_thread_started = True


def force_manual_update():
    """Ativa o modo de atualização manual por 60 minutos"""
    global manual_update_active_until, last_update_time
    manual_update_active_until = time.time() + MANUAL_UPDATE_DURATION
    last_update_time = 0  # Força atualização imediata
    st.session_state["force_update"] = True
    st.session_state["manual_update_active"] = True


def get_update_status():
    """Retorna o status atual da atualização"""
    current_time = time.time()
    if manual_update_active_until > current_time:
        time_left = int(manual_update_active_until - current_time)
        minutes = time_left // 60
        seconds = time_left % 60
        return f"🔄 Boost Ativo - {minutes:02d}:{seconds:02d} restantes"
    else:
        return "🌎 Atualização Automática (5min)"


# ==============================================
# FUNÇÕES PARA A ABA "BUSCAR JOGADOR"
# ==============================================

def obter_jogos_jogador(df_resultados: pd.DataFrame, jogador: str, n_jogos: int = 10) -> pd.DataFrame:
    """Obtém os últimos n jogos de um jogador específico"""
    mask_mandante = df_resultados["Mandante"] == jogador
    mask_visitante = df_resultados["Visitante"] == jogador
    jogos_jogador = df_resultados[mask_mandante | mask_visitante].copy()

    # Ordenar por data (mais recentes primeiro)
    if 'Data' in jogos_jogador.columns:
        jogos_jogador = jogos_jogador.sort_values('Data', ascending=False)
    else:
        jogos_jogador = jogos_jogador.iloc[::-1]

    return jogos_jogador.head(n_jogos)


def calcular_estatisticas_consolidadas(df_jogos: pd.DataFrame, jogador: str) -> dict:
    """Calcula estatísticas consolidadas do jogador"""
    if df_jogos.empty:
        return {}

    estatisticas = {
        'total_jogos': len(df_jogos),
        'vitorias': 0,
        'empates': 0,
        'derrotas': 0,
        'gols_marcados': 0,
        'gols_sofridos': 0,
        'gols_marcados_ht': 0,
        'gols_sofridos_ht': 0,
        'gols_marcados_2t': 0,
        'gols_sofridos_2t': 0,
        'clean_sheets': 0,
        'jogos_marcando': 0,
        'jogos_sofrendo': 0
    }

    for _, jogo in df_jogos.iterrows():
        if jogo["Mandante"] == jogador:
            gols_feitos_ft = jogo["Mandante FT"]
            gols_sofridos_ft = jogo["Visitante FT"]
            gols_feitos_ht = jogo["Mandante HT"]
            gols_sofridos_ht = jogo["Visitante HT"]
        else:
            gols_feitos_ft = jogo["Visitante FT"]
            gols_sofridos_ft = jogo["Mandante FT"]
            gols_feitos_ht = jogo["Visitante HT"]
            gols_sofridos_ht = jogo["Mandante HT"]

        gols_feitos_2t = gols_feitos_ft - gols_feitos_ht
        gols_sofridos_2t = gols_sofridos_ft - gols_sofridos_ht

        estatisticas['gols_marcados'] += gols_feitos_ft
        estatisticas['gols_sofridos'] += gols_sofridos_ft
        estatisticas['gols_marcados_ht'] += gols_feitos_ht
        estatisticas['gols_sofridos_ht'] += gols_sofridos_ht
        estatisticas['gols_marcados_2t'] += gols_feitos_2t
        estatisticas['gols_sofridos_2t'] += gols_sofridos_2t

        if gols_feitos_ft > gols_sofridos_ft:
            estatisticas['vitorias'] += 1
        elif gols_feitos_ft < gols_sofridos_ft:
            estatisticas['derrotas'] += 1
        else:
            estatisticas['empates'] += 1

        if gols_sofridos_ft == 0:
            estatisticas['clean_sheets'] += 1
        if gols_feitos_ft > 0:
            estatisticas['jogos_marcando'] += 1
        if gols_sofridos_ft > 0:
            estatisticas['jogos_sofrendo'] += 1

    estatisticas['ppg'] = (estatisticas['vitorias'] * 3 + estatisticas['empates']) / estatisticas['total_jogos'] if \
    estatisticas['total_jogos'] > 0 else 0
    estatisticas['media_gols_marcados'] = estatisticas['gols_marcados'] / estatisticas['total_jogos'] if estatisticas[
                                                                                                             'total_jogos'] > 0 else 0
    estatisticas['media_gols_sofridos'] = estatisticas['gols_sofridos'] / estatisticas['total_jogos'] if estatisticas[
                                                                                                             'total_jogos'] > 0 else 0
    estatisticas['saldo_gols'] = estatisticas['gols_marcados'] - estatisticas['gols_sofridos']

    total_gols_feitos = estatisticas['gols_marcados']
    estatisticas['percentual_gols_1t'] = (
                estatisticas['gols_marcados_ht'] / total_gols_feitos * 100) if total_gols_feitos > 0 else 0
    estatisticas['percentual_gols_2t'] = (
                estatisticas['gols_marcados_2t'] / total_gols_feitos * 100) if total_gols_feitos > 0 else 0

    return estatisticas


def classificar_estilo_jogo(estatisticas: dict) -> dict:
    """Classifica o estilo de jogo baseado nas estatísticas"""
    media_gm = estatisticas['media_gols_marcados']
    media_gs = estatisticas['media_gols_sofridos']
    ppg = estatisticas['ppg']

    if media_gm - media_gs >= 1.0:
        estilo = "⚡ OFENSIVO"
        descricao = "Ataca muito, marca muitos gols"
    elif media_gs - media_gm >= 1.0:
        estilo = "🛡️ DEFENSIVO"
        descricao = "Foca na defesa, poucos gols"
    else:
        estilo = "⚖️ EQUILIBRADO"
        descricao = "Balanço entre ataque e defesa"

    if estatisticas['percentual_gols_1t'] > 60:
        intensidade = "🎯 1º TEMPO"
        momento = "Começa forte e decide cedo"
    elif estatisticas['percentual_gols_2t'] > 60:
        intensidade = "💪 2º TEMPO"
        momento = "Melhora no decorrer do jogo"
    else:
        intensidade = "📊 DISTRIBUÍDO"
        momento = "Mantém ritmo constante"

    if ppg >= 2.0:
        consistencia = "📈 ALTA"
    elif ppg >= 1.5:
        consistencia = "📊 MÉDIA"
    else:
        consistencia = "🎭 VARIÁVEL"

    return {
        'estilo': estilo,
        'descricao_estilo': descricao,
        'intensidade': intensidade,
        'momento_pico': momento,
        'consistencia': consistencia,
        'classificacao_geral': f"{estilo} • {intensidade}"
    }


def analisar_mercados_jogador(df_jogos: pd.DataFrame, jogador: str) -> dict:
    """Analisa os mercados mais relevantes para o jogador"""
    if df_jogos.empty:
        return {}

    mercados = {
        'over_05_ft': 0, 'over_15_ft': 0, 'over_25_ft': 0, 'over_35_ft': 0,
        'over_05_ht': 0, 'over_15_ht': 0, 'over_25_ht': 0,
        'btts_ft': 0, 'btts_ht': 0,
        'ambos_marcam_ft': 0, 'ambos_marcam_ht': 0
    }

    for _, jogo in df_jogos.iterrows():
        total_ft = jogo["Total FT"]
        total_ht = jogo["Total HT"]

        if total_ft > 0.5: mercados['over_05_ft'] += 1
        if total_ft > 1.5: mercados['over_15_ft'] += 1
        if total_ft > 2.5: mercados['over_25_ft'] += 1
        if total_ft > 3.5: mercados['over_35_ft'] += 1

        if total_ht > 0.5: mercados['over_05_ht'] += 1
        if total_ht > 1.5: mercados['over_15_ht'] += 1
        if total_ht > 2.5: mercados['over_25_ht'] += 1

        if jogo["Mandante FT"] > 0 and jogo["Visitante FT"] > 0:
            mercados['btts_ft'] += 1

    total_jogos = len(df_jogos)
    for key in mercados:
        mercados[key] = (mercados[key] / total_jogos * 100) if total_jogos > 0 else 0

    melhores_mercados = []
    if mercados['over_25_ft'] >= 70:
        melhores_mercados.append(("Over 2.5 FT", "🟢 ALTA"))
    elif mercados['over_25_ft'] >= 60:
        melhores_mercados.append(("Over 2.5 FT", "🟡 MÉDIA"))

    if mercados['over_15_ft'] >= 80:
        melhores_mercados.append(("Over 1.5 FT", "🟢 ALTA"))
    elif mercados['over_15_ft'] >= 70:
        melhores_mercados.append(("Over 1.5 FT", "🟡 MÉDIA"))

    if mercados['btts_ft'] >= 70:
        melhores_mercados.append(("Ambos Marcam", "🟢 ALTA"))
    elif mercados['btts_ft'] >= 60:
        melhores_mercados.append(("Ambos Marcam", "🟡 MÉDIA"))

    mercados['melhores_mercados'] = melhores_mercados
    return mercados


def calcular_sequencias_atuais(df_jogos: pd.DataFrame, jogador: str) -> dict:
    """Calcula sequências atuais do jogador"""
    if df_jogos.empty:
        return {}

    sequencias = {
        'vitorias': 0,
        'empates': 0,
        'derrotas': 0,
        'marcando': 0,
        'sofrendo': 0,
        'invicto': 0,
        'over_15_gm': 0,
        'over_15_gs': 0
    }

    df_ordenado = df_jogos.head(10)

    for _, jogo in df_ordenado.iterrows():
        if jogo["Mandante"] == jogador:
            gols_feitos = jogo["Mandante FT"]
            gols_sofridos = jogo["Visitante FT"]
        else:
            gols_feitos = jogo["Visitante FT"]
            gols_sofridos = jogo["Mandante FT"]

        if sequencias['vitorias'] == 0 and sequencias['empates'] == 0 and sequencias['derrotas'] == 0:
            if gols_feitos > gols_sofridos:
                sequencias['vitorias'] = 1
                sequencias['invicto'] = 1
            elif gols_feitos == gols_sofridos:
                sequencias['empates'] = 1
                sequencias['invicto'] = 1
            else:
                sequencias['derrotas'] = 1
        else:
            if gols_feitos > gols_sofridos:
                if sequencias['derrotas'] > 0 or sequencias['empates'] > 0:
                    break
                sequencias['vitorias'] += 1
                sequencias['invicto'] += 1
            elif gols_feitos == gols_sofridos:
                if sequencias['vitorias'] > 0 or sequencias['derrotas'] > 0:
                    break
                sequencias['empates'] += 1
                sequencias['invicto'] += 1
            else:
                if sequencias['vitorias'] > 0 or sequencias['empates'] > 0:
                    break
                sequencias['derrotas'] += 1

        if gols_feitos > 0:
            sequencias['marcando'] += 1
        else:
            break

        if gols_feitos > 1.5:
            sequencias['over_15_gm'] += 1
        else:
            break

    for _, jogo in df_ordenado.iterrows():
        if jogo["Mandante"] == jogador:
            gols_sofridos = jogo["Visitante FT"]
        else:
            gols_sofridos = jogo["Mandante FT"]

        if gols_sofridos > 0:
            sequencias['sofrendo'] += 1
        else:
            break

        if gols_sofridos > 1.5:
            sequencias['over_15_gs'] += 1
        else:
            break

    return sequencias


def gerar_alertas_padroes(estatisticas: dict, estilo: dict, mercados: dict, sequencias: dict) -> list:
    """Gera alertas inteligentes baseados nos padrões do jogador"""
    alertas = []

    if estatisticas['media_gols_marcados'] >= 3.0:
        alertas.append("🎯 FAZ MUITOS GOLS - Média ofensiva muito alta")
    elif estatisticas['media_gols_marcados'] <= 1.0:
        alertas.append("⚠️ BAIXA PRODUÇÃO OFENSIVA - Poucos gols marcados")

    if estatisticas['media_gols_sofridos'] >= 3.0:
        alertas.append("🛡️ DEFESA FRACA - Sofre muitos gols")
    elif estatisticas['media_gols_sofridos'] <= 1.0:
        alertas.append("🔒 DEFESA SÓLIDA - Poucos gols sofridos")

    if estatisticas['percentual_gols_1t'] >= 70:
        alertas.append("⚡ COMEÇA FORTE - Maioria dos gols no 1º tempo")
    elif estatisticas['percentual_gols_2t'] >= 70:
        alertas.append("💪 MELHORA NO FIM - Maioria dos gols no 2º tempo")

    if sequencias['vitorias'] >= 3:
        alertas.append(f"📈 MOMENTO POSITIVO - {sequencias['vitorias']} vitórias consecutivas")
    if sequencias['derrotas'] >= 3:
        alertas.append(f"📉 MOMENTO NEGATIVO - {sequencias['derrotas']} derrotas consecutivas")
    if sequencias['marcando'] >= 5:
        alertas.append(f"🔥 SEQÜÊNCIA OFENSIVA - Marcou em {sequencias['marcando']} jogos seguidos")

    for mercado, confianca in mercados.get('melhores_mercados', []):
        if "ALTA" in confianca:
            alertas.append(f"💰 MELHOR MERCADO - {mercado} ({confianca})")

    return alertas


def criar_aba_buscar_jogador(df_resultados: pd.DataFrame):
    """Cria a aba de análise individual de jogadores - VERSÃO ORGANIZADA"""
    st.header("🎯 Análise Individual de Jogadores")
    st.write("Analise o desempenho detalhado de cada jogador com estatísticas avançadas")

    # Divisão em duas colunas principais
    col_filtro, col_info = st.columns([1, 2])

    with col_filtro:
        st.subheader("🔍 Filtros")

        # Obter lista de todos os jogadores únicos
        todos_jogadores = sorted(set(df_resultados['Mandante'].unique()) | set(df_resultados['Visitante'].unique()))

        jogador_selecionado = st.selectbox(
            "**Selecione o Jogador:**",
            options=todos_jogadores,
            index=0,
            help="Escolha um jogador para analisar seu desempenho"
        )

        n_jogos_analise = st.slider(
            "**Jogos para Análise:**",
            min_value=5,
            max_value=30,
            value=10,
            help="Número de jogos mais recentes a serem considerados"
        )

        # Botão de análise
        if st.button("🚀 **Analisar Jogador**", type="primary", use_container_width=True):
            st.session_state['analisar_jogador'] = True
            st.session_state['jogador_selecionado'] = jogador_selecionado
            st.session_state['n_jogos_analise'] = n_jogos_analise

    with col_info:
        st.subheader("💡 Como Usar")
        with st.expander("📖 Guia Rápido de Análise", expanded=True):
            st.markdown("""
            **🎯 Dicas para Análise:**
            - **PPG > 2.0**: Jogador consistente
            - **Média Gols > 2.5**: Bom poder ofensivo  
            - **Over 2.5 FT > 70%**: Forte candidato a Over
            - **Sequências +3**: Momento de forma

            **📊 Métricas Principais:**
            - **PPG**: Pontos por jogo (3 vitória, 1 empate)
            - **Gols/Partida**: Média de gols marcados
            - **Clean Sheets**: Jogos sem sofrer gols
            - **Sequências**: Momentum atual do jogador
            """)

    # Análise do jogador (após clique do botão)
    if st.session_state.get('analisar_jogador', False) and st.session_state.get('jogador_selecionado'):
        jogador_selecionado = st.session_state['jogador_selecionado']
        n_jogos_analise = st.session_state['n_jogos_analise']

        with st.spinner(f"🔍 Analisando {jogador_selecionado}..."):
            df_jogos_jogador = obter_jogos_jogador(df_resultados, jogador_selecionado, n_jogos_analise)

            if df_jogos_jogador.empty:
                st.error(f"❌ Nenhum jogo encontrado para **{jogador_selecionado}**")
                return

            # Calcular todas as métricas
            estatisticas = calcular_estatisticas_consolidadas(df_jogos_jogador, jogador_selecionado)
            estilo_jogo = classificar_estilo_jogo(estatisticas)
            analise_mercados = analisar_mercados_jogador(df_jogos_jogador, jogador_selecionado)
            sequencias = calcular_sequencias_atuais(df_jogos_jogador, jogador_selecionado)
            alertas = gerar_alertas_padroes(estatisticas, estilo_jogo, analise_mercados, sequencias)

            # ===== LAYOUT ORGANIZADO =====

            # CABEÇALHO DO JOGADOR
            st.markdown("---")
            col_header1, col_header2, col_header3 = st.columns([2, 1, 1])

            with col_header1:
                st.success(f"## 📊 {jogador_selecionado}")
                st.caption(
                    f"**Período analisado:** Últimos {len(df_jogos_jogador)} jogos | **Estilo:** {estilo_jogo['classificacao_geral']}")

            with col_header2:
                st.metric("**PPG**", f"{estatisticas['ppg']:.2f}")

            with col_header3:
                st.metric("**Saldo Gols**", estatisticas['saldo_gols'])

            # PRIMEIRA LINHA: ESTATÍSTICAS PRINCIPAIS
            st.subheader("📈 Desempenho Geral")

            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                st.metric("**Vitórias**", estatisticas['vitorias'],
                          delta=f"{estatisticas['vitorias'] / estatisticas['total_jogos'] * 100:.1f}%" if estatisticas[
                                                                                                              'total_jogos'] > 0 else "0%")

            with col2:
                st.metric("**Gols/Partida**", f"{estatisticas['media_gols_marcados']:.2f}")

            with col3:
                st.metric("**Sofrer/Partida**", f"{estatisticas['media_gols_sofridos']:.2f}")

            with col4:
                st.metric("**Clean Sheets**", estatisticas['clean_sheets'],
                          delta=f"{estatisticas['clean_sheets'] / estatisticas['total_jogos'] * 100:.1f}%" if
                          estatisticas['total_jogos'] > 0 else "0%")

            with col5:
                st.metric("**Jogos Marcando**", estatisticas['jogos_marcando'],
                          delta=f"{estatisticas['jogos_marcando'] / estatisticas['total_jogos'] * 100:.1f}%" if
                          estatisticas['total_jogos'] > 0 else "0%")

            # SEGUNDA LINHA: PERFIL E SEQUÊNCIAS
            col_perfil, col_sequencias = st.columns(2)

            with col_perfil:
                with st.container(border=True):
                    st.subheader("🎭 Perfil do Jogador")

                    col_p1, col_p2 = st.columns(2)

                    with col_p1:
                        st.markdown(f"**{estilo_jogo['estilo']}**")
                        st.caption(estilo_jogo['descricao_estilo'])

                        st.markdown(f"**{estilo_jogo['intensidade']}**")
                        st.caption(estilo_jogo['momento_pico'])

                    with col_p2:
                        st.markdown(f"**{estilo_jogo['consistencia']}**")
                        st.caption("Consistência de resultados")

                        # Distribuição de gols
                        st.markdown("**📊 Distribuição Gols**")
                        st.caption(
                            f"1ºT: {estatisticas['percentual_gols_1t']:.1f}% | 2ºT: {estatisticas['percentual_gols_2t']:.1f}%")

            with col_sequencias:
                with st.container(border=True):
                    st.subheader("📈 Sequências Atuais")

                    cols_seq = st.columns(4)
                    sequencias_display = [
                        ("✅ Vitórias", sequencias['vitorias'], "green"),
                        ("➖ Empates", sequencias['empates'], "yellow"),
                        ("❌ Derrotas", sequencias['derrotas'], "red"),
                        ("🎯 Marcando", sequencias['marcando'], "blue")
                    ]

                    for idx, (label, valor, cor) in enumerate(sequencias_display):
                        with cols_seq[idx]:
                            st.metric(label, valor)

            # TERCEIRA LINHA: ANÁLISE DE MERCADOS
            st.subheader("💰 Análise de Mercados")

            col_overs, col_btts, col_melhores = st.columns([2, 1, 2])

            with col_overs:
                with st.container(border=True):
                    st.markdown("**🎯 Probabilidade de Overs**")

                    # Full Time
                    st.markdown("**Full Time:**")
                    col_ft1, col_ft2, col_ft3, col_ft4 = st.columns(4)

                    with col_ft1:
                        st.metric("Over 0.5", f"{analise_mercados['over_05_ft']:.0f}%")
                    with col_ft2:
                        st.metric("Over 1.5", f"{analise_mercados['over_15_ft']:.0f}%")
                    with col_ft3:
                        st.metric("Over 2.5", f"{analise_mercados['over_25_ft']:.0f}%")
                    with col_ft4:
                        st.metric("Over 3.5", f"{analise_mercados['over_35_ft']:.0f}%")

                    # Half Time
                    st.markdown("**Half Time:**")
                    col_ht1, col_ht2, col_ht3 = st.columns(3)

                    with col_ht1:
                        st.metric("Over 0.5", f"{analise_mercados['over_05_ht']:.0f}%")
                    with col_ht2:
                        st.metric("Over 1.5", f"{analise_mercados['over_15_ht']:.0f}%")
                    with col_ht3:
                        st.metric("Over 2.5", f"{analise_mercados['over_25_ht']:.0f}%")

            with col_btts:
                with st.container(border=True):
                    st.markdown("**🔄 Ambos Marcam**")
                    st.metric("Full Time", f"{analise_mercados['btts_ft']:.0f}%")
                    st.metric("Half Time", f"{analise_mercados['btts_ht']:.0f}%")

            with col_melhores:
                with st.container(border=True):
                    st.markdown("**💎 Melhores Mercados**")

                    if analise_mercados.get('melhores_mercados'):
                        for mercado, confianca in analise_mercados['melhores_mercados']:
                            if "ALTA" in confianca:
                                st.success(f"🟢 **{mercado}** - {confianca}")
                            else:
                                st.warning(f"🟡 **{mercado}** - {confianca}")
                    else:
                        st.info("📊 Analisando padrões...")

            # QUARTA LINHA: ALERTAS E HISTÓRICO
            col_alertas, col_historico = st.columns([1, 2])

            with col_alertas:
                if alertas:
                    with st.container(border=True):
                        st.subheader("🚨 Alertas Inteligentes")

                        for alerta in alertas:
                            if "ALTA" in alerta or "MELHOR" in alerta:
                                st.success(f"• {alerta}")
                            elif "BAIXA" in alerta or "NEGATIVO" in alerta:
                                st.error(f"• {alerta}")
                            else:
                                st.warning(f"• {alerta}")

            with col_historico:
                with st.container(border=True):
                    st.subheader("📅 Últimos Jogos")

                    # Preparar DataFrame para exibição compacta
                    df_display = df_jogos_jogador.copy()
                    if 'Data' in df_display.columns:
                        df_display = df_display[
                            ['Data', 'Liga', 'Mandante', 'Visitante', 'Mandante FT', 'Visitante FT', 'Total FT']]
                    else:
                        df_display = df_display[
                            ['Liga', 'Mandante', 'Visitante', 'Mandante FT', 'Visitante FT', 'Total FT']]

                    # Estilizar a tabela
                    st.dataframe(
                        df_display,
                        use_container_width=True,
                        height=300
                    )

            # BOTÃO DE DOWNLOAD
            st.markdown("---")
            col_download, _ = st.columns([1, 3])

            with col_download:
                csv = df_jogos_jogador.to_csv(index=False)
                st.download_button(
                    label="📥 **Exportar Dados**",
                    data=csv,
                    file_name=f"{jogador_selecionado}_historico.csv",
                    mime="text/csv",
                    use_container_width=True
                )


# ==============================================
# CSS PERSONALIZADO - TEMA DARK MODERNO
# ==============================================

st.markdown("""
<style>
    /* TEMA DEEP SPACE PARA TABELA AO VIVO */
    div[data-testid="stDataFrame"] {
        position: relative;
        background: #000000;
        border-radius: 15px;
        overflow: hidden;
    }

    div[data-testid="stDataFrame"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image: 
            radial-gradient(2px 2px at 20% 30%, white, transparent),
            radial-gradient(2px 2px at 60% 70%, white, transparent),
            radial-gradient(1px 1px at 50% 50%, white, transparent),
            radial-gradient(1px 1px at 80% 10%, white, transparent),
            radial-gradient(2px 2px at 90% 60%, white, transparent),
            radial-gradient(1px 1px at 33% 80%, white, transparent),
            radial-gradient(1px 1px at 15% 45%, rgba(255,255,255,0.5), transparent),
            radial-gradient(1px 1px at 70% 20%, rgba(255,255,255,0.5), transparent);
        background-size: 200% 200%;
        animation: stars 60s linear infinite;
        pointer-events: none;
        z-index: 0;
    }

    @keyframes stars {
        0% { 
            transform: scale(1);
            opacity: 0.8;
        }
        50% { 
            transform: scale(1.5);
            opacity: 1;
        }
        100% { 
            transform: scale(1);
            opacity: 0.8;
        }
    }

    div[data-testid="stDataFrame"] table {
        background: rgba(0, 0, 0, 0.9) !important;
        position: relative;
        z-index: 1;
    }

    div[data-testid="stDataFrame"] thead th {
        background: linear-gradient(135deg, #1a1a3e 0%, #0f0f2e 100%) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        text-align: center !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        font-size: 1rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
    }

    div[data-testid="stDataFrame"] td {
        background: rgba(10, 10, 30, 0.8) !important;
        color: #e0e0e0 !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        text-align: center !important;
        padding: 12px 15px !important;
        position: relative;
    }

    div[data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background: rgba(15, 15, 40, 0.8) !important;
    }

    div[data-testid="stDataFrame"] tbody tr:nth-child(odd) td {
        background: rgba(10, 10, 30, 0.8) !important;
    }

    div[data-testid="stDataFrame"] tbody tr:hover td {
        background: rgba(30, 30, 60, 0.9) !important;
        box-shadow: 
            inset 0 0 20px rgba(100, 150, 255, 0.2),
            0 0 15px rgba(100, 150, 255, 0.3) !important;
        transform: scale(1.01);
        transition: all 0.3s ease;
    }

    div[data-testid="stDataFrame"] {
        box-shadow: 
            0 0 30px rgba(100, 150, 255, 0.2),
            inset 0 0 50px rgba(0, 0, 0, 0.5);
        border: 1px solid rgba(100, 150, 255, 0.3);
    }

    .ag-theme-streamlit,
    .ag-theme-alpine {
        background: #000000 !important;
    }

    .ag-theme-streamlit .ag-header,
    .ag-theme-alpine .ag-header {
        background: linear-gradient(135deg, #1a1a3e 0%, #0f0f2e 100%) !important;
        border-bottom: 2px solid rgba(100, 150, 255, 0.3) !important;
    }

    .ag-theme-streamlit .ag-header-cell,
    .ag-theme-alpine .ag-header-cell {
        color: #ffffff !important;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
    }

    .ag-theme-streamlit .ag-row,
    .ag-theme-alpine .ag-row {
        background: rgba(10, 10, 30, 0.8) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    .ag-theme-streamlit .ag-row-even,
    .ag-theme-alpine .ag-row-even {
        background: rgba(15, 15, 40, 0.8) !important;
    }

    .ag-theme-streamlit .ag-row:hover,
    .ag-theme-alpine .ag-row:hover {
        background: rgba(30, 30, 60, 0.9) !important;
        box-shadow: inset 0 0 20px rgba(100, 150, 255, 0.2) !important;
    }

    .ag-theme-streamlit .ag-cell,
    .ag-theme-alpine .ag-cell {
        color: #e0e0e0 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    .main > div:first-child {
        background: 
            radial-gradient(ellipse at 30% 40%, rgba(56, 89, 248, 0.08) 0%, transparent 50%),
            radial-gradient(ellipse at 70% 60%, rgba(168, 85, 247, 0.08) 0%, transparent 50%),
            #000000;
    }

    .live-indicator {
        background: linear-gradient(135deg, #ff0000, #ff6b6b);
        color: white;
        padding: 10px 20px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        margin-bottom: 20px;
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }

    .stButton button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 20px !important;
        font-weight: bold !important;
        transition: all 0.3s ease !important;
    }

    .stButton button:hover {
        transform: scale(1.05) !important;
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4) !important;
    }

    .stProgress > div > div > div {
        background: linear-gradient(90deg, #667eea, #764ba2) !important;
    }

    .update-status {
        background: rgba(102, 126, 234, 0.1);
        padding: 10px;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin: 10px 0;
    }

    .main-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 0;
    }

    .header-left {
        flex: 1;
    }

    .header-right {
        display: flex;
        align-items: center;
        gap: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================
# FUNÇÕES DO FIFALGORITHM (CORRIGIDAS)
# ==============================================

def requisicao_segura(url: str, timeout: int = 15) -> Optional[requests.Response]:
    """Realiza uma requisição HTTP segura"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao acessar {url}: {e}")
        st.error(f"❌ Erro de conexão com {url}: {e}")
        return None


@st.cache_data(show_spinner=False, ttl=300)
def extrair_dados_pagina(url: str) -> list[list[str]]:
    """Extrai dados de tabelas HTML"""
    resp = requisicao_segura(url)
    if not resp:
        return []

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        return [
            [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            for tr in soup.find_all("tr")
            if tr.find_all(["th", "td"])
        ]
    except Exception as e:
        logger.error(f"Erro ao processar HTML de {url}: {e}")
        st.error(f"❌ Erro ao processar dados de {url}")
        return []


@st.cache_data(show_spinner=False, ttl=300)
def buscar_resultados() -> pd.DataFrame:
    """Busca e processa os resultados históricos das partidas - CORRIGIDO"""
    linhas = extrair_dados_pagina(URL_RESULTADOS)
    if not linhas:
        return pd.DataFrame()

    try:
        max_cols = max(len(l) for l in linhas)
        for l in linhas:
            l.extend([""] * (max_cols - len(l)))
        df = pd.DataFrame(linhas)

        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = [
            str(c).strip() if pd.notna(c) else f"Coluna {i + 1}"
            for i, c in enumerate(df.columns)
        ]

        def clean_name(x):
            return re.sub(r"\s*\([^)]*\)", "", str(x)).strip()

        for col in ("Jogador 1", "Jogador 2"):
            if col in df.columns:
                df[col] = df[col].apply(clean_name)

        df = df.rename(
            columns={
                "Campeonato": "Liga",
                "Jogador 1": "Mandante",
                "Jogador 2": "Visitante",
                "Placar": "Placar Final",
            }
        )

        mapa_ligas = {
            "GT League": "GT 12 Min",
            "H2H 8m": "H2H 8 Min",
            "Battle 8m": "Battle 8 Min",
            "Battle 6m": "Volta 6 Min",
        }
        df["Liga"] = df["Liga"].replace(mapa_ligas)

        if "Placar HT" in df.columns:
            ht = (
                df["Placar HT"]
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.split("x", n=1, expand=True)
                .reindex(columns=[0, 1], fill_value="")
            )
            # CORREÇÃO: usar astype(int) em vez de ast(int)
            df["Mandante HT"] = pd.to_numeric(ht[0], errors="coerce").fillna(0).astype(int)
            df["Visitante HT"] = pd.to_numeric(ht[1], errors="coerce").fillna(0).astype(int)

        if "Placar Final" in df.columns:
            ft = (
                df["Placar Final"]
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.split("x", n=1, expand=True)
                .reindex(columns=[0, 1], fill_value="")
            )
            # CORREÇÃO: usar astype(int) em vez de ast(int)
            df["Mandante FT"] = pd.to_numeric(ft[0], errors="coerce").fillna(0).astype(int)
            df["Visitante FT"] = pd.to_numeric(ft[1], errors="coerce").fillna(0).astype(int)

            if {"Mandante HT", "Visitante HT"} <= set(df.columns):
                df["Total HT"] = df["Mandante HT"] + df["Visitante HT"]
            if {"Mandante FT", "Visitante FT"} <= set(df.columns):
                df["Total FT"] = df["Mandante FT"] + df["Visitante FT"]

            df = df.drop(columns=[c for c in ("Placar HT", "Placar Final") if c in df.columns])

            ordem = [
                "Data", "Liga", "Mandante", "Visitante",
                "Mandante HT", "Visitante HT", "Total HT",
                "Mandante FT", "Visitante FT", "Total FT",
            ]
            df = df[[c for c in ordem if c in df.columns]]

        return df

    except Exception as e:
        logger.error(f"Erro ao processar resultados: {e}")
        st.error(f"❌ Erro ao processar dados de resultados")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def carregar_dados_ao_vivo(df_resultados: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carrega dados ao vivo e calcula estatísticas"""
    linhas = extrair_dados_pagina(URL_AO_VIVO)
    if not linhas:
        return pd.DataFrame(), pd.DataFrame()

    try:
        df = pd.DataFrame(linhas)
        df = df[df.iloc[:, 3].isin(COMPETICOES_PERMITIDAS)].reset_index(drop=True)
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        df = df.drop(columns=[1])
        df.columns = ["Hora", "Confronto", "Liga"] + [
            f"Coluna {i}" for i in range(4, df.shape[1] + 1)
        ]

        def extrair_jogadores(txt: str):
            base = str(txt).replace("Ao Vivo Agora", "").strip()
            m = re.search(r"\(([^)]+)\).*?x.*?\(([^)]+)\)", base)
            return (m.group(1).strip(), m.group(2).strip()) if m else ("", "")

        df[["Mandante", "Visitante"]] = df["Confronto"].apply(
            lambda x: pd.Series(extrair_jogadores(x))
        )
        df = df.drop(columns=["Confronto"])

        mapa_ligas = {
            "E-soccer - H2H GG League - 8 minutos de jogo": "H2H 8 Min",
            "Esoccer Battle Volta - 6 Minutos de Jogo": "Volta 6 Min",
            "E-soccer - GT Leagues - 12 mins de jogo": "GT 12 Min",
            "E-soccer - Battle - 8 minutos de jogo": "Battle 8 Min",
        }
        df["Liga"] = df["Liga"].replace(mapa_ligas)

        stats_rows = []
        for _, r in df.iterrows():
            m, v, liga = r["Mandante"], r["Visitante"], r["Liga"]
            sm, sv = (
                calcular_estatisticas_jogador(df_resultados, m, liga),
                calcular_estatisticas_jogador(df_resultados, v, liga),
            )

            jm, jv = sm["jogos_total"], sv["jogos_total"]

            avg_m_gf_ht = sm["gols_marcados_ht"] / jm if jm else 0
            avg_m_ga_ht = sm["gols_sofridos_ht"] / jm if jm else 0
            avg_v_gf_ht = sv["gols_marcados_ht"] / jv if jv else 0
            avg_v_ga_ht = sv["gols_sofridos_ht"] / jv if jv else 0

            avg_m_gf_ft = sm["gols_marcados"] / jm if jm else 0
            avg_m_ga_ft = sm["gols_sofridos"] / jm if jm else 0
            avg_v_gf_ft = sv["gols_marcados"] / jv if jv else 0
            avg_v_ga_ft = sv["gols_sofridos"] / jv if jv else 0

            gp_calc = (avg_m_gf_ft + avg_v_ga_ft) / 2 if (jm and jv) else 0
            gc_calc = (avg_v_gf_ft + avg_m_ga_ft) / 2 if (jm and jv) else 0

            gp_ht = (avg_m_gf_ht + avg_v_ga_ht) / 2 if (jm and jv) else 0
            gc_ht = (avg_v_gf_ht + avg_m_ga_ht) / 2 if (jm and jv) else 0

            gols_ft = gp_calc + gc_calc
            gols_ht = gp_ht + gc_ht

            sugestao_ht = sugerir_over_ht(gols_ht)
            sugestao_ft = sugerir_over_ft(gols_ft)

            over_mandante = ""
            over_visitante = ""

            if 2.30 <= gp_calc <= 3.39:
                over_mandante = f"1.5 {m}"
            elif 3.40 <= gp_calc <= 4.50:
                over_mandante = f"2.5 {m}"

            if 2.30 <= gc_calc <= 3.39:
                over_visitante = f"1.5 {v}"
            elif 3.40 <= gc_calc <= 4.50:
                over_visitante = f"2.5 {v}"

            if "1.5" in over_mandante:
                over_mandante = f"🟡 {over_mandante}"
            elif "2.5" in over_mandante:
                over_mandante = f"🟢 {over_mandante}"

            if "1.5" in over_visitante:
                over_visitante = f"🟡 {over_visitante}"
            elif "2.5" in over_visitante:
                over_visitante = f"🟢 {over_visitante}"

            stats_rows.append(
                {
                    "J1": jm,
                    "J2": jv,
                    "GP": gp_calc,
                    "GC": gc_calc,
                    "GP_HT": gp_ht,
                    "GC_HT": gc_ht,
                    "Gols HT": gols_ht,
                    "Gols FT": gols_ft,
                    "Sugestão HT": sugestao_ht,
                    "Sugestão FT": sugestao_ft,
                    "Over Mandante": over_mandante,
                    "Over Visitante": over_visitante,
                }
            )

        df_stats = pd.DataFrame(stats_rows)
        df_base = df[["Hora", "Liga", "Mandante", "Visitante"]].copy()

        df_clean = pd.concat([df_base, df_stats], axis=1)
        df_display = df_clean.copy()

        df_display["GP"] = df_display["GP"].apply(lambda x: f"{x:.2f}")
        df_display["GC"] = df_display["GC"].apply(lambda x: f"{x:.2f}")
        df_display["Gols HT"] = df_display["Gols HT"].apply(lambda x: f"{x:.2f}")
        df_display["Gols FT"] = df_display["Gols FT"].apply(lambda x: f"{x:.2f}")

        colunas_ao_vivo_solicitadas = [
            "Hora", "Liga", "Mandante", "Visitante",
            "GP", "GC", "Gols HT", "Gols FT",
            "Over Mandante", "Over Visitante",
            "Sugestão HT", "Sugestão FT"
        ]

        return df_clean, df_display[colunas_ao_vivo_solicitadas]

    except Exception as e:
        logger.error(f"Erro ao carregar dados ao vivo: {e}")
        st.error(f"❌ Erro ao carregar e processar dados ao vivo.")
        return pd.DataFrame(), pd.DataFrame()


# ==============================================
# INTERFACE PRINCIPAL DO APLICATIVO
# ==============================================

def fifalgorithm_app():
    """Aplicativo principal do FIFAlgorithm"""

    # INICIALIZAÇÃO DO SESSION STATE
    if 'analisar_jogador' not in st.session_state:
        st.session_state.analisar_jogador = False
    if 'jogador_selecionado' not in st.session_state:
        st.session_state.jogador_selecionado = None
    if 'n_jogos_analise' not in st.session_state:
        st.session_state.n_jogos_analise = 10

    # Configuração da página
    st.set_page_config(
        page_title="FIFAlgorithm",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inicia a thread de atualização automática
    start_auto_update()

    brasil_timezone = pytz.timezone("America/Sao_Paulo")
    current_time_br = datetime.now(brasil_timezone).strftime("%H:%M:%S")

    # HEADER COM BOTÃO À DIREITA
    col_header_left, col_header_right = st.columns([3, 1])

    with col_header_left:
        st.markdown("""
        <div class="main-header">
            <div class="header-left">
                <h1>🦅 FIFAlgorithm</h1>
                <p>Análises Inteligentes de Partidas de E-soccer FIFA</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_header_right:
        if st.button("🚀 Atualizar Dados (60min Boost)", type="primary", use_container_width=True):
            with st.spinner("Ativando modo turbo..."):
                for i in range(100):
                    time.sleep(0.02)
                force_manual_update()
                st.success("✅ Boost ativado! Atualizando a cada 1min por 60min")
                st.rerun()

    # Status de atualização
    update_status = get_update_status()
    st.markdown(f'<div class="update-status"><strong>🟢 Status:</strong> {update_status}</div>', unsafe_allow_html=True)

    if st.session_state.get("force_update", False):
        st.success("✅ Dados atualizados automaticamente!")
        st.session_state["force_update"] = False

    st.markdown(f"**⌛️ Última atualização:** {current_time_br}")

    # Carrega os dados essenciais
    try:
        df_resultados = buscar_resultados()
        df_live_clean, df_live_display = carregar_dados_ao_vivo(df_resultados)

    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        df_resultados = pd.DataFrame()
        df_live_clean = pd.DataFrame()
        df_live_display = pd.DataFrame()

    # Sistema de abas - ORDEM CORRIGIDA
    tabs = st.tabs(["⚡️ Ao Vivo", "⭐️ Radar FIFA", "🔍 Buscar Jogador", "🧠 Alertas IA", "⚽️ Resultados"])

    # Aba 1: Ao Vivo - COM FILTROS SUPERIORES
    with tabs[0]:
        st.header("🔥 Buscar Jogos")

        if manual_update_active_until > time.time():
            time_left = int(manual_update_active_until - time.time())
            minutes = time_left // 60
            seconds = time_left % 60
            st.info(f"⏰ **Boost Ativo:** {minutes:02d}:{seconds:02d} restantes - Atualizando a cada 1 minuto")
            st.progress(time_left / MANUAL_UPDATE_DURATION)

        # Indicador de jogos ao vivo com animação
        if not df_live_display.empty:
            st.markdown(f"""
            <div class="live-indicator">
                🟢 AO VIVO - {len(df_live_display)} Jogos Disponíveis
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("⏳ Nenhuma partida ao vivo no momento")

        if not df_live_display.empty:
            # FILTROS SUPERIORES - ADICIONADOS AQUI
            st.subheader("🔍 Filtros")

            col_filtro1, col_filtro2, col_filtro3 = st.columns(3)

            with col_filtro1:
                # Filtro por Liga
                ligas_disponiveis = df_live_display['Liga'].unique()
                ligas_selecionadas = st.multiselect(
                    '**Filtrar por Liga:**',
                    options=ligas_disponiveis,
                    default=ligas_disponiveis,
                    help="Selecione as ligas para filtrar"
                )

            with col_filtro2:
                # Filtro por Sugestão HT
                sugestoes_ht = df_live_display['Sugestão HT'].unique()
                ht_selecionados = st.multiselect(
                    '**Filtrar por Sugestão HT:**',
                    options=sugestoes_ht,
                    default=sugestoes_ht,
                    help="Filtre pelas sugestões de Half Time"
                )

            with col_filtro3:
                # Filtro por Sugestão FT
                sugestoes_ft = df_live_display['Sugestão FT'].unique()
                ft_selecionados = st.multiselect(
                    '**Filtrar por Sugestão FT:**',
                    options=sugestoes_ft,
                    default=sugestoes_ft,
                    help="Filtre pelas sugestões de Full Time"
                )

            # Aplicar filtros
            df_filtrado = df_live_display[
                (df_live_display['Liga'].isin(ligas_selecionadas)) &
                (df_live_display['Sugestão HT'].isin(ht_selecionados)) &
                (df_live_display['Sugestão FT'].isin(ft_selecionados))
                ]

            # Mostrar contador de resultados
            st.info(f"📊 **{len(df_filtrado)} jogos** encontrados com os filtros aplicados")

            # Configuração da tabela SEM FILTROS NAS COLUNAS - MODIFICADO
            gb = GridOptionsBuilder.from_dataframe(df_filtrado)

            # Configuração para visualização limpa SEM FILTROS
            gb.configure_default_column(
                flex=1,
                minWidth=80,
                maxWidth=150,
                wrapText=True,
                autoHeight=True,
                editable=False,
                filterable=False,  # ✅ FILTROS DESABILITADOS nas colunas
                sortable=True,
                resizable=True
            )

            # Configurações específicas para cada coluna - SEM FILTROS
            column_configs = {
                "Hora": {"minWidth": 80, "maxWidth": 100},
                "Liga": {"minWidth": 100, "maxWidth": 120},
                "Mandante": {"minWidth": 120, "maxWidth": 150},
                "Visitante": {"minWidth": 120, "maxWidth": 150},
                "GP": {"minWidth": 60, "maxWidth": 80},
                "GC": {"minWidth": 60, "maxWidth": 80},
                "Gols HT": {"minWidth": 70, "maxWidth": 90},
                "Gols FT": {"minWidth": 70, "maxWidth": 90},
                "Over Mandante": {"minWidth": 120, "maxWidth": 150},
                "Over Visitante": {"minWidth": 120, "maxWidth": 150},
                "Sugestão HT": {"minWidth": 100, "maxWidth": 120},
                "Sugestão FT": {"minWidth": 100, "maxWidth": 120}
            }

            for col, config in column_configs.items():
                if col in df_filtrado.columns:
                    gb.configure_column(
                        col,
                        minWidth=config["minWidth"],
                        maxWidth=config["maxWidth"]
                        # ❌ REMOVIDO: filter=config["filter"]
                    )

            # Configurar seleção SEM paginação
            gb.configure_selection(
                selection_mode='multiple',
                use_checkbox=True
            )

            grid_options = gb.build()

            # Container para a tabela
            st.markdown('<div class="table-container">', unsafe_allow_html=True)

            # Renderizar tabela com altura dinâmica baseada no número de linhas
            height = min(800, 35 + 35 * len(df_filtrado))  # Altura máxima de 800px

            grid_response = AgGrid(
                df_filtrado,
                gridOptions=grid_options,
                height=height,
                width='100%',
                theme='streamlit',
                update_mode=GridUpdateMode.MODEL_CHANGED,
                allow_unsafe_jscode=True,
                enable_enterprise_modules=False
            )

            st.markdown('</div>', unsafe_allow_html=True)

            # Ações rápidas para seleção
            if grid_response['selected_rows']:
                selected_count = len(grid_response['selected_rows'])
                if st.button(f"📊 Analisar {selected_count} Jogos Selecionados", use_container_width=True):
                    st.info(f"Análise iniciada para {selected_count} jogos...")

    # Aba 2: Radar FIFA
    with tabs[1]:
        st.header("⭐️ Radar FIFA")
        st.write(" Indicador de Mercados Lucrativos por Liga em tempo Real.")

        CRITERIOS_HT = {
            "0.5 HT": {"min": 1.70, "max": float('inf')},
            "1.5 HT": {"min": 2.20, "max": float('inf')},
            "2.5 HT": {"min": 2.75, "max": float('inf')},
        }

        CRITERIOS_FT = {
            "0.5 FT": {"min": 2.00, "max": float('inf')},
            "1.5 FT": {"min": 2.40, "max": float('inf')},
            "2.5 FT": {"min": 3.45, "max": float('inf')},
            "3.5 FT": {"min": 4.50, "max": float('inf')},
            "4.5 FT": {"min": 5.70, "max": float('inf')},
            "5.5 FT": {"min": 6.70, "max": float('inf')},
        }

        if not df_live_clean.empty:
            ligas_unicas = df_live_clean["Liga"].unique()
            resultados_radar = []

            for liga in ligas_unicas:
                jogos_da_liga = df_live_clean[df_live_clean["Liga"] == liga].head(10)
                total_jogos_analisados = len(jogos_da_liga)

                if total_jogos_analisados == 0:
                    continue

                contadores_ht = {k: 0 for k in CRITERIOS_HT.keys()}
                contadores_ft = {k: 0 for k in CRITERIOS_FT.keys()}

                soma_gols_ht = 0
                soma_gols_ft = 0

                for _, jogo_ao_vivo in jogos_da_liga.iterrows():
                    media_gols_ht_jogo = jogo_ao_vivo["Gols HT"]
                    media_gols_ft_jogo = jogo_ao_vivo["Gols FT"]

                    if pd.isna(media_gols_ht_jogo): media_gols_ht_jogo = 0.0
                    if pd.isna(media_gols_ft_jogo): media_gols_ft_jogo = 0.0

                    soma_gols_ht += media_gols_ht_jogo
                    soma_gols_ft += media_gols_ft_jogo

                    for criterio, valores in CRITERIOS_HT.items():
                        if media_gols_ht_jogo >= valores["min"]:
                            contadores_ht[criterio] += 1

                    for criterio, contagem_info in CRITERIOS_FT.items():
                        if media_gols_ft_jogo >= contagem_info["min"]:
                            contadores_ft[criterio] += 1

                media_gols_ht_liga = soma_gols_ht / total_jogos_analisados if total_jogos_analisados > 0 else 0
                media_gols_ft_liga = soma_gols_ft / total_jogos_analisados if total_jogos_analisados > 0 else 0

                linha_liga = {
                    "Liga": liga,
                    "Média Gols HT": f"{media_gols_ht_liga:.2f}",
                    "Média Gols FT": f"{media_gols_ft_liga:.2f}"
                }

                for criterio, contagem in contadores_ht.items():
                    percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
                    if percentual == 100:
                        linha_liga[f"{criterio}"] = f"🟢 {int(percentual)}%"
                    elif 80 <= percentual <= 99:
                        linha_liga[f"{criterio}"] = f"🟡 {int(percentual)}%"
                    else:
                        linha_liga[f"{criterio}"] = f"{int(percentual)}%"

                for criterio, contagem in contadores_ft.items():
                    percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
                    if percentual == 100:
                        linha_liga[f"{criterio}"] = f"🟢 {int(percentual)}%"
                    elif 80 <= percentual <= 99:
                        linha_liga[f"{criterio}"] = f"🟡 {int(percentual)}%"
                    else:
                        linha_liga[f"{criterio}"] = f"{int(percentual)}%"

                resultados_radar.append(linha_liga)

            colunas_radar_ordenadas = [
                                          "Liga",
                                          "Média Gols HT",
                                          "Média Gols FT"
                                      ] + list(CRITERIOS_HT.keys()) + list(CRITERIOS_FT.keys())

            df_radar = pd.DataFrame(resultados_radar)

            for col in colunas_radar_ordenadas:
                if col not in df_radar.columns:
                    if col in ["Média Gols HT", "Média Gols FT"]:
                        df_radar[col] = "0.00"
                    else:
                        df_radar[col] = "0%"

            st.dataframe(
                df_radar[colunas_radar_ordenadas],
                use_container_width=True
            )
        else:
            st.info("Nenhum dado para o Radar FIFA.")

    # Aba 3: Buscar Jogador
    with tabs[2]:
        criar_aba_buscar_jogador(df_resultados)

    # Aba 4: Alertas IA
    with tabs[3]:
        st.header("🧠 Alertas IA")
        st.write("Dicas inteligentes de Apostas para cada Partida")

        if df_live_clean.empty or df_resultados.empty:
            st.warning("Dados insuficientes para gerar alertas. Aguarde a atualização.")
        else:
            MIN_JOGOS_CONFRONTO = 5
            MIN_PORCENTAGEM = 75

            brasil_tz = pytz.timezone('America/Sao_Paulo')
            hora_atual = datetime.now(brasil_tz).strftime("%H:%M")

            df_live_futuro = df_live_clean[df_live_clean['Hora'] > hora_atual].sort_values('Hora', ascending=True)

            if st.button("🎯 Gerar Análise Detalhada", type="primary", use_container_width=True):
                with st.spinner("Analisando confrontos diretos..."):
                    relatorios = []

                    for _, jogo in df_live_futuro.iterrows():
                        p1 = jogo["Mandante"]
                        p2 = jogo["Visitante"]
                        liga = jogo["Liga"]
                        hora_jogo = jogo["Hora"]

                        df_historico = df_resultados[
                            ((df_resultados["Mandante"] == p1) & (df_resultados["Visitante"] == p2)) |
                            ((df_resultados["Mandante"] == p2) & (df_resultados["Visitante"] == p1))
                            ]

                        if len(df_historico) >= MIN_JOGOS_CONFRONTO:
                            p1_wins = len(df_historico[((df_historico["Mandante"] == p1) & (
                                    df_historico["Mandante FT"] > df_historico["Visitante FT"])) |
                                                       ((df_historico["Visitante"] == p1) & (
                                                               df_historico["Visitante FT"] > df_historico[
                                                           "Mandante FT"]))])
                            p1_win_rate = (p1_wins / len(df_historico)) * 100

                            p2_wins = len(df_historico[((df_historico["Mandante"] == p2) & (
                                    df_historico["Mandante FT"] > df_historico["Visitante FT"])) |
                                                       ((df_historico["Visitante"] == p2) & (
                                                               df_historico["Visitante FT"] > df_historico[
                                                           "Mandante FT"]))])
                            p2_win_rate = (p2_wins / len(df_historico)) * 100

                            over_25_hits = len(df_historico[df_historico["Total FT"] > 2.5])
                            over_25_rate = (over_25_hits / len(df_historico)) * 100

                            if p1_win_rate >= MIN_PORCENTAGEM:
                                relatorios.append({
                                    "Hora": hora_jogo,
                                    "Liga": liga,
                                    "Jogo": f"{p1} x {p2}",
                                    "Tipo Aposta": f"Vitória {p1}",
                                    "Estatística": f"VENCEU {p1_wins} DE {len(df_historico)} JOGOS ({p1_win_rate:.0f}%)",
                                    "Confiança": "🟢 Alta" if p1_win_rate >= 80 else "🟡 Média",
                                    "Jogos Analisados": len(df_historico)
                                })

                            if p2_win_rate >= MIN_PORCENTAGEM:
                                relatorios.append({
                                    "Hora": hora_jogo,
                                    "Liga": liga,
                                    "Jogo": f"{p1} x {p2}",
                                    "Tipo Aposta": f"Vitória {p2}",
                                    "Estatística": f"VENCEU {p2_wins} DE {len(df_historico)} JOGOS ({p2_win_rate:.0f}%)",
                                    "Confiança": "🟢 Alta" if p2_win_rate >= 80 else "🟡 Média",
                                    "Jogos Analisados": len(df_historico)
                                })

                            if over_25_rate >= MIN_PORCENTAGEM:
                                relatorios.append({
                                    "Hora": hora_jogo,
                                    "Liga": liga,
                                    "Jogo": f"{p1} x {p2}",
                                    "Tipo Aposta": "Over 2.5 FT",
                                    "Estatística": f"OCORREU EM {over_25_hits} DE {len(df_historico)} JOGOS ({over_25_rate:.0f}%)",
                                    "Confiança": "🟢 Alta" if over_25_rate >= 80 else "🟡 Média",
                                    "Jogos Analisados": len(df_historico)
                                })

                    if relatorios:
                        df_relatorios = pd.DataFrame(relatorios)
                        df_relatorios = df_relatorios.sort_values("Hora", ascending=True)

                        st.subheader("💎 Oportunidades Identificadas")
                        st.dataframe(
                            df_relatorios,
                            use_container_width=True,
                            height=400
                        )

                        csv = df_relatorios.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Exportar Alertas",
                            data=csv,
                            file_name='alertas_ia.csv',
                            mime='text/csv'
                        )
                    else:
                        st.info("Nenhuma oportunidade encontrada com os critérios atuais.")

            st.info("💡 **Dica:** Clique no botão acima para gerar analises com Alta Chances de Acertividades")

    # Aba 5: Resultados
    with tabs[4]:
        st.header("📊 Resultados Históricos")

        if df_resultados.empty:
            st.warning("Nenhum dado de resultados disponível no momento.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                ligas_disponiveis = df_resultados['Liga'].unique()
                liga_selecionada = st.selectbox(
                    'Filtrar por Liga:',
                    options=['Todas'] + list(ligas_disponiveis),
                    index=0
                )
            with col2:
                num_jogos = st.slider(
                    'Jogos a exibir:',
                    min_value=10,
                    max_value=200,
                    value=50,
                    step=10
                )

            df_filtrado = df_resultados.copy()
            if liga_selecionada != 'Todas':
                df_filtrado = df_filtrado[df_filtrado['Liga'] == liga_selecionada]
            df_filtrado = df_filtrado.sort_values('Data', ascending=False).head(num_jogos)

            if not df_filtrado.empty:
                st.subheader("📈 Performance Geral")

                total_jogos = len(df_filtrado)
                avg_gols_ht = df_filtrado['Total HT'].mean()
                avg_gols_ft = df_filtrado['Total FT'].mean()
                over_25_ft = (df_filtrado['Total FT'] > 2.5).mean() * 100
                btts_ft = ((df_filtrado['Mandante FT'] > 0) & (df_filtrado['Visitante FT'] > 0)).mean() * 100
                over_15_ht = (df_filtrado['Total HT'] > 1.5).mean() * 100

                cols = st.columns(5)
                cols[0].metric("Jogos", total_jogos)
                cols[1].metric("Média Gols HT", f"{avg_gols_ht:.2f}")
                cols[2].metric("Média Gols FT", f"{avg_gols_ft:.2f}")
                cols[3].metric("Over 2.5 FT", f"{over_25_ft:.1f}%")
                cols[4].metric("Over 1.5 HT", f"{over_15_ht:.1f}%")

            st.subheader("📋 Últimos Resultados")

            colunas_completas = [
                'Data', 'Liga', 'Mandante', 'Visitante',
                'Mandante HT', 'Visitante HT', 'Total HT',
                'Mandante FT', 'Visitante FT', 'Total FT'
            ]

            colunas_existentes = [col for col in colunas_completas if col in df_filtrado.columns]

            st.dataframe(
                df_filtrado[colunas_existentes],
                use_container_width=True,
                height=400
            )

            csv = df_filtrado[colunas_existentes].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Resultados",
                data=csv,
                file_name='resultados_fifa.csv',
                mime='text/csv'
            )


# ==============================================
# PONTO DE ENTRADA PRINCIPAL
# ==============================================

def main():
    """Função principal que controla o fluxo do aplicativo"""
    try:
        fifalgorithm_app()
    except Exception as e:
        st.error(f"Erro crítico no aplicativo: {str(e)}")
        st.info("Tente recarregar a página ou verificar sua conexão com a internet.")


if __name__ == "__main__":
    main()