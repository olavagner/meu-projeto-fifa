from __future__ import annotations
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
import re
import numpy as np
from scipy.stats import poisson
from streamlit_autorefresh import st_autorefresh
from typing import Dict, List

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


class PoissonMonteCarloPredictor:
    def __init__(self, num_simulacoes=5000):
        self.num_simulacoes = num_simulacoes
        self.max_gols = 8

    def calcular_lambda_ponderado(self, jogador: str, confrontos: pd.DataFrame, forma: pd.DataFrame,
                                  df_resultados: pd.DataFrame) -> float:
        """Calcula lambda Poisson com pesos para confrontos + forma recente"""

        # ANALISAR CONFRONTOS DIRETOS
        if not confrontos.empty:
            estat_confrontos = self.analisar_desempenho_jogos(jogador, confrontos)
            lambda_confrontos = estat_confrontos['media_gols_feitos_ft']
            peso_confrontos = min(0.5, 0.3 + (len(confrontos) * 0.04))
        else:
            lambda_confrontos = 0
            peso_confrontos = 0

        # ANALISAR FORMA RECENTE
        estat_forma = self.analisar_desempenho_jogos(jogador, forma)
        lambda_forma = estat_forma['media_gols_feitos_ft']
        peso_forma = 0.35

        # ANALISAR HISTÓRICO GERAL (base)
        historico = self.obter_ultimos_jogos_gerais(jogador, df_resultados, 20)
        estat_historico = self.analisar_desempenho_jogos(jogador, historico)
        lambda_historico = estat_historico['media_gols_feitos_ft']
        peso_historico = 0.15

        # CALCULAR LAMBDA FINAL
        pesos_total = peso_confrontos + peso_forma + peso_historico
        if pesos_total > 0:
            lambda_final = (
                                   (lambda_confrontos * peso_confrontos) +
                                   (lambda_forma * peso_forma) +
                                   (lambda_historico * peso_historico)
                           ) / pesos_total
        else:
            lambda_final = 1.5  # Default

        return max(0.3, min(lambda_final, 3.5))

    def analisar_desempenho_jogos(self, jogador: str, jogos: pd.DataFrame) -> Dict:
        """Analisa desempenho em um conjunto de jogos"""
        if jogos.empty:
            return {'media_gols_feitos_ft': 1.5, 'media_gols_sofridos_ft': 1.5}

        gols_feitos = 0
        gols_sofridos = 0

        for _, jogo in jogos.iterrows():
            eh_mandante = jogo['Mandante'] == jogador

            try:
                if eh_mandante:
                    gols_feitos += int(jogo['Mandante FT']) if jogo['Mandante FT'] not in ['', 'NaN'] else 0
                    gols_sofridos += int(jogo['Visitante FT']) if jogo['Visitante FT'] not in ['', 'NaN'] else 0
                else:
                    gols_feitos += int(jogo['Visitante FT']) if jogo['Visitante FT'] not in ['', 'NaN'] else 0
                    gols_sofridos += int(jogo['Mandante FT']) if jogo['Mandante FT'] not in ['', 'NaN'] else 0
            except (ValueError, TypeError):
                continue

        total_jogos = len(jogos)
        return {
            'media_gols_feitos_ft': gols_feitos / total_jogos if total_jogos > 0 else 1.5,
            'media_gols_sofridos_ft': gols_sofridos / total_jogos if total_jogos > 0 else 1.5
        }

    def obter_ultimos_jogos_gerais(self, jogador: str, df_resultados: pd.DataFrame, limite: int) -> pd.DataFrame:
        """Busca últimos jogos gerais"""
        jogos = df_resultados[
            (df_resultados['Mandante'] == jogador) |
            (df_resultados['Visitante'] == jogador)
            ].sort_values('Data', ascending=False).head(limite)
        return jogos

    def simular_monte_carlo_avancado(self, lambda_casa: float, lambda_fora: float) -> Dict:
        """Simulação Monte Carlo completa"""

        resultados = {
            'over_05_ht': 0, 'over_15_ht': 0, 'over_25_ht': 0,
            'over_05_ft': 0, 'over_15_ft': 0, 'over_25_ft': 0,
            'over_35_ft': 0, 'over_45_ft': 0, 'over_55_ft': 0,
            'btts_ht': 0, 'btts_ft': 0,
            'vitorias_casa': 0, 'empates': 0, 'vitorias_fora': 0
        }

        for _ in range(self.num_simulacoes):
            # Simular gols FT com Poisson
            gols_casa_ft = np.random.poisson(lambda_casa)
            gols_fora_ft = np.random.poisson(lambda_fora)

            gols_casa_ft = min(gols_casa_ft, self.max_gols)
            gols_fora_ft = min(gols_fora_ft, self.max_gols)

            # Simular HT (40% dos gols em média)
            gols_casa_ht = np.random.binomial(gols_casa_ft, 0.4)
            gols_fora_ht = np.random.binomial(gols_fora_ft, 0.4)

            # Analisar HT
            total_ht = gols_casa_ht + gols_fora_ht
            if total_ht > 0.5: resultados['over_05_ht'] += 1
            if total_ht > 1.5: resultados['over_15_ht'] += 1
            if total_ht > 2.5: resultados['over_25_ht'] += 1
            if gols_casa_ht > 0 and gols_fora_ht > 0: resultados['btts_ht'] += 1

            # Analisar FT
            total_ft = gols_casa_ft + gols_fora_ft
            if total_ft > 0.5: resultados['over_05_ft'] += 1
            if total_ft > 1.5: resultados['over_15_ft'] += 1
            if total_ft > 2.5: resultados['over_25_ft'] += 1
            if total_ft > 3.5: resultados['over_35_ft'] += 1
            if total_ft > 4.5: resultados['over_45_ft'] += 1
            if total_ft > 5.5: resultados['over_55_ft'] += 1
            if gols_casa_ft > 0 and gols_fora_ft > 0: resultados['btts_ft'] += 1

            # Resultado final
            if gols_casa_ft > gols_fora_ft:
                resultados['vitorias_casa'] += 1
            elif gols_casa_ft == gols_fora_ft:
                resultados['empates'] += 1
            else:
                resultados['vitorias_fora'] += 1

        return self._calcular_probabilidades_finais(resultados)

    def _calcular_probabilidades_finais(self, resultados: Dict) -> Dict:
        """Calcula probabilidades finais"""
        total = self.num_simulacoes

        return {
            'over_05_ht': (resultados['over_05_ht'] / total) * 100,
            'over_15_ht': (resultados['over_15_ht'] / total) * 100,
            'over_25_ht': (resultados['over_25_ht'] / total) * 100,
            'over_05_ft': (resultados['over_05_ft'] / total) * 100,
            'over_15_ft': (resultados['over_15_ft'] / total) * 100,
            'over_25_ft': (resultados['over_25_ft'] / total) * 100,
            'over_35_ft': (resultados['over_35_ft'] / total) * 100,
            'over_45_ft': (resultados['over_45_ft'] / total) * 100,
            'over_55_ft': (resultados['over_55_ft'] / total) * 100,
            'btts_ht': (resultados['btts_ht'] / total) * 100,
            'btts_ft': (resultados['btts_ft'] / total) * 100,
            'casa_vence': (resultados['vitorias_casa'] / total) * 100,
            'empate': (resultados['empates'] / total) * 100,
            'fora_vence': (resultados['vitorias_fora'] / total) * 100
        }


# FUNÇÕES AUXILIARES
def obter_confrontos_diretos(jogador1: str, jogador2: str, df_resultados: pd.DataFrame,
                             limite: int = 5) -> pd.DataFrame:
    """Busca últimos confrontos diretos entre dois jogadores"""
    confrontos = df_resultados[
        ((df_resultados['Mandante'] == jogador1) & (df_resultados['Visitante'] == jogador2)) |
        ((df_resultados['Mandante'] == jogador2) & (df_resultados['Visitante'] == jogador1))
        ].sort_values('Data', ascending=False).head(limite)
    return confrontos


def obter_ultimos_jogos_gerais(jogador: str, df_resultados: pd.DataFrame, limite: int = 10,
                               excluir: pd.DataFrame = None) -> pd.DataFrame:
    """Busca últimos jogos gerais excluindo confrontos já considerados"""
    todos_jogos = df_resultados[
        (df_resultados['Mandante'] == jogador) |
        (df_resultados['Visitante'] == jogador)
        ].sort_values('Data', ascending=False)

    if excluir is not None and not excluir.empty:
        mask = ~todos_jogos.index.isin(excluir.index)
        todos_jogos = todos_jogos[mask]

    return todos_jogos.head(limite)


def calcular_estatisticas_jogador(jogador: str, jogos: pd.DataFrame) -> Dict:
    """Calcula estatísticas básicas do jogador"""
    if jogos.empty:
        return {
            'vitorias': 0, 'empates': 0, 'derrotas': 0,
            'forma': 0, 'record': "0-0-0", 'forma_emoji': "⚡0%"
        }

    vitorias = empates = derrotas = 0

    for _, jogo in jogos.iterrows():
        eh_mandante = jogo['Mandante'] == jogador

        try:
            if eh_mandante:
                gols_feito = int(jogo['Mandante FT']) if jogo['Mandante FT'] not in ['', 'NaN', None] else 0
                gols_sofrido = int(jogo['Visitante FT']) if jogo['Visitante FT'] not in ['', 'NaN', None] else 0
            else:
                gols_feito = int(jogo['Visitante FT']) if jogo['Visitante FT'] not in ['', 'NaN', None] else 0
                gols_sofrido = int(jogo['Mandante FT']) if jogo['Mandante FT'] not in ['', 'NaN', None] else 0

            if gols_feito > gols_sofrido:
                vitorias += 1
            elif gols_feito == gols_sofrido:
                empates += 1
            else:
                derrotas += 1

        except (ValueError, TypeError):
            continue

    total_jogos = len(jogos)
    forma = (vitorias / total_jogos * 100) if total_jogos > 0 else 0

    # ✅ GARANTIR QUE TODAS AS CHAVES ESTEJAM SEMPRE PRESENTES
    return {
        'vitorias': vitorias,
        'empates': empates,
        'derrotas': derrotas,
        'forma': forma,
        'record': f"{vitorias}-{empates}-{derrotas}",
        'forma_emoji': f"⚡{forma:.0f}%"
    }


def identificar_valor_aposta(previsao: Dict, confianca: float) -> str:
    """Identifica oportunidades de valor"""
    if confianca < 70:
        return ""

    if (previsao['over_25_ft'] > 70 and
            previsao['btts_ft'] > 65 and
            confianca > 85):
        return "💎"
    elif (previsao['over_25_ft'] > 65 or
          previsao['btts_ft'] > 60) and confianca > 75:
        return "🔶"
    else:
        return ""


def calcular_confianca(confrontos: pd.DataFrame, forma_casa: pd.DataFrame, forma_fora: pd.DataFrame) -> float:
    """Calcula confiança baseada na qualidade dos dados"""
    confianca = 50  # Base

    # Bônus por confrontos diretos
    if len(confrontos) >= 3:
        confianca += 20
    elif len(confrontos) >= 1:
        confianca += 10

    # Bônus por forma recente
    if len(forma_casa) >= 8 and len(forma_fora) >= 8:
        confianca += 20
    elif len(forma_casa) >= 5 and len(forma_fora) >= 5:
        confianca += 10

    return min(95, confianca)


def formatar_porcentagem(valor: float) -> str:
    """Formata porcentagem com cor"""
    if valor >= 70:
        return f"🟢 {valor:.1f}%"
    elif valor >= 55:
        return f"🟡 {valor:.1f}%"
    else:
        return f"🔴 {valor:.1f}%"


# FUNÇÕES ORIGINAIS DO SEU CÓDIGO (mantidas intactas)
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


def aplicar_previsoes_avancadas(df_live: pd.DataFrame, df_resultados: pd.DataFrame) -> pd.DataFrame:
    """Aplica previsões Poisson + Monte Carlo aos dados ao vivo"""
    if df_live.empty:
        return df_live

    # Inicializar predictor
    predictor = PoissonMonteCarloPredictor(num_simulacoes=5000)

    # CORREÇÃO PRINCIPAL: Definir a ordem EXATA das colunas conforme solicitado
    ordem_colunas = [
        'Hora', 'Liga', 'Mandante', 'Visitante',
        'Casa Vence', 'Empate', 'Fora Vence',
        'xG Casa', 'xG Fora', 'Valor', 'Confiança',
        'Over 0.5 HT', 'Over 1.5 HT', 'Over 2.5 HT', 'BTTS HT',
        'Over 0.5 FT', 'Over 1.5 FT', 'Over 2.5 FT', 'Over 3.5 FT',
        'Over 4.5 FT', 'Over 5.5 FT', 'BTTS FT'
    ]

    # Inicializar todas as colunas
    for coluna in ordem_colunas:
        if coluna not in df_live.columns:
            df_live[coluna] = ""

    # Calcular previsões para cada partida
    for idx, row in df_live.iterrows():
        casa = row['Mandante']
        fora = row['Visitante']

        if casa and fora:
            try:
                # Buscar dados focados da aba Resultados
                confrontos = obter_confrontos_diretos(casa, fora, df_resultados, 5)
                forma_casa = obter_ultimos_jogos_gerais(casa, df_resultados, 10, confrontos)
                forma_fora = obter_ultimos_jogos_gerais(fora, df_resultados, 10, confrontos)

                # Calcular estatísticas dos jogadores
                estat_casa = calcular_estatisticas_jogador(casa, forma_casa)
                estat_fora = calcular_estatisticas_jogador(fora, forma_fora)

                # Calcular lambda Poisson
                lambda_casa = predictor.calcular_lambda_ponderado(casa, confrontos, forma_casa, df_resultados)
                lambda_fora = predictor.calcular_lambda_ponderado(fora, confrontos, forma_fora, df_resultados)

                # Simular Monte Carlo
                simulacoes = predictor.simular_monte_carlo_avancado(lambda_casa, lambda_fora)

                # Calcular confiança e valor
                confianca = calcular_confianca(confrontos, forma_casa, forma_fora)
                valor = identificar_valor_aposta(simulacoes, confianca)

                # Preencher dados principais
                df_live.at[idx, 'Mandante'] = f"{casa} ({estat_casa['record']}) {estat_casa['forma_emoji']}"
                df_live.at[idx, 'Visitante'] = f"{fora} ({estat_fora['record']}) {estat_fora['forma_emoji']}"
                df_live.at[idx, 'xG Casa'] = f"{lambda_casa:.1f}"
                df_live.at[idx, 'xG Fora'] = f"{lambda_fora:.1f}"
                df_live.at[idx, 'Valor'] = valor
                df_live.at[idx, 'Confiança'] = f"{confianca:.0f}%"

                # Preencher colunas de resultados
                df_live.at[idx, 'Casa Vence'] = formatar_porcentagem(simulacoes['casa_vence'])
                df_live.at[idx, 'Empate'] = formatar_porcentagem(simulacoes['empate'])
                df_live.at[idx, 'Fora Vence'] = formatar_porcentagem(simulacoes['fora_vence'])
                df_live.at[idx, 'Over 0.5 HT'] = formatar_porcentagem(simulacoes['over_05_ht'])
                df_live.at[idx, 'Over 1.5 HT'] = formatar_porcentagem(simulacoes['over_15_ht'])
                df_live.at[idx, 'Over 2.5 HT'] = formatar_porcentagem(simulacoes['over_25_ht'])
                df_live.at[idx, 'BTTS HT'] = formatar_porcentagem(simulacoes['btts_ht'])
                df_live.at[idx, 'Over 0.5 FT'] = formatar_porcentagem(simulacoes['over_05_ft'])
                df_live.at[idx, 'Over 1.5 FT'] = formatar_porcentagem(simulacoes['over_15_ft'])
                df_live.at[idx, 'Over 2.5 FT'] = formatar_porcentagem(simulacoes['over_25_ft'])
                df_live.at[idx, 'Over 3.5 FT'] = formatar_porcentagem(simulacoes['over_35_ft'])
                df_live.at[idx, 'Over 4.5 FT'] = formatar_porcentagem(simulacoes['over_45_ft'])
                df_live.at[idx, 'Over 5.5 FT'] = formatar_porcentagem(simulacoes['over_55_ft'])
                df_live.at[idx, 'BTTS FT'] = formatar_porcentagem(simulacoes['btts_ft'])

            except Exception as e:
                print(f"Erro ao processar {casa} vs {fora}: {e}")
                # Preencher com valores padrão em caso de erro
                df_live.at[idx, 'Confiança'] = "0%"
                continue

    # CORREÇÃO FINAL: Garantir a ordem exata das colunas e incluir quaisquer colunas extras
    colunas_existentes = [col for col in ordem_colunas if col in df_live.columns]
    colunas_restantes = [col for col in df_live.columns if col not in ordem_colunas]

    df_live = df_live[colunas_existentes + colunas_restantes]

    return df_live


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

    df[['Mandante', 'Visitante']] = df['Confronto'].apply(lambda x: pd.Series(players(x)))
    df = df.drop(columns=['Confronto'])

    liga_map_ao_vivo = {
        "E-soccer - H2H GG League - 8 minutos de jogo": "H2H 8 Min",
        "E-soccer - GT Leagues - 12 mins de jogo": "GT 12 Min",
        "Esoccer Battle Volta - 6 Minutos de Jogo": "Volta 6 Min",
        "E-soccer - Battle - 8 minutos de jogo": "Battle 8 Min"
    }
    df['Liga'] = df['Liga'].replace(liga_map_ao_vivo)

    ordem = ['Hora', 'Liga', 'Mandante', 'Visitante']
    df = df[ordem + [c for c in df.columns if c not in ordem]]
    return df


@st.cache_data(show_spinner=False, ttl=300)
def load_data_with_update(update_param: int) -> pd.DataFrame:
    return load_data()


@st.cache_data(show_spinner=False, ttl=300)
def scrape_resultados_with_update(update_param: int) -> pd.DataFrame:
    return scrape_resultados()


def aplicar_filtros(df: pd.DataFrame, liga_selecionada: str, filtro_valor: str, confianca_minima: int) -> pd.DataFrame:
    """Aplica filtros ao DataFrame"""
    df_filtrado = df.copy()

    # Filtro por Liga
    if liga_selecionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Liga'] == liga_selecionada]

    # Filtro por Valor
    if filtro_valor == "Apenas 💎 Diamante":
        df_filtrado = df_filtrado[df_filtrado['Valor'] == "💎"]
    elif filtro_valor == "💎 Diamante + 🔶 Laranja":
        df_filtrado = df_filtrado[df_filtrado['Valor'].isin(["💎", "🔶"])]

    # Filtro por Confiança
    if confianca_minima > 0:
        # Criar coluna temporária com tratamento de erros
        confianca_numerica = []
        for conf in df_filtrado['Confiança']:
            try:
                if conf and str(conf).strip() != '':
                    valor = float(str(conf).replace('%', '').strip())
                else:
                    valor = 0.0
            except (ValueError, AttributeError):
                valor = 0.0
            confianca_numerica.append(valor)

        df_filtrado = df_filtrado[pd.Series(confianca_numerica) >= confianca_minima]

    return df_filtrado


def main() -> None:
    st.set_page_config(page_title="Simulador FIFA", layout="wide", page_icon="🤖")

    col1, col2 = st.columns([1, 8])
    with col1:
        st.markdown("## 🤖")
    with col2:
        st.markdown("## Simulador FIFA - Previsões Avançadas")

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
        <h3 style="margin: 0; font-weight: 600;">🎮 Sistema Poisson + Monte Carlo 🎮</h3>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">Previsões baseadas em confrontos diretos + forma recente</p>
    </div>
    """, unsafe_allow_html=True)

    # Atualiza a página automaticamente a cada 60 segundos
    count = st_autorefresh(interval=60000, limit=None, key="auto_refresh")

    # Botão para atualizar manualmente
    atualizar = st.button("🔄 Atualizar Dados")

    # Parâmetro para invalidar cache: 1 se atualizar manual, senão count da auto atualização
    update_param = 1 if atualizar else count

    tab1, tab2 = st.tabs(["🎯 Ao Vivo - Previsões", "📊 Resultados"])

    with tab1:
        st.markdown("### 🎯 Partidas Ao Vivo - Previsões Avançadas")

        with st.spinner("Carregando dados ao vivo e aplicando previsões…"):
            df_live = load_data_with_update(update_param)
            df_resultados = scrape_resultados_with_update(update_param)

            # APLICAR PREVISÕES AVANÇADAS
            df_live_com_previsoes = aplicar_previsoes_avancadas(df_live, df_resultados)

        st.success(f"{len(df_live_com_previsoes)} partidas ao vivo encontradas.")

        if not df_live_com_previsoes.empty:
            # Filtros
            st.markdown("---")
            st.markdown("#### 🔍 Filtros Inteligentes")

            col1, col2, col3 = st.columns(3)

            with col1:
                ligas_disponiveis = ["Todas"] + sorted(df_live_com_previsoes['Liga'].unique().tolist())
                liga_selecionada = st.selectbox("Liga", ligas_disponiveis)

            with col2:
                opcoes_valor = [
                    "Todas as Partidas",
                    "Apenas 💎 Diamante",
                    "💎 Diamante + 🔶 Laranja"
                ]
                filtro_valor = st.selectbox("Oportunidades", opcoes_valor)

            with col3:
                confianca_minima = st.slider("Confiança Mínima", 0, 95, 70)

            # Aplicar filtros
            df_filtrado = aplicar_filtros(df_live_com_previsoes, liga_selecionada, filtro_valor, confianca_minima)

            st.success(f"**{len(df_filtrado)}** partidas filtradas")

            # Exibir dataframe
            st.dataframe(df_filtrado, use_container_width=True)

            # Estatísticas
            if not df_filtrado.empty:
                st.markdown("#### 📊 Estatísticas das Previsões")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    oportunidades_diamante = len(df_filtrado[df_filtrado['Valor'] == "💎"])
                    st.metric("Oportunidades 💎", oportunidades_diamante)

                with col2:
                    # Calcular confiança média com tratamento de erro
                    confiancas = []
                    for conf in df_filtrado['Confiança']:
                        try:
                            if conf and str(conf).strip() != '':
                                valor = float(str(conf).replace('%', '').strip())
                                confiancas.append(valor)
                        except:
                            continue
                    avg_confianca = np.mean(confiancas) if confiancas else 0
                    st.metric("Confiança Média", f"{avg_confianca:.1f}%")

                with col3:
                    # Extrair porcentagem de Over 2.5 com tratamento de erro
                    over_25_values = []
                    for over in df_filtrado['Over 2.5 FT']:
                        try:
                            if over and '🟢' in over or '🟡' in over or '🔴' in over:
                                valor = float(re.findall(r'([\d.]+)%', over)[0])
                                over_25_values.append(valor)
                        except:
                            continue
                    avg_over_25 = np.mean(over_25_values) if over_25_values else 0
                    st.metric("Avg Over 2.5", f"{avg_over_25:.1f}%")

                with col4:
                    st.metric("Simulações/Partida", "5,000")
        else:
            st.info("Nenhuma partida ao vivo encontrada no momento.")

    with tab2:
        st.markdown("### 📊 Resultados Recentes")
        with st.spinner("Carregando resultados…"):
            df_res = scrape_resultados_with_update(update_param)

        st.success(f"{len(df_res)} linhas de resultados encontradas.")
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)
        else:
            st.info("Nenhum resultado encontrado.")

    st.caption("🎯 Poisson + Monte Carlo | ⚡ Confrontos Diretos + Forma Recente | 🔄 Atualização automática")


if __name__ == "__main__":
    main()