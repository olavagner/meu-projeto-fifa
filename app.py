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
from collections import Counter  # Importar Counter

# ----------------------------------------------------------------------
# LOGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# CONSTANTES
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

# --- Critérios para o Radar FIFA ---
CRITERIOS_HT = {
    "0.5 HT": {"min": 1.70, "max": float('inf')},  # Gols HT (média do confronto) deve ser >= 1.70
    "1.5 HT": {"min": 2.20, "max": float('inf')},  # Gols HT (média do confronto) deve ser >= 2.20
    "2.5 HT": {"min": 2.75, "max": float('inf')},  # Gols HT (média do confronto) deve ser >= 2.75
}

CRITERIOS_FT = {
    "0.5 FT": {"min": 2.00, "max": float('inf')},
    "1.5 FT": {"min": 2.40, "max": float('inf')},
    "2.5 FT": {"min": 3.45, "max": float('inf')},
    "3.5 FT": {"min": 4.50, "max": float('inf')},
    "4.5 FT": {"min": 5.70, "max": float('inf')},
    "5.5 FT": {"min": 6.70, "max": float('inf')},
}


# Reajuste da faixa de Sugestão FT para refletir o Over (>=)
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


# ----------------------------------------------------------------------
# UTILITÁRIOS DE REDE
def requisicao_segura(url: str, timeout: int = 15) -> Optional[requests.Response]:
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


# ----------------------------------------------------------------------
# PROCESSA RESULTADOS
@st.cache_data(show_spinner=False, ttl=300)
def buscar_resultados() -> pd.DataFrame:
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


# ----------------------------------------------------------------------
# ESTATÍSTICAS
def calcular_estatisticas_jogador(df: pd.DataFrame, jogador: str, liga: str) -> dict:
    zeros = {
        "jogos_total": 0, "gols_marcados": 0, "gols_sofridos": 0,
        "gols_marcados_ht": 0, "gols_sofridos_ht": 0,
        "over_05_ht": 0, "over_15_ht": 0, "over_25_ht": 0, "btts_ht": 0,
        "over_05_ft": 0, "over_15_ft": 0, "over_25_ft": 0, "over_35_ft": 0,
        "over_45_ft": 0, "over_55_ft": 0, "over_65_ft": 0, "btts_ft": 0
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

        # Contagem de over deve ser para gols inteiros
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


# ----------------------------------------------------------------------
# FUNÇÕES DE FORMATAÇÃO
def cor_icon(h_m, t_m, h_v, t_v) -> str:
    pct_m = h_m / t_m if t_m else 0
    pct_v = h_v / t_v if t_v else 0
    if pct_m >= 0.70 and pct_v >= 0.70:
        return "🟢"
    if pct_m >= 0.60 and pct_v >= 0.60:
        return "🟡"
    return "🔴"


def format_stats(h_m, t_m, h_v, t_v) -> str:
    """
    Formata as estatísticas de Over/BTTS com ícone e hits/total, sem nomes de jogadores.
    Exemplo:
    🟢 26/29
    26/30
    """
    icon = cor_icon(h_m, t_m, h_v, t_v)
    return f"{icon} {h_m}/{t_m}\n{h_v}/{t_v}"


def format_gols_ht_com_icone_para_display(gols_ht_media: float) -> str:
    """
    Formata a média de gols HT com um ícone verde ou amarelo baseado nos critérios,
    garantindo que o ícone e o número fiquem na mesma linha.
    """
    if gols_ht_media >= 2.75:
        return f"🟢 {gols_ht_media:.2f}"
    elif 2.62 <= gols_ht_media <= 2.74:  # Apenas para dar um amarelo se estiver muito próximo do 2.75
        return f"🟡 {gols_ht_media:.2f}"
    return f"⚪ {gols_ht_media:.2f}"


# --- Funções de Sugestão ---
def sugerir_over_ht(media_gols_ht: float) -> str:
    """Retorna a sugestão para Over HT com base na média de gols HT."""
    if media_gols_ht >= 2.75:  # Corresponde a "Over 2.5 HT"
        return "Over 2.5 HT"
    elif media_gols_ht >= 2.20:  # Corresponde a "Over 1.5 HT"
        return "Over 1.5 HT"
    elif media_gols_ht >= 1.70:  # Corresponde a "Over 0.5 HT"
        return "Over 0.5 HT"
    else:
        return "Sem Entrada"


# A função sugerir_over_ft já foi ajustada acima com base nos critérios de >=
# -----------------------------------------------------

# ----------------------------------------------------------------------
# AO VIVO - Função agora retorna 2 DataFrames: um limpo e um formatado para display
@st.cache_data(show_spinner=False, ttl=300)
def carregar_dados_ao_vivo() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carrega dados ao vivo, calcula as médias de gols e retorna:
    1. Um DataFrame 'limpo' com 'Gols HT' e 'Gols FT' como floats (para cálculos).
    2. Um DataFrame 'formatado' para exibição na aba 'Ao Vivo' (com ícones).
    """
    linhas = extrair_dados_pagina(URL_AO_VIVO)
    if not linhas:
        return pd.DataFrame(), pd.DataFrame()  # Retorna dois DataFrames vazios

    try:
        max_cols = max(len(l) for l in linhas)
        for l in linhas:
            l.extend([""] * (max_cols - len(l)))
        df = pd.DataFrame(linhas)

        if df.shape[1] < 4:
            return pd.DataFrame(), pd.DataFrame()

        df = df[df[3].isin(COMPETICOES_PERMITIDAS)].reset_index(drop=True)
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

        res = buscar_resultados()  # Carrega os resultados históricos

        stats_rows = []
        for _, r in df.iterrows():
            m, v, liga = r["Mandante"], r["Visitante"], r["Liga"]
            sm, sv = (
                calcular_estatisticas_jogador(res, m, liga),
                calcular_estatisticas_jogador(res, v, liga),
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
            soma_ft_mandante = avg_m_gf_ft + avg_m_ga_ft
            soma_ft_visitante = avg_v_gf_ft + avg_v_ga_ft

            # GOLS HT e GOLS FT (MÉDIA DO CONFRONTO) - SEMPRE NUMÉRICO AQUI
            gols_ht_media_confronto = (soma_ht_mandante + soma_ht_visitante) / 2
            gols_ft_media_confronto = (soma_ft_mandante + soma_ft_visitante) / 2

            gp_calc = (avg_m_gf_ft + avg_v_ga_ft) / 2 if (jm and jv) else 0
            gc_calc = (avg_v_gf_ft + avg_m_ga_ft) / 2 if (jm and jv) else 0

            sugestao_ht = sugerir_over_ht(gols_ht_media_confronto)
            sugestao_ft = sugerir_over_ft(gols_ft_media_confronto)

            stats_rows.append(
                {
                    "J1": jm,
                    "J2": jv,
                    "GP": gp_calc,  # Manter como numérico aqui
                    "GC": gc_calc,  # Manter como numérico aqui
                    "Gols HT": gols_ht_media_confronto,  # ESTE É O VALOR NUMÉRICO PURO QUE O RADAR PRECISA
                    "Gols FT": gols_ft_media_confronto,  # ESTE É O VALOR NUMÉRICO PURO QUE O RADAR PRECISA
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

        # DataFrame LIMPO com Gols HT/FT numéricos (para o Radar)
        df_clean = pd.concat([df_base, df_stats], axis=1)

        # DataFrame FORMATADO para exibição na tabela "Ao Vivo"
        df_display = df_clean.copy()
        df_display["Gols HT"] = df_display["Gols HT"].apply(format_gols_ht_com_icone_para_display)
        df_display["Gols FT"] = df_display["Gols FT"].apply(lambda x: f"{x:.2f}")
        df_display["GP"] = df_display["GP"].apply(lambda x: f"{x:.2f}")
        df_display["GC"] = df_display["GC"].apply(lambda x: f"{x:.2f}")

        colunas_ao_vivo_ordenadas = [
            "Hora", "Liga", "Mandante", "Visitante", "J1", "J2", "GP", "GC",
            "Sugestão HT", "Sugestão FT", "Gols HT", "Gols FT",
            "0.5 HT", "1.5 HT", "2.5 HT", "BTTS HT", "BTTS FT",
            "0.5 FT", "1.5 FT", "2.5 FT", "3.5 FT", "4.5 FT", "5.5 FT", "6.5 FT",
        ]

        # Retorna o DataFrame limpo e o DataFrame formatado para exibição
        return df_clean[colunas_ao_vivo_ordenadas], df_display[colunas_ao_vivo_ordenadas]

    except Exception as e:
        logger.error(f"Erro ao processar dados ao vivo: {e}")
        st.error(f"❌ Erro ao processar dados ao vivo: {e}")
        return pd.DataFrame(), pd.DataFrame()


# ----------------------------------------------------------------------
# LÓGICA DO RADAR FIFA - USANDO OS VALORES NUMÉRICOS DA COLUNA "Gols HT" e "Gols FT"
@st.cache_data(show_spinner=False, ttl=300)
def calcular_radar_fifa(df_live_clean: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula as porcentagens de atendimento dos critérios de gols HT e FT para
    os próximos 10 jogos de cada liga, usando os valores numéricos de 'Gols HT' e 'Gols FT'
    já presentes no DataFrame 'Ao Vivo' (limpo).
    """
    if df_live_clean.empty:
        return pd.DataFrame()

    ligas_unicas = df_live_clean["Liga"].unique()
    resultados_radar = []

    for liga in ligas_unicas:
        # **ESTE É O "PROCV": Seleciona os primeiros 10 jogos da LIGA específica**
        jogos_da_liga = df_live_clean[df_live_clean["Liga"] == liga].head(10)

        total_jogos_analisados = len(jogos_da_liga)

        if total_jogos_analisados == 0:
            continue

        # Inicializa contadores para os critérios
        contadores_ht = {k: 0 for k in CRITERIOS_HT.keys()}
        contadores_ft = {k: 0 for k in CRITERIOS_FT.keys()}

        # A lista sugestoes_ht_jogos não será mais usada para 'Padrão Over HT',
        # mas mantida aqui caso a lógica de 'Sugestão HT' individual seja útil em outro lugar.
        sugestoes_ht_jogos = []

        for _, jogo_ao_vivo in jogos_da_liga.iterrows():
            # **AQUI PEGA O VALOR DA COLUNA "Gols HT" E "Gols FT" PARA ESTE JOGO**
            # (Assumimos que df_live_clean já tem esses valores como float)
            media_gols_ht_jogo = jogo_ao_vivo["Gols HT"]
            media_gols_ft_jogo = jogo_ao_vivo["Gols FT"]

            # Garante que os valores são numéricos antes de usar (importante caso haja NaNs)
            if pd.isna(media_gols_ht_jogo): media_gols_ht_jogo = 0.0
            if pd.isna(media_gols_ft_jogo): media_gols_ft_jogo = 0.0

            # Adiciona a sugestão HT do jogo atual à lista (mesmo que não seja usada na tabela do Radar)
            sugestoes_ht_jogos.append(sugerir_over_ht(media_gols_ht_jogo))

            # Verifica os critérios HT - **DIRETO NA MÉDIA DO JOGO**
            for criterio, valores in CRITERIOS_HT.items():
                if media_gols_ht_jogo >= valores["min"]:
                    contadores_ht[criterio] += 1

            # Verifica os critérios FT - **DIRETO NA MÉDIA DO JOGO**
            for criterio, valores in CRITERIOS_FT.items():
                if media_gols_ft_jogo >= valores["min"]:
                    contadores_ft[criterio] += 1

        # A lógica para 'Padrão Over HT' é removida, pois a coluna foi removida.
        # Determinando um valor 'N/A' ou similar para fins de depuração, se necessário.
        # padrao_over_ht_sugestao = "N/A"

        # Formata os resultados para a liga atual
        # A coluna "Padrão Over HT" é removida daqui
        linha_liga = {"Liga": liga}
        for criterio, contagem in contadores_ht.items():
            percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
            linha_liga[f"{criterio}"] = f"{int(percentual)}%"

        for criterio, contagem in contadores_ft.items():
            percentual = (contagem / total_jogos_analisados) * 100 if total_jogos_analisados > 0 else 0
            linha_liga[f"{criterio}"] = f"{int(percentual)}%"

        resultados_radar.append(linha_liga)

    # Definir a ordem das colunas para o Radar FIFA
    # REMOVIDO "Padrão Over HT" daqui
    colunas_radar_ordenadas = ["Liga"] + list(CRITERIOS_HT.keys()) + list(CRITERIOS_FT.keys())

    df_radar = pd.DataFrame(resultados_radar)

    for col in colunas_radar_ordenadas:
        if col not in df_radar.columns:
            df_radar[col] = "0%"

    df_radar = df_radar[colunas_radar_ordenadas]

    return df_radar


# ----------------------------------------------------------------------
# CACHE HELPERS
@st.cache_data(show_spinner=False, ttl=300)
def carregar_dados_com_atualizacao(flag: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Esta função apenas chama carregar_dados_ao_vivo, que já é @st.cache_data
    # e retorna os dois DataFrames necessários
    return carregar_dados_ao_vivo()


@st.cache_data(show_spinner=False, ttl=300)
def buscar_resultados_com_atualizacao(flag: int) -> pd.DataFrame:
    # Esta função apenas chama buscar_resultados, que já é @st.cache_data
    return buscar_resultados()


# ----------------------------------------------------------------------
# VISUAL STREAMLIT
def exibir_estatisticas_partidas(df: pd.DataFrame, titulo: str) -> None:
    if df.empty:
        st.info(f"🔍 Nenhum dado encontrado para {titulo.lower()}.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Total de Partidas", len(df))

    if "Liga" in df.columns:
        uniq = df["Liga"].nunique()
        col2.metric("🏆 Ligas Diferentes", uniq)
        if uniq > 1:
            col3.metric("🥇 Liga Mais Ativa", df["Liga"].mode().iloc[0])
            col4.metric("📈 Máx. Partidas/Liga", df["Liga"].value_counts().max())

    st.dataframe(df, use_container_width=True, height=430)


def get_color_for_percentage(percentage_str: str) -> str:
    """Returns a CSS color based on the percentage string."""
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
    """
    Returns the direct URL for a league logo based on its name.
    """
    # **IMPORTANT: Substitua estes URLs de placeholder pelos URLs diretos reais de suas imagens hospedadas.**
    # Você precisa fazer o upload de suas imagens (image_a25b56.png, image_a2625d.png, etc.)
    # para um serviço de hospedagem de imagens online (como Imgur, link raw do GitHub, etc.)
    # e então colocar os URLs diretos aqui.

    logo_map = {
        # Baseado em image_a25b56.png / image_a26281.png mostrando o logotipo verde "ESPORTS BATTLE"
        "Battle 8 Min": "https://i.imgur.com/your_battle_8_min_logo_url.png",  # EX: https://i.imgur.com/KzY8g0A.png

        # Baseado em image_a2625d.png mostrando o logotipo "GT LEAGUES"
        "GT 12 Min": "https://i.imgur.com/your_gt_12_min_logo_url.png",  # EX: https://i.imgur.com/J2xY0Zl.png

        # Baseado em image_a2623d.png mostrando o logotipo "VOLTA FOOTBALL"
        "Volta 6 Min": "https://i.imgur.com/your_volta_6_min_logo_url.png",  # EX: https://i.imgur.com/T0bX6qC.png

        # Baseado em image_a25e23.png / image_a26220.png mostrando o logotipo "H2H GLOBAL GAMING LEAGUE"
        "H2H 8 Min": "https://i.imgur.com/your_h2h_8_min_logo_url.png",  # EX: https://i.imgur.com/L8tY9xM.png
    }
    # Retorna o URL do logotipo específico, ou um placeholder genérico se não encontrado
    return logo_map.get(league_name,
                        "https://i.imgur.com/gK2oD6f.png")  # Logotipo de bola da FIFA genérico como fallback


def exibir_radar_fifa(df_radar: pd.DataFrame) -> None:
    """
    Exibe a tabela do Radar FIFA com um layout mais limpo e integrado,
    com cores condicionais para as probabilidades.
    """
    if df_radar.empty:
        st.info("🔍 Nenhum dado de Radar FIFA encontrado. Verifique os dados 'Ao Vivo' e 'Resultados'.")
        return

    st.markdown("### 📡 Radar FIFA - Análise de Próximos Jogos")

    # Aplica CSS global para uma aparência mais limpa e estilo personalizado
    st.markdown(
        """
        <style>
        .radar-table-container {
            background-color: #262730; /* Fundo escuro para a tabela/painel inteiro */
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.4);
        }
        .radar-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 0;
            margin-bottom: 15px;
            border-bottom: 2px solid #444; /* Separador para o cabeçalho */
            color: #f0f0f0;
            font-weight: bold;
            font-size: 1.1em;
        }
        .radar-row {
            display: flex;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #333; /* Separador para as linhas */
            transition: background-color 0.2s ease-in-out;
        }
        .radar-row:last-child {
            border-bottom: none; /* Sem borda para a última linha */
        }
        .radar-row:hover {
            background-color: #333; /* Efeito de hover */
        }
        .radar-cell {
            flex: 1;
            padding: 5px 10px;
            text-align: center;
            color: #e0e0e0;
            font-size: 0.95em;
        }
        .radar-cell.league-name {
            flex: 2; /* Torna o nome da liga mais largo */
            text-align: left;
            display: flex;
            align-items: center;
            font-weight: bold;
            font-size: 1.05em;
        }
        /* A classe .radar-cell.pattern-ht e .pattern-ht-header não são mais necessárias
           já que a coluna 'Padrão Over HT' foi removida.
        .radar-cell.pattern-ht {
            flex: 1.5;
            font-weight: bold;
            color: #FFD700;
            font-size: 0.9em;
        }
        */
        .radar-logo {
            height: 30px;
            width: 30px;
            margin-right: 10px;
            border-radius: 5px; /* Cantos ligeiramente arredondados para os logotipos */
        }
        .probability-box {
            padding: 4px 8px;
            border-radius: 5px;
            display: inline-block; /* Permite que a cor de fundo se ajuste ao conteúdo */
            min-width: 60px;
            text-align: center;
            color: white;
            font-weight: bold;
        }
        .header-cell {
            text-align: center;
            font-size: 0.9em; /* Fonte menor para cabeçalhos */
            color: #b0b0b0; /* Cor mais clara para cabeçalhos */
            font-weight: normal; /* Peso normal para cabeçalhos */
        }
        .header-cell.league-name-header {
            text-align: left;
        }
        /* A classe .header-cell.pattern-ht-header não é mais necessária */
        /*
        .header-cell.pattern-ht-header {
            text-align: center;
        }
        */
        /* Torna as colunas responsivas para telas menores */
        @media (max-width: 768px) {
            .radar-header, .radar-row {
                flex-wrap: wrap;
            }
            .radar-cell, .header-cell {
                flex: 1 1 50%; /* Cada item ocupa 50% da largura em telas pequenas */
                padding: 5px;
                margin-bottom: 5px;
            }
            .radar-cell.league-name, .header-cell.league-name-header {
                flex: 1 1 100%; /* Nome da liga ocupa largura total */
                text-align: center;
            }
            /* Estas regras não são mais necessárias
            .radar-cell.pattern-ht, .header-cell.pattern-ht-header {
                flex: 1 1 100%;
                text-align: center;
            }
            */
            .radar-logo {
                display: none; /* Oculta logotipos em telas muito pequenas se o espaço for limitado */
            }
        }
        /* Correção para o preenchimento padrão do Streamlit em torno das colunas para parecer uma única tabela */
        /* Estes seletores podem precisar de ajuste se os nomes de classe internos do Streamlit mudarem */
        .st-emotion-cache-row-gap-e3gdfw > div:first-child, .st-emotion-cache-j7qp64 > div:first-child {
            padding-left: 0 !important;
        }
        .st-emotion-cache-row-gap-e3gdfw > div:last-child, .st-emotion-cache-j7qp64 > div:last-child {
            padding-right: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True
    )

    st.markdown('<div class="radar-table-container">', unsafe_allow_html=True)

    # --- Cabeçalho da Tabela ---
    # Define as larguras das colunas para o cabeçalho e as linhas de dados
    # [2] para Liga, então [1] para cada critério HT e FT
    column_widths = [2] + [1] * (len(CRITERIOS_HT) + len(CRITERIOS_FT))

    header_cols = st.columns(column_widths)

    header_cols[0].markdown('<div class="radar-cell header-cell league-name-header">Liga</div>', unsafe_allow_html=True)
    # A coluna 'Padrão Over HT' foi removida, então o próximo índice é 1
    col_idx = 1
    for k in CRITERIOS_HT.keys():
        header_cols[col_idx].markdown(f'<div class="radar-cell header-cell">{k}</div>', unsafe_allow_html=True)
        col_idx += 1
    for k in CRITERIOS_FT.keys():
        header_cols[col_idx].markdown(f'<div class="radar-cell header-cell">{k}</div>', unsafe_allow_html=True)
        col_idx += 1

    # Este div vazio ajuda a aplicar o estilo border-bottom para o cabeçalho
    st.markdown('<div style="border-bottom: 2px solid #444; margin-bottom: 15px;"></div>', unsafe_allow_html=True)

    # --- Linhas da Tabela (Dados) ---
    for i, (idx, row) in enumerate(df_radar.iterrows()):
        logo_url = get_logo_path(row['Liga'])  # Obtém o URL do logotipo

        cols = st.columns(column_widths)  # Usa as mesmas larguras de coluna do cabeçalho

        # Nome da Liga e Logotipo
        cols[0].markdown(
            f"""
            <div class="radar-cell league-name">
                <img src="{logo_url}" class="radar-logo" />
                {row['Liga']}
            </div>
            """, unsafe_allow_html=True
        )

        # O "Padrão Over HT" foi removido, então o próximo índice é 1
        col_idx = 1
        # Probabilidades HT
        for k in CRITERIOS_HT.keys():
            percentage_str = row[k]
            color = get_color_for_percentage(percentage_str)
            cols[col_idx].markdown(
                f"""
                <div class="radar-cell">
                    <span class="probability-box" style="background-color: {color};">
                        {percentage_str}
                    </span>
                </div>
                """, unsafe_allow_html=True
            )
            col_idx += 1

        # Probabilidades FT
        for k in CRITERIOS_FT.keys():
            percentage_str = row[k]
            color = get_color_for_percentage(percentage_str)
            cols[col_idx].markdown(
                f"""
                <div class="radar-cell">
                    <span class="probability-box" style="background-color: {color};">
                        {percentage_str}
                    </span>
                </div>
                """, unsafe_allow_html=True
            )
            col_idx += 1

        # Adiciona um separador visual se não for a última linha
        if i < len(df_radar) - 1:
            st.markdown('<div style="border-bottom: 1px solid #333; margin: 10px 0;"></div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # Fecha radar-table-container


# ----------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="Simulador FIFA",
        layout="wide",
        page_icon="🤖",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <div style="text-align:center">
            <h1>🤖 Simulador FIFA - E‑Soccer</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div style="
            background:linear-gradient(135deg,#667eea 0%,#764ba2 50%,#f093fb 100%);
            padding:25px;border-radius:15px;text-align:center;color:white;
            margin-bottom:30px;box-shadow:0 8px 32px rgba(0,0,0,.1);backdrop-filter:blur(10px);
            border:1px solid rgba(255,255,255,.1);">
            <h2 style="margin:0;font-weight:700;text-shadow:2px 2px 4px rgba(0,0,0,.3);">
                🎮 Competições E‑Soccer em Tempo Real
            </h2>
            <p style="margin:15px 0 0 0;opacity:.95;font-size:1.1em;">
                Dados atualizados automaticamente das principais ligas virtuais
            </p>
            <div style="margin-top:15px;font-size:.9em;opacity:.8;">
                ⏰ Última atualização: {datetime.now().strftime("%H:%M:%S")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l, col_c, col_r = st.columns([2, 1, 2])
    with col_c:
        intervalo = st.selectbox(
            "⚙️ Intervalo de Atualização",
            options=[30, 60, 120, 300],
            index=1,
            format_func=lambda x: f"{x} seg",
        )

    contador = st_autorefresh(interval=intervalo * 1000, key="auto_refresh")

    col_l, col_c, col_r = st.columns([2, 1, 2])
    with col_c:
        click_manual = st.button("🔄 Atualizar Dados Agora", use_container_width=True)

    flag = 1 if click_manual else contador

    aba_ao_vivo, aba_radar, aba_res, aba_cfg = st.tabs(
        ["🎯 Ao Vivo", "📡 Radar FIFA", "📊 Resultados", "⚙️ Configurações"])

    # As chamadas a carregar_dados_ao_vivo() e buscar_resultados_com_atualizacao()
    # estão corretas aqui, pois as funções são definidas ANTES desta chamada.
    df_live_clean, df_live_display = carregar_dados_ao_vivo()
    df_res = buscar_resultados_com_atualizacao(flag)

    with aba_ao_vivo:
        st.markdown("### 🔴 Partidas Ao Vivo")
        with st.spinner("Carregando..."):
            exibir_estatisticas_partidas(df_live_display, "Partidas Ao Vivo")

    with aba_radar:
        with st.spinner("Analisando dados para o Radar FIFA..."):
            df_radar = calcular_radar_fifa(df_live_clean)
        exibir_radar_fifa(df_radar)

    with aba_res:
        st.markdown("### 📈 Resultados Recentes")
        with st.spinner("Carregando..."):
            exibir_estatisticas_partidas(df_res, "Resultados")

    with aba_cfg:
        st.markdown("### ⚙️ Configurações do Sistema")
        st.markdown("#### 🌐 URLs")
        with st.expander("Ver URLs"):
            st.code(f"Ao Vivo: {URL_AO_VIVO}")
            st.code(f"Resultados: {URL_RESULTADOS}")

        st.markdown("#### 🏆 Competições Monitoradas")
        with st.expander("Ver Competições"):
            for c in COMPETICOES_PERMITIDAS:
                st.markdown(f"• {c}")

        col1, col2 = st.columns(2)
        col1.info("⏱️ TTL Cache: 5 min")
        col1.info("🌐 Timeout: 15 s")
        col2.info(f"🔄 Auto‑refresh: {intervalo} s")
        col2.info(f"📊 Atualização #{contador}")

        if st.button("🗑️ Limpar Cache"):
            st.cache_data.clear()
            st.success("Cache limpo — recarregando…")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    st.markdown(
        """
        <div style="text-align:center;color:#666;margin-top:20px">
            <small>
                🚀 Desenvolvido com ❤️ em Streamlit&nbsp;&nbsp;•&nbsp;&nbsp;
                Dependências: requests • pandas • beautifulsoup4 • lxml • streamlit‑autorefresh
            </small>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------
if __name__ == "__main__":
    main()