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
# CONFIGURAÇÕES PARA EVITAR ERROS DE CACHE
# ==============================================
# ==============================================
# CONFIGURAÇÕES PARA EVITAR ERROS DE CACHE
# ==============================================
# Removidas as opções depreciadas - não existem mais nas versões recentes

# Limpeza de cache forçada ao iniciar
try:
    # Método mais recente para limpar cache
    if hasattr(st, 'cache_data'):
        st.cache_data.clear()
    if hasattr(st, 'cache_resource'):
        st.cache_resource.clear()

    # Método antigo (para versões anteriores)
    if hasattr(st, 'caching'):
        st.caching.clear_cache()
except Exception as e:
    print(f"Erro ao limpar cache: {e}")

# Limpar arquivos temporários do Streamlit
try:
    import tempfile
    import shutil

    temp_dir = tempfile.gettempdir()
    for item in os.listdir(temp_dir):
        if item.startswith('streamlit-') or item.startswith('st-'):
            item_path = os.path.join(temp_dir, item)
            try:
                if os.path.isfile(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except:
                pass
except Exception as e:
    print(f"Erro ao limpar arquivos temporários: {e}")


# Função para limpeza periódica (opcional)
@st.cache_resource
def clear_cache_periodically():
    import time
    if 'last_cache_clear' not in st.session_state:
        st.session_state.last_cache_clear = time.time()

    current_time = time.time()
    if current_time - st.session_state.last_cache_clear > 3600:  # Limpa a cada 1 hora
        try:
            if hasattr(st, 'cache_data'):
                st.cache_data.clear()
            if hasattr(st, 'cache_resource'):
                st.cache_resource.clear()
            st.session_state.last_cache_clear = current_time
        except:
            pass


# Executar a limpeza de cache periódica
clear_cache_periodically()


# Limpar cache periodicamente para evitar erros
@st.cache_resource
def clear_cache_periodically():
    import time
    if 'last_cache_clear' not in st.session_state:
        st.session_state.last_cache_clear = time.time()

    current_time = time.time()
    if current_time - st.session_state.last_cache_clear > 3600:  # Limpa a cada 1 hora
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state.last_cache_clear = current_time


# Executar a limpeza de cache
clear_cache_periodically()

# Limpeza de cache forçada
try:
    st.cache_data.clear()
    st.cache_resource.clear()
except:
    pass

# Também tente limpar qualquer arquivo temporário
import tempfile
import shutil

try:
    temp_dir = tempfile.gettempdir()
    for item in os.listdir(temp_dir):
        if item.startswith('streamlit-') or item.startswith('st-'):
            item_path = os.path.join(temp_dir, item)
            try:
                if os.path.isfile(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except:
                pass
except:
    pass


# ==============================================
# FUNÇÕES AUXILIARES PARA FORMATAÇÃO
# ==============================================
def color_percent(val):
    """Aplica formatação condicional a valores percentuais"""
    if '%' in str(val):
        try:
            percent = int(val.replace('%', ''))
            if percent >= 80:
                return 'background-color: #4CAF50; color: white; font-weight: bold;'
            elif percent >= 60:
                return 'background-color: #FFEB3B; color: black; font-weight: bold;'
            elif percent <= 40:
                return 'background-color: #F44336; color: white; font-weight: bold;'
        except:
            return ''
    return ''


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
# FUNÇÕES DO FIFALGORITHM (ANÁLISE DE PARTIDAS)
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
        soup = BeautifulSoup(resp.text, "lxml")
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
# FUNÇÕES AUXILIARES DE ANÁLISE
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
    st.title("💀 FIFAlgorithm")

    # Adiciona indicador de atualização automática
    if st.session_state.get("force_update", False):
        st.success("✅ Dados atualizados automaticamente!")
        st.session_state["force_update"] = False

    st.markdown(f"**🔷 Última atualização:** {current_time_br}")

    # Carrega os dados essenciais
    try:
        # Verifica se a função existe antes de chamar
        if 'carregar_todos_os_dados_essenciais' not in globals():
            # Se não existir, define a função
            def carregar_todos_os_dados_essenciais(reload_flag):
                """Carrega todos os dados necessários para o aplicativo"""
                df_resultados = buscar_resultados()
                df_live_clean, df_live_display = carregar_dados_ao_vivo(df_resultados)
                return df_resultados, df_live_clean, df_live_display

        # Obtém o flag de recarregamento
        reload_flag = st.session_state.get("reload_flag", 0)

        # Carrega os dados
        df_resultados = buscar_resultados()
        df_live_clean, df_live_display = carregar_dados_ao_vivo(df_resultados)

        # Calcula estatísticas
        df_stats_all_players = calcular_estatisticas_todos_jogadores(df_resultados)

    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        # Cria DataFrames vazios para evitar erros no resto do app
        df_resultados = pd.DataFrame()
        df_live_clean = pd.DataFrame()
        df_live_display = pd.DataFrame()
        df_stats_all_players = pd.DataFrame()

    # Sistema de abas
    if "current_tab" not in st.session_state:
        st.session_state["current_tab"] = "⚡️ Ao Vivo"

    tabs = st.tabs(["⚡️ Ao Vivo", "⭐️ Radar FIFA", "⭐️ Dicas Inteligentes", "⭐️ Previsão IA", "⭐️ Análise Manual",
                    "💰 Ganhos & Perdas", "✅ Salvar Jogos", "📊 Resultados", "📈 Relatórios"])

    # Aba 1: Ao Vivo
    with tabs[0]:
        st.header("🎮 𝐋𝐢𝐬𝐭𝐚 𝐝𝐞 𝐉𝐨𝐠𝐨𝐬")

        # Mostra o total de jogos disponíveis
        if not df_live_display.empty:
            st.subheader(f"📊 {len(df_live_display)} Jogos Disponíveis nas Próximas Horas")
        else:
            st.warning("⏳ Nenhuma partida ao vivo no momento")

        # CSS personalizado
        st.markdown("""
        <style>
            @media screen and (max-width: 768px) {
                .ag-root-wrapper { width: 100vw !important; margin-left: -10px !important; }
                .ag-header-cell-label { font-size: 12px !important; padding: 0 5px !important; }
                .ag-cell { font-size: 12px !important; padding: 4px 2px !important; line-height: 1.2 !important; }
                .hide-on-mobile { display: none !important; }
            }
        </style>
        """, unsafe_allow_html=True)

        if not df_live_display.empty:
            # Configuração dos filtros na sidebar
            with st.sidebar:
                st.subheader("🔍 Filtros Avançados")

                # Filtro por Liga
                ligas_disponiveis = df_live_display['Liga'].unique()
                ligas_selecionadas = st.multiselect(
                    'Selecione as Ligas:',
                    options=ligas_disponiveis,
                    default=ligas_disponiveis
                )

                # Filtro por Sugestão HT
                sugestoes_ht = df_live_display['Sugestão HT'].unique()
                ht_selecionados = st.multiselect(
                    'Filtrar por Sugestão HT:',
                    options=sugestoes_ht,
                    default=sugestoes_ht
                )

                # Filtro por Sugestão FT
                sugestoes_ft = df_live_display['Sugestão FT'].unique()
                ft_selecionados = st.multiselect(
                    'Filtrar por Sugestão FT:',
                    options=sugestoes_ft,
                    default=sugestoes_ft
                )

                # Filtro por Over Mandante
                over_mandante_opcoes = df_live_display['Over Mandante'].unique()
                over_mandante_selecionados = st.multiselect(
                    'Filtrar por Over Mandante:',
                    options=over_mandante_opcoes,
                    default=over_mandante_opcoes
                )

                # Filtro por Over Visitante
                over_visitante_opcoes = df_live_display['Over Visitante'].unique()
                over_visitante_selecionados = st.multiselect(
                    'Filtrar por Over Visitante:',
                    options=over_visitante_opcoes,
                    default=over_visitante_opcoes
                )

                # Botão para resetar filtros
                if st.button("🔄 Resetar Filtros"):
                    ligas_selecionadas = ligas_disponiveis
                    ht_selecionados = sugestoes_ht
                    ft_selecionados = sugestoes_ft
                    over_mandante_selecionados = over_mandante_opcoes
                    over_visitante_selecionados = over_visitante_opcoes

            # Aplicar filtros
            df_filtrado = df_live_display[
                (df_live_display['Liga'].isin(ligas_selecionadas)) &
                (df_live_display['Sugestão HT'].isin(ht_selecionados)) &
                (df_live_display['Sugestão FT'].isin(ft_selecionados)) &
                (df_live_display['Over Mandante'].isin(over_mandante_selecionados)) &
                (df_live_display['Over Visitante'].isin(over_visitante_selecionados))
                ]

            # Atualizar contador de jogos filtrados
            st.write(f"🔍 Mostrando {len(df_filtrado)} de {len(df_live_display)} jogos")

            # Configuração da tabela interativa com AgGrid
            gb = GridOptionsBuilder.from_dataframe(df_filtrado)

            # Configuração padrão com seleção múltipla de colunas
            gb.configure_default_column(
                flex=1,
                minWidth=100,
                wrapText=True,
                autoHeight=True,
                editable=False,
                filterable=True,
                sortable=True
            )

            # Configurar coluna de seleção
            gb.configure_selection(
                selection_mode='multiple',
                use_checkbox=True,
                rowMultiSelectWithClick=True
            )

            # Configurar todas as colunas como filtros
            for col in df_filtrado.columns:
                gb.configure_column(col, header_name=col, filter=True)

            grid_options = gb.build()

            # Renderizar tabela
            grid_response = AgGrid(
                df_filtrado,
                gridOptions=grid_options,
                height=min(600, 35 + 35 * len(df_filtrado)),
                width='100%',
                fit_columns_on_grid_load=False,
                theme='streamlit',
                update_mode=GridUpdateMode.MODEL_CHANGED,
                allow_unsafe_jscode=True,
                enable_enterprise_modules=True,
                custom_css={
                    "#gridToolBar": {
                        "padding-bottom": "0px !important",
                    }
                }
            )

            # Botão de salvamento
            if st.button("💾 Salvar Jogos Selecionados", type="primary"):
                selected_rows = grid_response['selected_rows']
                if not selected_rows.empty:  # Verifica se o DataFrame não está vazio
                    selected_df = pd.DataFrame(selected_rows)
                    # Adiciona data de salvamento
                    selected_df['Data Salvamento'] = datetime.now().strftime("%d/%m/%Y %H:%M")

                    # Atualiza jogos salvos
                    if 'saved_games' not in st.session_state:
                        st.session_state.saved_games = selected_df
                    else:
                        # Evita duplicatas
                        existing_games = st.session_state.saved_games
                        mask = selected_df.apply(
                            lambda row: ~((existing_games['Mandante'] == row['Mandante']) &
                                          (existing_games['Visitante'] == row['Visitante']) &
                                          (existing_games['Hora'] == row['Hora'])).any(),
                            axis=1
                        )
                        new_games = selected_df[mask]

                        if not new_games.empty:
                            st.session_state.saved_games = pd.concat([existing_games, new_games])
                            st.success(f"✅ {len(new_games)} novos jogos salvos!")
                        else:
                            st.warning("Nenhum jogo novo para salvar (todos já estão na lista)")
                else:
                    st.warning("Nenhum jogo selecionado")

    # ==============================================
    # ABA 2: RADAR FIFA - ATUALIZADO
    # ==============================================

    with tabs[1]:
        st.header("🎯 Radar FIFA - Análise de Ligas")
        st.write("Identifica as melhores oportunidades de apostas por liga com base em estatísticas históricas")

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

            # ==============================================
            # TABELA ESTATÍSTICAS POR LIGA (FILTRADA)
            # ==============================================

            st.subheader("📊 Estatísticas por Liga")

            # Definir cores para os ícones baseados nos percentuais
            def get_icon_color(value):
                if '%' in str(value):
                    try:
                        percent = int(value.replace('%', ''))
                        if percent >= 80:
                            return "🟢"  # Verde - Excelente
                        elif percent >= 70:
                            return "🟡"  # Amarelo - Bom
                        elif percent >= 60:
                            return "🟠"  # Laranja - Razoável
                        else:
                            return "🔴"  # Vermelho - Fraco
                    except:
                        return "⚪"  # Neutro
                return "⚪"

            # Aplicar formatação condicional completa
            def style_radar_table(df):
                # Copiar o DataFrame para não modificar o original
                styled_df = df.copy()

                # Adicionar ícones de cor às colunas percentuais
                for col in styled_df.columns:
                    if col not in ['Liga', 'Média Gols HT', 'Média Gols FT']:
                        styled_df[col] = styled_df[col].apply(
                            lambda x: f"{get_icon_color(x)} {x}" if '%' in str(x) else x
                        )

                # Estilizar as médias de gols
                def style_avg_gols(val):
                    try:
                        num_val = float(val)
                        if num_val >= 2.75:
                            return f"🟢 {val}"
                        elif num_val >= 2.20:
                            return f"🟡 {val}"
                        elif num_val >= 1.70:
                            return f"🟠 {val}"
                        else:
                            return f"🔴 {val}"
                    except:
                        return val

                if 'Média Gols HT' in styled_df.columns:
                    styled_df['Média Gols HT'] = styled_df['Média Gols HT'].apply(style_avg_gols)

                if 'Média Gols FT' in styled_df.columns:
                    styled_df['Média Gols FT'] = styled_df['Média Gols FT'].apply(style_avg_gols)

                return styled_df

            # Filtrar apenas linhas com dados válidos (não zeros)
            def filter_valid_rows(df):
                valid_rows = []
                for _, row in df.iterrows():
                    # Verificar se a linha tem dados válidos (pelo menos um valor não zero)
                    has_valid_data = False
                    for col, value in row.items():
                        if col != 'Liga' and value not in ['0%', '0.00', '0', 0, '0.0']:
                            has_valid_data = True
                            break

                    if has_valid_data:
                        valid_rows.append(row)

                return pd.DataFrame(valid_rows)

            # Filtrar o DataFrame para mostrar apenas linhas com dados
            df_radar_filtrado = filter_valid_rows(df_radar)

            if not df_radar_filtrado.empty:
                # Aplicar o estilo apenas nas linhas com dados
                styled_df = style_radar_table(df_radar_filtrado)

                # Exibir a tabela com a classe CSS personalizada
                st.markdown('<div class="radar-table">', unsafe_allow_html=True)
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Liga": st.column_config.TextColumn(
                            "Liga",
                            width="medium",
                            help="Liga sendo analisada"
                        ),
                        "Média Gols HT": st.column_config.TextColumn(
                            "Média HT",
                            width="small",
                            help="Média de gols no primeiro tempo"
                        ),
                        "Média Gols FT": st.column_config.TextColumn(
                            "Média FT",
                            width="small",
                            help="Média de gols no tempo total"
                        )
                    }
                )
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("📊 Nenhuma liga com dados válidos encontrada para exibição")

            # ==============================================
            # OBSERVAÇÕES POR LIGA - MELHORES OPORTUNIDADES (FORMATO TABELA)
            # ==============================================

            st.subheader("🎯 Linhas Maximas de Segurança HT & FT")

            # Criar dados para a tabela
            tabela_oportunidades = []

            for liga in df_radar_filtrado["Liga"].unique() if not df_radar_filtrado.empty else []:
                dados_liga = df_radar_filtrado[df_radar_filtrado["Liga"] == liga].iloc[0]

                # Encontrar linha máxima segura para HT (CRITÉRIO ORIGINAL)
                linha_max_ht = "Nenhuma"
                for mercado in ["2.5 HT", "1.5 HT", "0.5 HT"]:
                    if mercado in dados_liga:
                        try:
                            percentual = int(dados_liga[mercado].replace('%', ''))
                            if percentual >= 80:
                                linha_max_ht = f"🟢 {mercado} ({percentual}%)"
                                break
                            elif 70 <= percentual <= 79:
                                linha_max_ht = f"🟡 {mercado} ({percentual}%)"
                                break
                            elif 60 <= percentual <= 69:
                                linha_max_ht = f"🟠 {mercado} ({percentual}%)"
                                break
                        except:
                            continue

                # Encontrar linha máxima segura para FT (CRITÉRIO ORIGINAL)
                linha_max_ft = "Nenhuma"
                for mercado in ["5.5 FT", "4.5 FT", "3.5 FT", "2.5 FT", "1.5 FT", "0.5 FT"]:
                    if mercado in dados_liga:
                        try:
                            percentual = int(dados_liga[mercado].replace('%', ''))
                            if percentual >= 80:
                                linha_max_ft = f"🟢 {mercado} ({percentual}%)"
                                break
                            elif 70 <= percentual <= 79:
                                linha_max_ft = f"🟡 {mercado} ({percentual}%)"
                                break
                            elif 60 <= percentual <= 69:
                                linha_max_ft = f"🟠 {mercado} ({percentual}%)"
                                break
                        except:
                            continue

                # Adicionar à tabela apenas se houver oportunidades (REMOVENDO AS COLUNAS DE MÉDIA)
                if linha_max_ht != "Nenhuma" or linha_max_ft != "Nenhuma":
                    tabela_oportunidades.append({
                        "Liga": f"🎮 {liga}",
                        "Linha Maxima HT": linha_max_ht,
                        "Linha Maxima FT": linha_max_ft
                        # Removidas as colunas: "Média Gols HT" e "Média Gols FT"
                    })

            # Criar DataFrame e exibir tabela apenas se houver dados
            if tabela_oportunidades:
                df_oportunidades = pd.DataFrame(tabela_oportunidades)

                # Aplicar formatação condicional
                def color_recommendation(val):
                    if "🟢" in str(val):
                        return 'background-color: #4CAF50; color: white; font-weight: bold;'
                    elif "🟡" in str(val):
                        return 'background-color: #FFEB3B; color: black; font-weight: bold;'
                    elif "🟠" in str(val):
                        return 'background-color: #FF9800; color: white; font-weight: bold;'
                    elif "Nenhuma" in str(val):
                        return 'background-color: #F44336; color: white; font-weight: bold;'
                    return ''

                styled_table = df_oportunidades.style.map(
                    color_recommendation,
                    subset=["Linha Maxima HT", "Linha Maxima FT"]
                )

                st.dataframe(styled_table, use_container_width=True, height=200)

                # Legenda
                st.markdown("""
                    **📊 Legenda:**
                    - 🟢 **Linha Máxima Segura** (≥80% de acerto)
                    - 🟡 **Cautela** (70-79% de acerto)
                    - 🟠 **Cuidado** (60-69% de acerto)
                    - 🔴 **Evitar** (<60% de acerto ou dados insuficientes)
                    """)
            else:
                st.info("📊 Nenhuma oportunidade identificada com os critérios atuais")

            # ==============================================
            # REMOVIDA A SEÇÃO "Análise Detalhada por Liga"
            # ==============================================

        else:
            st.info("Aguardando dados das partidas ao vivo para análise...")
            st.info("⏳ Os dados serão atualizados automaticamente quando as partidas estiverem disponíveis")

    # Aba 3: Dicas Inteligentes
    with tabs[2]:
        st.header("💡 Dicas Inteligentes por Liga")
        st.write("Análise de consistência e oscilações de cada jogador na liga")

        if df_resultados.empty:
            st.warning("Dados insuficientes para gerar dicas.")
        else:
            min_jogos = 5
            total_jogos_analise = 10
            ligas_principais = ["Battle 8 Min", "Volta 6 Min", "H2H 8 Min", "GT 12 Min"]

            for liga in ligas_principais:
                st.markdown(f"### 🏆 Liga: {liga}")

                df_liga = df_resultados[df_resultados["Liga"] == liga]

                if df_liga.empty:
                    st.info(f"Nenhum dado disponível para a liga {liga}")
                    continue

                jogadores = pd.concat([df_liga["Mandante"], df_liga["Visitante"]]).unique()
                dados_jogadores = []

                for jogador in jogadores:
                    jogos_jogador = df_liga[
                        (df_liga["Mandante"] == jogador) |
                        (df_liga["Visitante"] == jogador)
                        ].sort_values("Data", ascending=False).head(total_jogos_analise)

                    if len(jogos_jogador) < min_jogos:
                        continue

                    stats = {
                        "Jogador": jogador,
                        "Jogos": len(jogos_jogador),
                        "Over 1.5 HT": 0,
                        "Over 2.5 HT": 0,
                        "Over 2.5 FT": 0,
                        "Over 3.5 FT": 0,
                        "Over 4.5 FT": 0,
                        "Gols Marcados Média": 0,
                        "Gols Sofridos Média": 0,
                        "BTTS FT": 0
                    }

                    for _, jogo in jogos_jogador.iterrows():
                        is_mandante = jogo["Mandante"] == jogador

                        total_ht = jogo["Total HT"]
                        if total_ht > 1.5: stats["Over 1.5 HT"] += 1
                        if total_ht > 2.5: stats["Over 2.5 HT"] += 1

                        total_ft = jogo["Total FT"]
                        if total_ft > 2.5: stats["Over 2.5 FT"] += 1
                        if total_ft > 3.5: stats["Over 3.5 FT"] += 1
                        if total_ft > 4.5: stats["Over 4.5 FT"] += 1

                        if is_mandante:
                            stats["Gols Marcados Média"] += jogo["Mandante FT"]
                            stats["Gols Sofridos Média"] += jogo["Visitante FT"]
                        else:
                            stats["Gols Marcados Média"] += jogo["Visitante FT"]
                            stats["Gols Sofridos Média"] += jogo["Mandante FT"]

                        if jogo["Mandante FT"] > 0 and jogo["Visitante FT"] > 0:
                            stats["BTTS FT"] += 1

                    stats["Gols Marcados Média"] = round(stats["Gols Marcados Média"] / len(jogos_jogador), 2)
                    stats["Gols Sofridos Média"] = round(stats["Gols Sofridos Média"] / len(jogos_jogador), 2)

                    for key in ["Over 1.5 HT", "Over 2.5 HT", "Over 2.5 FT", "Over 3.5 FT", "Over 4.5 FT", "BTTS FT"]:
                        stats[key] = round((stats[key] / len(jogos_jogador)) * 100)

                    dados_jogadores.append(stats)

                if not dados_jogadores:
                    st.info(f"Nenhum jogador com mínimo de {min_jogos} jogos na liga {liga}")
                    continue

                df_ranking = pd.DataFrame(dados_jogadores)
                df_ranking = df_ranking.sort_values("Over 2.5 FT", ascending=False)

                medalhas = {0: "🥇", 1: "🥈", 2: "🥉"}
                df_ranking = df_ranking.reset_index(drop=True)
                df_ranking["Pos"] = df_ranking.index + 1
                df_ranking["Jogador"] = df_ranking.apply(
                    lambda row: f"{medalhas.get(row.name, '')} {row['Jogador']}" if row.name in medalhas else row[
                        "Jogador"],
                    axis=1
                )

                st.dataframe(
                    df_ranking[
                        ["Pos", "Jogador", "Jogos", "Over 2.5 FT", "Over 3.5 FT", "Over 1.5 HT", "Gols Marcados Média",
                         "Gols Sofridos Média"]],
                    use_container_width=True,
                    height=400
                )

                st.markdown("#### 🔍 Relatórios de Consistência")

                for _, jogador in df_ranking.head(10).iterrows():
                    with st.expander(
                            f"📌 Análise detalhada: {jogador['Jogador'].replace('🥇', '').replace('🥈', '').replace('🥉', '').strip()}"):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.metric("📈 Over 2.5 FT", f"{jogador['Over 2.5 FT']}%")
                            st.metric("⚽ Gols Marcados (Média)", jogador["Gols Marcados Média"])
                            st.metric("🎯 Over 1.5 HT", f"{jogador['Over 1.5 HT']}%")

                        with col2:
                            st.metric("🔥 Over 3.5 FT", f"{jogador['Over 3.5 FT']}%")
                            st.metric("🥅 Gols Sofridos (Média)", jogador["Gols Sofridos Média"])
                            st.metric("⚡ Over 2.5 HT", f"{jogador['Over 2.5 HT']}%")

                        # Gera o relatório textual inteligente
                        over_25_rate = jogador["Over 2.5 FT"]
                        over_35_rate = jogador["Over 3.5 FT"]
                        over_15_ht_rate = jogador["Over 1.5 HT"]
                        gols_marcados = jogador["Gols Marcados Média"]
                        gols_sofridos = jogador["Gols Sofridos Média"]

                        report_parts = []

                        if over_25_rate >= 80:
                            report_parts.append(
                                f"🔹 **Máquina de Over Gols** - {over_25_rate}% dos jogos com Over 2.5 FT")
                            if over_35_rate >= 60:
                                report_parts.append(
                                    f"🔹 **Especialista em Placar Alto** - {over_35_rate}% dos jogos com Over 3.5 FT")
                        elif over_25_rate <= 30:
                            report_parts.append(
                                f"🔹 **Padrão Under** - Apenas {over_25_rate}% dos jogos com Over 2.5 FT")
                        else:
                            report_parts.append(
                                f"🔹 **Desempenho Intermediário** - {over_25_rate}% dos jogos com Over 2.5 FT")

                        if gols_marcados >= 2.5:
                            report_parts.append(
                                f"🔹 **Ataque Potente** - Média de {gols_marcados} gols marcados por jogo")
                        elif gols_marcados <= 1.0:
                            report_parts.append(
                                f"🔹 **Ataque Limitado** - Apenas {gols_marcados} gols marcados em média")

                        if gols_sofridos >= 2.0:
                            report_parts.append(
                                f"🔹 **Defesa Instável** - Média de {gols_sofridos} gols sofridos por jogo")
                        elif gols_sofridos <= 1.0:
                            report_parts.append(f"🔹 **Defesa Sólida** - Apenas {gols_sofridos} gols sofridos em média")

                        if over_15_ht_rate >= 80:
                            report_parts.append(f"🔹 **Começo Forte** - {over_15_ht_rate}% dos jogos com Over 1.5 HT")

                        recomendacoes = []
                        if over_25_rate >= 80 and gols_marcados >= 2.0:
                            if over_35_rate >= 60:
                                recomendacoes.append("Over 3.5 FT é uma aposta altamente recomendada")
                            else:
                                recomendacoes.append("Over 2.5 FT é uma aposta segura")

                        if over_15_ht_rate >= 70:
                            recomendacoes.append("Over 1.5 HT tem bom potencial")

                        if recomendacoes:
                            report_parts.append("\n🌟 **Recomendações de Aposta:**")
                            for rec in recomendacoes:
                                report_parts.append(f"✅ {rec}")

                        if over_25_rate >= 80 and gols_marcados >= 2.5:
                            report_parts.append(
                                "\n🟢 **ALERTA DE CONFIANÇA:** Apostas em over são altamente recomendadas")
                        elif over_25_rate <= 30 and gols_marcados <= 1.0:
                            report_parts.append("\n🔴 **ALERTA DE RISCO:** Evitar apostas em over")

                        st.markdown("\n\n".join(report_parts))

    # Aba 4: Previsão IA
    with tabs[3]:
        st.header("🤖 Previsão IA (Liga)")

        if df_resultados.empty:
            st.warning("Dados insuficientes para análise.")
        else:
            config = {
                "jogos_por_liga": 20,
                "min_sequencia": 3,
                "min_sucesso": 70,
                "ligas": ["Battle 8 Min", "Volta 6 Min", "H2H 8 Min", "GT 12 Min"]
            }

            dfs_ligas = []
            for liga in config["ligas"]:
                df_liga = df_resultados[df_resultados["Liga"] == liga].tail(config["jogos_por_liga"])
                dfs_ligas.append(df_liga)

            df_recente = pd.concat(dfs_ligas) if dfs_ligas else pd.DataFrame()

            if df_recente.empty:
                st.info("Nenhum dado recente encontrado.")
            else:
                sequences_data = []
                all_players = pd.concat([df_recente["Mandante"], df_recente["Visitante"]]).unique()

                for player in all_players:
                    player_matches = df_recente[
                        (df_recente["Mandante"] == player) |
                        (df_recente["Visitante"] == player)
                        ].sort_values("Data", ascending=False)

                    if len(player_matches) < config["min_sequencia"]:
                        continue

                    markets = {
                        "🎯 1.5+ Gols": {
                            "condition": lambda r, p: (r["Mandante FT"] if r["Mandante"] == p else r[
                                "Visitante FT"]) >= 1.5,
                            "weight": 1.2
                        },
                        "🎯 2.5+ Gols": {
                            "condition": lambda r, p: (r["Mandante FT"] if r["Mandante"] == p else r[
                                "Visitante FT"]) >= 2.5,
                            "weight": 1.5
                        },
                        "⚡ Over 1.5 HT": {
                            "condition": lambda r, _: r["Total HT"] > 1.5,
                            "weight": 1.0
                        },
                        "⚡ Over 2.5 HT": {
                            "condition": lambda r, _: r["Total HT"] > 2.5,
                            "weight": 1.3
                        },
                        "🔥 Over 2.5 FT": {
                            "condition": lambda r, _: r["Total FT"] > 2.5,
                            "weight": 1.4
                        },
                        "💥 Over 3.5 FT": {
                            "condition": lambda r, _: r["Total FT"] > 3.5,
                            "weight": 1.6
                        },
                        "🔀 BTTS FT": {
                            "condition": lambda r, _: (r["Mandante FT"] > 0) & (r["Visitante FT"] > 0),
                            "weight": 1.1
                        }
                    }

                    for market_name, config_market in markets.items():
                        seq = current_seq = hits = 0
                        for _, row in player_matches.iterrows():
                            if config_market["condition"](row, player):
                                current_seq += 1
                                seq = max(seq, current_seq)
                                hits += 1
                            else:
                                current_seq = 0

                        success_rate = (hits / len(player_matches)) * 100 if len(player_matches) > 0 else 0

                        if seq >= config["min_sequencia"] and success_rate >= config["min_sucesso"]:
                            score = seq * config_market["weight"] * (success_rate / 100)
                            sequences_data.append({
                                "Jogador": player,
                                "Sequência": seq,
                                "Mercado": market_name,
                                "Taxa": f"{success_rate:.0f}%",
                                "Liga": player_matches.iloc[0]["Liga"],
                                "Score": score,
                                "Jogos Analisados": len(player_matches),
                                "Último Jogo": player_matches.iloc[0]["Data"]
                            })

                if sequences_data:
                    df = pd.DataFrame(sequences_data)
                    df_sorted = df.sort_values(["Score", "Último Jogo"], ascending=[False, False])

                    st.markdown("### 🏆 Melhores Sequências")
                    st.dataframe(
                        df_sorted[["Jogador", "Mercado", "Sequência", "Taxa", "Liga", "Jogos Analisados"]],
                        hide_index=True,
                        use_container_width=True,
                        height=500
                    )

                    st.markdown("### 💎 Dicas Estratégicas")
                    for _, row in df_sorted.head(5).iterrows():
                        st.success(
                            f"**{row['Jogador']}** ({row['Liga']}): "
                            f"{row['Sequência']} jogos consecutivos com {row['Mercado']} "
                            f"({row['Taxa']} acerto) - **Score: {row['Score']:.1f}/10**"
                        )
                else:
                    st.info("Nenhuma sequência relevante encontrada nos últimos 20 jogos de cada liga.")

    # Aba 5: Análise Manual
    with tabs[4]:
        st.header("🔍 Análise Manual de Confrontos e Desempenho Individual")
        st.write(
            "Insira os nomes dos jogadores para analisar seus confrontos diretos recentes e o desempenho individual nas últimas partidas.")

        if df_resultados.empty:
            st.info("Carregando dados dos resultados para a análise manual...")

        all_players = sorted([re.sub(r'^[🥇🥈🥉]\s', '', p) for p in
                              df_stats_all_players["Jogador"].unique()]) if not df_stats_all_players.empty else []

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            player1_manual = st.selectbox(
                "Jogador 1:",
                [""] + all_players,
                key="player1_manual"
            )
        with col_p2:
            player2_manual = st.selectbox(
                "Jogador 2:",
                [""] + all_players,
                key="player2_manual"
            )

        num_games_h2h = st.number_input(
            "Número de últimos confrontos diretos a analisar (máx. 10):",
            min_value=1,
            max_value=10,
            value=10,
            key="num_games_h2h"
        )

        num_games_individual = st.number_input(
            "Número de últimos jogos individuais a analisar (máx. 20):",
            min_value=1,
            max_value=20,
            value=10,
            key="num_games_individual"
        )

        if st.button("Analisar Confronto e Desempenho", key="analyze_button"):
            if player1_manual and player2_manual:
                if player1_manual == player2_manual:
                    st.warning("Por favor, selecione jogadores diferentes.")
                else:
                    perform_manual_analysis(df_resultados, player1_manual, player2_manual, num_games_h2h,
                                            num_games_individual)
            else:
                st.warning("Por favor, selecione ambos os jogadores.")

    # Aba 6: Ganhos & Perdas
    # Aba 6: Ganhos & Perdas
    with tabs[5]:
        st.header("💰 Análise Individual de Jogadores")
        st.write("Analise o desempenho financeiro detalhado de cada jogador")

        if not df_stats_all_players.empty and not df_resultados.empty:
            # ==============================================
            # SELEÇÃO DE JOGADORES E CONFIGURAÇÕES
            # ==============================================
            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                player_names_for_selectbox = sorted([
                    re.sub(r'^[🥇🥈🥉]\s', '', p)
                    for p in df_stats_all_players["Jogador"].unique()
                ])
                selected_players = st.multiselect(
                    "🔍 Selecione os Jogadores (máx. 8):",
                    options=player_names_for_selectbox,
                    default=[],
                    max_selections=8,
                    key="players_multiselect"
                )

            with col2:
                default_odds = st.number_input(
                    "🎯 Odd Média:",
                    min_value=1.50,
                    max_value=3.00,
                    value=1.90,
                    step=0.05,
                    key="odds_input"
                )

            with col3:
                stake_value = st.number_input(
                    "💵 Valor por Aposta (R$):",
                    min_value=0.0,
                    max_value=1000.0,
                    value=100.0,
                    step=10.0,
                    key="stake_input"
                )

            if selected_players:
                # ==============================================
                # FUNÇÕES PARA CÁLCULO PRECISO
                # ==============================================
                def calcular_vitorias(df_resultados, jogador_nome):
                    jogos_jogador = df_resultados[
                        (df_resultados["Mandante"] == jogador_nome) |
                        (df_resultados["Visitante"] == jogador_nome)
                        ]
                    vitorias = 0
                    for _, jogo in jogos_jogador.iterrows():
                        if jogo["Mandante"] == jogador_nome:
                            if jogo["Mandante FT"] > jogo["Visitante FT"]:
                                vitorias += 1
                        else:
                            if jogo["Visitante FT"] > jogo["Mandante FT"]:
                                vitorias += 1
                    return vitorias, len(jogos_jogador)

                def calcular_over_15_gols_jogador(df_resultados, jogador_nome):
                    jogos_jogador = df_resultados[
                        (df_resultados["Mandante"] == jogador_nome) |
                        (df_resultados["Visitante"] == jogador_nome)
                        ]
                    acertos = 0
                    for _, jogo in jogos_jogador.iterrows():
                        if jogo["Mandante"] == jogador_nome:
                            gols_jogador = jogo["Mandante FT"]
                        else:
                            gols_jogador = jogo["Visitante FT"]
                        if gols_jogador >= 2:
                            acertos += 1
                    return acertos, len(jogos_jogador)

                def calcular_over_25_jogador(df_resultados, jogador_nome):
                    jogos_jogador = df_resultados[
                        (df_resultados["Mandante"] == jogador_nome) |
                        (df_resultados["Visitante"] == jogador_nome)
                        ]
                    acertos = 0
                    for _, jogo in jogos_jogador.iterrows():
                        if jogo["Mandante"] == jogador_nome:
                            gols = jogo["Mandante FT"]
                        else:
                            gols = jogo["Visitante FT"]
                        if gols >= 3:
                            acertos += 1
                    return acertos, len(jogos_jogador)

                def calcular_under_ft(df_resultados, jogador_nome, linha):
                    jogos_jogador = df_resultados[
                        (df_resultados["Mandante"] == jogador_nome) |
                        (df_resultados["Visitante"] == jogador_nome)
                        ]
                    acertos = 0
                    for _, jogo in jogos_jogador.iterrows():
                        total_ft = jogo["Total FT"]
                        if total_ft < linha:
                            acertos += 1
                    return acertos, len(jogos_jogador)

                def calcular_mercado_ht(df_resultados, jogador_nome, mercado):
                    jogos_jogador = df_resultados[
                        (df_resultados["Mandante"] == jogador_nome) |
                        (df_resultados["Visitante"] == jogador_nome)
                        ]
                    acertos = 0
                    for _, jogo in jogos_jogador.iterrows():
                        total_ht = jogo["Total HT"]
                        if mercado == "Jogos 0.5 HT" and total_ht > 0.5:
                            acertos += 1
                        elif mercado == "Jogos 1.5 HT" and total_ht > 1.5:
                            acertos += 1
                        elif mercado == "Jogos 2.5 HT" and total_ht > 2.5:
                            acertos += 1
                        elif mercado == "BTTS HT":
                            mandante_ht = jogo.get("Mandante HT", 0)
                            visitante_ht = jogo.get("Visitante HT", 0)
                            if mandante_ht > 0 and visitante_ht > 0:
                                acertos += 1
                    return acertos, len(jogos_jogador)

                def calcular_mercado_ft(df_resultados, jogador_nome, mercado):
                    jogos_jogador = df_resultados[
                        (df_resultados["Mandante"] == jogador_nome) |
                        (df_resultados["Visitante"] == jogador_nome)
                        ]
                    acertos = 0
                    for _, jogo in jogos_jogador.iterrows():
                        total_ft = jogo["Total FT"]
                        if mercado == "Jogos 0.5 FT" and total_ft > 0.5:
                            acertos += 1
                        elif mercado == "Jogos 1.5 FT" and total_ft > 1.5:
                            acertos += 1
                        elif mercado == "Jogos 2.5 FT" and total_ft > 2.5:
                            acertos += 1
                        elif mercado == "Jogos 3.5 FT" and total_ft > 3.5:
                            acertos += 1
                        elif mercado == "Jogos 4.5 FT" and total_ft > 4.5:
                            acertos += 1
                        elif mercado == "Jogos 5.5 FT" and total_ft > 5.5:
                            acertos += 1
                        elif mercado == "BTTS FT":
                            mandante_ft = jogo["Mandante FT"]
                            visitante_ft = jogo["Visitante FT"]
                            if mandante_ft > 0 and visitante_ft > 0:
                                acertos += 1
                    return acertos, len(jogos_jogador)

                # ==============================================
                # CÁLCULO PRECISO PARA TODOS OS JOGADORES
                # ==============================================
                all_results = []

                for selected_player in selected_players:
                    cleaned_player_name = re.sub(r'^[🥇🥈🥉]\s', '', selected_player)

                    # Calcular cada mercado com precisão
                    vitorias, total_jogos = calcular_vitorias(df_resultados, cleaned_player_name)
                    over_15_gols, _ = calcular_over_15_gols_jogador(df_resultados, cleaned_player_name)
                    over_25_jogador, _ = calcular_over_25_jogador(df_resultados, cleaned_player_name)
                    jogos_05_ht, _ = calcular_mercado_ht(df_resultados, cleaned_player_name, "Jogos 0.5 HT")
                    jogos_15_ht, _ = calcular_mercado_ht(df_resultados, cleaned_player_name, "Jogos 1.5 HT")
                    jogos_25_ht, _ = calcular_mercado_ht(df_resultados, cleaned_player_name, "Jogos 2.5 HT")
                    btts_ht, _ = calcular_mercado_ht(df_resultados, cleaned_player_name, "BTTS HT")
                    jogos_05_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "Jogos 0.5 FT")
                    jogos_15_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "Jogos 1.5 FT")
                    jogos_25_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "Jogos 2.5 FT")
                    jogos_35_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "Jogos 3.5 FT")
                    jogos_45_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "Jogos 4.5 FT")
                    jogos_55_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "Jogos 5.5 FT")
                    btts_ft, _ = calcular_mercado_ft(df_resultados, cleaned_player_name, "BTTS FT")
                    under_35_ft, _ = calcular_under_ft(df_resultados, cleaned_player_name, 3.5)
                    under_45_ft, _ = calcular_under_ft(df_resultados, cleaned_player_name, 4.5)
                    under_55_ft, _ = calcular_under_ft(df_resultados, cleaned_player_name, 5.5)

                    if total_jogos > 0:
                        # Lista de mercados na ORDEM SOLICITADA
                        market_data = [
                            {"Mercado": "Vitória", "Acertos": vitorias, "Jogos": total_jogos},
                            {"Mercado": "Jogos 0.5 HT", "Acertos": jogos_05_ht, "Jogos": total_jogos},
                            {"Mercado": "Jogos 1.5 HT", "Acertos": jogos_15_ht, "Jogos": total_jogos},
                            {"Mercado": "Jogos 2.5 HT", "Acertos": jogos_25_ht, "Jogos": total_jogos},
                            {"Mercado": "BTTS HT", "Acertos": btts_ht, "Jogos": total_jogos},
                            {"Mercado": "Over 1.5 Jogador", "Acertos": over_15_gols, "Jogos": total_jogos},
                            {"Mercado": "Over 2.5 Jogador", "Acertos": over_25_jogador, "Jogos": total_jogos},
                            {"Mercado": "Jogos 0.5 FT", "Acertos": jogos_05_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos 1.5 FT", "Acertos": jogos_15_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos 2.5 FT", "Acertos": jogos_25_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos 3.5 FT", "Acertos": jogos_35_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos 4.5 FT", "Acertos": jogos_45_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos 5.5 FT", "Acertos": jogos_55_ft, "Jogos": total_jogos},
                            {"Mercado": "BTTS FT", "Acertos": btts_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos Under 3.5 FT", "Acertos": under_35_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos Under 4.5 FT", "Acertos": under_45_ft, "Jogos": total_jogos},
                            {"Mercado": "Jogos Under 5.5 FT", "Acertos": under_55_ft, "Jogos": total_jogos}
                        ]

                        for market in market_data:
                            hits = market["Acertos"]
                            total_games = market["Jogos"]
                            misses = total_games - hits
                            hit_rate = (hits / total_games) * 100 if total_games > 0 else 0

                            profit_loss_units = (hits * (default_odds - 1)) - misses
                            total_invested = total_games * stake_value
                            roi = (profit_loss_units / total_invested) * 100 if total_invested > 0 else 0

                            all_results.append({
                                "Jogador": selected_player,
                                "Mercado": market["Mercado"],
                                "Total de Jogos": total_games,
                                "Acertos": hits,
                                "Erros": misses,
                                "Taxa Acerto (%)": hit_rate,
                                "Lucro/Prejuizo (Unidades)": profit_loss_units,
                                "ROI (%)": roi
                            })

                if all_results:
                    df_all_results = pd.DataFrame(all_results)

                    # ==============================================
                    # CSS PARA TEMA ESCURO
                    # ==============================================
                    st.markdown("""
                    <style>
                    .dark-table {
                        background-color: #1E1E1E !important;
                        color: white !important;
                        width: 100% !important;
                        table-layout: fixed !important;
                    }
                    .dark-table thead th {
                        background-color: #2C2C2C !important;
                        color: white !important;
                        font-weight: bold !important;
                        text-align: center !important;
                        border: 1px solid #444 !important;
                        padding: 8px !important;
                    }
                    .dark-table td {
                        background-color: #1E1E1E !important;
                        color: white !important;
                        border: 1px solid #444 !important;
                        text-align: center !important;
                        padding: 8px !important;
                        white-space: nowrap !important;
                    }
                    .profit-positive {
                        background-color: #155724 !important;
                        color: #d4edda !important;
                        font-weight: bold !important;
                    }
                    .profit-negative {
                        background-color: #721c24 !important;
                        color: #f8d7da !important;
                        font-weight: bold !important;
                    }
                    </style>
                    """, unsafe_allow_html=True)

                    # ==============================================
                    # TABELAS INDIVIDUAIS PARA CADA JOGADOR
                    # ==============================================
                    for player in selected_players:
                        st.markdown("---")
                        st.subheader(f"🎯 Desempenho Financeiro - {player}")

                        player_results = df_all_results[df_all_results['Jogador'] == player]

                        if not player_results.empty:
                            player_results = player_results.sort_values('Lucro/Prejuizo (Unidades)', ascending=False)

                            # Formatar valores
                            player_results_formatted = player_results.copy()
                            player_results_formatted['Taxa Acerto (%)'] = player_results_formatted[
                                'Taxa Acerto (%)'].apply(lambda x: f"{x:.1f}%")
                            player_results_formatted['Lucro/Prejuizo (Unidades)'] = player_results_formatted[
                                'Lucro/Prejuizo (Unidades)'].apply(lambda x: f"{x:.2f} Unid")
                            player_results_formatted['ROI (%)'] = player_results_formatted['ROI (%)'].apply(
                                lambda x: f"{x:.1f}%")

                            column_order = [
                                "Mercado", "Total de Jogos", "Acertos", "Erros",
                                "Taxa Acerto (%)", "Lucro/Prejuizo (Unidades)", "ROI (%)"
                            ]

                            df_player_display = player_results_formatted[column_order]

                            # Aplicar estilo
                            styled_data = []
                            for _, row in df_player_display.iterrows():
                                styled_row = {}
                                for col in column_order:
                                    cell_value = row[col]
                                    cell_class = ''
                                    if col == 'Lucro/Prejuizo (Unidades)' and 'Unid' in str(cell_value):
                                        num_val = float(str(cell_value).replace(' Unid', ''))
                                        cell_class = 'profit-positive' if num_val > 0 else 'profit-negative'
                                    elif col == 'ROI (%)' and '%' in str(cell_value):
                                        num_val = float(str(cell_value).replace('%', ''))
                                        cell_class = 'profit-positive' if num_val > 0 else 'profit-negative'

                                    if cell_class:
                                        styled_row[col] = f'<div class="{cell_class}">{cell_value}</div>'
                                    else:
                                        styled_row[col] = cell_value
                                styled_data.append(styled_row)

                            df_styled = pd.DataFrame(styled_data)

                            st.markdown('<div class="dark-table">', unsafe_allow_html=True)
                            st.write(df_styled.to_html(escape=False, index=False), unsafe_allow_html=True)
                            st.markdown('</div>', unsafe_allow_html=True)

                            # DICAS ESTRATÉGICAS
                            st.subheader("💎 Dicas Estratégicas")
                            top_5_mercados = player_results.nlargest(5, 'Lucro/Prejuizo (Unidades)')

                            for _, mercado in top_5_mercados.iterrows():
                                if mercado['Lucro/Prejuizo (Unidades)'] > 0:
                                    if mercado['Taxa Acerto (%)'] >= 90:
                                        emoji, intensidade, recomendacao = "🔥", "absurdo", "OPORTUNIDADE EXCELENTE"
                                    elif mercado['Taxa Acerto (%)'] >= 80:
                                        emoji, intensidade, recomendacao = "⚡", "excelente", "OPORTUNIDADE DE ALTO NÍVEL"
                                    elif mercado['Taxa Acerto (%)'] >= 70:
                                        emoji, intensidade, recomendacao = "🎯", "muito bom", "BOA OPORTUNIDADE"
                                    else:
                                        emoji, intensidade, recomendacao = "📈", "bom", "OPORTUNIDADE INTERESSANTE"

                                    st.success(
                                        f"{emoji} **{recomendacao}**: O mercado **{mercado['Mercado']}** em jogos do **{player}** "
                                        f"tem um aproveitamento {intensidade} de **{mercado['Taxa Acerto (%)']:.1f}%**, "
                                        f"gerando um lucro de **{mercado['Lucro/Prejuizo (Unidades)']:.2f} Unid** com odd {default_odds}."
                                    )

                            # ALERTAS DE RISCO
                            worst_mercados = player_results[player_results['Lucro/Prejuizo (Unidades)'] < 0]
                            if not worst_mercados.empty:
                                st.subheader("⚠️ Alertas de Risco")
                                for _, mercado in worst_mercados.iterrows():
                                    st.error(
                                        f"🔴 **EVITAR**: O mercado **{mercado['Mercado']}** do **{player}** "
                                        f"está com prejuízo de **{mercado['Lucro/Prejuizo (Unidades)']:.2f} Unid**. "
                                        f"Apenas **{mercado['Taxa Acerto (%)']:.1f}%** de acerto."
                                    )

                            # RESUMO ESTATÍSTICO
                            col_res1, col_res2, col_res3, col_res4 = st.columns(4)
                            with col_res1:
                                total_lucro = player_results['Lucro/Prejuizo (Unidades)'].sum()
                                st.metric("💰 Lucro Total", f"{total_lucro:.2f} Unid",
                                          delta_color="normal" if total_lucro >= 0 else "inverse")
                            with col_res2:
                                melhor_mercado = player_results.nlargest(1, 'Lucro/Prejuizo (Unidades)').iloc[0]
                                st.metric("🏆 Melhor Mercado", melhor_mercado['Mercado'],
                                          f"{melhor_mercado['Lucro/Prejuizo (Unidades)']:.2f} Unid")
                            with col_res3:
                                pior_mercado = player_results.nsmallest(1, 'Lucro/Prejuizo (Unidades)').iloc[0]
                                st.metric("⚡ Pior Mercado", pior_mercado['Mercado'],
                                          f"{pior_mercado['Lucro/Prejuizo (Unidades)']:.2f} Unid")
                            with col_res4:
                                avg_roi = player_results['ROI (%)'].mean()
                                st.metric("📈 ROI Médio", f"{avg_roi:.1f}%")

                    # ==============================================
                    # GRADE DE CONFRONTOS - ANÁLISE ESTRATÉGICA
                    # ==============================================
                    if len(selected_players) >= 2:
                        st.markdown("---")
                        st.header("⚔️ Grade de Confrontos - Análise Estratégica")
                        st.write("Cruza os dados de desempenho para identificar mercados lucrativos nos confrontos")

                        # Gerar confrontos
                        confrontos = []
                        for i in range(len(selected_players)):
                            for j in range(i + 1, len(selected_players)):
                                confrontos.append((selected_players[i], selected_players[j]))

                        recomendacoes_confrontos = []

                        for jogador1, jogador2 in confrontos:
                            dados_jogador1 = df_all_results[df_all_results['Jogador'] == jogador1]
                            dados_jogador2 = df_all_results[df_all_results['Jogador'] == jogador2]

                            if not dados_jogador1.empty and not dados_jogador2.empty:
                                mercados_lucrativos = []

                                for mercado in dados_jogador1['Mercado'].unique():
                                    mercado_j1 = dados_jogador1[dados_jogador1['Mercado'] == mercado]
                                    mercado_j2 = dados_jogador2[dados_jogador2['Mercado'] == mercado]

                                    if not mercado_j1.empty and not mercado_j2.empty:
                                        lucro_j1 = mercado_j1.iloc[0]['Lucro/Prejuizo (Unidades)']
                                        lucro_j2 = mercado_j2.iloc[0]['Lucro/Prejuizo (Unidades)']
                                        taxa_j1 = mercado_j1.iloc[0]['Taxa Acerto (%)']
                                        taxa_j2 = mercado_j2.iloc[0]['Taxa Acerto (%)']

                                        if lucro_j1 > 0 and lucro_j2 > 0:
                                            mercados_lucrativos.append({
                                                "Mercado": mercado,
                                                "Lucro J1": lucro_j1,
                                                "Lucro J2": lucro_j2,
                                                "Taxa J1": taxa_j1,
                                                "Taxa J2": taxa_j2,
                                                "Confiança": "🟢 Excelente"
                                            })
                                        elif (lucro_j1 > 0 and taxa_j1 >= 70) or (lucro_j2 > 0 and taxa_j2 >= 70):
                                            mercados_lucrativos.append({
                                                "Mercado": mercado,
                                                "Lucro J1": lucro_j1,
                                                "Lucro J2": lucro_j2,
                                                "Taxa J1": taxa_j1,
                                                "Taxa J2": taxa_j2,
                                                "Confiança": "🟡 Boa"
                                            })

                                if mercados_lucrativos:
                                    mercados_lucrativos.sort(key=lambda x: (
                                        0 if "🟢" in x["Confiança"] else 1,
                                        x["Lucro J1"] + x["Lucro J2"]
                                    ), reverse=True)

                                    for mercado_info in mercados_lucrativos[:3]:
                                        recomendacoes_confrontos.append({
                                            "Confronto": f"{jogador1} vs {jogador2}",
                                            "Mercado Recomendado": mercado_info["Mercado"],
                                            "Confiança": mercado_info["Confiança"],
                                            "Lucro Potencial": f"{(mercado_info['Lucro J1'] + mercado_info['Lucro J2']):.2f} Unid",
                                            "Desempenho J1": f"{mercado_info['Taxa J1']:.1f}%",
                                            "Desempenho J2": f"{mercado_info['Taxa J2']:.1f}%"
                                        })

                        # EXIBIR RECOMENDAÇÕES
                        if recomendacoes_confrontos:
                            df_recomendacoes = pd.DataFrame(recomendacoes_confrontos)

                            st.subheader("🎯 Melhores Oportunidades de Apostas")

                            # Mercados mais frequentes
                            st.success("**💎 MERCADOS MAIS PROMISSORES:**")
                            mercados_frequentes = df_recomendacoes['Mercado Recomendado'].value_counts()
                            for mercado, count in mercados_frequentes.items():
                                st.write(f"• **{mercado}**: Recomendado em {count} confrontos")

                            st.dataframe(df_recomendacoes, use_container_width=True, height=300)

                            # Top 3 confrontos
                            st.subheader("🏆 Top 3 Confrontos com Maior Potencial")
                            lucro_por_confronto = {}
                            for rec in recomendacoes_confrontos:
                                confronto = rec["Confronto"]
                                lucro = float(rec["Lucro Potencial"].replace(" Unid", ""))
                                lucro_por_confronto[confronto] = lucro_por_confronto.get(confronto, 0) + lucro

                            top_confrontos = sorted(lucro_por_confronto.items(), key=lambda x: x[1], reverse=True)[:3]

                            col1, col2, col3 = st.columns(3)
                            for i, (confronto, lucro) in enumerate(top_confrontos):
                                with [col1, col2, col3][i]:
                                    st.metric(f"{['🥇', '🥈', '🥉'][i]} {confronto}", f"{lucro:.2f} Unid",
                                              "Alto Potencial")

                            # Estratégia
                            st.subheader("💡 Estratégia Recomendada")
                            mercado_mais_frequente = df_recomendacoes['Mercado Recomendado'].mode()[0]
                            st.info(f"""
                            **🎯 FOQUE NO MERCADO:** {mercado_mais_frequente}

                            • **Odd ideal**: 1.80-2.20
                            • **Gestão de banca**: 2-3% por aposta
                            • **Priorize os confrontos do Top 3**
                            """)

                        else:
                            st.info("📊 Não foram identificadas oportunidades claras nos confrontos analisados.")

                    # ==============================================
                    # COMPARAÇÃO ENTRE JOGADORES
                    # ==============================================
                    if len(selected_players) > 1:
                        st.markdown("---")
                        st.subheader("📊 Comparativo entre Jogadores")

                        comparativo = df_all_results.groupby('Jogador').agg({
                            'Total de Jogos': 'first',
                            'Lucro/Prejuizo (Unidades)': 'sum',
                            'ROI (%)': 'mean'
                        }).reset_index()

                        comparativo = comparativo.sort_values('Lucro/Prejuizo (Unidades)', ascending=False)

                        col_comp1, col_comp2 = st.columns(2)
                        with col_comp1:
                            st.write("**🏆 Ranking por Lucro:**")
                            for i, (_, jogador) in enumerate(comparativo.iterrows()):
                                st.write(
                                    f"{i + 1}º **{jogador['Jogador']}** - {jogador['Lucro/Prejuizo (Unidades)']:.2f}u (ROI: {jogador['ROI (%)']:.1f}%)")
                        with col_comp2:
                            st.write("**🎯 Melhor Mercado por Jogador:**")
                            for jogador in selected_players:
                                jogador_data = df_all_results[df_all_results['Jogador'] == jogador]
                                if not jogador_data.empty:
                                    melhor = jogador_data.nlargest(1, 'Lucro/Prejuizo (Unidades)').iloc[0]
                                    st.write(
                                        f"**{jogador}**: {melhor['Mercado']} ({melhor['Lucro/Prejuizo (Unidades)']:.2f}u)")

                    # ==============================================
                    # DOWNLOAD DOS DADOS
                    # ==============================================
                    st.markdown("---")
                    st.subheader("📥 Exportar Dados")
                    csv = df_all_results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="💾 Baixar Análise Completa (CSV)",
                        data=csv,
                        file_name='analise_jogadores_detalhada.csv',
                        mime='text/csv',
                    )

                else:
                    st.info("📊 Nenhum dado encontrado para os jogadores selecionados")

            else:
                st.info("👆 Selecione pelo menos um jogador para ver a análise")

        else:
            st.info("📊 Aguardando carregamento dos dados...")

    # Aba 7: Salvar Jogos
    with tabs[6]:
        st.header("💾 Jogos Salvos - Análise")

        if 'saved_games' not in st.session_state:
            st.session_state.saved_games = pd.DataFrame(columns=[
                'Hora', 'Liga', 'Mandante', 'Visitante',
                'Sugestão HT', 'Sugestão FT', 'Data Salvamento'
            ])

        st.subheader("📊 Análise de Resultados")

        if st.button("🔍 Atualizar Análise de Resultados", key="update_results_analysis"):
            results = []
            total_games = 0
            ht_greens = 0
            ht_reds = 0
            ft_greens = 0
            ft_reds = 0
            total_ht_profit = 0.0
            total_ft_profit = 0.0

            for _, game in st.session_state.saved_games.iterrows():
                game_date = game.get('Data do Jogo', None)

                if not game_date or game_date == "Aguardando":
                    result_data = df_resultados[
                        (df_resultados['Mandante'] == game['Mandante']) &
                        (df_resultados['Visitante'] == game['Visitante'])
                        ]
                    if not result_data.empty:
                        game_date = result_data.iloc[0].get('Data', "Aguardando")

                result_data = df_resultados[
                    (df_resultados['Mandante'] == game['Mandante']) &
                    (df_resultados['Visitante'] == game['Visitante'])
                    ]

                if not result_data.empty:
                    latest_result = result_data.iloc[0]
                    total_ht = latest_result.get('Mandante HT', 0) + latest_result.get('Visitante HT', 0)
                    total_ft = latest_result.get('Mandante FT', 0) + latest_result.get('Visitante FT', 0)

                    ht_profit = calculate_profit(game.get('Sugestão HT', ''), total_ht, odd=1.60)
                    ft_profit = calculate_profit(game.get('Sugestão FT', ''), total_ft, odd=1.60)

                    if ht_profit > 0:
                        ht_greens += 1
                    elif ht_profit < 0:
                        ht_reds += 1
                    if ft_profit > 0:
                        ft_greens += 1
                    elif ft_profit < 0:
                        ft_reds += 1

                    total_ht_profit += ht_profit
                    total_ft_profit += ft_profit
                    total_games += 1

                    results.append({
                        'Hora': game['Hora'],
                        'Data do Jogo': latest_result.get('Data', game_date if game_date else "Aguardando"),
                        'Jogo': f"{game['Mandante']} vs {game['Visitante']}",
                        'Status': "✅ Finalizado",
                        'Sugestão HT': game.get('Sugestão HT', 'N/A'),
                        'Resultado HT': f"{latest_result.get('Mandante HT', '?')}-{latest_result.get('Visitante HT', '?')}",
                        'Lucro HT': f"{ht_profit:.2f}u",
                        'Sugestão FT': game.get('Sugestão FT', 'N/A'),
                        'Resultado FT': f"{latest_result.get('Mandante FT', '?')}-{latest_result.get('Visitante FT', '?')}",
                        'Lucro FT': f"{ft_profit:.2f}u"
                    })
                else:
                    results.append({
                        'Hora': game['Hora'],
                        'Data do Jogo': game_date if game_date else "Aguardando",
                        'Jogo': f"{game['Mandante']} vs {game['Visitante']}",
                        'Status': "✅ Finalizado",
                        'Sugestão HT': game.get('Sugestão HT', 'N/A'),
                        'Resultado HT': "N/D",
                        'Lucro HT': "0.00u",
                        'Sugestão FT': game.get('Sugestão FT', 'N/A'),
                        'Resultado FT': "N/D",
                        'Lucro FT': "0.00u"
                    })

            if results:
                df_results = pd.DataFrame(results)
                df_results = df_results.sort_values('Data do Jogo', ascending=False)

                def color_profit(val):
                    if isinstance(val, str) and 'u' in val:
                        num = float(val.replace('u', ''))
                        if num > 0:
                            return 'color: green; font-weight: bold;'
                        elif num < 0:
                            return 'color: red; font-weight: bold;'
                    return ''

                styled_df = df_results.style.map(color_profit, subset=['Lucro HT', 'Lucro FT'])
                st.dataframe(styled_df, use_container_width=True, height=500)

                if total_games > 0:
                    odds_range = [1.50, 1.75, 2.00, 2.25, 2.50, 2.75, 3.00]
                    projection_data = []

                    for odd in odds_range:
                        ht_profit = 0.0
                        ft_profit = 0.0
                        ht_greens = 0
                        ht_reds = 0
                        ft_greens = 0
                        ft_reds = 0

                        for _, game in st.session_state.saved_games.iterrows():
                            result_data = df_resultados[
                                (df_resultados['Mandante'] == game['Mandante']) &
                                (df_resultados['Visitante'] == game['Visitante'])
                                ]
                            if not result_data.empty:
                                latest_result = result_data.iloc[0]
                                total_ht = latest_result.get('Mandante HT', 0) + latest_result.get('Visitante HT', 0)
                                total_ft = latest_result.get('Mandante FT', 0) + latest_result.get('Visitante FT', 0)

                                ht_p = calculate_profit(game.get('Sugestão HT', ''), total_ht, odd=odd)
                                ft_p = calculate_profit(game.get('Sugestão FT', ''), total_ft, odd=odd)

                                if ht_p > 0:
                                    ht_greens += 1
                                elif ht_p < 0:
                                    ht_reds += 1
                                if ft_p > 0:
                                    ft_greens += 1
                                elif ft_p < 0:
                                    ft_reds += 1

                                ht_profit += ht_p
                                ft_profit += ft_p

                        total_profit = ht_profit + ft_profit
                        projection_data.append({
                            'Odd': f"{odd:.2f}",
                            'Total Jogos': total_games,
                            'Greens HT': ht_greens,
                            'Reds HT': ht_reds,
                            'Greens FT': ft_greens,
                            'Reds FT': ft_reds,
                            'Lucro HT': f"{ht_profit:.2f}u",
                            'Lucro FT': f"{ft_profit:.2f}u",
                            'Lucro Total': f"{total_profit:.2f}u"
                        })

                    df_projection = pd.DataFrame(projection_data)

                    styled_projection = df_projection.style.map(
                        color_profit, subset=['Lucro HT', 'Lucro FT', 'Lucro Total']
                    ).format({
                        'Odd': '{}',
                        'Total Jogos': '{:.0f}',
                        'Greens HT': '{:.0f}',
                        'Reds HT': '{:.0f}',
                        'Greens FT': '{:.0f}',
                        'Reds FT': '{:.0f}',
                        'Lucro HT': '{}',
                        'Lucro FT': '{}',
                        'Lucro Total': '{}'
                    })

                    st.dataframe(styled_projection, use_container_width=True)

                    st.markdown("### 📊 Resumo Geral")
                    cols = st.columns(4)
                    cols[0].metric("Total de Jogos Analisados", total_games)
                    cols[1].metric("Greens HT", ht_greens)
                    cols[2].metric("Reds HT", ht_reds)
                    cols[3].metric("Lucro HT (Odd 1.60)", f"{total_ht_profit:.2f}u")
                    cols = st.columns(4)
                    cols[0].metric("Total de Jogos Analisados", total_games)
                    cols[1].metric("Greens FT", ft_greens)
                    cols[2].metric("Reds FT", ft_reds)
                    cols[3].metric("Lucro FT (Odd 1.60)", f"{total_ft_profit:.2f}u")
                    cols = st.columns(2)
                    cols[0].metric("Lucro Combinado (Odd 1.60)", f"{total_ht_profit + total_ft_profit:.2f}u")

                else:
                    st.info("Nenhum jogo finalizado para calcular projeção de ganhos.")

            else:
                st.info("Nenhum resultado encontrado para análise.")

        st.subheader("📋 Jogos Salvos")
        if st.session_state.saved_games.empty:
            st.info("Nenhum jogo salvo ainda. Selecione jogos da aba 'Ao Vivo' para salvá-los aqui.")
        else:
            st.dataframe(st.session_state.saved_games, use_container_width=True, height=400)
            if st.button("🗑️ Limpar Todos os Jogos Salvos", key="clear_all_saved"):
                st.session_state.saved_games = pd.DataFrame(columns=[
                    'Hora', 'Liga', 'Mandante', 'Visitante',
                    'Sugestão HT', 'Sugestão FT', 'Data Salvamento'
                ])
                st.success("Todos os jogos salvos foram removidos!")
                st.rerun()
            csv = st.session_state.saved_games.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Jogos Salvos",
                data=csv,
                file_name='jogos_salvos.csv',
                mime='text/csv'
            )

    with tabs[7]:  # Agora a aba 7 é "Resultados"
        st.header("📊 Resultados Históricos")

        if df_resultados.empty:
            st.warning("Nenhum dado de resultados disponível no momento.")
        else:
            # Filtros
            col1, col2, col3 = st.columns(3)
            with col1:
                ligas_disponiveis = df_resultados['Liga'].unique()
                liga_selecionada = st.selectbox(
                    'Filtrar por Liga:',
                    options=['Todas'] + list(ligas_disponiveis),
                    index=0
                )

            with col2:
                jogadores_disponiveis = sorted(
                    list(set(df_resultados['Mandante'].unique()) | set(df_resultados['Visitante'].unique())))
                jogador_selecionado = st.selectbox(
                    'Filtrar por Jogador:',
                    options=['Todos'] + jogadores_disponiveis,
                    index=0
                )

            with col3:
                num_jogos = st.slider(
                    'Número de jogos a exibir:',
                    min_value=10,
                    max_value=500,
                    value=100,
                    step=10
                )

            # Aplicar filtros
            df_filtrado = df_resultados.copy()
            if liga_selecionada != 'Todas':
                df_filtrado = df_filtrado[df_filtrado['Liga'] == liga_selecionada]
            if jogador_selecionado != 'Todos':
                df_filtrado = df_filtrado[
                    (df_filtrado['Mandante'] == jogador_selecionado) |
                    (df_filtrado['Visitante'] == jogador_selecionado)
                    ]

            df_filtrado = df_filtrado.sort_values('Data', ascending=False).head(num_jogos)

            # Mostrar estatísticas resumidas
            st.subheader("📈 Estatísticas Resumidas")
            if not df_filtrado.empty:
                total_jogos = len(df_filtrado)
                avg_gols_ht = df_filtrado['Total HT'].mean()
                avg_gols_ft = df_filtrado['Total FT'].mean()
                over_25_ft = (df_filtrado['Total FT'] > 2.5).mean() * 100
                over_15_ht = (df_filtrado['Total HT'] > 1.5).mean() * 100
                btts_ft = ((df_filtrado['Mandante FT'] > 0) & (df_filtrado['Visitante FT'] > 0)).mean() * 100

                cols = st.columns(5)
                cols[0].metric("Total de Jogos", total_jogos)
                cols[1].metric("Média Gols HT", f"{avg_gols_ht:.2f}")
                cols[2].metric("Média Gols FT", f"{avg_gols_ft:.2f}")
                cols[3].metric("Over 2.5 FT", f"{over_25_ft:.1f}%")
                cols[4].metric("BTTS FT", f"{btts_ft:.1f}%")

            # Mostrar tabela de resultados
            st.subheader("📋 Últimos Resultados")

            # Selecionar colunas para exibição
            colunas_exibicao = [
                'Data', 'Liga', 'Mandante', 'Visitante',
                'Mandante HT', 'Visitante HT', 'Total HT',
                'Mandante FT', 'Visitante FT', 'Total FT'
            ]

            # Configurar AgGrid
            gb = GridOptionsBuilder.from_dataframe(df_filtrado[colunas_exibicao])
            gb.configure_default_column(
                flex=1,
                minWidth=100,
                wrapText=True,
                autoHeight=True,
                resizable=True
            )

            # Configurar paginação
            gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)

            # Configurar filtros
            for col in colunas_exibicao:
                gb.configure_column(col, header_name=col, filter=True)

            grid_options = gb.build()

            # Exibir tabela
            AgGrid(
                df_filtrado[colunas_exibicao],
                gridOptions=grid_options,
                height=600,
                width='100%',
                fit_columns_on_grid_load=False,
                theme='streamlit',
                update_mode=GridUpdateMode.MODEL_CHANGED,
                allow_unsafe_jscode=True
            )

            # Botão para download
            csv = df_filtrado[colunas_exibicao].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Resultados",
                data=csv,
                file_name='resultados_fifa.csv',
                mime='text/csv'
            )

    with tabs[8]:  # Nova aba "Relatórios"
        st.header("📈 Relatórios de Oportunidades (Confrontos Diretos)")
        st.write(
            "Analisa apenas confrontos diretos com histórico de pelo menos 5 jogos para identificar as melhores oportunidades")

        if df_live_clean.empty or df_resultados.empty:
            st.warning("Dados insuficientes para gerar relatórios. Aguarde a atualização.")
        else:
            # Configurações mais rigorosas
            MIN_JOGOS_CONFRONTO = 5
            MIN_PORCENTAGEM = 75  # Aumentado para 75% conforme solicitado
            MAX_SUGESTOES_POR_PARTIDA = 8  # Limite de sugestões por partida

            # Definindo todos os mercados solicitados com seus respectivos critérios
            TIPOS_APOSTA = {
                "Vencedor da Partida": {
                    "col": "Vencedor",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "p1_wins": len(df[((df["Mandante"] == p1) & (df["Mandante FT"] > df["Visitante FT"])) |
                                          ((df["Visitante"] == p1) & (df["Visitante FT"] > df["Mandante FT"]))]),
                        "p2_wins": len(df[((df["Mandante"] == p2) & (df["Mandante FT"] > df["Visitante FT"])) |
                                          ((df["Visitante"] == p2) & (df["Visitante FT"] > df["Mandante FT"]))]),
                        "draws": len(df[df["Mandante FT"] == df["Visitante FT"]])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 1  # Prioridade mais alta
                },
                "Over 1.5 Jogador": {
                    "col": "Over 1.5 Player",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "p1_hits": len(df[((df["Mandante"] == p1) & (df["Mandante FT"] >= 2)) |
                                          ((df["Visitante"] == p1) & (df["Visitante FT"] >= 2))]),
                        "p2_hits": len(df[((df["Mandante"] == p2) & (df["Mandante FT"] >= 2)) |
                                          ((df["Visitante"] == p2) & (df["Visitante FT"] >= 2))])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 2
                },
                "Over 2.5 Jogador": {
                    "col": "Over 2.5 Player",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "p1_hits": len(df[((df["Mandante"] == p1) & (df["Mandante FT"] >= 3)) |
                                          ((df["Visitante"] == p1) & (df["Visitante FT"] >= 3))]),
                        "p2_hits": len(df[((df["Mandante"] == p2) & (df["Mandante FT"] >= 3)) |
                                          ((df["Visitante"] == p2) & (df["Visitante FT"] >= 3))])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 3
                },
                "BTTS HT": {
                    "col": "BTTS HT",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "hits": len(df[(df["Mandante HT"] > 0) & (df["Visitante HT"] > 0)])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 4
                },
                "Over 2.5 HT": {
                    "col": "Over 2.5 HT",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "hits": len(df[(df["Mandante HT"] + df["Visitante HT"]) > 2.5])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 5
                },
                "Over 3.5 FT": {
                    "col": "Over 3.5",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "hits": len(df[(df["Mandante FT"] + df["Visitante FT"]) > 3.5])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 6
                },
                "Over 4.5 FT": {
                    "col": "Over 4.5",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "hits": len(df[(df["Mandante FT"] + df["Visitante FT"]) > 4.5])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 7
                },
                "Over 5.5 FT": {
                    "col": "Over 5.5",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "hits": len(df[(df["Mandante FT"] + df["Visitante FT"]) > 5.5])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 8
                },
                "Under 5.5 FT": {
                    "col": "Under 5.5",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "hits": len(df[(df["Mandante FT"] + df["Visitante FT"]) < 5.5])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 9
                },
                "Under 2.5 Jogador": {
                    "col": "Under 2.5 Player",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "p1_hits": len(df[((df["Mandante"] == p1) & (df["Mandante FT"] < 2.5)) |
                                          ((df["Visitante"] == p1) & (df["Visitante FT"] < 2.5))]),
                        "p2_hits": len(df[((df["Mandante"] == p2) & (df["Mandante FT"] < 2.5)) |
                                          ((df["Visitante"] == p2) & (df["Visitante FT"] < 2.5))])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 10
                },
                "Under 3.5 Jogador": {
                    "col": "Under 3.5 Player",
                    "analysis": lambda df, p1, p2: {
                        "total": len(df),
                        "p1_hits": len(df[((df["Mandante"] == p1) & (df["Mandante FT"] < 3.5)) |
                                          ((df["Visitante"] == p1) & (df["Visitante FT"] < 3.5))]),
                        "p2_hits": len(df[((df["Mandante"] == p2) & (df["Mandante FT"] < 3.5)) |
                                          ((df["Visitante"] == p2) & (df["Visitante FT"] < 3.5))])
                    },
                    "threshold": MIN_PORCENTAGEM,
                    "priority": 11
                }
            }

            # Obter hora atual
            brasil_tz = pytz.timezone('America/Sao_Paulo')
            hora_atual = datetime.now(brasil_tz).strftime("%H:%M")

            # Processar cada jogo ao vivo FUTURO (hora > hora_atual)
            relatorios = []
            jogos_com_historico = 0

            # Ordenar jogos ao vivo por hora (do mais próximo para o mais distante)
            df_live_futuro = df_live_clean[df_live_clean['Hora'] > hora_atual].sort_values('Hora', ascending=True)

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
                    jogos_com_historico += 1

                    # Dicionário para armazenar todas as oportunidades encontradas para esta partida
                    oportunidades_partida = []

                    # Analisar confrontos diretos para cada tipo de aposta
                    for aposta, config in TIPOS_APOSTA.items():
                        stats = config["analysis"](df_historico, p1, p2)
                        threshold = config["threshold"]
                        priority = config["priority"]

                        if aposta == "Vencedor da Partida":
                            p1_win_rate = (stats["p1_wins"] / stats["total"]) * 100 if stats["total"] > 0 else 0
                            p2_win_rate = (stats["p2_wins"] / stats["total"]) * 100 if stats["total"] > 0 else 0
                            draw_rate = (stats["draws"] / stats["total"]) * 100 if stats["total"] > 0 else 0

                            if p1_win_rate >= threshold:
                                oportunidades_partida.append({
                                    "priority": priority,
                                    "tipo": f"Vitória {p1}",
                                    "stats": f"VENCEU {stats['p1_wins']} DE {stats['total']} JOGOS ({p1_win_rate:.0f}%)",
                                    "confianca": "🟢 Alta" if p1_win_rate >= 80 else "🟡 Média"
                                })
                            if p2_win_rate >= threshold:
                                oportunidades_partida.append({
                                    "priority": priority,
                                    "tipo": f"Vitória {p2}",
                                    "stats": f"VENCEU {stats['p2_wins']} DE {stats['total']} JOGOS ({p2_win_rate:.0f}%)",
                                    "confianca": "🟢 Alta" if p2_win_rate >= 80 else "🟡 Média"
                                })
                            if draw_rate >= threshold:
                                oportunidades_partida.append({
                                    "priority": priority,
                                    "tipo": "Empate FT",
                                    "stats": f"OCORREU {stats['draws']} DE {stats['total']} JOGOS ({draw_rate:.0f}%)",
                                    "confianca": "🟢 Alta" if draw_rate >= 80 else "🟡 Média"
                                })
                        elif "Over" in aposta or "Under" in aposta:
                            if "Jogador" in aposta:
                                # Mercados por jogador (Over/Under)
                                p1_hits = stats["p1_hits"]
                                p2_hits = stats["p2_hits"]
                                total = stats["total"]

                                p1_rate = (p1_hits / total) * 100 if total > 0 else 0
                                p2_rate = (p2_hits / total) * 100 if total > 0 else 0

                                if p1_rate >= threshold:
                                    oportunidades_partida.append({
                                        "priority": priority,
                                        "tipo": f"{aposta} - {p1}",
                                        "stats": f"ACERTOU {p1_hits} DE {total} JOGOS ({p1_rate:.0f}%)",
                                        "confianca": "🟢 Alta" if p1_rate >= 80 else "🟡 Média"
                                    })
                                if p2_rate >= threshold:
                                    oportunidades_partida.append({
                                        "priority": priority,
                                        "tipo": f"{aposta} - {p2}",
                                        "stats": f"ACERTOU {p2_hits} DE {total} JOGOS ({p2_rate:.0f}%)",
                                        "confianca": "🟢 Alta" if p2_rate >= 80 else "🟡 Média"
                                    })
                            else:
                                # Mercados gerais (Over/Under HT/FT)
                                hits = stats["hits"]
                                total = stats["total"]
                                rate = (hits / total) * 100 if total > 0 else 0

                                if rate >= threshold:
                                    oportunidades_partida.append({
                                        "priority": priority,
                                        "tipo": aposta,
                                        "stats": f"OCORREU EM {hits} DE {total} JOGOS ({rate:.0f}%)",
                                        "confianca": "🟢 Alta" if rate >= 80 else "🟡 Média"
                                    })
                        else:
                            # Outros mercados (BTTS HT)
                            hits = stats["hits"]
                            total = stats["total"]
                            rate = (hits / total) * 100 if total > 0 else 0

                            if rate >= threshold:
                                oportunidades_partida.append({
                                    "priority": priority,
                                    "tipo": aposta,
                                    "stats": f"OCORREU EM {hits} DE {total} JOGOS ({rate:.0f}%)",
                                    "confianca": "🟢 Alta" if rate >= 80 else "🟡 Média"
                                })

                    # Ordenar oportunidades por prioridade e selecionar até 4 por partida
                    oportunidades_partida.sort(key=lambda x: x["priority"])

                    # Agrupar por tipo para evitar duplicatas
                    tipos_unicos = set()
                    oportunidades_filtradas = []

                    for op in oportunidades_partida:
                        tipo_base = op["tipo"].split(" - ")[0]  # Remove o nome do jogador para comparação
                        if tipo_base not in tipos_unicos:
                            tipos_unicos.add(tipo_base)
                            oportunidades_filtradas.append(op)
                            if len(oportunidades_filtradas) >= MAX_SUGESTOES_POR_PARTIDA:
                                break

                    # Adicionar ao relatório final
                    for op in oportunidades_filtradas:
                        relatorios.append({
                            "Hora": hora_jogo,
                            "Liga": liga,
                            "Jogo": f"{p1} x {p2}",
                            "Tipo Aposta": op["tipo"],
                            "Estatística": op["stats"],
                            "Confiança": op["confianca"],
                            "Jogos Analisados": len(df_historico)
                        })

            # Resumo inicial
            st.markdown(f"""
            ### 🔍 Relatório de Análise (Próximos Jogos)
            - **Hora atual:** {hora_atual}
            - **Próximos jogos ao vivo analisados:** {len(df_live_futuro)}
            - **Jogos com histórico suficiente (≥{MIN_JOGOS_CONFRONTO} confrontos diretos):** {jogos_com_historico}
            - **Oportunidades identificadas:** {len(relatorios)}
            - **Critério mínimo:** {MIN_PORCENTAGEM}% de acerto histórico
            """)

            if relatorios:
                df_relatorios = pd.DataFrame(relatorios)

                # Ordenar por hora do jogo (do mais próximo para o mais distante)
                df_relatorios = df_relatorios.sort_values("Hora", ascending=True)

                # Agrupar por jogo com expanders
                st.subheader("🎯 Melhores Oportunidades nos Próximos Jogos")
                for jogo in df_relatorios["Jogo"].unique():
                    df_jogo = df_relatorios[df_relatorios["Jogo"] == jogo]
                    hora_jogo = df_jogo["Hora"].iloc[0]
                    liga_jogo = df_jogo["Liga"].iloc[0]

                    with st.expander(f"⚽ {jogo} | {liga_jogo} | Hora: {hora_jogo} | {len(df_jogo)} oportunidades"):
                        for _, row in df_jogo.iterrows():
                            st.success(
                                f"**{row['Tipo Aposta']}**\n\n"
                                f"- {row['Estatística']}\n"
                                f"- Confiança: {row['Confiança']}\n"
                                f"- Jogos analisados: {row['Jogos Analisados']}"
                            )

                # Tabela detalhada
                st.subheader("📋 Detalhes de Todas as Oportunidades (Ordenadas por Hora)")
                st.dataframe(
                    df_relatorios,
                    column_config={
                        "Jogos Analisados": st.column_config.NumberColumn(format="%d jogos")
                    },
                    use_container_width=True,
                    height=600
                )

                # Botão para exportar
                csv = df_relatorios.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Exportar Relatórios Completos",
                    data=csv,
                    file_name='relatorios_proximos_jogos.csv',
                    mime='text/csv',
                    help="Exporta todas as oportunidades identificadas para um arquivo CSV"
                )
            else:
                st.info("""
                Nenhuma oportunidade de aposta identificada nos próximos jogos com base nos critérios:
                - Mínimo de 5 confrontos diretos históricos
                - Porcentagem de acerto acima de 72% para cada mercado
                - Máximo de 4 sugestões por partida, evitando repetições de mercados
                """)


# ==============================================
# FUNÇÕES AUXILIARES PARA ANÁLISE
# ==============================================

def perform_manual_analysis(df_resultados: pd.DataFrame, player1: str, player2: str, num_games_h2h: int,
                            num_games_individual: int):
    """Realiza análise manual entre dois jogadores"""
    st.subheader(f"Análise Manual para **{player1}** vs **{player2}**")

    if df_resultados.empty:
        st.warning("⚠️ Não há dados de resultados históricos disponíveis para análise.")
        return

    player1_clean = re.sub(r'^[🥇🥈🥉]\s', '', player1)
    player2_clean = re.sub(r'^[🥇🥈🥉]\s', '', player2)

    st.markdown("---")
    st.header("📈 Desempenho Individual Recente")
    col_p1_stats, col_p2_stats = st.columns(2)

    stats_p1_recent = get_recent_player_stats(df_resultados, player1_clean, num_games_individual)
    stats_p2_recent = get_recent_player_stats(df_resultados, player2_clean, num_games_individual)

    def display_individual_stats(player_name_display: str, stats: dict):
        if not stats:
            st.info(f"Não há dados recentes para **{player_name_display}** nos últimos {num_games_individual} jogos.")
            return

        st.markdown(f"### **{player_name_display}** (Últimos {stats['jogos_recentes']} jogos)")
        st.metric("Total de Jogos Analisados", stats['jogos_recentes'])

        st.write("**Força de Ataque (Média Gols Marcados):**")
        st.info(f"**FT:** {stats['media_gols_marcados_ft']:.2f} gols/jogo")
        st.info(f"**HT:** {stats['media_gols_marcados_ht']:.2f} gols/jogo")

        st.write("**Força de Defesa (Média Gols Sofridos):**")
        st.success(f"**FT:** {stats['media_gols_sofridos_ft']:.2f} gols/jogo")
        st.success(f"**HT:** {stats['media_gols_sofridos_ht']:.2f} gols/jogo")

        st.write("**Tendências de Gols:**")
        st.markdown(f"- **Over 0.5 HT:** {stats['pct_over_05_ht']:.2f}% dos jogos")
        st.markdown(f"- **Over 1.5 HT:** {stats['pct_over_15_ht']:.2f}% dos jogos")
        st.markdown(f"- **Over 2.5 HT:** {stats['pct_over_25_ht']:.2f}% dos jogos")
        st.markdown(f"- **Over 2.5 FT:** {stats['pct_over_25_ft']:.2f}% dos jogos")
        st.markdown(f"- **Under 2.5 FT:** {stats['pct_under_25_ft']:.2f}% dos jogos")
        st.markdown(f"- **BTTS FT:** {stats['pct_btts_ft']:.2f}% dos jogos")

        st.write("**Sequências Atuais:**")
        st.markdown(f"- Vitórias: {stats['sequencia_vitorias']} jogo(s)")
        st.markdown(f"- Derrotas: {stats['sequencia_derrotas']} jogo(s)")
        st.markdown(f"- Empates: {stats['sequencia_empates']} jogo(s)")
        st.markdown(f"- BTTS FT: {stats['sequencia_btts']} jogo(s) seguidos")
        st.markdown(f"- Over 2.5 FT: {stats['sequencia_over_25_ft']} jogo(s) seguidos")

        st.write("**Gols Marcados HT vs FT:**")
        if stats['media_gols_marcados_ht'] > stats['media_gols_marcados_ft'] / 2:
            st.warning("Parece que marca mais gols no **Primeiro Tempo**.")
        else:
            st.warning("Parece que se destaca mais marcando gols no **Segundo Tempo**.")

    with col_p1_stats:
        display_individual_stats(player1, stats_p1_recent)

    with col_p2_stats:
        display_individual_stats(player2, stats_p2_recent)

    st.markdown("---")
    st.header("⚔️ Confrontos Diretos Recentes")

    filtered_df_p1_p2 = df_resultados[
        ((df_resultados["Mandante"] == player1_clean) & (df_resultados["Visitante"] == player2_clean)) |
        ((df_resultados["Mandante"] == player2_clean) & (df_resultados["Visitante"] == player1_clean))
        ].tail(num_games_h2h)

    if filtered_df_p1_p2.empty:
        st.info(
            f"Não foram encontrados jogos recentes entre **{player1}** e **{player2}** nos últimos **{num_games_h2h}** confrontos diretos.")
        return

    st.write(f"Últimos **{len(filtered_df_p1_p2)}** confrontos diretos:")
    st.dataframe(filtered_df_p1_p2[
                     ["Data", "Liga", "Mandante", "Visitante", "Mandante FT", "Visitante FT", "Mandante HT",
                      "Visitante HT"]], use_container_width=True)

    total_gols_ht_h2h = filtered_df_p1_p2["Total HT"].sum()
    total_gols_ft_h2h = filtered_df_p1_p2["Total FT"].sum()

    media_gols_ht_confronto = total_gols_ht_h2h / len(filtered_df_p1_p2) if len(filtered_df_p1_p2) > 0 else 0
    media_gols_ft_confronto = total_gols_ft_h2h / len(filtered_df_p1_p2) if len(filtered_df_p1_p2) > 0 else 0

    st.markdown("---")
    st.subheader("Média de Gols no Confronto Direto:")
    col_mg_ht, col_mg_ft = st.columns(2)
    col_mg_ht.metric("Média de Gols HT", f"{media_gols_ht_confronto:.2f}")
    col_mg_ft.metric("Média de Gols FT", f"{media_gols_ft_confronto:.2f}")

    st.markdown("---")
    st.header("🎯 Dicas de Apostas para esta Partida:")

    best_line_ht = sugerir_over_ht(media_gols_ht_confronto)
    best_line_ft = sugerir_over_ft(media_gols_ft_confronto)

    st.markdown(f"**Sugestão HT:** **{best_line_ht}**")
    st.markdown(f"**Sugestão FT:** **{best_line_ft}**")

    if stats_p1_recent.get('pct_btts_ft', 0) >= 60 and stats_p2_recent.get('pct_btts_ft', 0) >= 60:
        btts_confronto_hits = ((filtered_df_p1_p2["Mandante FT"] > 0) & (filtered_df_p1_p2["Visitante FT"] > 0)).sum()
        btts_confronto_percent = (btts_confronto_hits / len(filtered_df_p1_p2)) * 100 if len(
            filtered_df_p1_p2) > 0 else 0
        if btts_confronto_percent >= 60:
            st.markdown(
                f"**Sugestão Adicional:** **Ambos Marcam (BTTS FT)** com {btts_confronto_percent:.2f}% de acerto nos confrontos diretos.")

    st.markdown("---")


def display_metrics_for_player(df_player_stats: pd.DataFrame, player_name: str, default_odds: float = 1.90):
    """Calcula e exibe métricas de ganhos/perdas para um jogador"""
    cleaned_player_name = re.sub(r'^[🥇🥈🥉]\s', '', player_name)
    player_data_row = df_player_stats[df_player_stats["Jogador"] == cleaned_player_name]

    if player_data_row.empty:
        st.info(f"Não há dados suficientes para calcular Ganhos & Perdas para {player_name}.")
        return

    player_data = player_data_row.iloc[0]
    jogos_total = player_data["jogos_total"]

    st.subheader(f"Estatísticas para {player_name} (Total de Jogos: {jogos_total})")

    if jogos_total == 0:
        st.info(f"Não há jogos registrados para {player_name}.")
        return

    market_data = [
        {
            "Mercado": "Vitória do Jogador",
            "Acertos": player_data["vitorias"],
            "Jogos": jogos_total
        },
        {
            "Mercado": "Jogos Over 1.5 HT",
            "Acertos": player_data["over_15_ht_hits"],
            "Jogos": jogos_total
        },
        {
            "Mercado": "Jogos Over 2.5 FT",
            "Acertos": player_data["over_25_ft_hits"],
            "Jogos": jogos_total
        },
        {
            "Mercado": "Jogos BTTS FT",
            "Acertos": player_data["btts_ft_hits"],
            "Jogos": jogos_total
        }
    ]

    results = []
    for market in market_data:
        hits = market["Acertos"]
        total_games = market["Jogos"]
        hit_rate = (hits / total_games) * 100 if total_games > 0 else 0
        profit_loss = (hits * (default_odds - 1)) - ((total_games - hits) * 1)

        results.append({
            "Mercado": market["Mercado"],
            "Jogos Analisados": total_games,
            "Acertos": hits,
            "Taxa de Acerto (%)": hit_rate,
            "Lucro/Prejuízo (Unidades)": profit_loss
        })

    df_results = pd.DataFrame(results)

    styled_df = df_results.style.map(
        lambda x: 'color: green; font-weight: bold;' if isinstance(x, (int, float)) and x > 0 else
        ('color: red; font-weight: bold;' if isinstance(x, (int, float)) and x < 0 else ''),
        subset=['Lucro/Prejuízo (Unidades)']
    ).format({
        'Taxa de Acerto (%)': "{:.2f}%",
        'Lucro/Prejuízo (Unidades)': "{:.2f}"
    })

    st.dataframe(styled_df, use_container_width=True)

    st.markdown("---")
    st.subheader("📊 Análise de Mercados para este Jogador:")

    df_top_tips = df_results[df_results["Mercado"].isin([
        "Vitória do Jogador",
        "Jogos Over 1.5 HT",
        "Jogos Over 2.5 FT",
        "Jogos BTTS FT"
    ])].copy()

    df_top_tips = df_top_tips.sort_values("Lucro/Prejuízo (Unidades)", ascending=False)

    for _, row in df_top_tips.iterrows():
        profit = row["Lucro/Prejuízo (Unidades)"]
        hit_rate = row["Taxa de Acerto (%)"]

        if profit > 0:
            st.success(
                f"✅ **{row['Mercado']}**: "
                f"Lucrativo com {hit_rate:.2f}% de acerto. "
                f"Lucro esperado: **{profit:.2f} unidades** "
                f"(em {row['Jogos Analisados']} jogos)"
            )
        else:
            st.error(
                f"❌ **{row['Mercado']}**: "
                f"Prejuízo com {hit_rate:.2f}% de acerto. "
                f"Perda esperada: **{profit:.2f} unidades** "
                f"(em {row['Jogos Analisados']} jogos)"
            )


def calculate_profit(suggestion, actual_score, odd=1.60):
    """Calcula o lucro/prejuízo de uma aposta"""
    if not suggestion or suggestion == "Sem Entrada":
        return 0.0
    try:
        if "Over" in suggestion:
            required = float(suggestion.split()[1])
            if actual_score > required:
                return odd - 1  # Ganho
            else:
                return -1  # Perda
    except:
        return 0.0
    return 0.0


# ==============================================
# PONTO DE ENTRADA PRINCIPAL
# ==============================================

def main():
    """Função principal que controla o fluxo do aplicativo"""
    # Configuração inicial da página
    st.set_page_config(page_title="FIFAlgorithm", layout="wide")

    # Inicializa o sistema de atualização automática
    if 'last_update_time' not in st.session_state:
        st.session_state.last_update_time = time.time()

    # Verifica se é hora de atualizar
    if time.time() - st.session_state.last_update_time > UPDATE_INTERVAL:
        st.session_state.last_update_time = time.time()
        st.session_state.force_update = True
        st.rerun()

    # Inicializa a sessão como autenticada diretamente
    st.session_state.update({
        "authenticated": True,
        "current_tab": "⚡️ Ao Vivo"
    })

    # Executa o aplicativo principal
    fifalgorithm_app()


if __name__ == "__main__":
    main()