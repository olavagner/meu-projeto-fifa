from __future__ import annotations
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
import re
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import logging
from typing import Optional
import time
from collections import defaultdict
import pytz

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
URL_AO_VIVO = "https://www.aceodds.com/pt/bet365-transmissao-ao-vivo.html"
URL_RESULTADOS = "https://www.fifastats.net/resultados"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
}
COMPETICOES_PERMITIDAS = {
    "E-soccer - H2H GG League - 8 minutos de jogo",
    "Esoccer Battle Volta - 6 Minutos de Jogo",
    "E-soccer - GT Leagues - 12 mins de jogo",
    "E-soccer - Battle - 8 minutos de jogo",
}

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


def sugerir_over_ft(media_gols_ft: float) -> str:
    """Retorna a sugestão para Over FT com base na média de gols FT."""
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


# Utilitários de Rede
def requisicao_segura(url: str, timeout: int = 15) -> Optional[requests.Response]:
    """Realiza uma requisição HTTP segura."""
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
    """Extrai dados de tabelas HTML de uma URL."""
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


# Processamento de Resultados Históricos
@st.cache_data(show_spinner=False, ttl=300)
def buscar_resultados() -> pd.DataFrame:
    """Busca e processa os resultados históricos das partidas."""
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


# Funções de Estatísticas
def calcular_estatisticas_jogador(df: pd.DataFrame, jogador: str, liga: str) -> dict:
    """Calcula estatísticas de um jogador em uma liga específica."""
    zeros = {
        "jogos_total": 0, "gols_marcados": 0, "gols_sofridos": 0,
        "gols_marcados_ht": 0, "gols_sofridos_ht": 0,
        "over_05_ht_hits": 0, "over_15_ht_hits": 0, "over_25_ht_hits": 0, "btts_ht_hits": 0,
        "over_05_ft_hits": 0, "over_15_ft_hits": 0, "over_25_ft_hits": 0, "over_35_ft_hits": 0,
        "over_45_ft_hits": 0, "over_55_ft_hits": 0, "over_65_ft_hits": 0, "btts_ft_hits": 0
    }
    if df.empty:
        return zeros.copy()

    # Filtra por jogador e liga específica
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
    """
    Calcula estatísticas consolidadas para todos os jogadores no DataFrame de resultados,
    considerando tanto quando jogam como mandante quanto como visitante.
    """
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

    # Itera sobre cada linha do DataFrame de resultados
    for _, row in df_resultados.iterrows():
        mandante = row["Mandante"]
        visitante = row["Visitante"]
        liga = row["Liga"]

        # Adiciona a liga ao conjunto de ligas atuantes para ambos os jogadores
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

        if row["Visitante FT"] == 0:  # Clean sheet para o mandante
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

        if row["Mandante FT"] == 0:  # Clean sheet para o visitante
            jogador_stats[visitante]["clean_sheets"] += 1

        # Contagem de Overs e BTTS (aplicável ao jogo, então ambos os jogadores na partida recebem o "hit")
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
        else:  # Para Under 2.5 FT (total_ft <= 2)
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


# --- Nova função para buscar e analisar os últimos N jogos de um jogador ---
def get_recent_player_stats(df_resultados: pd.DataFrame, player_name: str, num_games: int) -> dict:
    """
    Calcula estatísticas para um jogador nas suas últimas N partidas,
    independentemente do adversário.
    """
    player_games = df_resultados[
        (df_resultados["Mandante"] == player_name) | (df_resultados["Visitante"] == player_name)
        ].tail(num_games).copy()

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

        # Cálculo de sequências (simplificado: apenas a sequência atual)
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


# Funções de Formatação e Ranking
def cor_icon(h_m, t_m, h_v, t_v) -> str:
    """Retorna um ícone de cor com base nos percentuais de acerto."""
    pct_m = h_m / t_m if t_m else 0
    pct_v = h_v / t_v if t_v else 0
    if pct_m >= 0.70 and pct_v >= 0.70:
        return "🟢"
    if pct_m >= 0.60 and pct_v >= 0.60:
        return "🟡"
    return "🔴"


def format_stats(h_m, t_m, h_v, t_v) -> str:
    """Formata estatísticas com ícones de cor."""
    icon = cor_icon(h_m, t_m, h_v, t_v)
    return f"{icon} {h_m}/{t_m}\n{h_v}/{t_v}"


def format_gols_ht_com_icone_para_display(gols_ht_media: float) -> str:
    """Formata a média de gols HT com ícone de cor."""
    if gols_ht_media >= 2.75:
        return f"🟢 {gols_ht_media:.2f}"
    elif 2.62 <= gols_ht_media <= 2.74:
        return f"🟡 {gols_ht_media:.2f}"
    return f"⚪ {gols_ht_media:.2f}"


def sugerir_over_ht(media_gols_ht: float) -> str:
    """Sugere um mercado Over HT com base na média de gols HT."""
    if media_gols_ht >= 2.75:
        return "Over 2.5 HT"
    elif media_gols_ht >= 2.20:
        return "Over 1.5 HT"
    elif media_gols_ht >= 1.70:
        return "Over 0.5 HT"
    else:
        return "Sem Entrada"


def gerar_ranking(
        df_stats_base: pd.DataFrame,
        metrica_principal: str,
        colunas_exibicao: list[str],
        nomes_para_exibicao: Optional[dict[str, str]] = None,
        ascendente: bool = False,
        min_jogos: int = 10,
        top_n: int = 20
) -> pd.DataFrame:
    """
    Gera um ranking de jogadores com base em uma métrica principal, aplicando filtros,
    ordenação e adicionando medalhas.
    """
    df_ranking = df_stats_base[df_stats_base["jogos_total"] >= min_jogos].copy()
    if df_ranking.empty:
        dummy_data = {"Jogador": "N/A"}
        for col in colunas_exibicao:
            if col != "Jogador":
                dummy_data[col] = "N/A"
        return pd.DataFrame([dummy_data])

    # Ordena pela métrica principal. Para casos de "piores", 'ascendente' deve ser True.
    df_ranking = df_ranking.sort_values(by=metrica_principal, ascending=ascendente).head(top_n)

    # Adiciona as medalhas
    medalhas = {0: "🥇", 1: "🥈", 2: "🥉"}
    df_ranking = df_ranking.reset_index(drop=True)
    df_ranking["Jogador"] = df_ranking.apply(
        lambda row: f"{medalhas.get(row.name)} {row['Jogador']}"
        if row.name in medalhas else row["Jogador"], axis=1
    )

    # Seleciona as colunas originais para exibição
    df_final = df_ranking[colunas_exibicao].copy()

    # Renomeia as colunas para exibição, se um mapeamento for fornecido
    if nomes_para_exibicao:
        df_final = df_final.rename(columns=nomes_para_exibicao)

    # Formata percentuais para 2 casas decimais e adiciona '%'
    for col in df_final.columns:
        original_col_name = col
        if nomes_para_exibicao:
            for original, displayed in nomes_para_exibicao.items():
                if displayed == col:
                    original_col_name = original
                    break

        if "(%)" in original_col_name and pd.api.types.is_numeric_dtype(df_final[col]):
            df_final[col] = df_final[col].apply(lambda x: f"{x:.2f}%")
        elif "Média" in original_col_name and pd.api.types.is_numeric_dtype(df_final[col]):
            df_final[col] = df_final[col].apply(lambda x: f"{x:.2f}")
        elif "Saldo" in original_col_name and pd.api.types.is_numeric_dtype(df_final[col]):
            df_final[col] = df_final[col].apply(lambda x: f"{x:+.0f}")

    return df_final


# Processamento de Dados Ao Vivo
@st.cache_data(show_spinner=False, ttl=300)
def carregar_dados_ao_vivo(df_resultados: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carrega dados ao vivo, calcula as médias de gols e retorna:
    1. Um DataFrame 'limpo' com 'Gols HT' e 'Gols FT' como floats (para cálculos).
    2. Um DataFrame 'formatado' para exibição na aba 'Ao Vivo' (com ícones).
    """
    linhas = extrair_dados_pagina(URL_AO_VIVO)
    if not linhas:
        return pd.DataFrame(), pd.DataFrame()

    try:
        df = pd.DataFrame(linhas)

        # Ensure df has enough columns before attempting to access them
        if df.empty or df.shape[1] < 4:
            return pd.DataFrame(), pd.DataFrame()

        # Assuming competition name is in column index 3 (0-indexed)
        # Drop column 1 as it's not used (Hora, ?, Confronto, Liga)
        df = df[df.iloc[:, 3].isin(COMPETICOES_PERMITIDAS)].reset_index(drop=True)
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        df = df.drop(columns=[1])  # Drop the second column (index 1)
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

            # GP e GC são agora as médias Gols Pró e Gols Contra do CONFRONTO
            # GP = Média Gols Marcados Mandante + Média Gols Sofridos Visitante / 2
            # GC = Média Gols Marcados Visitante + Média Gols Sofridos Mandante / 2
            gp_calc = (avg_m_gf_ft + avg_v_ga_ft) / 2 if (jm and jv) else 0
            gc_calc = (avg_v_gf_ft + avg_m_ga_ft) / 2 if (jm and jv) else 0

            sugestao_ht = sugerir_over_ht(gols_ht_media_confronto)
            sugestao_ft = sugerir_over_ft(gols_ft_media_confronto)

            # --- Nova lógica para "Over Mandante" e "Over Visitante" ---
            def get_over_text(player_name: str, avg_goals: float) -> str:
                if 2.30 <= avg_goals <= 3.39:
                    return f"{player_name}  1.5 Gols"
                elif 3.40 <= avg_goals <= 4.50:
                    return f"{player_name}  2.5 Gols"
                return "Instável"  # Or an empty string if you prefer no output for other ranges

            over_mandante_text = get_over_text(m, gp_calc)
            over_visitante_text = get_over_text(v, gc_calc)
            # --- Fim da nova lógica ---

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
                    "Over Mandante": over_mandante_text,  # Adicionado
                    "Over Visitante": over_visitante_text,  # Adicionado
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
            "Over Mandante", "Over Visitante",  # Adicionadas ao display
            "Sugestão HT", "Sugestão FT"
        ]

        return df_clean, df_display[colunas_ao_vivo_solicitadas]

    except Exception as e:
        logger.error(f"Erro ao carregar dados ao vivo: {e}")
        st.error(f"❌ Erro ao carregar e processar dados ao vivo.")
        return pd.DataFrame(), pd.DataFrame()


# Lógica do Radar FIFA
@st.cache_data(show_spinner=False, ttl=300)
def calcular_radar_fifa(df_live_clean: pd.DataFrame) -> pd.DataFrame:
    """Calcula as porcentagens de Over e BTTS para o Radar FIFA."""
    if df_live_clean.empty:
        return pd.DataFrame()

    ligas_unicas = df_live_clean["Liga"].unique()
    resultados_radar = []

    for liga in ligas_unicas:
        jogos_da_liga = df_live_clean[df_live_clean["Liga"] == liga].head(10)
        total_jogos_analisados = len(jogos_da_liga)

        if total_jogos_analisados == 0:
            continue

        contadores_ht = {k: 0 for k in CRITERIOS_HT.keys()}
        contadores_ft = {k: 0 for k in CRITERIOS_FT.keys()}

        for _, jogo_ao_vivo in jogos_da_liga.iterrows():
            media_gols_ht_jogo = jogo_ao_vivo["Gols HT"]
            media_gols_ft_jogo = jogo_ao_vivo["Gols FT"]

            if pd.isna(media_gols_ht_jogo): media_gols_ht_jogo = 0.0
            if pd.isna(media_gols_ft_jogo): media_gols_ft_jogo = 0.0

            for criterio, valores in CRITERIOS_HT.items():
                if media_gols_ht_jogo >= valores["min"]:
                    contadores_ht[criterio] += 1

            for criterio, contagem_info in CRITERIOS_FT.items():
                if media_gols_ft_jogo >= contagem_info["min"]:
                    contadores_ft[criterio] += 1

        linha_liga = {"Liga": liga}
        for criterio, contagem in contadores_ht.items():
            percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
            linha_liga[f"{criterio}"] = f"{int(percentual)}%"

        for criterio, contagem in contadores_ft.items():
            percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
            linha_liga[f"{criterio}"] = f"{int(percentual)}%"

        resultados_radar.append(linha_liga)

    colunas_radar_ordenadas = ["Liga"] + list(CRITERIOS_HT.keys()) + list(CRITERIOS_FT.keys())

    df_radar = pd.DataFrame(resultados_radar)

    for col in colunas_radar_ordenadas:
        if col not in df_radar.columns:
            df_radar[col] = "0%"

    df_radar = df_radar[colunas_radar_ordenadas]

    return df_radar


# Função de Carga de Dados Essenciais
@st.cache_data(show_spinner=False, ttl=300)
def carregar_todos_os_dados_essenciais(flag: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carrega todos os DataFrames necessários para o dashboard."""
    df_resultados = buscar_resultados()
    df_live_clean, df_live_display = carregar_dados_ao_vivo(df_resultados)
    return df_resultados, df_live_clean, df_live_display


# Componentes Visuais do Streamlit
def exibir_estatisticas_partidas(df: pd.DataFrame, titulo: str) -> None:
    """Exibe um cabeçalho de estatísticas e um DataFrame de partidas."""
    if df.empty:
        st.info(f"🔍 Nenhum dado encontrado para {titulo.lower()}.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Total de Partidas", len(df))

    if "Liga" in df.columns:
        uniq = df["Liga"].nunique()
        col2.metric("🏆 Ligas Diferentes", uniq)
        if uniq > 1:
            # Pega a liga com mais ocorrências
            liga_mais_ativa = df["Liga"].mode().iloc[0] if not df["Liga"].mode().empty else "N/A"
            col3.metric("🥇 Liga Mais Ativa", liga_mais_ativa)

            # Conta o máximo de partidas na liga mais ativa
            max_partidas_liga = df["Liga"].value_counts().max() if not df["Liga"].value_counts().empty else 0
            col4.metric("📈 Máx. Partidas/Liga", max_partidas_liga)

    st.dataframe(df, use_container_width=True, height=430)


def get_color_for_percentage(percentage_str: str) -> str:
    """
    Retorna uma string CSS para aplicar cor de fundo baseada no valor percentual.
    Corrigido para retornar a propriedade CSS completa.
    """
    try:
        # Remove o '%' e converte para int. Se não for numérico, assume 0.
        percentage = int(percentage_str.replace('%', ''))
    except ValueError:
        percentage = 0  # Default to 0 for non-numeric values or "N/A"

    if percentage >= 80:
        return "background-color: #28a745"  # Green
    elif percentage >= 60:
        return "background-color: #ffc107"  # Yellow
    else:
        return "background-color: #dc3545"  # Red


def get_color_for_profit(value):
    """
    Retorna uma string CSS para colorir o lucro/prejuízo.
    """
    try:
        num_value = float(value)
        if num_value > 0:
            return 'color: green; font-weight: bold;'  # Positivo
        elif num_value < 0:
            return 'color: red; font-weight: bold;'  # Negativo
        else:
            return 'color: orange; font-weight: bold;'  # Neutro (ou pode ser 'color: black' se preferir)
    except ValueError:
        return ''  # Sem estilo para valores não numéricos (ex: N/A)


def display_metrics_for_player(df_player_stats: pd.DataFrame, player_name: str, default_odds: float = 1.90):
    """
    Calculates and displays 'Taxa de Acerto (%)' and 'Lucro/Prejuizo (Unidades)'
    para os mercados específicos: Vitória, Over 1.5 HT, Over 2.5 FT e BTTS FT.
    """
    # Limpa o nome do jogador (remove emojis de medalha se houver)
    cleaned_player_name = re.sub(r'^[🥇🥈🥉]\s', '', player_name)

    # Filtra os dados do jogador
    player_data_row = df_player_stats[df_player_stats["Jogador"] == cleaned_player_name]

    if player_data_row.empty:
        st.info(f"Não há dados suficientes para calcular Ganhos & Perdas para {player_name}.")
        return

    player_data = player_data_row.iloc[0]  # Pega a primeira linha correspondente
    jogos_total = player_data["jogos_total"]

    # Mostra o total de jogos do jogador
    st.subheader(f"Estatísticas para {player_name} (Total de Jogos: {jogos_total})")

    if jogos_total == 0:
        st.info(f"Não há jogos registrados para {player_name}.")
        return

    # Define os mercados que queremos analisar
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

    # Calcula taxa de acerto e lucro/prejuízo para cada mercado
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

    # Aplica formatação condicional
    styled_df = df_results.style.applymap(
        lambda x: 'color: green; font-weight: bold;' if isinstance(x, (int, float)) and x > 0 else
        ('color: red; font-weight: bold;' if isinstance(x, (int, float)) and x < 0 else ''),
        subset=['Lucro/Prejuízo (Unidades)']
    ).format({
        'Taxa de Acerto (%)': "{:.2f}%",
        'Lucro/Prejuízo (Unidades)': "{:.2f}"
    })

    # Exibe a tabela formatada
    st.dataframe(styled_df, use_container_width=True)

    # --- Top 3 Dicas de Aposta ---
    st.markdown("---")
    st.subheader("📊 Análise de Mercados para este Jogador:")

    # Filtra apenas os mercados que queremos considerar para as dicas
    df_top_tips = df_results[df_results["Mercado"].isin([
        "Vitória do Jogador",
        "Jogos Over 1.5 HT",
        "Jogos Over 2.5 FT",
        "Jogos BTTS FT"
    ])].copy()

    # Ordena por lucro potencial (do maior para o menor)
    df_top_tips = df_top_tips.sort_values("Lucro/Prejuízo (Unidades)", ascending=False)

    # Exibe análise para cada mercado
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


def perform_manual_analysis(df_resultados: pd.DataFrame, player1: str, player2: str, num_games_h2h: int,
                            num_games_individual: int):
    st.subheader(f"Análise Manual para **{player1}** vs **{player2}**")

    if df_resultados.empty:
        st.warning("⚠️ Não há dados de resultados históricos disponíveis para análise.")
        return

    # Limpa os nomes dos jogadores para buscar nas estatísticas (remover medalhas se presentes)
    player1_clean = re.sub(r'^[🥇🥈🥉]\s', '', player1)
    player2_clean = re.sub(r'^[🥇🥈🥉]\s', '', player2)

    # --- Estatísticas Individuais Recentes (Últimas N partidas) ---
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
        if stats['media_gols_marcados_ht'] > stats[
            'media_gols_marcados_ft'] / 2:  # heuristic: if HT goals are more than half of FT goals
            st.warning("Parece que marca mais gols no **Primeiro Tempo**.")
        else:
            st.warning("Parece que se destaca mais marcando gols no **Segundo Tempo**.")

    with col_p1_stats:
        display_individual_stats(player1, stats_p1_recent)

    with col_p2_stats:
        display_individual_stats(player2, stats_p2_recent)

    # --- Confrontos Diretos Recentes ---
    st.markdown("---")
    st.header("⚔️ Confrontos Diretos Recentes")

    filtered_df_p1_p2 = df_resultados[
        ((df_resultados["Mandante"] == player1_clean) & (df_resultados["Visitante"] == player2_clean)) |
        ((df_resultados["Mandante"] == player2_clean) & (df_resultados["Visitante"] == player1_clean))
        ].tail(num_games_h2h)  # Pega os 'num_games_h2h' mais recentes

    if filtered_df_p1_p2.empty:
        st.info(
            f"Não foram encontrados jogos recentes entre **{player1}** e **{player2}** nos últimos **{num_games_h2h}** confrontos diretos.")
        return

    st.write(f"Últimos **{len(filtered_df_p1_p2)}** confrontos diretos:")
    st.dataframe(filtered_df_p1_p2[
                     ["Data", "Liga", "Mandante", "Visitante", "Mandante FT", "Visitante FT", "Mandante HT",
                      "Visitante HT"]], use_container_width=True)

    # Calcular estatísticas médias para o confronto direto
    total_gols_ht_h2h = filtered_df_p1_p2["Total HT"].sum()
    total_gols_ft_h2h = filtered_df_p1_p2["Total FT"].sum()

    media_gols_ht_confronto = total_gols_ht_h2h / len(filtered_df_p1_p2) if len(filtered_df_p1_p2) > 0 else 0
    media_gols_ft_confronto = total_gols_ft_h2h / len(filtered_df_p1_p2) if len(filtered_df_p1_p2) > 0 else 0

    st.markdown("---")
    st.subheader("Média de Gols no Confronto Direto:")
    col_mg_ht, col_mg_ft = st.columns(2)
    col_mg_ht.metric("Média de Gols HT", f"{media_gols_ht_confronto:.2f}")
    col_mg_ft.metric("Média de Gols FT", f"{media_gols_ft_confronto:.2f}")

    # --- Dicas de Apostas (Melhores Linhas de Over) ---
    st.markdown("---")
    st.header("🎯 Dicas de Apostas para esta Partida:")

    def get_best_over_line(media_gols: float, period: str) -> str:
        if period == "HT":
            if media_gols >= 2.75:
                return "Over 2.5 HT"
            elif media_gols >= 2.20:
                return "Over 1.5 HT"
            elif media_gols >= 1.70:
                return "Over 0.5 HT"
            else:
                return "Sem entrada Over HT clara"
        elif period == "FT":
            if media_gols >= 6.70:
                return "Over 5.5 FT"
            elif media_gols >= 5.70:
                return "Over 4.5 FT"
            elif media_gols >= 4.50:
                return "Over 3.5 FT"
            elif media_gols >= 3.45:
                return "Over 2.5 FT"
            elif media_gols >= 2.40:
                return "Over 1.5 FT"
            elif media_gols >= 2.00:
                return "Over 0.5 FT"
            else:
                return "Sem entrada Over FT clara"
        return "N/A"

    best_line_ht = get_best_over_line(media_gols_ht_confronto, "HT")
    best_line_ft = get_best_over_line(media_gols_ft_confronto, "FT")

    st.markdown(f"**Sugestão HT:** **{best_line_ht}**")
    st.markdown(f"**Sugestão FT:** **{best_line_ft}**")

    # Adicionar BTTS FT se a taxa for alta para ambos e no confronto
    if stats_p1_recent.get('pct_btts_ft', 0) >= 60 and stats_p2_recent.get('pct_btts_ft', 0) >= 60:
        btts_confronto_hits = ((filtered_df_p1_p2["Mandante FT"] > 0) & (filtered_df_p1_p2["Visitante FT"] > 0)).sum()
        btts_confronto_percent = (btts_confronto_hits / len(filtered_df_p1_p2)) * 100 if len(
            filtered_df_p1_p2) > 0 else 0
        if btts_confronto_percent >= 60:
            st.markdown(
                f"**Sugestão Adicional:** **Ambos Marcam (BTTS FT)** com {btts_confronto_percent:.2f}% de acerto nos confrontos diretos.")

    st.markdown("---")


def generate_ai_prediction(df_resultados: pd.DataFrame) -> None:
    """Gera ranking baseado nas ÚLTIMAS 20 PARTIDAS de cada liga."""
    st.header("🤖 Previsão IA (Liga)")

    if df_resultados.empty:
        st.warning("Dados insuficientes para análise.")
        return

    # Configurações
    config = {
        "jogos_por_liga": 20,  # Analisa apenas os 20 jogos mais recentes de cada liga
        "min_sequencia": 3,
        "min_sucesso": 70,
        "ligas": ["Battle 8 Min", "Volta 6 Min", "H2H 8 Min", "GT 12 Min"]
    }

    # Coleta os últimos 20 jogos de CADA LIGA
    dfs_ligas = []
    for liga in config["ligas"]:
        df_liga = df_resultados[df_resultados["Liga"] == liga].tail(config["jogos_por_liga"])
        dfs_ligas.append(df_liga)

    df_recente = pd.concat(dfs_ligas) if dfs_ligas else pd.DataFrame()

    if df_recente.empty:
        st.info("Nenhum dado recente encontrado.")
        return

    # Análise por jogador (agora com dados já filtrados)
    sequences_data = []
    all_players = pd.concat([df_recente["Mandante"], df_recente["Visitante"]]).unique()

    for player in all_players:
        player_matches = df_recente[
            (df_recente["Mandante"] == player) |
            (df_recente["Visitante"] == player)
            ].sort_values("Data", ascending=False)  # Jogos mais recentes primeiro

        if len(player_matches) < config["min_sequencia"]:
            continue

        # Mercados analisados (com pesos para cálculo de confiança)
        markets = {
            "🎯 1.5+ Gols": {
                "condition": lambda r, p: (r["Mandante FT"] if r["Mandante"] == p else r["Visitante FT"]) >= 1.5,
                "weight": 1.2
            },
            "🎯 2.5+ Gols": {
                "condition": lambda r, p: (r["Mandante FT"] if r["Mandante"] == p else r["Visitante FT"]) >= 2.5,
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
                    "Último Jogo": player_matches.iloc[0]["Data"]  # Data do jogo mais recente
                })

    # Exibição dos resultados
    if sequences_data:
        df = pd.DataFrame(sequences_data)

        # Filtra sequências muito antigas (opcional)
        # df = df[df["Último Jogo"] >= (datetime.now() - timedelta(days=30))]

        # Ordenação por score e data recente
        df_sorted = df.sort_values(["Score", "Último Jogo"], ascending=[False, False])

        # Tabela principal
        st.markdown("### 🏆 Melhores Sequências")
        st.dataframe(
            df_sorted[["Jogador", "Mercado", "Sequência", "Taxa", "Liga", "Jogos Analisados"]],
            hide_index=True,
            use_container_width=True,
            height=500
        )

        # Destaques
        st.markdown("### 💎 Dicas Estratégicas")
        for _, row in df_sorted.head(5).iterrows():
            st.success(
                f"**{row['Jogador']}** ({row['Liga']}): "
                f"{row['Sequência']} jogos consecutivos com {row['Mercado']} "
                f"({row['Taxa']} acerto) - **Score: {row['Score']:.1f}/10**"
            )
    else:
        st.info("Nenhuma sequência relevante encontrada nos últimos 20 jogos de cada liga.")

def generate_smart_alerts(df_resultados: pd.DataFrame, df_stats_all_players: pd.DataFrame) -> None:
    """Gera alertas inteligentes sobre tendências recentes."""
    st.header("🔔 Alertas Inteligentes")
    st.write("Análise de jogadores e ligas com desempenhos relevantes")

    if df_resultados.empty or df_stats_all_players.empty:
        st.warning("Dados insuficientes para gerar alertas.")
        return

    # Configurações básicas
    ligas_principais = ["Battle 8 Min", "Volta 6 Min", "H2H 8 Min", "GT 12 Min"]
    min_jogos = 10

    st.subheader("🌟 Destaques Recentes")

    # Aqui você pode adicionar a lógica específica de alertas que deseja
    st.info("Funcionalidade em desenvolvimento. Em breve terá análises automáticas de tendências.")

    # Exemplo básico de alertas
    try:
        # Verifica jogadores com alta performance
        df_top = df_stats_all_players[
            (df_stats_all_players["jogos_total"] >= min_jogos)
        ].sort_values("Win Rate (%)", ascending=False).head(3)

        if not df_top.empty:
            st.markdown("### 🏆 Top Jogadores (Win Rate)")
            for _, row in df_top.iterrows():
                st.success(
                    f"**{row['Jogador']}**: {row['Win Rate (%)']:.1f}% "
                    f"vitórias em {row['jogos_total']} jogos"
                )
    except Exception as e:
        st.error(f"Erro ao gerar alertas: {str(e)}")

def app():
    st.set_page_config(
        page_title="Dashboard FIFA Esoccer",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🎮 Dashboard FIFA Esoccer")

    brasil_timezone = pytz.timezone("America/Sao_Paulo")
    current_time_br = datetime.now(brasil_timezone).strftime("%H:%M:%S")

    st.markdown(f"**Última atualização:** {current_time_br}")

    # Auto-refresh every 60 seconds
    st_autorefresh(interval=60 * 1000, key="data_refresh")

    # Flag to control data reload
    if "reload_flag" not in st.session_state:
        st.session_state.reload_flag = 0

    df_resultados, df_live_clean, df_live_display = carregar_todos_os_dados_essenciais(st.session_state.reload_flag)
    df_stats_all_players = calcular_estatisticas_todos_jogadores(
        df_resultados)  # Carrega as estatísticas de todos os jogadores aqui

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📊 Ao Vivo", "📈 Rankings", "💰 Ganhos & Perdas", "🔍 Análise Manual", "🔔 Alertas Inteligentes", "🤖 Previsão IA"])
    with tab1:
        st.header("Jogos Ao Vivo")
        exibir_estatisticas_partidas(df_live_display, "Jogos ao Vivo")
        st.markdown("---")
        st.header("Radar FIFA")
        df_radar = calcular_radar_fifa(df_live_clean)
        if not df_radar.empty:
            st.dataframe(
                df_radar.style.map(get_color_for_percentage, subset=pd.IndexSlice[:, df_radar.columns.drop('Liga')]),
                use_container_width=True
            )
        else:
            st.info("Nenhum dado para o Radar FIFA.")

    with tab2:
        st.header("Rankings de Jogadores")
        if not df_stats_all_players.empty:
            col_rank1, col_rank2, col_rank3 = st.columns(3)

            with col_rank1:
                st.subheader("Melhores Saldo de Gols")
                ranking_saldo_gols = gerar_ranking(
                    df_stats_all_players,
                    "Saldo de Gols",
                    ["Jogador", "jogos_total", "Saldo de Gols"],
                    {"jogos_total": "Jogos"},
                    ascendente=False
                )
                st.dataframe(ranking_saldo_gols, use_container_width=True)

            with col_rank2:
                st.subheader("Melhores Win Rate")
                ranking_win_rate = gerar_ranking(
                    df_stats_all_players,
                    "Win Rate (%)",
                    ["Jogador", "jogos_total", "Win Rate (%)", "Derrota Rate (%)"],
                    {"jogos_total": "Jogos"},
                    ascendente=False
                )
                st.dataframe(ranking_win_rate, use_container_width=True)

            with col_rank3:
                st.subheader("Piores Clean Sheets")
                ranking_clean_sheets = gerar_ranking(
                    df_stats_all_players,
                    "Clean Sheets (%)",
                    ["Jogador", "jogos_total", "Clean Sheets (%)"],
                    {"jogos_total": "Jogos"},
                    ascendente=True
                )
                st.dataframe(ranking_clean_sheets, use_container_width=True)

            st.markdown("---")
            st.subheader("Rankings de Overs e BTTS")

            col_over_ht, col_over_ft, col_btts_ft = st.columns(3)

            with col_over_ht:
                st.subheader("Mais Overs 2.5 HT")
                ranking_over_ht = gerar_ranking(
                    df_stats_all_players,
                    "Over 2.5 HT (%)",
                    ["Jogador", "jogos_total", "Over 2.5 HT (%)"],
                    {"jogos_total": "Jogos"},
                    ascendente=False
                )
                st.dataframe(ranking_over_ht, use_container_width=True)

            with col_over_ft:
                st.subheader("Mais Overs 3.5 FT")
                ranking_over_ft = gerar_ranking(
                    df_stats_all_players,
                    "Over 3.5 FT (%)",
                    ["Jogador", "jogos_total", "Over 3.5 FT (%)"],
                    {"jogos_total": "Jogos"},
                    ascendente=False
                )
                st.dataframe(ranking_over_ft, use_container_width=True)

            with col_btts_ft:
                st.subheader("Mais BTTS FT")
                ranking_btts_ft = gerar_ranking(
                    df_stats_all_players,
                    "BTTS FT (%)",
                    ["Jogador", "jogos_total", "BTTS FT (%)"],
                    {"jogos_total": "Jogos"},
                    ascendente=False
                )
                st.dataframe(ranking_btts_ft, use_container_width=True)

        else:
            st.info("Nenhum dado de jogador encontrado para rankings.")

    with tab3:
        st.header("💰 Ganhos & Perdas por Jogador")
        if not df_stats_all_players.empty:
            # Extrai nomes dos jogadores (remove emojis de medalha)
            player_names_for_selectbox = sorted([
                re.sub(r'^[🥇🥈🥉]\s', '', p)
                for p in df_stats_all_players["Jogador"].unique()
            ])

            selected_player = st.selectbox(
                "Selecione um Jogador para Análise:",
                [""] + player_names_for_selectbox
            )

            if selected_player:
                # Adiciona slider para definir as odds (opcional)
                default_odds = st.slider(
                    "Defina as odds médias para cálculo:",
                    min_value=1.50,
                    max_value=3.00,
                    value=1.90,
                    step=0.05
                )

                # Chama a função atualizada
                display_metrics_for_player(df_stats_all_players, selected_player, default_odds)
            else:
                st.info("Por favor, selecione um jogador para ver a análise.")
        else:
            st.info("Nenhum dado de jogador disponível para análise.")

    with tab4:
        st.header("🔍 Análise Manual de Confrontos e Desempenho Individual")
        st.write(
            "Insira os nomes dos jogadores para analisar seus confrontos diretos recentes e o desempenho individual nas últimas partidas.")

        # Certifique-se de que df_stats_all_players esteja carregado antes de usar
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
            max_value=10,  # Limite de 10 confrontos diretos
            value=10,
            key="num_games_h2h"
        )

        num_games_individual = st.number_input(
            "Número de últimos jogos individuais a analisar (máx. 20):",  # Ajustei o máximo
            min_value=1,
            max_value=20,  # Limite de 20 jogos individuais para desempenho recente
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

    with tab5:
        if not df_resultados.empty and not df_stats_all_players.empty:
            generate_smart_alerts(df_resultados, df_stats_all_players)
        else:
            st.warning("Carregando dados para os alertas inteligentes...")
    with tab6:
        generate_ai_prediction(df_resultados)


if __name__ == "__main__":
    app()