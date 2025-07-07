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
            "Hora", "Liga", "Mandante", "Visitante", "GP", "GC", "Sugestão HT", "Sugestão FT"
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
        "H2H 8 Min": "https://i.imgur.com/65W1s9k.png",  # H2H Global Gaming League
    }
    return logo_map.get(league_name, "https://i.imgur.com/neR5gSO.png")  # Logo padrão

def exibir_radar_fifa(df_radar: pd.DataFrame) -> None:
    """Exibe a tabela do Radar FIFA com formatação customizada."""
    if df_radar.empty:
        st.info("🔍 Nenhum dado de Radar FIFA encontrado. Verifique os dados 'Ao Vivo' e 'Resultados'.")
        return

    st.markdown("### 📡 Aqui voce encontra o melhor padrão no HT & FT de cada liga")

    # CSS para estilização das tabelas de Radar e Ranking
    st.markdown(
        """
        <style>
        .radar-table-container, .ranking-table-container {
            background-color: #262730;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.4);
            margin-bottom: 20px;
            margin-top: 20px;
        }
        .radar-header, .ranking-header {
            color: #E0E0E0;
            text-align: center;
            margin-bottom: 15px;
            font-size: 1.8em;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 0;
            padding: 0;
            color: #E0E0E0;
        }
        th, td {
            padding: 10px 15px;
            text-align: center;
            border-bottom: 1px solid #3a3b40;
        }
        th {
            background-color: #3a3b40;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #b0b0b0;
        }
        tr:hover {
            background-color: #2d2e36;
        }
        .stDataFrame {
            width: 100% !important;
            max-height: 500px; /* Adjust as needed */
            overflow: auto;
        }
        .stDataFrame > div > div > div > div > div {
            padding: 0px !important; /* Remove internal padding */
        }
        .stDataFrame table {
            width: 100%; /* Ensure table takes full width */
        }
        .dataframe tbody tr th {
            display: none; /* Hide index column for cleaner look */
        }
        .dataframe thead tr th:first-child {
            display: table-cell; /* Keep the 'Liga' header */
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    html_table = "<div class='radar-table-container'><table><thead><tr>"
    for col in df_radar.columns:
        if col == "Liga":
            html_table += f"<th style='text-align: left;'>{col}</th>"
        else:
            html_table += f"<th>{col}</th>"
    html_table += "</tr></thead><tbody>"

    for _, row in df_radar.iterrows():
        html_table += "<tr>"
        for col in df_radar.columns:
            value = row[col]
            if col == "Liga":
                logo_path = get_logo_path(value)
                html_table += f"<td style='text-align: left;'><img src='{logo_path}' style='height: 20px; vertical-align: middle; margin-right: 8px;'>{value}</td>"
            else:
                color = get_color_for_percentage(value)
                html_table += f"<td style='color: {color}; font-weight: bold;'>{value}</td>"
        html_table += "</tr>"
    html_table += "</tbody></table></div>"
    st.markdown(html_table, unsafe_allow_html=True)


def exibir_ranking_em_tabela(df_ranking: pd.DataFrame, titulo: str) -> None:
    """Exibe um DataFrame de ranking em formato de tabela."""
    if df_ranking.empty:
        st.info(f"🔍 Nenhum dado de ranking encontrado para '{titulo.lower()}'.")
        return

    st.markdown(f"### {titulo}")
    # Applying the custom CSS for ranking tables
    st.markdown("<div class='ranking-table-container'>", unsafe_allow_html=True)
    st.dataframe(df_ranking, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


# --- Streamlit App ---
def main():
    st.set_page_config(
        page_title="Radar FIFA Bet365",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for overall app styling
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #1a1a2e; /* Dark background */
            color: #e0e0e0; /* Light text color */
        }
        .sidebar .sidebar-content {
            background-color: #262730; /* Darker sidebar */
            padding: 20px;
        }
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
            color: #f0f0f0; /* Headers color */
        }
        .stButton>button {
            background-color: #4CAF50;
            color: white;
            border-radius: 5px;
            border: none;
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
        }
        .stButton>button:hover {
            background-color: #45a049;
        }
        .stAlert {
            background-color: #333344;
            color: #e0e0e0;
            border-left: 5px solid #6a0571;
            border-radius: 5px;
        }
        /* Custom styles for metrics */
        [data-testid="stMetric"] {
            background-color: #262730;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
        [data-testid="stMetricLabel"] {
            color: #b0b0b0;
            font-size: 1em;
        }
        [data-testid="stMetricValue"] {
            color: #f0f0f0;
            font-size: 1.8em;
            font-weight: bold;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.title("🤖 SIMULADOR FIFA")
    st.sidebar.markdown("Programador: https://www.instagram.com/vagsembrani/")

    st_autorefresh(interval=300 * 1000, key="data_refresh") # Refresh every 5 minutes

    # Using session state for data caching and to avoid re-fetching unnecessarily
    if "df_resultados" not in st.session_state:
        st.session_state.df_resultados = pd.DataFrame()
    if "df_live_clean" not in st.session_state:
        st.session_state.df_live_clean = pd.DataFrame()
    if "df_live_display" not in st.session_state:
        st.session_state.df_live_display = pd.DataFrame()
    if "df_stats_all_players" not in st.session_state:
        st.session_state.df_stats_all_players = pd.DataFrame()

    with st.spinner("Carregando dados... Isso pode levar alguns segundos."):
        # Pass a dummy flag to force cache clear if needed (e.g., every 6 hours)
        df_resultados, df_live_clean, df_live_display = carregar_todos_os_dados_essenciais(
            datetime.now().hour // 6
        )
        st.session_state.df_resultados = df_resultados
        st.session_state.df_live_clean = df_live_clean
        st.session_state.df_live_display = df_live_display
        st.session_state.df_stats_all_players = calcular_estatisticas_todos_jogadores(df_resultados)

    st.markdown(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    # Define the tabs including the new "Radar FIFA" tab
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Ao Vivo", "📡 Radar FIFA", "📜 Resultados Históricos", "🏆 Análise de Rankings"])

    with tab1:
        st.header("🤖 Simulador (Bet365)")
        st.write("Analises enviadas em tempo real para cada partida.")
        exibir_estatisticas_partidas(st.session_state.df_live_display, "Partidas Ao Vivo")

    with tab2: # New tab for Radar FIFA
        st.header("📡 Radar FIFA (Saiba como está cada grade em tempo real)")
        st.write("Identifique padrões no HT & FT de cada liga")
        df_radar_fifa = calcular_radar_fifa(st.session_state.df_live_clean)
        exibir_radar_fifa(df_radar_fifa)

    with tab3: # Renamed from tab2 to tab3
        st.header("📜 Resultados Históricos (Fifa)")
        st.write("Base de dados completa dos resultados de jogos anteriores.")
        exibir_estatisticas_partidas(st.session_state.df_resultados, "Resultados Históricos")

    with tab4: # Renamed from tab3 to tab4
        st.header("🏆 Análises de Rankings de Jogadores")
        st.markdown(
            "Explore os rankings dos jogadores com base em diversas métricas, "
            "considerando jogadores com no mínimo 10 jogos e os TOP 20 em cada categoria."
        )

        # min_jogos_ranking and top_n_ranking are now fixed inside gerar_ranking
        # They are not exposed as sliders in the sidebar anymore.
        min_jogos_ranking_fixed = 10
        top_n_ranking_fixed = 20

        df_stats_all_players = st.session_state.df_stats_all_players

        if df_stats_all_players.empty:
            st.info("Nenhuma estatística de jogador disponível para gerar rankings.")
        else:
            st.markdown("---")

            # --- Ranking Tabs within 'Análise de Rankings' ---
            tab_ht_overs, tab_ft_overs, tab_btts, tab_geral = st.tabs([
                "📊 Overs HT", "📈 Overs FT", "⚽ Ambos Marcam (BTTS)", "🏆 Geral"
            ])

            with tab_ht_overs:
                st.subheader("Rankings de Gols no Primeiro Tempo (HT)")

                # Over 0.5 HT
                colunas_over_ht_05 = ["Jogador", "Over 0.5 HT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ht_05 = {"jogos_total": "Jogos"}
                df_ranking_over_05_ht = gerar_ranking(
                    df_stats_all_players, "Over 0.5 HT (%)", colunas_over_ht_05,
                    nomes_para_exibicao=nomes_over_ht_05, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_05_ht, "Melhores para Over 0.5 HT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 0.5 HT.")

                st.markdown("---")

                # Over 1.5 HT
                colunas_over_ht_15 = ["Jogador", "Over 1.5 HT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ht_15 = {"jogos_total": "Jogos"}
                df_ranking_over_15_ht = gerar_ranking(
                    df_stats_all_players, "Over 1.5 HT (%)", colunas_over_ht_15,
                    nomes_para_exibicao=nomes_over_ht_15, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_15_ht, "Melhores para Over 1.5 HT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 1.5 HT.")

                st.markdown("---")

                # Over 2.5 HT
                colunas_over_ht_25 = ["Jogador", "Over 2.5 HT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ht_25 = {"jogos_total": "Jogos"}
                df_ranking_over_25_ht = gerar_ranking(
                    df_stats_all_players, "Over 2.5 HT (%)", colunas_over_ht_25,
                    nomes_para_exibicao=nomes_over_ht_25, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_25_ht, "Melhores para Over 2.5 HT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 2.5 HT.")

            with tab_ft_overs:
                st.subheader("Rankings de Gols no Jogo Completo (FT)")

                # Over 0.5 FT
                colunas_over_ft_05 = ["Jogador", "Over 0.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_05 = {"jogos_total": "Jogos"}
                df_ranking_over_05_ft = gerar_ranking(
                    df_stats_all_players, "Over 0.5 FT (%)", colunas_over_ft_05,
                    nomes_para_exibicao=nomes_over_ft_05, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_05_ft, "Melhores para Over 0.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 0.5 FT.")

                st.markdown("---")

                # Over 1.5 FT
                colunas_over_ft_15 = ["Jogador", "Over 1.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_15 = {"jogos_total": "Jogos"}
                df_ranking_over_15_ft = gerar_ranking(
                    df_stats_all_players, "Over 1.5 FT (%)", colunas_over_ft_15,
                    nomes_para_exibicao=nomes_over_ft_15, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_15_ft, "Melhores para Over 1.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 1.5 FT.")

                st.markdown("---")

                # Over 2.5 FT
                colunas_over_ft_25 = ["Jogador", "Over 2.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_25 = {"jogos_total": "Jogos"}
                df_ranking_over_25_ft = gerar_ranking(
                    df_stats_all_players, "Over 2.5 FT (%)", colunas_over_ft_25,
                    nomes_para_exibicao=nomes_over_ft_25, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_25_ft, "Melhores para Over 2.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 2.5 FT.")

                st.markdown("---")

                # Over 3.5 FT
                colunas_over_ft_35 = ["Jogador", "Over 3.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_35 = {"jogos_total": "Jogos"}
                df_ranking_over_35_ft = gerar_ranking(
                    df_stats_all_players, "Over 3.5 FT (%)", colunas_over_ft_35,
                    nomes_para_exibicao=nomes_over_ft_35, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_35_ft, "Melhores para Over 3.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 3.5 FT.")

                st.markdown("---")

                # Over 4.5 FT
                colunas_over_ft_45 = ["Jogador", "Over 4.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_45 = {"jogos_total": "Jogos"}
                df_ranking_over_45_ft = gerar_ranking(
                    df_stats_all_players, "Over 4.5 FT (%)", colunas_over_ft_45,
                    nomes_para_exibicao=nomes_over_ft_45, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_45_ft, "Melhores para Over 4.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 4.5 FT.")

                st.markdown("---")

                # Over 5.5 FT
                colunas_over_ft_55 = ["Jogador", "Over 5.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_55 = {"jogos_total": "Jogos"}
                df_ranking_over_55_ft = gerar_ranking(
                    df_stats_all_players, "Over 5.5 FT (%)", colunas_over_ft_55,
                    nomes_para_exibicao=nomes_over_ft_55, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_55_ft, "Melhores para Over 5.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 5.5 FT.")

                st.markdown("---")

                # Over 6.5 FT
                colunas_over_ft_65 = ["Jogador", "Over 6.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_over_ft_65 = {"jogos_total": "Jogos"}
                df_ranking_over_65_ft = gerar_ranking(
                    df_stats_all_players, "Over 6.5 FT (%)", colunas_over_ft_65,
                    nomes_para_exibicao=nomes_over_ft_65, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_over_65_ft, "Melhores para Over 6.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Over 6.5 FT.")

                st.markdown("---")

                # Under 2.5 FT (New tab within FT Overs)
                colunas_under_ft_25 = ["Jogador", "Under 2.5 FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_under_ft_25 = {"jogos_total": "Jogos"}
                df_ranking_under_25_ft = gerar_ranking(
                    df_stats_all_players, "Under 2.5 FT (%)", colunas_under_ft_25,
                    nomes_para_exibicao=nomes_under_ft_25, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_under_25_ft, "Melhores para Under 2.5 FT")
                st.write("Jogadores com a maior porcentagem de jogos com Menos de 2.5 Gols no FT.")


            with tab_btts:
                st.subheader("Rankings de Ambos Marcam (BTTS)")

                # BTTS HT
                colunas_btts_ht = ["Jogador", "BTTS HT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_btts_ht = {"jogos_total": "Jogos"}
                df_ranking_btts_ht = gerar_ranking(
                    df_stats_all_players, "BTTS HT (%)", colunas_btts_ht,
                    nomes_para_exibicao=nomes_btts_ht, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_btts_ht, "Melhores para BTTS HT")
                st.write("Jogadores com a maior porcentagem de jogos com Ambos Marcam no HT.")

                st.markdown("---")

                # BTTS FT
                colunas_btts_ft = ["Jogador", "BTTS FT (%)", "jogos_total", "Ligas Atuantes"]
                nomes_btts_ft = {"jogos_total": "Jogos"}
                df_ranking_btts_ft = gerar_ranking(
                    df_stats_all_players, "BTTS FT (%)", colunas_btts_ft,
                    nomes_para_exibicao=nomes_btts_ft, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_btts_ft, "Melhores para BTTS FT")
                st.write("Jogadores com a maior porcentagem de jogos com Ambos Marcam no FT.")

            with tab_geral:
                st.subheader("Rankings Gerais de Jogadores")

                # Melhores Gols Marcados Média
                colunas_gm = ["Jogador", "Gols Marcados Média", "jogos_total", "Ligas Atuantes"]
                nomes_gm = {"jogos_total": "Jogos"}
                df_ranking_gm = gerar_ranking(
                    df_stats_all_players, "Gols Marcados Média", colunas_gm,
                    nomes_para_exibicao=nomes_gm, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_gm, "Melhores Gols Marcados (Média)")
                st.write("Jogadores com a maior média de gols marcados por jogo.")

                st.markdown("---")

                # Piores Gols Sofridos Média (para Clean Sheets ou Under)
                colunas_gs = ["Jogador", "Gols Sofridos Média", "jogos_total", "Ligas Atuantes"]
                nomes_gs = {"jogos_total": "Jogos"}
                df_ranking_gs = gerar_ranking(
                    df_stats_all_players, "Gols Sofridos Média", colunas_gs,
                    nomes_para_exibicao=nomes_gs, ascendente=True, # Ascendente para Piores (menor média de gols sofridos)
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_gs, "Melhores Gols Sofridos (Média)")
                st.write("Jogadores com a menor média de gols sofridos por jogo (bons para Under / Clean Sheet).")

                st.markdown("---")

                # Melhores Saldo de Gols
                colunas_saldo = ["Jogador", "Saldo de Gols", "jogos_total", "Ligas Atuantes"]
                nomes_saldo = {"jogos_total": "Jogos"}
                df_ranking_saldo = gerar_ranking(
                    df_stats_all_players, "Saldo de Gols", colunas_saldo,
                    nomes_para_exibicao=nomes_saldo, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_saldo, "Melhores Saldo de Gols")
                st.write("Jogadores com o maior saldo de gols (Gols Marcados - Gols Sofridos).")

                st.markdown("---")

                # Melhores Win Rate
                colunas_win_rate = ["Jogador", "Win Rate (%)", "jogos_total", "Ligas Atuantes"]
                nomes_win_rate = {"jogos_total": "Jogos"}
                df_ranking_win_rate = gerar_ranking(
                    df_stats_all_players, "Win Rate (%)", colunas_win_rate,
                    nomes_para_exibicao=nomes_win_rate, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_win_rate, "Melhores Win Rate")
                st.write("Jogadores com a maior porcentagem de vitórias.")

                st.markdown("---")

                # Melhores Clean Sheets
                colunas_cs = ["Jogador", "Clean Sheets (%)", "jogos_total", "Ligas Atuantes"]
                nomes_cs = {"jogos_total": "Jogos"}
                df_ranking_cs = gerar_ranking(
                    df_stats_all_players, "Clean Sheets (%)", colunas_cs,
                    nomes_para_exibicao=nomes_cs, ascendente=False,
                    min_jogos=min_jogos_ranking_fixed, top_n=top_n_ranking_fixed
                )
                exibir_ranking_em_tabela(df_ranking_cs, "Melhores Clean Sheets")
                st.write("Jogadores com a maior porcentagem de jogos sem sofrer gols.")

if __name__ == "__main__":
    main()