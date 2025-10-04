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

# Variável global para controle de atualização
UPDATE_INTERVAL = 300  # 5 minutos em segundos
last_update_time = time.time()

# ==============================================
# CSS PERSONALIZADO - TEMA DARK MODERNO
# ==============================================

st.markdown("""
<style>
    /* TEMA DEEP SPACE PARA TABELA AO VIVO */

    /* Container da tabela ao vivo com efeito de estrelas */
    div[data-testid="stDataFrame"] {
        position: relative;
        background: #000000;
        border-radius: 15px;
        overflow: hidden;
    }

    /* Efeito de estrelas animadas no fundo */
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

    /* Tabela com fundo escuro espacial */
    div[data-testid="stDataFrame"] table {
        background: rgba(0, 0, 0, 0.9) !important;
        position: relative;
        z-index: 1;
    }

    /* Headers com gradiente espacial */
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

    /* Células da tabela */
    div[data-testid="stDataFrame"] td {
        background: rgba(10, 10, 30, 0.8) !important;
        color: #e0e0e0 !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        text-align: center !important;
        padding: 12px 15px !important;
        position: relative;
    }

    /* Linhas alternadas com efeito espacial */
    div[data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background: rgba(15, 15, 40, 0.8) !important;
    }

    div[data-testid="stDataFrame"] tbody tr:nth-child(odd) td {
        background: rgba(10, 10, 30, 0.8) !important;
    }

    /* Hover com brilho espacial */
    div[data-testid="stDataFrame"] tbody tr:hover td {
        background: rgba(30, 30, 60, 0.9) !important;
        box-shadow: 
            inset 0 0 20px rgba(100, 150, 255, 0.2),
            0 0 15px rgba(100, 150, 255, 0.3) !important;
        transform: scale(1.01);
        transition: all 0.3s ease;
    }

    /* Efeito de brilho nas bordas da tabela */
    div[data-testid="stDataFrame"] {
        box-shadow: 
            0 0 30px rgba(100, 150, 255, 0.2),
            inset 0 0 50px rgba(0, 0, 0, 0.5);
        border: 1px solid rgba(100, 150, 255, 0.3);
    }

    /* Estilo para AgGrid (se estiver usando) */
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

    /* Efeito de nebulosa no background do container principal */
    .main > div:first-child {
        background: 
            radial-gradient(ellipse at 30% 40%, rgba(56, 89, 248, 0.08) 0%, transparent 50%),
            radial-gradient(ellipse at 70% 60%, rgba(168, 85, 247, 0.08) 0%, transparent 50%),
            #000000;
    }

    /* Live indicator */
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
    """Busca e processa os resultados históricos das partidas"""
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

            soma_ht_mandante = avg_m_gf_ht + avg_m_ga_ht
            soma_ht_visitante = avg_v_gf_ht + avg_v_ga_ht
            soma_ft_mandante = avg_m_gf_ft + avg_v_ga_ft
            soma_ft_visitante = avg_v_gf_ft + avg_m_ga_ft

            gols_ht_media_confronto = (soma_ht_mandante + soma_ht_visitante) / 2
            gols_ft_media_confronto = (soma_ft_mandante + soma_ft_visitante) / 2

            gp_calc = (avg_m_gf_ft + avg_v_ga_ft) / 2 if (jm and jv) else 0
            gc_calc = (avg_v_gf_ft + avg_m_ga_ft) / 2 if (jm and jv) else 0

            sugestao_ht = sugerir_over_ht(gols_ht_media_confronto)
            sugestao_ft = sugerir_over_ft(gols_ft_media_confronto)

            # Novas colunas Over Mandante e Over Visitante
            over_mandante = ""
            over_visitante = ""

            # Lógica para Over Mandante
            if 2.30 <= gp_calc <= 3.39:
                over_mandante = f"1.5 {m}"
            elif 3.40 <= gp_calc <= 4.50:
                over_mandante = f"2.5 {m}"

            # Lógica para Over Visitante
            if 2.30 <= gc_calc <= 3.39:
                over_visitante = f"1.5 {v}"
            elif 3.40 <= gc_calc <= 4.50:
                over_visitante = f"2.5 {v}"

            # Adiciona ícones de cor
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
                    "Gols HT": gols_ht_media_confronto,
                    "Gols FT": gols_ft_media_confronto,
                    "Sugestão HT": sugestao_ht,
                    "Sugestão FT": sugestao_ft,
                    "Over Mandante": over_mandante,
                    "Over Visitante": over_visitante,
                    "0.5 HT": format_stats(sm["over_05_ht_hits"], jm, sv["over_05_ht_hits"], jv),
                    "1.5 HT": format_stats(sm["over_15_ht_hits"], jm, sv["over_15_ht_hits"], jv),
                    "2.5 HT": format_stats(sm["over_25_ht_hits"], jm, sv["over_25_ht_hits"], jv),
                    "BTTS HT": format_stats(sm["btts_ht_hits"], jm, sv["btts_ht_hits"], jv),
                    "BTTS FT": format_stats(sm["btts_ft_hits"], jm, sv["btts_ft_hits"], jv),
                    "0.5 FT": format_stats(sm["over_05_ft_hits"], jm, sv["over_05_ft_hits"], jv),
                    "1.5 FT": format_stats(sm["over_15_ft_hits"], jm, sv["over_15_ft_hits"], jv),
                    "2.5 FT": format_stats(sm["over_25_ft_hits"], jm, sv["over_25_ft_hits"], jv),
                    "3.5 FT": format_stats(sm["over_35_ft_hits"], jm, sv["over_35_ft_hits"], jv),
                    "4.5 FT": format_stats(sm["over_45_ft_hits"], jm, sv["over_45_ft_hits"], jv),
                    "5.5 FT": format_stats(sm["over_55_ft_hits"], jm, sv["over_55_ft_hits"], jv),
                    "6.5 FT": format_stats(sm["over_65_ft_hits"], jm, sv["over_65_ft_hits"], jv),
                }
            )

        df_stats = pd.DataFrame(stats_rows)
        df_base = df[["Hora", "Liga", "Mandante", "Visitante"]].copy()

        df_clean = pd.concat([df_base, df_stats], axis=1)
        df_display = df_clean.copy()
        df_display["Gols HT"] = df_display["Gols HT"].apply(format_gols_ht_com_icone_para_display)
        df_display["Gols FT"] = df_display["Gols FT"].apply(lambda x: f"{x:.2f}")
        df_display["GP"] = df_display["GP"].apply(lambda x: f"{x:.2f}")
        df_display["GC"] = df_display["GC"].apply(lambda x: f"{x:.2f}")

        colunas_ao_vivo_solicitadas = [
            "Hora", "Liga", "Mandante", "Visitante", "GP", "GC",
            "Over Mandante", "Over Visitante",  # Novas colunas
            "Sugestão HT", "Sugestão FT"
        ]

        return df_clean, df_display[colunas_ao_vivo_solicitadas]

    except Exception as e:
        logger.error(f"Erro ao carregar dados ao vivo: {e}")
        st.error(f"❌ Erro ao carregar e processar dados ao vivo.")
        return pd.DataFrame(), pd.DataFrame()


# ==============================================
# FUNÇÕES AUXILIARES (MANTIDAS ORIGINAIS)
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


@st.cache_data(show_spinner=False, ttl=300)
def calcular_estatisticas_todos_jogadores(df_resultados: pd.DataFrame) -> pd.DataFrame:
    """Calcula estatísticas consolidadas para todos os jogadores"""
    if df_resultados.empty:
        return pd.DataFrame()

    jogador_stats = defaultdict(lambda: {
        "jogos_total": 0,
        "vitorias": 0,
        "derrotas": 0,
        "empates": 0,
        "gols_marcados": 0,
        "gols_sofridos": 0,
        "gols_marcados_ht": 0,
        "gols_sofridos_ht": 0,
        "clean_sheets": 0,
        "over_05_ht_hits": 0,
        "over_15_ht_hits": 0,
        "over_25_ht_hits": 0,
        "btts_ht_hits": 0,
        "over_05_ft_hits": 0,
        "over_15_ft_hits": 0,
        "over_25_ft_hits": 0,
        "over_35_ft_hits": 0,
        "over_45_ft_hits": 0,
        "over_55_ft_hits": 0,
        "over_65_ft_hits": 0,
        "btts_ft_hits": 0,
        "under_25_ft_hits": 0,
        "ligas_atuantes": set()
    })

    for _, row in df_resultados.iterrows():
        mandante = row["Mandante"]
        visitante = row["Visitante"]
        liga = row["Liga"]

        jogador_stats[mandante]["ligas_atuantes"].add(liga)
        jogador_stats[visitante]["ligas_atuantes"].add(liga)

        # Processa o mandante
        jogador_stats[mandante]["jogos_total"] += 1
        jogador_stats[mandante]["gols_marcados"] += row["Mandante FT"]
        jogador_stats[mandante]["gols_sofridos"] += row["Visitante FT"]
        jogador_stats[mandante]["gols_marcados_ht"] += row["Mandante HT"]
        jogador_stats[mandante]["gols_sofridos_ht"] += row["Visitante HT"]

        if row["Mandante FT"] > row["Visitante FT"]:
            jogador_stats[mandante]["vitorias"] += 1
        elif row["Mandante FT"] < row["Visitante FT"]:
            jogador_stats[mandante]["derrotas"] += 1
        else:
            jogador_stats[mandante]["empates"] += 1

        if row["Visitante FT"] == 0:
            jogador_stats[mandante]["clean_sheets"] += 1

        # Processa o visitante
        jogador_stats[visitante]["jogos_total"] += 1
        jogador_stats[visitante]["gols_marcados"] += row["Visitante FT"]
        jogador_stats[visitante]["gols_sofridos"] += row["Mandante FT"]
        jogador_stats[visitante]["gols_marcados_ht"] += row["Visitante HT"]
        jogador_stats[visitante]["gols_sofridos_ht"] += row["Mandante HT"]

        if row["Visitante FT"] > row["Mandante FT"]:
            jogador_stats[visitante]["vitorias"] += 1
        elif row["Visitante FT"] < row["Mandante FT"]:
            jogador_stats[visitante]["derrotas"] += 1
        else:
            jogador_stats[visitante]["empates"] += 1

        if row["Mandante FT"] == 0:
            jogador_stats[visitante]["clean_sheets"] += 1

        # Contagem de Overs e BTTS
        total_ht = row["Total HT"]
        total_ft = row["Total FT"]

        # Overs HT
        if total_ht > 0:
            jogador_stats[mandante]["over_05_ht_hits"] += 1
            jogador_stats[visitante]["over_05_ht_hits"] += 1
        if total_ht > 1:
            jogador_stats[mandante]["over_15_ht_hits"] += 1
            jogador_stats[visitante]["over_15_ht_hits"] += 1
        if total_ht > 2:
            jogador_stats[mandante]["over_25_ht_hits"] += 1
            jogador_stats[visitante]["over_25_ht_hits"] += 1

        # BTTS HT
        if row["Mandante HT"] > 0 and row["Visitante HT"] > 0:
            jogador_stats[mandante]["btts_ht_hits"] += 1
            jogador_stats[visitante]["btts_ht_hits"] += 1

        # Overs FT
        if total_ft > 0:
            jogador_stats[mandante]["over_05_ft_hits"] += 1
            jogador_stats[visitante]["over_05_ft_hits"] += 1
        if total_ft > 1:
            jogador_stats[mandante]["over_15_ft_hits"] += 1
            jogador_stats[visitante]["over_15_ft_hits"] += 1
        if total_ft > 2:
            jogador_stats[mandante]["over_25_ft_hits"] += 1
            jogador_stats[visitante]["over_25_ft_hits"] += 1
        else:
            jogador_stats[mandante]["under_25_ft_hits"] += 1
            jogador_stats[visitante]["under_25_ft_hits"] += 1
        if total_ft > 3:
            jogador_stats[mandante]["over_35_ft_hits"] += 1
            jogador_stats[visitante]["over_35_ft_hits"] += 1
        if total_ft > 4:
            jogador_stats[mandante]["over_45_ft_hits"] += 1
            jogador_stats[visitante]["over_45_ft_hits"] += 1
        if total_ft > 5:
            jogador_stats[mandante]["over_55_ft_hits"] += 1
            jogador_stats[visitante]["over_55_ft_hits"] += 1
        if total_ft > 6:
            jogador_stats[mandante]["over_65_ft_hits"] += 1
            jogador_stats[visitante]["over_65_ft_hits"] += 1

        # BTTS FT
        if row["Mandante FT"] > 0 and row["Visitante FT"] > 0:
            jogador_stats[mandante]["btts_ft_hits"] += 1
            jogador_stats[visitante]["btts_ft_hits"] += 1

    # Converter para DataFrame e calcular percentuais/médias
    df_rankings_base = pd.DataFrame.from_dict(jogador_stats, orient="index")
    df_rankings_base.index.name = "Jogador"
    df_rankings_base = df_rankings_base.reset_index()

    # Calcula as métricas percentuais/médias
    df_rankings_base["Win Rate (%)"] = (df_rankings_base["vitorias"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Derrota Rate (%)"] = (
            df_rankings_base["derrotas"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Gols Marcados Média"] = (
            df_rankings_base["gols_marcados"] / df_rankings_base["jogos_total"]).fillna(0)
    df_rankings_base["Gols Sofridos Média"] = (
            df_rankings_base["gols_sofridos"] / df_rankings_base["jogos_total"]).fillna(0)
    df_rankings_base["Saldo de Gols"] = df_rankings_base["gols_marcados"] - df_rankings_base["gols_sofridos"]
    df_rankings_base["Clean Sheets (%)"] = (
            df_rankings_base["clean_sheets"] / df_rankings_base["jogos_total"] * 100).fillna(0)

    # Percentuais de Overs e BTTS
    df_rankings_base["Over 0.5 HT (%)"] = (
            df_rankings_base["over_05_ht_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 1.5 HT (%)"] = (
            df_rankings_base["over_15_ht_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 2.5 HT (%)"] = (
            df_rankings_base["over_25_ht_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["BTTS HT (%)"] = (df_rankings_base["btts_ht_hits"] / df_rankings_base["jogos_total"] * 100).fillna(
        0)
    df_rankings_base["Over 0.5 FT (%)"] = (
            df_rankings_base["over_05_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 1.5 FT (%)"] = (
            df_rankings_base["over_15_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 2.5 FT (%)"] = (
            df_rankings_base["over_25_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 3.5 FT (%)"] = (
            df_rankings_base["over_35_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 4.5 FT (%)"] = (
            df_rankings_base["over_45_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 5.5 FT (%)"] = (
            df_rankings_base["over_55_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["Over 6.5 FT (%)"] = (
            df_rankings_base["over_65_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)
    df_rankings_base["BTTS FT (%)"] = (df_rankings_base["btts_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(
        0)
    df_rankings_base["Under 2.5 FT (%)"] = (
            df_rankings_base["under_25_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)

    # Converte o set de ligas para string para exibição
    df_rankings_base["Ligas Atuantes"] = df_rankings_base["ligas_atuantes"].apply(lambda x: ", ".join(sorted(list(x))))

    return df_rankings_base


def get_recent_player_stats(df_resultados: pd.DataFrame, player_name: str, num_games: int) -> dict:
    """Calcula estatísticas para um jogador nas suas últimas N partidas"""
    player_games = df_resultados[
        (df_resultados["Mandante"] == player_name) | (df_resultados["Visitante"] == player_name)
        ].sort_values("Data", ascending=False).head(num_games).copy()

    if player_games.empty:
        return {}

    stats = {
        "jogos_recentes": len(player_games),
        "gols_marcados_ft": 0,
        "gols_sofridos_ft": 0,
        "gols_marcados_ht": 0,
        "gols_sofridos_ht": 0,
        "over_05_ht_hits": 0,
        "over_15_ht_hits": 0,
        "over_25_ht_hits": 0,
        "btts_ht_hits": 0,
        "over_05_ft_hits": 0,
        "over_15_ft_hits": 0,
        "over_25_ft_hits": 0,
        "over_35_ft_hits": 0,
        "over_45_ft_hits": 0,
        "over_55_ft_hits": 0,
        "over_65_ft_hits": 0,
        "btts_ft_hits": 0,
        "under_25_ft_hits": 0,
        "sequencia_vitorias": 0,
        "sequencia_derrotas": 0,
        "sequencia_empates": 0,
        "sequencia_btts": 0,
        "sequencia_over_25_ft": 0
    }

    last_result = None
    last_btts = None
    last_over_25_ft = None

    for idx, row in player_games.iterrows():
        is_home = row["Mandante"] == player_name
        gf_ft = row["Mandante FT"] if is_home else row["Visitante FT"]
        ga_ft = row["Visitante FT"] if is_home else row["Mandante FT"]
        gf_ht = row["Mandante HT"] if is_home else row["Visitante HT"]
        ga_ht = row["Visitante HT"] if is_home else row["Mandante HT"]

        stats["gols_marcados_ft"] += gf_ft
        stats["gols_sofridos_ft"] += ga_ft
        stats["gols_marcados_ht"] += gf_ht
        stats["gols_sofridos_ht"] += ga_ht

        total_ht = row["Total HT"]
        if total_ht > 0: stats["over_05_ht_hits"] += 1
        if total_ht > 1: stats["over_15_ht_hits"] += 1
        if total_ht > 2: stats["over_25_ht_hits"] += 1
        if gf_ht > 0 and ga_ht > 0: stats["btts_ht_hits"] += 1

        total_ft = row["Total FT"]
        if total_ft > 0: stats["over_05_ft_hits"] += 1
        if total_ft > 1: stats["over_15_ft_hits"] += 1
        if total_ft > 2:
            stats["over_25_ft_hits"] += 1
        else:
            stats["under_25_ft_hits"] += 1
        if total_ft > 3: stats["over_35_ft_hits"] += 1
        if total_ft > 4: stats["over_45_ft_hits"] += 1
        if total_ft > 5: stats["over_55_ft_hits"] += 1
        if total_ft > 6: stats["over_65_ft_hits"] += 1

        btts_ft_current = (gf_ft > 0 and ga_ft > 0)
        if btts_ft_current: stats["btts_ft_hits"] += 1

        over_25_ft_current = (total_ft > 2)

        # Cálculo de sequências
        current_result = "win" if gf_ft > ga_ft else ("loss" if gf_ft < ga_ft else "draw")
        if last_result is None or current_result == last_result:
            if current_result == "win":
                stats["sequencia_vitorias"] += 1
            elif current_result == "loss":
                stats["sequencia_derrotas"] += 1
            else:
                stats["sequencia_empates"] += 1
        else:
            stats["sequencia_vitorias"] = 1 if current_result == "win" else 0
            stats["sequencia_derrotas"] = 1 if current_result == "loss" else 0
            stats["sequencia_empates"] = 1 if current_result == "draw" else 0
        last_result = current_result

        if last_btts is None or btts_ft_current == last_btts:
            if btts_ft_current: stats["sequencia_btts"] += 1
        else:
            stats["sequencia_btts"] = 1 if btts_ft_current else 0
        last_btts = btts_ft_current

        if last_over_25_ft is None or over_25_ft_current == last_over_25_ft:
            if over_25_ft_current: stats["sequencia_over_25_ft"] += 1
        else:
            stats["sequencia_over_25_ft"] = 1 if over_25_ft_current else 0
        last_over_25_ft = over_25_ft_current

    # Calcular médias e percentuais
    total_jogos = stats["jogos_recentes"]
    if total_jogos > 0:
        stats["media_gols_marcados_ft"] = stats["gols_marcados_ft"] / total_jogos
        stats["media_gols_sofridos_ft"] = stats["gols_sofridos_ft"] / total_jogos
        stats["media_gols_marcados_ht"] = stats["gols_marcados_ht"] / total_jogos
        stats["media_gols_sofridos_ht"] = stats["gols_sofridos_ht"] / total_jogos

        stats["pct_over_05_ht"] = (stats["over_05_ht_hits"] / total_jogos) * 100
        stats["pct_over_15_ht"] = (stats["over_15_ht_hits"] / total_jogos) * 100
        stats["pct_over_25_ht"] = (stats["over_25_ht_hits"] / total_jogos) * 100
        stats["pct_btts_ht"] = (stats["btts_ht_hits"] / total_jogos) * 100

        stats["pct_over_05_ft"] = (stats["over_05_ft_hits"] / total_jogos) * 100
        stats["pct_over_15_ft"] = (stats["over_15_ft_hits"] / total_jogos) * 100
        stats["pct_over_25_ft"] = (stats["over_25_ft_hits"] / total_jogos) * 100
        stats["pct_over_35_ft"] = (stats["over_35_ft_hits"] / total_jogos) * 100
        stats["pct_over_45_ft"] = (stats["over_45_ft_hits"] / total_jogos) * 100
        stats["pct_over_55_ft"] = (stats["over_55_ft_hits"] / total_jogos) * 100
        stats["pct_over_65_ft"] = (stats["over_65_ft_hits"] / total_jogos) * 100
        stats["pct_btts_ft"] = (stats["btts_ft_hits"] / total_jogos) * 100
        stats["pct_under_25_ft"] = (stats["under_25_ft_hits"] / total_jogos) * 100
    else:
        for key in list(stats.keys()):
            if key not in ["jogos_recentes", "sequencia_vitorias", "sequencia_derrotas", "sequencia_empates",
                           "sequencia_btts", "sequencia_over_25_ft"]:
                stats[key] = 0.0

    return stats


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
# FUNÇÕES DE ATUALIZAÇÃO AUTOMÁTICA
# ==============================================

def start_auto_update():
    """Inicia a thread de atualização automática"""

    def update_loop():
        while True:
            time.sleep(UPDATE_INTERVAL)
            if st.session_state.get("authenticated", False):
                st.session_state["force_update"] = True
                st.rerun()

    if not hasattr(st.session_state, 'update_thread'):
        st.session_state.update_thread = threading.Thread(target=update_loop, daemon=True)
        st.session_state.update_thread.start()


def check_for_updates():
    """Verifica se é hora de atualizar os dados"""
    global last_update_time
    current_time = time.time()
    if current_time - last_update_time >= UPDATE_INTERVAL:
        last_update_time = current_time
        return True
    return False


# ==============================================
# INTERFACE PRINCIPAL DO APLICATIVO
# ==============================================

def fifalgorithm_app():
    """Aplicativo principal do FIFAlgorithm"""
    st.set_page_config(
        page_title="FIFAlgorithm",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inicia a thread de atualização automática
    start_auto_update()

    brasil_timezone = pytz.timezone("America/Sao_Paulo")
    current_time_br = datetime.now(brasil_timezone).strftime("%H:%M:%S")

    # Header personalizado com tema dark
    st.markdown("""
    <div class="main-header">
        <h1>🦅 FIFAlgorithm</h1>
        <p>Análises Inteligentes de Partidas de E-soccer FIFA</p>
    </div>
    """, unsafe_allow_html=True)

    # Adiciona indicador de atualização automática
    if st.session_state.get("force_update", False):
        st.success("✅ Dados atualizados automaticamente!")
        st.session_state["force_update"] = False

    st.markdown(f"**⌛️ Última atualização:** {current_time_br}")

    # Carrega os dados essenciais
    try:
        df_resultados = buscar_resultados()
        df_live_clean, df_live_display = carregar_dados_ao_vivo(df_resultados)
        df_stats_all_players = calcular_estatisticas_todos_jogadores(df_resultados)

    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        # Cria DataFrames vazios para evitar erros no resto do app
        df_resultados = pd.DataFrame()
        df_live_clean = pd.DataFrame()
        df_live_display = pd.DataFrame()
        df_stats_all_players = pd.DataFrame()

    # Sistema de abas
    tabs = st.tabs(["⚡️ Ao Vivo", "⭐️ Radar FIFA", "🧠 Alertas IA", "⚽️ Resultados"])

    # Aba 1: Ao Vivo - SEM MÉTRICAS mas com dados normais na tabela
    with tabs[0]:
        st.header("🔥 Buscar Jogos")

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
            # Filtros básicos na sidebar
            with st.sidebar:
                st.subheader("🔍 Filtros Rápidos")

                # Filtro por Liga
                ligas_disponiveis = df_live_display['Liga'].unique()
                ligas_selecionadas = st.multiselect(
                    'Selecione as Ligas:',
                    options=ligas_disponiveis,
                    default=ligas_disponiveis
                )

            # Aplicar filtros
            df_filtrado = df_live_display[
                (df_live_display['Liga'].isin(ligas_selecionadas))
            ]

            # REMOVIDAS TODAS AS MÉTRICAS/ESTATÍSTICAS - vai direto para a tabela

            # Configuração da tabela COM DADOS NORMAIS
            gb = GridOptionsBuilder.from_dataframe(df_filtrado)

            # Configuração para visualização normal (mantendo responsividade)
            gb.configure_default_column(
                flex=1,
                minWidth=80,
                maxWidth=150,
                wrapText=True,
                autoHeight=True,
                editable=False,
                filterable=True,
                sortable=True,
                resizable=True
            )

            # Colunas principais para exibição (TODAS AS COLUNAS ORIGINAIS)
            colunas_principais = [
                "Hora", "Liga", "Mandante", "Visitante", "GP", "GC",
                "Over Mandante", "Over Visitante", "Sugestão HT", "Sugestão FT"
            ]

            # Configurações específicas para cada coluna
            config_colunas = {
                "Hora": {"minWidth": 70, "maxWidth": 90},
                "Liga": {"minWidth": 90, "maxWidth": 120},
                "Mandante": {"minWidth": 100, "maxWidth": 140},
                "Visitante": {"minWidth": 100, "maxWidth": 140},
                "GP": {"minWidth": 60, "maxWidth": 80},
                "GC": {"minWidth": 60, "maxWidth": 80},
                "Over Mandante": {"minWidth": 110, "maxWidth": 150},
                "Over Visitante": {"minWidth": 110, "maxWidth": 150},
                "Sugestão HT": {"minWidth": 100, "maxWidth": 130},
                "Sugestão FT": {"minWidth": 100, "maxWidth": 130},
            }

            for col in colunas_principais:
                if col in df_filtrado.columns:
                    config = config_colunas.get(col, {"minWidth": 80, "maxWidth": 120})
                    gb.configure_column(col, **config)

            # Configurar seleção
            gb.configure_selection(
                selection_mode='multiple',
                use_checkbox=True
            )

            grid_options = gb.build()

            # Renderizar tabela com altura dinâmica
            height = min(600, 35 + 35 * len(df_filtrado))

            grid_response = AgGrid(
                df_filtrado[colunas_principais],
                gridOptions=grid_options,
                height=height,
                width='100%',
                theme='streamlit',
                update_mode=GridUpdateMode.MODEL_CHANGED,
                allow_unsafe_jscode=True,
                fit_columns_on_grid_load=True
            )

            # Ações rápidas para seleção
            if grid_response['selected_rows']:
                selected_count = len(grid_response['selected_rows'])
                if st.button(f"📊 Analisar {selected_count} Jogos Selecionados", use_container_width=True):
                    st.info(f"Análise iniciada para {selected_count} jogos...")

    # Aba 2: Radar FIFA
    with tabs[1]:
        st.header("⭐️ Radar FIFA")
        st.write(" Indicador de Mercados Lucrativos por Liga em tempo Real.")

        # Critérios para o Radar FIFA
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
                    linha_liga[f"{criterio}"] = f"{int(percentual)}%"

                for criterio, contagem in contadores_ft.items():
                    percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
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

    # Aba 3: Alertas IA - SIMPLIFICADA
    with tabs[2]:
        st.header("🧠 Alertas IA")
        st.write("Dicas inteligentes de Apostas para cada Partida")

        if df_live_clean.empty or df_resultados.empty:
            st.warning("Dados insuficientes para gerar alertas. Aguarde a atualização.")
        else:
            # Configurações
            MIN_JOGOS_CONFRONTO = 5
            MIN_PORCENTAGEM = 75

            # Obter hora atual
            brasil_tz = pytz.timezone('America/Sao_Paulo')
            hora_atual = datetime.now(brasil_tz).strftime("%H:%M")

            # Processar jogos futuros
            df_live_futuro = df_live_clean[df_live_clean['Hora'] > hora_atual].sort_values('Hora', ascending=True)

            # Resumo rápido
            st.subheader("📈 Resumo Executivo")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Próximos Jogos", len(df_live_futuro))
            with col2:
                jogos_com_historico = sum(1 for _, jogo in df_live_futuro.iterrows()
                                          if len(df_resultados[((df_resultados["Mandante"] == jogo["Mandante"]) &
                                                                (df_resultados["Visitante"] == jogo["Visitante"])) |
                                                               ((df_resultados["Mandante"] == jogo["Visitante"]) &
                                                                (df_resultados["Visitante"] == jogo[
                                                                    "Mandante"]))]) >= MIN_JOGOS_CONFRONTO)
                st.metric("Com Histórico", jogos_com_historico)
            with col3:
                st.metric("Critério Mínimo", f"{MIN_PORCENTAGEM}%")

            # Botão para análise detalhada
            if st.button("🎯 Gerar Análise Detalhada", type="primary", use_container_width=True):
                with st.spinner("Analisando confrontos diretos..."):
                    # Lógica de análise simplificada
                    relatorios = []

                    for _, jogo in df_live_futuro.iterrows():
                        p1 = jogo["Mandante"]
                        p2 = jogo["Visitante"]
                        liga = jogo["Liga"]
                        hora_jogo = jogo["Hora"]

                        # Filtrar jogos históricos entre esses jogadores
                        df_historico = df_resultados[
                            ((df_resultados["Mandante"] == p1) & (df_resultados["Visitante"] == p2)) |
                            ((df_resultados["Mandante"] == p2) & (df_resultados["Visitante"] == p1))
                            ]

                        if len(df_historico) >= MIN_JOGOS_CONFRONTO:
                            # Análise básica de vitórias
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

                            # Análise de Over 2.5 FT
                            over_25_hits = len(df_historico[df_historico["Total FT"] > 2.5])
                            over_25_rate = (over_25_hits / len(df_historico)) * 100

                            # Adicionar oportunidades se atenderem aos critérios
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

                        # Botão para exportar
                        csv = df_relatorios.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Exportar Alertas",
                            data=csv,
                            file_name='alertas_ia.csv',
                            mime='text/csv'
                        )
                    else:
                        st.info("Nenhuma oportunidade encontrada com os critérios atuais.")

            # Dica rápida
            st.info(
                "💡 **Dica:** Clique no botão acima para gerar analises com Alta Chances de Acertividades")

    # Aba 4: Resultados - CORRIGIDA: Mostra dados HT também
    with tabs[3]:
        st.header("📊 Resultados Históricos")

        if df_resultados.empty:
            st.warning("Nenhum dado de resultados disponível no momento.")
        else:
            # Filtro rápido
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

            # Aplicar filtros
            df_filtrado = df_resultados.copy()
            if liga_selecionada != 'Todas':
                df_filtrado = df_filtrado[df_filtrado['Liga'] == liga_selecionada]
            df_filtrado = df_filtrado.sort_values('Data', ascending=False).head(num_jogos)

            # Estatísticas resumidas - INCLUINDO DADOS HT
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

            # Tabela com dados HT e FT
            st.subheader("📋 Últimos Resultados")

            # Colunas incluindo dados HT
            colunas_completas = [
                'Data', 'Liga', 'Mandante', 'Visitante',
                'Mandante HT', 'Visitante HT', 'Total HT',
                'Mandante FT', 'Visitante FT', 'Total FT'
            ]

            # Verificar quais colunas existem no DataFrame
            colunas_existentes = [col for col in colunas_completas if col in df_filtrado.columns]

            st.dataframe(
                df_filtrado[colunas_existentes],
                use_container_width=True,
                height=400
            )

            # Botão para download
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