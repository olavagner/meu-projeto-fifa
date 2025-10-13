from __future__ import annotations
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
import re
from streamlit_autorefresh import st_autorefresh
from typing import Tuple, Dict, List

URL = "https://www.aceodds.com/pt/bet365-transmissao-ao-vivo.html"
URL_RESULTADOS = "https://www.fifastats.net/resultados"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/114.0.0.0 Safari/537.36"
}

ALLOWED_COMPETITIONS = {
    "E-soccer - H2H GG League - 8 minutos de jogo",
    "Esoccer Battle Volta - 6 Minutos de Jogo",
    "E-soccer - GT Leagues - 12 mins de jogo",
    "E-soccer - Battle - 8 minutos de jogo"
}


@st.cache_data(show_spinner=False, ttl=300)
def scrape_page(url: str) -> list[list[str]]:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    rows = [
        [cell.get_text(strip=True) for cell in tr.find_all(["th", "td"])]
        for tr in soup.find_all("tr")
        if tr.find_all(["th", "td"])
    ]
    return rows


@st.cache_data(show_spinner=False, ttl=300)
def scrape_resultados() -> pd.DataFrame:
    rows = scrape_page(URL_RESULTADOS)
    if not rows:
        return pd.DataFrame()

    max_cols = max(len(r) for r in rows)
    for r in rows:
        r.extend([""] * (max_cols - len(r)))
    df = pd.DataFrame(rows)

    if len(df) <= 1:
        df.columns = [f"Coluna {i + 1}" for i in range(df.shape[1])]
        return df

    df.columns = df.iloc[0]
    df = df.iloc[1:].reset_index(drop=True)
    df.columns = [str(c).strip() if pd.notna(c) else f"Coluna {i + 1}"
                  for i, c in enumerate(df.columns)]

    def sem_parenteses(txt: str) -> str:
        return re.sub(r'\s*\([^)]*\)', '', str(txt)).strip()

    if 'Jogador 1' in df.columns:
        df['Jogador 1'] = df['Jogador 1'].apply(sem_parenteses)
    if 'Jogador 2' in df.columns:
        df['Jogador 2'] = df['Jogador 2'].apply(sem_parenteses)

    df = df.rename(columns={
        'Campeonato': 'Liga',
        'Jogador 1': 'Mandante',
        'Jogador 2': 'Visitante',
        'Placar': 'Placar Final'
    })

    liga_map_resultados = {
        "GT League": "GT 12 Min",
        "H2H 8m": "H2H 8 Min",
        "Battle 8m": "Battle 8 Min",
        "Battle 6m": "Volta 6 Min"
    }
    df['Liga'] = df['Liga'].replace(liga_map_resultados)

    if 'Placar HT' in df.columns:
        ht = (
            df['Placar HT'].fillna('')
            .astype(str).str.replace(' ', '', regex=False).str.strip()
            .str.split('x', n=1, expand=True)
            .reindex(columns=[0, 1], fill_value='')
        )
        df['Mandante HT'] = ht[0].str.strip()
        df['Visitante HT'] = ht[1].str.strip()

    if 'Placar Final' in df.columns:
        ft = (
            df['Placar Final'].fillna('')
            .astype(str).str.replace(' ', '', regex=False).str.strip()
            .str.split('x', n=1, expand=True)
            .reindex(columns=[0, 1], fill_value='')
        )
        df['Mandante FT'] = ft[0].str.strip()
        df['Visitante FT'] = ft[1].str.strip()

    df['Total HT'] = (
            pd.to_numeric(df['Mandante HT'], errors='coerce').fillna(0) +
            pd.to_numeric(df['Visitante HT'], errors='coerce').fillna(0)
    ).astype(int)

    df['Total FT'] = (
            pd.to_numeric(df['Mandante FT'], errors='coerce').fillna(0) +
            pd.to_numeric(df['Visitante FT'], errors='coerce').fillna(0)
    ).astype(int)

    df = df.drop(columns=[c for c in ['Placar HT', 'Placar Final'] if c in df.columns])

    col_final = [
        'Data', 'Liga', 'Mandante', 'Visitante',
        'Mandante HT', 'Visitante HT', 'Total HT',
        'Mandante FT', 'Visitante FT', 'Total FT'
    ]
    df = df[[c for c in col_final if c in df.columns]]

    return df


def calcular_estatisticas_jogador(jogador: str, df_resultados: pd.DataFrame, adversario: str = None) -> Dict:
    """Calcula estatísticas para um jogador considerando confrontos diretos e últimos jogos"""

    # Filtrar jogos onde o jogador participou (como mandante ou visitante)
    mask_mandante = df_resultados['Mandante'] == jogador
    mask_visitante = df_resultados['Visitante'] == jogador
    jogos_jogador = df_resultados[mask_mandante | mask_visitante].copy()

    if jogos_jogador.empty:
        return {
            'vitorias_ht': 0, 'empates_ht': 0, 'derrotas_ht': 0,
            'gols_marcados_ht': 0, 'gols_sofridos_ht': 0,
            'vitorias_ft': 0, 'empates_ft': 0, 'derrotas_ft': 0,
            'gols_marcados_ft': 0, 'gols_sofridos_ft': 0,
            'total_jogos': 0,
            'media_gols_ht': 0.0, 'media_gols_ft': 0.0,
            'over_05_ht': 0, 'over_15_ht': 0, 'over_25_ht': 0,
            'over_05_ft': 0, 'over_15_ft': 0, 'over_25_ft': 0,
            'over_35_ft': 0, 'over_45_ft': 0, 'over_55_ft': 0,
            'btts_ht': 0, 'btts_ft': 0
        }

    # Ordenar por data (assumindo que a coluna Data existe)
    if 'Data' in jogos_jogador.columns:
        jogos_jogador = jogos_jogador.sort_values('Data', ascending=False)

    # Separar confrontos diretos se adversário for especificado
    confrontos_diretos = pd.DataFrame()
    if adversario:
        mask_confronto_mandante = (df_resultados['Mandante'] == jogador) & (df_resultados['Visitante'] == adversario)
        mask_confronto_visitante = (df_resultados['Mandante'] == adversario) & (df_resultados['Visitante'] == jogador)
        confrontos_diretos = df_resultados[mask_confronto_mandante | mask_confronto_visitante].head(5)

    # Últimos 10 jogos gerais (excluindo confrontos diretos já considerados)
    jogos_gerais = jogos_jogador
    if not confrontos_diretos.empty:
        # Remover confrontos diretos dos jogos gerais para não duplicar
        mask = ~jogos_jogador.index.isin(confrontos_diretos.index)
        jogos_gerais = jogos_jogador[mask]

    jogos_gerais = jogos_gerais.head(10)  # Últimos 10 jogos gerais

    # Combinar todos os jogos (confrontos diretos + jogos gerais)
    todos_jogos = pd.concat([confrontos_diretos, jogos_gerais]).drop_duplicates().head(15)

    if todos_jogos.empty:
        return {
            'vitorias_ht': 0, 'empates_ht': 0, 'derrotas_ht': 0,
            'gols_marcados_ht': 0, 'gols_sofridos_ht': 0,
            'vitorias_ft': 0, 'empates_ft': 0, 'derrotas_ft': 0,
            'gols_marcados_ft': 0, 'gols_sofridos_ft': 0,
            'total_jogos': 0,
            'media_gols_ht': 0.0, 'media_gols_ft': 0.0,
            'over_05_ht': 0, 'over_15_ht': 0, 'over_25_ht': 0,
            'over_05_ft': 0, 'over_15_ft': 0, 'over_25_ft': 0,
            'over_35_ft': 0, 'over_45_ft': 0, 'over_55_ft': 0,
            'btts_ht': 0, 'btts_ft': 0
        }

    # Inicializar contadores
    vitorias_ht = empates_ht = derrotas_ht = 0
    gols_marcados_ht = gols_sofridos_ht = 0
    vitorias_ft = empates_ft = derrotas_ft = 0
    gols_marcados_ft = gols_sofridos_ft = 0

    over_05_ht = over_15_ht = over_25_ht = 0
    over_05_ft = over_15_ft = over_25_ft = over_35_ft = over_45_ft = over_55_ft = 0
    btts_ht = btts_ft = 0

    for _, jogo in todos_jogos.iterrows():
        # Verificar se o jogador é mandante ou visitante
        eh_mandante = jogo['Mandante'] == jogador

        # Dados do HT
        if 'Mandante HT' in jogo and 'Visitante HT' in jogo:
            try:
                gols_mandante_ht = int(jogo['Mandante HT']) if jogo['Mandante HT'] not in ['', 'NaN'] else 0
                gols_visitante_ht = int(jogo['Visitante HT']) if jogo['Visitante HT'] not in ['', 'NaN'] else 0
                total_gols_ht = gols_mandante_ht + gols_visitante_ht

                # Contar Overs HT
                if total_gols_ht > 0.5: over_05_ht += 1
                if total_gols_ht > 1.5: over_15_ht += 1
                if total_gols_ht > 2.5: over_25_ht += 1

                # Contar BTTS HT (ambos marcaram no HT) - MESMA LÓGICA DOS OVER
                if gols_mandante_ht > 0 and gols_visitante_ht > 0:
                    btts_ht += 1

                if eh_mandante:
                    gols_marcados_ht += gols_mandante_ht
                    gols_sofridos_ht += gols_visitante_ht

                    if gols_mandante_ht > gols_visitante_ht:
                        vitorias_ht += 1
                    elif gols_mandante_ht == gols_visitante_ht:
                        empates_ht += 1
                    else:
                        derrotas_ht += 1
                else:
                    gols_marcados_ht += gols_visitante_ht
                    gols_sofridos_ht += gols_mandante_ht

                    if gols_visitante_ht > gols_mandante_ht:
                        vitorias_ht += 1
                    elif gols_visitante_ht == gols_mandante_ht:
                        empates_ht += 1
                    else:
                        derrotas_ht += 1
            except (ValueError, TypeError):
                pass

        # Dados do FT
        if 'Mandante FT' in jogo and 'Visitante FT' in jogo:
            try:
                gols_mandante_ft = int(jogo['Mandante FT']) if jogo['Mandante FT'] not in ['', 'NaN'] else 0
                gols_visitante_ft = int(jogo['Visitante FT']) if jogo['Visitante FT'] not in ['', 'NaN'] else 0
                total_gols_ft = gols_mandante_ft + gols_visitante_ft

                # Contar Overs FT
                if total_gols_ft > 0.5: over_05_ft += 1
                if total_gols_ft > 1.5: over_15_ft += 1
                if total_gols_ft > 2.5: over_25_ft += 1
                if total_gols_ft > 3.5: over_35_ft += 1
                if total_gols_ft > 4.5: over_45_ft += 1
                if total_gols_ft > 5.5: over_55_ft += 1

                # Contar BTTS FT (ambos marcaram no FT) - MESMA LÓGICA DOS OVER
                if gols_mandante_ft > 0 and gols_visitante_ft > 0:
                    btts_ft += 1

                if eh_mandante:
                    gols_marcados_ft += gols_mandante_ft
                    gols_sofridos_ft += gols_visitante_ft

                    if gols_mandante_ft > gols_visitante_ft:
                        vitorias_ft += 1
                    elif gols_mandante_ft == gols_visitante_ft:
                        empates_ft += 1
                    else:
                        derrotas_ft += 1
                else:
                    gols_marcados_ft += gols_visitante_ft
                    gols_sofridos_ft += gols_mandante_ft

                    if gols_visitante_ft > gols_mandante_ft:
                        vitorias_ft += 1
                    elif gols_visitante_ft == gols_mandante_ft:
                        empates_ft += 1
                    else:
                        derrotas_ft += 1
            except (ValueError, TypeError):
                pass

    total_jogos = len(todos_jogos)

    # Média de gols = (Gols Marcados + Gols Sofridos) / Total de Jogos
    media_gols_ht = round((gols_marcados_ht + gols_sofridos_ht) / total_jogos, 2) if total_jogos > 0 else 0.0
    media_gols_ft = round((gols_marcados_ft + gols_sofridos_ft) / total_jogos, 2) if total_jogos > 0 else 0.0

    return {
        'vitorias_ht': vitorias_ht,
        'empates_ht': empates_ht,
        'derrotas_ht': derrotas_ht,
        'gols_marcados_ht': gols_marcados_ht,
        'gols_sofridos_ht': gols_sofridos_ht,
        'media_gols_ht': media_gols_ht,

        'vitorias_ft': vitorias_ft,
        'empates_ft': empates_ft,
        'derrotas_ft': derrotas_ft,
        'gols_marcados_ft': gols_marcados_ft,
        'gols_sofridos_ft': gols_sofridos_ft,
        'media_gols_ft': media_gols_ft,

        'total_jogos': total_jogos,
        'over_05_ht': over_05_ht, 'over_15_ht': over_15_ht, 'over_25_ht': over_25_ht,
        'over_05_ft': over_05_ft, 'over_15_ft': over_15_ft, 'over_25_ft': over_25_ft,
        'over_35_ft': over_35_ft, 'over_45_ft': over_45_ft, 'over_55_ft': over_55_ft,
        'btts_ht': btts_ht, 'btts_ft': btts_ft
    }


def calcular_probabilidades(estat_casa: Dict, estat_fora: Dict, tipo: str = 'ht') -> Tuple[float, float, float]:
    """Calcula probabilidades para 1X2 baseado nas estatísticas"""

    if tipo == 'ht':
        vitorias_casa = estat_casa['vitorias_ht']
        empates_casa = estat_casa['empates_ht']
        derrotas_casa = estat_casa['derrotas_ht']
        vitorias_fora = estat_fora['vitorias_ht']
        empates_fora = estat_fora['empates_ht']
        derrotas_fora = estat_fora['derrotas_ht']
    else:  # ft
        vitorias_casa = estat_casa['vitorias_ft']
        empates_casa = estat_casa['empates_ft']
        derrotas_casa = estat_casa['derrotas_ft']
        vitorias_fora = estat_fora['vitorias_ft']
        empates_fora = estat_fora['empates_ft']
        derrotas_fora = estat_fora['derrotas_ft']

    total_casa = vitorias_casa + empates_casa + derrotas_casa
    total_fora = vitorias_fora + empates_fora + derrotas_fora

    if total_casa == 0 or total_fora == 0:
        return 0.33, 0.34, 0.33

    # Fórmulas conforme especificado
    casa_vence = (vitorias_casa + derrotas_fora) / (total_casa + total_fora)
    fora_vence = (vitorias_fora + derrotas_casa) / (total_casa + total_fora)
    empate = 1 - (casa_vence + fora_vence)

    # Garantir que as probabilidades somem 1
    total = casa_vence + empate + fora_vence
    if total > 0:
        casa_vence /= total
        empate /= total
        fora_vence /= total

    return casa_vence, empate, fora_vence


def calcular_overs_combinados(estat_casa: Dict, estat_fora: Dict, total_jogos_combinados: int) -> Dict:
    """Calcula porcentagens de Over e BTTS combinando dados de casa e fora"""

    if total_jogos_combinados == 0:
        return {
            'over_05_ht': 0, 'over_15_ht': 0, 'over_25_ht': 0,
            'over_05_ft': 0, 'over_15_ft': 0, 'over_25_ft': 0,
            'over_35_ft': 0, 'over_45_ft': 0, 'over_55_ft': 0,
            'btts_ht': 0, 'btts_ft': 0
        }

    # Para Over e BTTS, usamos a mesma lógica: se qualquer um dos dois jogadores teve, conta
    over_05_ht = (estat_casa['over_05_ht'] + estat_fora['over_05_ht']) / (2 * total_jogos_combinados)
    over_15_ht = (estat_casa['over_15_ht'] + estat_fora['over_15_ht']) / (2 * total_jogos_combinados)
    over_25_ht = (estat_casa['over_25_ht'] + estat_fora['over_25_ht']) / (2 * total_jogos_combinados)

    over_05_ft = (estat_casa['over_05_ft'] + estat_fora['over_05_ft']) / (2 * total_jogos_combinados)
    over_15_ft = (estat_casa['over_15_ft'] + estat_fora['over_15_ft']) / (2 * total_jogos_combinados)
    over_25_ft = (estat_casa['over_25_ft'] + estat_fora['over_25_ft']) / (2 * total_jogos_combinados)
    over_35_ft = (estat_casa['over_35_ft'] + estat_fora['over_35_ft']) / (2 * total_jogos_combinados)
    over_45_ft = (estat_casa['over_45_ft'] + estat_fora['over_45_ft']) / (2 * total_jogos_combinados)
    over_55_ft = (estat_casa['over_55_ft'] + estat_fora['over_55_ft']) / (2 * total_jogos_combinados)

    # BTTS segue a MESMA lógica dos Over
    btts_ht = (estat_casa['btts_ht'] + estat_fora['btts_ht']) / (2 * total_jogos_combinados)
    btts_ft = (estat_casa['btts_ft'] + estat_fora['btts_ft']) / (2 * total_jogos_combinados)

    return {
        'over_05_ht': round(over_05_ht * 100, 1),
        'over_15_ht': round(over_15_ht * 100, 1),
        'over_25_ht': round(over_25_ht * 100, 1),
        'over_05_ft': round(over_05_ft * 100, 1),
        'over_15_ft': round(over_15_ft * 100, 1),
        'over_25_ft': round(over_25_ft * 100, 1),
        'over_35_ft': round(over_35_ft * 100, 1),
        'over_45_ft': round(over_45_ft * 100, 1),
        'over_55_ft': round(over_55_ft * 100, 1),
        'btts_ht': round(btts_ht * 100, 1),
        'btts_ft': round(btts_ft * 100, 1)
    }


def formatar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Formata o DataFrame para exibir porcentagens com o símbolo % e gols com 2 casas decimais"""
    df_formatado = df.copy()

    # Colunas que devem ser formatadas como porcentagem
    colunas_porcentagem = [
        'Casa Vence HT', 'Empate HT', 'Fora Vence HT', 'Btts HT',
        'Casa Vence FT', 'Empate FT', 'Fora Vence FT', 'Btts FT',
        'Over 0.5 HT', 'Over 1.5 HT', 'Over 2.5 HT',
        'Over 0.5 FT', 'Over 1.5 FT', 'Over 2.5 FT',
        'Over 3.5 FT', 'Over 4.5 FT', 'Over 5.5 FT'
    ]

    for coluna in colunas_porcentagem:
        if coluna in df_formatado.columns:
            df_formatado[coluna] = df_formatado[coluna].apply(lambda x: f"{x}%" if pd.notna(x) else "0%")

    # Formatar Gols HT e Gols FT com 2 casas decimais
    if 'Gols HT' in df_formatado.columns:
        df_formatado['Gols HT'] = df_formatado['Gols HT'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else "0.00")

    if 'Gols FT' in df_formatado.columns:
        df_formatado['Gols FT'] = df_formatado['Gols FT'].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else "0.00")

    return df_formatado


def load_data() -> pd.DataFrame:
    rows = scrape_page(URL)
    if not rows:
        return pd.DataFrame()

    max_cols = max(len(r) for r in rows)
    for r in rows:
        r.extend([''] * (max_cols - len(r)))
    df = pd.DataFrame(rows)

    if df.shape[1] < 4:
        return pd.DataFrame()

    df = df[df[3].isin(ALLOWED_COMPETITIONS)].reset_index(drop=True)
    df = df.drop(columns=[1])
    df.columns = ["Hora", "Confronto", "Liga"] + \
                 [f"Coluna {i}" for i in range(4, df.shape[1] + 1)]

    def players(txt: str):
        clean = str(txt).replace("Ao Vivo Agora", "").strip()
        m = re.search(r'\(([^)]+)\).*?x.*?\(([^)]+)\)', clean)
        return (m.group(1).strip(), m.group(2).strip()) if m else ("", "")

    df[['Casa', 'Fora']] = df['Confronto'].apply(lambda x: pd.Series(players(x)))
    df = df.drop(columns=['Confronto'])

    liga_map_ao_vivo = {
        "E-soccer - H2H GG League - 8 minutos de jogo": "H2H 8 Min",
        "E-soccer - GT Leagues - 12 mins de jogo": "GT 12 Min",
        "Esoccer Battle Volta - 6 Minutos de Jogo": "Volta 6 Min",
        "E-soccer - Battle - 8 minutos de jogo": "Battle 8 Min"
    }
    df['Liga'] = df['Liga'].replace(liga_map_ao_vivo)

    # Obter dados de resultados para calcular estatísticas
    df_resultados = scrape_resultados()

    # Criar colunas vazias para as estatísticas
    colunas_novas = [
        'Casa Vence HT', 'Empate HT', 'Fora Vence HT', 'Btts HT',
        'Casa Vence FT', 'Empate FT', 'Fora Vence FT', 'Btts FT',
        'Gols HT', 'Gols FT',
        'Over 0.5 HT', 'Over 1.5 HT', 'Over 2.5 HT',
        'Over 0.5 FT', 'Over 1.5 FT', 'Over 2.5 FT',
        'Over 3.5 FT', 'Over 4.5 FT', 'Over 5.5 FT'
    ]

    for coluna in colunas_novas:
        if 'Over' in coluna or 'Gols' in coluna or 'Btts' in coluna:
            df[coluna] = 0.0
        else:
            df[coluna] = 0.0

    # Calcular estatísticas para cada partida
    for idx, row in df.iterrows():
        casa = row['Casa']
        fora = row['Fora']

        if casa and fora:
            # Calcular estatísticas considerando confrontos diretos
            estat_casa = calcular_estatisticas_jogador(casa, df_resultados, fora)
            estat_fora = calcular_estatisticas_jogador(fora, df_resultados, casa)

            # Calcular probabilidades
            casa_vence_ht, empate_ht, fora_vence_ht = calcular_probabilidades(estat_casa, estat_fora, 'ht')
            casa_vence_ft, empate_ft, fora_vence_ft = calcular_probabilidades(estat_casa, estat_fora, 'ft')

            # Calcular médias de gols combinadas com 2 casas decimais
            gols_ht = round((estat_casa['media_gols_ht'] + estat_fora['media_gols_ht']) / 2, 2)
            gols_ft = round((estat_casa['media_gols_ft'] + estat_fora['media_gols_ft']) / 2, 2)

            # Calcular Overs e BTTS combinados
            total_jogos_combinados = max(estat_casa['total_jogos'], estat_fora['total_jogos'])
            estatisticas = calcular_overs_combinados(estat_casa, estat_fora, total_jogos_combinados)

            # Preencher dados
            df.at[idx, 'Casa Vence HT'] = round(casa_vence_ht * 100, 1)
            df.at[idx, 'Empate HT'] = round(empate_ht * 100, 1)
            df.at[idx, 'Fora Vence HT'] = round(fora_vence_ht * 100, 1)
            df.at[idx, 'Btts HT'] = estatisticas['btts_ht']

            df.at[idx, 'Casa Vence FT'] = round(casa_vence_ft * 100, 1)
            df.at[idx, 'Empate FT'] = round(empate_ft * 100, 1)
            df.at[idx, 'Fora Vence FT'] = round(fora_vence_ft * 100, 1)
            df.at[idx, 'Btts FT'] = estatisticas['btts_ft']

            # Garantir 2 casas decimais para Gols HT e Gols FT
            df.at[idx, 'Gols HT'] = gols_ht
            df.at[idx, 'Gols FT'] = gols_ft

            # Preencher Overs
            df.at[idx, 'Over 0.5 HT'] = estatisticas['over_05_ht']
            df.at[idx, 'Over 1.5 HT'] = estatisticas['over_15_ht']
            df.at[idx, 'Over 2.5 HT'] = estatisticas['over_25_ht']

            df.at[idx, 'Over 0.5 FT'] = estatisticas['over_05_ft']
            df.at[idx, 'Over 1.5 FT'] = estatisticas['over_15_ft']
            df.at[idx, 'Over 2.5 FT'] = estatisticas['over_25_ft']
            df.at[idx, 'Over 3.5 FT'] = estatisticas['over_35_ft']
            df.at[idx, 'Over 4.5 FT'] = estatisticas['over_45_ft']
            df.at[idx, 'Over 5.5 FT'] = estatisticas['over_55_ft']

    # Ordem das colunas conforme solicitado
    ordem_colunas = [
        'Hora', 'Liga', 'Casa', 'Fora',
        'Casa Vence HT', 'Empate HT', 'Fora Vence HT', 'Btts HT',
        'Casa Vence FT', 'Empate FT', 'Fora Vence FT', 'Btts FT',
        'Gols HT', 'Over 0.5 HT', 'Over 1.5 HT', 'Over 2.5 HT',
        'Gols FT', 'Over 0.5 FT', 'Over 1.5 FT', 'Over 2.5 FT',
        'Over 3.5 FT', 'Over 4.5 FT', 'Over 5.5 FT'
    ]

    df = df[ordem_colunas + [c for c in df.columns if c not in ordem_colunas]]

    # Formatar o DataFrame antes de retornar
    return formatar_dataframe(df)


@st.cache_data(show_spinner=False, ttl=300)
def load_data_with_update(update_param: int) -> pd.DataFrame:
    return load_data()


@st.cache_data(show_spinner=False, ttl=300)
def scrape_resultados_with_update(update_param: int) -> pd.DataFrame:
    return scrape_resultados()


def aplicar_filtros(df: pd.DataFrame, liga_selecionada: str, over_tipo: str, over_valor: float,
                    porcentagem_minima: float) -> pd.DataFrame:
    """Aplica os filtros selecionados ao DataFrame"""
    df_filtrado = df.copy()

    # Filtro por Liga
    if liga_selecionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Liga'] == liga_selecionada]

    # Converter colunas de porcentagem para valores numéricos para filtragem
    colunas_numericas = [
        'Casa Vence HT', 'Empate HT', 'Fora Vence HT', 'Btts HT',
        'Casa Vence FT', 'Empate FT', 'Fora Vence FT', 'Btts FT',
        'Over 0.5 HT', 'Over 1.5 HT', 'Over 2.5 HT',
        'Over 0.5 FT', 'Over 1.5 FT', 'Over 2.5 FT',
        'Over 3.5 FT', 'Over 4.5 FT', 'Over 5.5 FT'
    ]

    for coluna in colunas_numericas:
        if coluna in df_filtrado.columns:
            df_filtrado[coluna] = df_filtrado[coluna].str.replace('%', '').astype(float)

    # Filtro por Over
    if over_tipo != "Nenhum":
        df_filtrado = df_filtrado[df_filtrado[over_tipo] >= over_valor]

    # Filtro por Porcentagem Mínima
    if porcentagem_minima > 0:
        # Criar uma máscara para qualquer coluna de porcentagem que atinja o mínimo
        mask = False
        for coluna in colunas_numericas:
            if coluna in df_filtrado.columns:
                mask = mask | (df_filtrado[coluna] >= porcentagem_minima)
        df_filtrado = df_filtrado[mask]

    # Converter de volta para formato com %
    for coluna in colunas_numericas:
        if coluna in df_filtrado.columns:
            df_filtrado[coluna] = df_filtrado[coluna].apply(lambda x: f"{x}%")

    return df_filtrado


def main() -> None:
    st.set_page_config(page_title="Simulador FIFA", layout="wide", page_icon="🤖")

    col1, col2 = st.columns([1, 8])
    with col1:
        st.markdown("## 🤖")
    with col2:
        st.markdown("## Simulador FIFA")

    st.markdown("""
    <div style="
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    ">
        <h3 style="margin: 0; font-weight: 600;">🎮 Competições E-Soccer em Tempo Real 🎮</h3>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">Dados atualizados automaticamente das principais ligas virtuais</p>
    </div>
    """, unsafe_allow_html=True)

    # Atualiza a página automaticamente a cada 5 minutos (300 segundos)
    count = st_autorefresh(interval=300000, limit=None, key="auto_refresh")

    # Botão para atualizar manualmente
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        atualizar = st.button("🔄 Atualizar Dados Agora", use_container_width=True)

    # Parâmetro para invalidar cache: 1 se atualizar manual, senão count da auto atualização
    update_param = 1 if atualizar else count

    tab1, tab2 = st.tabs(["🎯 Ao Vivo", "📊 Resultados"])

    with tab1:
        st.markdown("### Partidas Ao Vivo")

        # Carregar dados
        with st.spinner("Carregando dados ao vivo…"):
            df_live = load_data_with_update(update_param)

        if not df_live.empty:
            # Filtros
            st.markdown("---")
            st.markdown("#### 🔍 Filtros")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                ligas_disponiveis = ["Todas"] + sorted(df_live['Liga'].unique().tolist())
                liga_selecionada = st.selectbox("Liga", ligas_disponiveis)

            with col2:
                opcoes_over = [
                    "Nenhum", "Over 0.5 HT", "Over 1.5 HT", "Over 2.5 HT",
                    "Over 0.5 FT", "Over 1.5 FT", "Over 2.5 FT",
                    "Over 3.5 FT", "Over 4.5 FT", "Over 5.5 FT"
                ]
                over_tipo = st.selectbox("Over Gols", opcoes_over)

            with col3:
                over_valor = st.slider("% Mínima Over", 0, 100, 70, help="Porcentagem mínima para o Over selecionado")

            with col4:
                porcentagem_minima = st.slider("% Mínima Geral", 0, 100, 0,
                                               help="Porcentagem mínima em qualquer coluna")

            # Aplicar filtros
            df_filtrado = aplicar_filtros(df_live, liga_selecionada, over_tipo, over_valor, porcentagem_minima)

            st.success(f"**{len(df_filtrado)}** partidas encontradas (de {len(df_live)} totais)")

            # Exibir dataframe
            st.dataframe(df_filtrado, use_container_width=True)

            # Estatísticas rápidas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de Partidas", len(df_live))
            with col2:
                st.metric("Partidas Filtradas", len(df_filtrado))
            with col3:
                if len(df_live) > 0:
                    percentual = (len(df_filtrado) / len(df_live)) * 100
                    st.metric("Taxa de Filtro", f"{percentual:.1f}%")
        else:
            st.info("Nenhuma partida ao vivo encontrada no momento.")

    with tab2:
        st.markdown("### Resultados Recentes")
        with st.spinner("Carregando resultados…"):
            df_res = scrape_resultados_with_update(update_param)

        st.success(f"**{len(df_res)}** linhas de resultados encontradas.")
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)

            # Estatísticas dos resultados
            if 'Liga' in df_res.columns:
                st.markdown("#### 📈 Estatísticas por Liga")
                stats_liga = df_res['Liga'].value_counts()
                col1, col2, col3, col4 = st.columns(4)
                for i, (liga, count) in enumerate(stats_liga.items()):
                    with [col1, col2, col3, col4][i % 4]:
                        st.metric(liga, count)
        else:
            st.info("Nenhum resultado encontrado.")

    st.caption(
        "🔄 Atualização automática a cada 5 minutos | Dependências: requests • pandas • beautifulsoup4 • lxml • streamlit • streamlit-autorefresh")


if __name__ == "__main__":
    main()