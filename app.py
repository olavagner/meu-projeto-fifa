# Vagner S.

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
        r.raise_for_status()  # Lança um HTTPError para respostas de erro (4xx ou 5xx)
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
        "over_05_ht": 0, "over_15_ht": 0, "over_25_ht": 0, "btts_ht": 0,
        "over_05_ft": 0, "over_15_ft": 0, "over_25_ft": 0, "over_35_ft": 0,
        "over_45_ft": 0, "over_55_ft": 0, "over_65_ft": 0, "btts_ft": 0
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
        s["over_05_ht"] += 1 if total_ht > 0 else 0
        s["over_15_ht"] += 1 if total_ht > 1 else 0
        s["over_25_ht"] += 1 if total_ht > 2 else 0
        s["btts_ht"] += 1 if (gf_ht > 0 and ga_ht > 0) else 0

        total_ft = jogo["Total FT"]
        s["over_05_ft"] += 1 if total_ft > 0 else 0
        s["over_15_ft"] += 1 if total_ft > 1 else 0
        s["over_25_ft"] += 1 if total_ft > 2 else 0
        s["over_35_ft"] += 1 if total_ft > 3 else 0
        s["over_45_ft"] += 1 if total_ft > 4 else 0
        s["over_55_ft"] += 1 if total_ft > 5 else 0
        s["over_65_ft"] += 1 if total_ft > 6 else 0
        s["btts_ft"] += 1 if (gf_ft > 0 and ga_ft > 0) else 0

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
        else: # Para Under 2.5 FT (total_ft <= 2)
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
    df_rankings_base["Derrota Rate (%)"] = (df_rankings_base["derrotas"] / df_rankings_base["jogos_total"] * 100).fillna(0)
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
    df_rankings_base["Under 2.5 FT (%)"] = (df_rankings_base["under_25_ft_hits"] / df_rankings_base["jogos_total"] * 100).fillna(0)

    # Converte o set de ligas para string para exibição
    df_rankings_base["Ligas Atuantes"] = df_rankings_base["ligas_atuantes"].apply(lambda x: ", ".join(sorted(list(x))))

    return df_rankings_base

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

        df = df.drop(columns=[1]) # Drop the second column (index 1)
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
                return "Instável" # Or an empty string if you prefer no output for other ranges

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
                    "Over Mandante": over_mandante_text, # Adicionado
                    "Over Visitante": over_visitante_text, # Adicionado
                    "0.5 HT": format_stats(sm["over_05_ht"], jm, sv["over_05_ht"], jv),
                    "1.5 HT": format_stats(sm["over_15_ht"], jm, sv["over_15_ht"], jv),
                    "2.5 HT": format_stats(sm["over_25_ht"], jm, sv["over_25_ht"], jv),
                    "BTTS HT": format_stats(sm["btts_ht"], jm, sv["btts_ht"], jv),
                    "BTTS FT": format_stats(sm["btts_ft"], jm, sv["btts_ft"], jv),
                    "0.5 FT": format_stats(sm["over_05_ft"], jm, sv["over_05_ft"], jv),
                    "1.5 FT": format_stats(sm["over_15_ft"], jm, sv["over_15_ft"], jv),
                    "2.5 FT": format_stats(sm["over_25_ft"], jm, sv["over_25_ft"], jv),
                    "3.5 FT": format_stats(sm["over_35_ft"], jm, sv["over_35_ft"], jv),
                    "4.5 FT": format_stats(sm["over_45_ft"], jm, sv["over_45_ft"], jv),
                    "5.5 FT": format_stats(sm["over_55_ft"], jm, sv["over_55_ft"], jv),
                    "6.5 FT": format_stats(sm["over_65_ft"], jm, sv["over_65_ft"], jv),
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
            "Over Mandante", "Over Visitante", # Adicionadas ao display
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
    """Retorna uma cor HTML baseada no valor percentual."""
    try:
        percentage = int(percentage_str.replace('%', ''))
        if percentage >= 80:
            return "#28a745"  # Green
        elif 68 <= percentage <= 79:
            return "#ffc107"  # Yellow (Amber)
        else:
            return "#dc3545"  # Red
    except ValueError:
        return "#6c757d"  # Grey for invalid percentage

def get_logo_path(league_name: str) -> str:
    """Retorna o URL do logotipo da liga."""
    logo_map = {
        "Battle 8 Min": "https://i.imgur.com/65W1s9k.png",  # Esports Battle
        "GT 12 Min": "https://i.imgur.com/65W1s9k.png",  # GT Leagues
        "Volta 6 Min": "https://i.imgur.com/65W1s9k.png",  # Volta Football
        "H2H 8 Min": "https://i.imgur.com/65W1s9k.png",  # Exemplo de URL para H2H 8 Min
    }
    return logo_map.get(league_name, "https://i.imgur.com/placeholder.png") # Retorna um placeholder se a liga não for encontrada


def exibir_radar_fifa(df_radar: pd.DataFrame) -> None:
    """Exibe a tabela do radar FIFA com porcentagens de Over e BTTS."""
    if df_radar.empty:
        st.info("🔍 Nenhum dado de radar encontrado.")
        return

    # Adicionar o logo na coluna da Liga
    df_radar_display = df_radar.copy()
    df_radar_display["Liga"] = df_radar_display["Liga"].apply(
        lambda x: f'<div style="display: flex; align-items: center;">'
                  f'<img src="{get_logo_path(x)}" width="20" style="margin-right: 5px;"> {x}'
                  f'</div>'
    )

    # Função para aplicar a cor aos percentuais
    def format_percentage_with_color(val):
        if isinstance(val, str) and '%' in val:
            color = get_color_for_percentage(val)
            return f'<span style="color:{color};"><b>{val}</b></span>'
        return val

    # Aplica a formatação de cor a todas as colunas de percentual
    for col in df_radar_display.columns:
        if col != "Liga":
            df_radar_display[col] = df_radar_display[col].apply(format_percentage_with_color)

    st.markdown(
        df_radar_display.to_html(escape=False, index=False),
        unsafe_allow_html=True
    )
    st.markdown(
        """
        <style>
        /* Estilos para o tema escuro */
        body {
            background-color: #0e1117; /* Fundo escuro */
            color: #fafafa; /* Cor do texto principal */
        }
        .stMarkdown {
            color: #fafafa; /* Garante que o Markdown tenha cor clara */
        }
        h1, h2, h3, h4, h5, h6 {
            color: #e0e0e0; /* Títulos um pouco mais claros para contraste */
        }
        /* Estilo da tabela do radar */
        .dataframe {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
            text-align: center;
            color: #e0e0e0; /* Cor do texto da tabela */
        }
        .dataframe th {
            background-color: #262626; /* Fundo do cabeçalho da tabela mais escuro */
            padding: 10px;
            border: 1px solid #333; /* Borda mais escura */
            color: #f0f0f0; /* Cor do texto do cabeçalho */
        }
        .dataframe td {
            padding: 8px;
            border: 1px solid #333; /* Borda mais escura */
            vertical-align: middle;
            background-color: #1a1a1a; /* Fundo das células da tabela */
        }
        .dataframe tr:nth-child(even) {
            background-color: #1a1a1a; /* Fundo de linhas pares */
        }
        .dataframe tr:nth-child(odd) {
            background-color: #212121; /* Fundo de linhas ímpares para contraste */
        }
        .dataframe tr:hover {
            background-color: #2c2c2c; /* Fundo ao passar o mouse */
        }
        .stMetric {
            background-color: #1a1a1a; /* Fundo dos cards de métricas */
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            color: #e0e0e0;
        }
        .stMetric > div > div > div:first-child {
            color: #bb86fc; /* Cor do título da métrica (roxa) */
            font-weight: bold;
        }
        .stMetric > div > div > div:nth-child(2) {
            color: #03dac6; /* Cor do valor da métrica (ciano) */
            font-size: 1.8em;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def exibir_rankings(df_stats_base: pd.DataFrame) -> None:
    """Exibe os rankings de jogadores."""
    if df_stats_base.empty:
        st.info("🔍 Nenhum dado de estatísticas de jogadores encontrado para gerar rankings.")
        return

    st.subheader("🏆 Melhores e Piores Jogadores (Geral)")

    # Aba para Melhores
    tab_melhores, tab_piores = st.tabs(["👍 Melhores", "👎 Piores"])

    with tab_melhores:
        st.write("---")
        st.markdown("##### Maiores Gols Marcados")
        ranking_maiores_gols_marcados = gerar_ranking(
            df_stats_base,
            metrica_principal="Gols Marcados Média",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Gols Marcados Média"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Gols Marcados Média": "Média Gols Marcados"
            },
            ascendente=False,
        )
        st.dataframe(ranking_maiores_gols_marcados, use_container_width=True)

        st.write("---")
        st.markdown("##### Maiores Win Rate")
        ranking_maiores_win_rate = gerar_ranking(
            df_stats_base,
            metrica_principal="Win Rate (%)",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Win Rate (%)"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Win Rate (%)": "Win Rate (%)"
            },
            ascendente=False,
        )
        st.dataframe(ranking_maiores_win_rate, use_container_width=True)

        st.write("---")
        st.markdown("##### Maiores Saldo de Gols")
        ranking_maiores_saldo_gols = gerar_ranking(
            df_stats_base,
            metrica_principal="Saldo de Gols",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Saldo de Gols"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Saldo de Gols": "Saldo de Gols"
            },
            ascendente=False,
        )
        st.dataframe(ranking_maiores_saldo_gols, use_container_width=True)

        st.write("---")
        st.markdown("##### Maiores Over 2.5 FT (%)")
        ranking_maiores_over25ft = gerar_ranking(
            df_stats_base,
            metrica_principal="Over 2.5 FT (%)",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Over 2.5 FT (%)"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Over 2.5 FT (%)": "Over 2.5 FT (%)"
            },
            ascendente=False,
        )
        st.dataframe(ranking_maiores_over25ft, use_container_width=True)

        st.write("---")
        st.markdown("##### Maiores BTTS FT (%)")
        ranking_maiores_btts_ft = gerar_ranking(
            df_stats_base,
            metrica_principal="BTTS FT (%)",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "BTTS FT (%)"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "BTTS FT (%)": "BTTS FT (%)"
            },
            ascendente=False,
        )
        st.dataframe(ranking_maiores_btts_ft, use_container_width=True)

    with tab_piores:
        st.write("---")
        st.markdown("##### Piores Gols Sofridos (Média)")
        ranking_piores_gols_sofridos = gerar_ranking(
            df_stats_base,
            metrica_principal="Gols Sofridos Média",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Gols Sofridos Média"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Gols Sofridos Média": "Média Gols Sofridos"
            },
            ascendente=False,
        )
        st.dataframe(ranking_piores_gols_sofridos, use_container_width=True)

        st.write("---")
        st.markdown("##### Piores Win Rate")
        ranking_piores_win_rate = gerar_ranking(
            df_stats_base,
            metrica_principal="Win Rate (%)",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Win Rate (%)"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Win Rate (%)": "Win Rate (%)"
            },
            ascendente=True, # Piores significa menor Win Rate
        )
        st.dataframe(ranking_piores_win_rate, use_container_width=True)

        st.write("---")
        st.markdown("##### Piores Saldo de Gols")
        ranking_piores_saldo_gols = gerar_ranking(
            df_stats_base,
            metrica_principal="Saldo de Gols",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Saldo de Gols"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Saldo de Gols": "Saldo de Gols"
            },
            ascendente=True, # Piores significa menor Saldo de Gols
        )
        st.dataframe(ranking_piores_saldo_gols, use_container_width=True)

        st.write("---")
        st.markdown("##### Piores Over 2.5 FT (%)")
        ranking_piores_over25ft = gerar_ranking(
            df_stats_base,
            metrica_principal="Over 2.5 FT (%)",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "Over 2.5 FT (%)"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "Over 2.5 FT (%)": "Over 2.5 FT (%)"
            },
            ascendente=True, # Piores significa menor Over 2.5 FT
        )
        st.dataframe(ranking_piores_over25ft, use_container_width=True)

        st.write("---")
        st.markdown("##### Piores BTTS FT (%)")
        ranking_piores_btts_ft = gerar_ranking(
            df_stats_base,
            metrica_principal="BTTS FT (%)",
            colunas_exibicao=["Jogador", "Ligas Atuantes", "jogos_total", "BTTS FT (%)"],
            nomes_para_exibicao={
                "jogos_total": "Total de Jogos",
                "BTTS FT (%)": "BTTS FT (%)"
            },
            ascendente=True, # Piores significa menor BTTS FT
        )
        st.dataframe(ranking_piores_btts_ft, use_container_width=True)


def exibir_sobre() -> None:
    """Exibe informações sobre o projeto."""
    st.subheader("🌟 Sobre")
    st.markdown(
        """
        Este aplicativo foi desenvolvido para fornecer **estatísticas e análises** de jogos FIFA,
        com foco nas ligas de E-soccer (H2H, GT Leagues, Battle e Volta).
        Ele busca dados de partidas ao vivo e históricas para ajudar na tomada de decisões.

        ### Funcionalidades Principais:
        - **Ao Vivo:** Acompanhe jogos em tempo real com sugestões de Over Players,HT e FT.
        - **Resultados:** Visualize um histórico detalhado das partidas do dia.
        - **Radar FIFA:** Analise a tendência de Overs gols nos mercados HT & FT das ligas em tempo real.
        - **Rankings:** Descubra os melhores e piores jogadores com base em diversas métricas.

        ### Desenvolvedor:
        - **Vagner Sembrani**

        ### Feedback e Sugestões:
        Sua opinião é muito importante! Se tiver sugestões ou encontrar algum problema, entre em contato.
        """
    )

# --- Configuração do Layout do Streamlit ---
st.set_page_config(
    page_title="FIFA Stats - Vagner S.",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injeção de CSS personalizado para o tema escuro
st.markdown(
    """
    <style>
    /* Estilos Gerais para o tema escuro */
    .stApp {
        background-color: #0e1117; /* Cor de fundo principal mais escura */
        color: #fafafa; /* Cor de texto padrão mais clara */
    }
    .st-emotion-cache-1r6dm7m { /* Sidebar background */
        background-color: #1a1a1a;
    }
    .st-emotion-cache-1r6dm7m .st-bw { /* Links na sidebar */
        color: #bb86fc; /* Cor de link para um toque mais moderno */
    }
    .st-emotion-cache-1r6dm7m .st-dq { /* Título na sidebar */
        color: #f0f0f0;
    }

    /* Estilo para as métricas (st.metric) - Mantido, mas pode ser mais genérico */
    .stMetric {
        background-color: #1a1a1a; /* Fundo dos cards de métricas */
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        color: #e0e0e0;
    }
    .stMetric > div > div > div:first-child {
        color: #bb86fc; /* Cor do título da métrica (roxa) */
        font-weight: bold;
    }
    .stMetric > div > div > div:nth-child(2) {
        color: #03dac6; /* Cor do valor da métrica (ciano) */
        font-size: 1.8em;
    }

    /* Estilo para o novo card de atualização (st.info customizado) */
    .custom-info-card {
        background-color: #1a1a1a; /* Fundo escuro do card */
        border-radius: 10px;
        padding: 15px 20px;
        margin-bottom: 20px; /* Espaço abaixo do card */
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3); /* Sombra mais destacada */
        display: flex;
        align-items: center;
        gap: 15px; /* Espaço entre ícone e texto */
        color: #e0e0e0; /* Cor do texto */
        font-size: 1.1em;
        font-weight: bold;
        border: 1px solid #333; /* Borda sutil */
    }
    .custom-info-card .icon {
        font-size: 2.2em; /* Tamanho maior para o ícone */
        color: #03dac6; /* Cor do ícone (ciano) */
        line-height: 1; /* Alinhamento vertical */
    }
    .custom-info-card .text {
        flex-grow: 1; /* Permite que o texto ocupe o espaço restante */
    }
    .custom-info-card .datetime {
        font-size: 1.2em;
        color: #bb86fc; /* Cor do timestamp (roxo) */
    }


    /* Estilo para os cabeçalhos de seção */
    h1, h2, h3, h4, h5, h6 {
        color: #e0e0e0; /* Cor dos títulos para melhor contraste */
    }

    /* Estilo para abas (tabs) */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        color: #bb86fc; /* Cor do texto das abas */
    }
    .stTabs [data-baseweb="tab-list"] button.st-emotion-cache-fnmr37 { /* Aba selecionada */
        background-color: #333333;
        color: #f0f0f0; /* Cor do texto da aba selecionada */
        border-bottom: 2px solid #03dac6; /* Borda inferior ciano */
    }
    .stTabs [data-baseweb="tab-list"] button {
        background-color: #212121; /* Fundo das abas não selecionadas */
        color: #bb86fc; /* Cor do texto das abas não selecionadas */
    }


    /* Estilos para a tabela do radar FIFA (já estava no código) */
    .dataframe {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9em;
        text-align: center;
        color: #e0e0e0;
    }
    .dataframe th {
        background-color: #262626;
        padding: 10px;
        border: 1px solid #333;
        color: #f0f0f0;
    }
    .dataframe td {
        padding: 8px;
        border: 1px solid #333;
        vertical-align: middle;
        background-color: #1a1a1a;
    }
    .dataframe tr:nth-child(even) {
        background-color: #1a1a1a;
    }
    .dataframe tr:nth-child(odd) {
        background-color: #212121;
    }
    .dataframe tr:hover {
        background-color: #2c2c2c;
    }

    /* Ajustes para o st.info padrão (caso ainda seja usado em outro lugar) */
    .stAlert p {
        color: #f0f0f0 !important; /* Garante que o texto do st.info seja claro */
    }
    .stAlert.info-alert {
        background-color: #2a2a2a; /* Fundo mais escuro para info */
        border-left: 5px solid #2196F3; /* Borda azul para info */
        color: #f0f0f0;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# Sidebar
with st.sidebar:
    st.image("https://i.imgur.com/neR5gSO.png", width=150) # Substitua pela sua imagem de logo
    st.title("  🎮 SIMULADOR FIFA")
    st.markdown("---")

    aba_selecionada = st.radio(
        "Menu",
        ["Ao Vivo", "Resultados", "Radar FIFA", "Rankings", "Sobre"],
        index=0,
        help="Selecione a seção que deseja visualizar.",
        key="main_navigation"
    )
    st.markdown("---")

    # st_autorefresh mantido para o cache TTL funcionar, sem o argumento display_spinner
    # O TTL (Time To Live) de 300 segundos (5 minutos) no @st.cache_data fará com que os dados sejam buscados
    # novamente a cada 5 minutos, garantindo que o "Última atualização" no topo da tela principal
    # seja atualizado e os dados também.
    st_autorefresh(interval=300 * 1000, key="data_refresh_hidden")


# --- Carregamento de Dados Principal ---
# Use um contador simples para forçar o recarregamento dos dados em cada refresh do autorefresh
# Isso garante que as funções @st.cache_data sejam invalidadas e os dados sejam buscados novamente.
if 'refresh_flag' not in st.session_state:
    st.session_state.refresh_flag = 0

df_resultados, df_live_clean, df_live_display = carregar_todos_os_dados_essenciais(st.session_state.refresh_flag)
df_stats_base = calcular_estatisticas_todos_jogadores(df_resultados)
df_radar = calcular_radar_fifa(df_live_clean)

# --- Renderização do Conteúdo Principal ---
st.header(f"Página: {aba_selecionada}")

# NOVO: Card de Última Atualização no topo da tela principal
tz = pytz.timezone('America/Sao_Paulo')
now = datetime.now(tz)
st.markdown(
    f"""
    <div class="custom-info-card">
        <span class="icon">⏰</span>
        <div class="text">
            Última atualização dos dados:
            <br>
            <span class="datetime">{now.strftime('%d/%m/%Y %H:%M:%S')}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

if aba_selecionada == "Ao Vivo":
    st.subheader("🔴 Jogos Ao Vivo")
    exibir_estatisticas_partidas(df_live_display, "Jogos Ao Vivo")
elif aba_selecionada == "Resultados":
    st.subheader("📜 Resultados Históricos")
    exibir_estatisticas_partidas(df_resultados, "Resultados Históricos")
elif aba_selecionada == "Radar FIFA":
    st.subheader("📊 Radar FIFA - Tendências por Liga")
    st.write("Análise da frequência de Linhas Over HT & FT de cada liga em tempo real.")
    st.markdown("---")
    st.markdown("---")
    exibir_radar_fifa(df_radar)
elif aba_selecionada == "Rankings":
    exibir_rankings(df_stats_base)
elif aba_selecionada == "Sobre":
    exibir_sobre()

# Incrementar a flag para o próximo refresh
st.session_state.refresh_flag += 1