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

# Configurações de pagamento PIX
PIX_CPF = "01905990065"
WHATSAPP_NUM = "49991663166"  # Número sem código do país
PIX_AMOUNT = 9.90

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
UPDATE_INTERVAL = 300
last_update_time = time.time()

# ==============================================
# SISTEMA DE AUTENTICAÇÃO
# ==============================================

# Configurações de acesso
SENHA_TESTE = "bl2205"
ACESSO_TESTE_ATIVO = True  # Você controla isso via painel admin


# Dicionário para armazenar acessos 24h
def carregar_acessos_24h():
    """Carrega os acessos 24h do arquivo"""
    try:
        if KEYS_FILE.exists():
            with open(KEYS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except:
        return {}


def salvar_acessos_24h(acessos):
    """Salva os acessos 24h no arquivo"""
    try:
        with open(KEYS_FILE, 'w') as f:
            json.dump(acessos, f, indent=4)
    except Exception as e:
        logger.error(f"Erro ao salvar acessos: {e}")


def gerar_codigo_24h():
    """Gera um código único de 8 caracteres"""
    return hashlib.sha256(f"{datetime.now()}{os.urandom(8)}".encode()).hexdigest()[:8].upper()


def criar_acesso_24h():
    """Cria um novo acesso de 24 horas"""
    codigo = gerar_codigo_24h()
    data_expiracao = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    acessos = carregar_acessos_24h()
    acessos[codigo] = {
        "codigo": codigo,
        "data_criacao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_expiracao": data_expiracao,
        "status": "ativo"
    }

    salvar_acessos_24h(acessos)
    return codigo


def validar_acesso_24h(codigo):
    """Valida se o código de 24h é válido"""
    acessos = carregar_acessos_24h()

    if codigo in acessos:
        dados = acessos[codigo]
        data_expiracao = datetime.strptime(dados["data_expiracao"], "%Y-%m-%d %H:%M:%S")

        if datetime.now() < data_expiracao and dados.get("status") == "ativo":
            return True, dados
        else:
            # Remove código expirado
            del acessos[codigo]
            salvar_acessos_24h(acessos)

    return False, None


def revogar_acesso_24h(codigo):
    """Revoga um acesso 24h"""
    acessos = carregar_acessos_24h()
    if codigo in acessos:
        acessos[codigo]["status"] = "revogado"
        salvar_acessos_24h(acessos)
        return True
    return False


# ==============================================
# TELA DE LOGIN COMPLETA
# ==============================================

def tela_login():
    """Tela de login com dois tipos de acesso"""
    st.set_page_config(
        page_title="FIFAlgorithm - Acesso",
        layout="centered"
    )

    st.markdown("""
    <style>
    .login-container {
        background: linear-gradient(135deg, #0f0f2e 0%, #1a1a3e 100%);
        padding: 30px;
        border-radius: 20px;
        border: 2px solid rgba(100, 150, 255, 0.3);
        max-width: 500px;
        margin: 30px auto;
    }
    .acesso-card {
        background: rgba(255,255,255,0.1);
        padding: 20px;
        border-radius: 15px;
        margin: 15px 0;
        border-left: 4px solid #4CAF50;
    }
    .premium-card {
        background: linear-gradient(135deg, #FFD700, #FFA500);
        color: black;
        padding: 20px;
        border-radius: 15px;
        margin: 15px 0;
        border: 2px solid rgba(255,255,255,0.3);
    }
    .pix-section {
        background: rgba(255,255,255,0.1);
        padding: 15px;
        border-radius: 10px;
        margin: 15px 0;
        border-left: 4px solid #32CD32;
    }
    .admin-panel {
        background: rgba(255,0,0,0.1);
        padding: 15px;
        border-radius: 10px;
        margin: 15px 0;
        border-left: 4px solid #FF0000;
    }
    .step-box {
        background: rgba(255,255,255,0.05);
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        text-align: center;
    }
    @media (max-width: 768px) {
        .login-container {
            padding: 20px;
            margin: 20px 10px;
        }
        .step-box {
            padding: 10px;
            margin: 8px 0;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    # Container principal
    st.markdown("""
    <div class="login-container">
        <div style='text-align: center; margin-bottom: 25px;'>
            <h1 style='color: white; margin-bottom: 10px; font-size: 1.8rem;'>🦅 FIFAlgorithm</h1>
            <p style='color: #e0e0e0; font-size: 0.9rem;'>Sistema Profissional de Análise E-soccer</p>
        </div>
    """, unsafe_allow_html=True)

    # Abas para diferentes tipos de acesso
    tab1, tab2 = st.tabs(["🔐 Acesso Teste", "💎 Acesso 24h - R$20,00"])

    with tab1:
        st.markdown("### Acesso Teste Gratuito")

        if not ACESSO_TESTE_ATIVO:
            st.error("🚫 Acesso teste temporariamente desativado pelo administrador")
        else:
            st.markdown("""
            <div class="acesso-card">
                <h4 style='margin: 0;'>🎯 Acesso Imediato</h4>
                <p style='margin: 5px 0 0 0; font-size: 0.9rem;'>Teste todas as funcionalidades do sistema</p>
            </div>
            """, unsafe_allow_html=True)

            senha = st.text_input("**Senha de teste:**", type="password",
                                  placeholder="Digite a senha de teste...",
                                  key="senha_teste")

            if st.button("🚀 ACESSAR TESTE", use_container_width=True):
                if senha == SENHA_TESTE:
                    st.session_state.authenticated = True
                    st.session_state.tipo_acesso = "teste"
                    st.success("✅ Acesso teste liberado!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta!")

    with tab2:
        st.markdown("### 💎 Acesso Premium 24h")

        st.markdown("""
        <div class="premium-card">
            <h3 style='margin: 0 0 10px 0;'>🚀 ACESSO COMPLETO 24H</h3>
            <h2 style='margin: 0;'>R$ 20,00</h2>
            <p style='margin: 10px 0 0 0; font-size: 0.9rem;'>✅ Todas as funcionalidades liberadas por 24 horas</p>
        </div>
        """, unsafe_allow_html=True)

        # Processo de compra simplificado para mobile
        st.markdown("#### 📋 Como Funciona:")

        st.markdown("""
        <div class="step-box">
            <strong>1️⃣ Pague o PIX</strong>
            <p style='margin: 5px 0 0 0; font-size: 0.8rem;'>Chave: <strong>01905990065</strong></p>
            <p style='margin: 0; font-size: 0.8rem;'>Valor: <strong>R$ 20,00</strong></p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="step-box">
            <strong>2️⃣ Envie Comprovante</strong>
            <p style='margin: 5px 0 0 0; font-size: 0.8rem;'>Via WhatsApp para:</p>
            <p style='margin: 0; font-size: 0.8rem;'><strong>49991663166</strong></p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="step-box">
            <strong>3️⃣ Receba o Código</strong>
            <p style='margin: 5px 0 0 0; font-size: 0.8rem;'>Acesso imediato por 24h</p>
        </div>
        """, unsafe_allow_html=True)

        # Seção PIX simplificada
        st.markdown("---")
        st.markdown("#### 💰 Dados PIX")

        st.markdown(f"""
        <div class="pix-section">
            <div style='text-align: center;'>
                <h4 style='color: #4CAF50; margin: 0;'>Chave PIX (CPF):</h4>
                <h3 style='color: #4CAF50; margin: 10px 0;'>{PIX_CPF}</h3>

                <h4 style='margin: 15px 0 5px 0;'>Valor:</h4>
                <h3 style='color: #4CAF50; margin: 0;'>R$ {PIX_AMOUNT}</h3>

                <p style='margin: 15px 0 5px 0;'><strong>Beneficiário:</strong></p>
                <p style='margin: 0;'><strong>FIFALGORITHM</strong></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Botão WhatsApp otimizado para mobile
        mensagem_whatsapp = f"Olá! Acabei de fazer o PIX de R$ {PIX_AMOUNT} para acesso 24h ao FIFAlgorithm."
        whatsapp_url = f"https://wa.me/55{WHATSAPP_NUM}?text={requests.utils.quote(mensagem_whatsapp)}"

        st.markdown(f"""
        <a href="{whatsapp_url}" target="_blank" style='
            background: linear-gradient(135deg, #25D366, #128C7E); 
            color: white; 
            padding: 12px 20px; 
            border-radius: 10px; 
            text-decoration: none; 
            font-weight: bold; 
            display: block; 
            text-align: center;
            margin: 20px 0;
            font-size: 1rem;
        '>
            📱 ENVIAR COMPROVANTE NO WHATSAPP
        </a>
        """, unsafe_allow_html=True)

        # Área para digitar código de acesso
        st.markdown("---")
        st.markdown("#### 🔑 Já tem seu código de acesso?")

        codigo_acesso = st.text_input("**Código de acesso 24h:**",
                                      placeholder="Digite o código recebido...",
                                      key="codigo_24h").upper()

        if st.button("🚀 ATIVAR ACESSO 24H", use_container_width=True):
            if codigo_acesso:
                valido, dados_acesso = validar_acesso_24h(codigo_acesso)

                if valido:
                    st.session_state.authenticated = True
                    st.session_state.tipo_acesso = "premium_24h"
                    st.session_state.codigo_acesso = codigo_acesso
                    st.session_state.data_expiracao = dados_acesso["data_expiracao"]

                    st.success("✅ Acesso premium ativado por 24 horas!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Código inválido ou expirado!")
            else:
                st.warning("⚠️ Digite o código de acesso")

    st.markdown("</div>", unsafe_allow_html=True)

    # Área administrativa OTIMIZADA PARA MOBILE
    with st.expander("🔧 PAINEL ADMINISTRATIVO (Mobile)"):
        st.markdown("### 🛠 Controle de Acessos")

        # Status atual em cards otimizados para mobile
        col1, col2 = st.columns(2)
        with col1:
            status_teste = "✅ ATIVO" if ACESSO_TESTE_ATIVO else "🚫 BLOQUEADO"
            st.metric("Acesso Teste", status_teste)

        with col2:
            acessos_24h = carregar_acessos_24h()
            acessos_ativos = [k for k, v in acessos_24h.items()
                              if v.get("status") == "ativo" and
                              datetime.now() < datetime.strptime(v["data_expiracao"], "%Y-%m-%d %H:%M:%S")]
            st.metric("Acessos 24h Ativos", len(acessos_ativos))

        # Controles do admin OTIMIZADOS PARA MOBILE
        st.markdown("#### ⚡ Controles Rápidos")

        # Botão único para gerar código (mais fácil no mobile)
        if st.button("🎫 GERAR NOVO CÓDIGO 24h", use_container_width=True):
            novo_codigo = criar_acesso_24h()
            st.success(f"✅ **Código gerado:** `{novo_codigo}`")
            st.info("📋 **Copie e envie para o cliente:**")
            st.code(novo_codigo)

            # Mensagem pronta para WhatsApp
            mensagem_cliente = f"Seu código de acesso FIFAlgorithm é: {novo_codigo}\n\nAcesso válido por 24 horas. Use na aba 'Acesso 24h'."
            whatsapp_cliente_url = f"https://wa.me/55{WHATSAPP_NUM}?text={requests.utils.quote(mensagem_cliente)}"

            st.markdown(f"""
            <a href="{whatsapp_cliente_url}" target="_blank" style='
                background: linear-gradient(135deg, #25D366, #128C7E); 
                color: white; 
                padding: 10px 15px; 
                border-radius: 8px; 
                text-decoration: none; 
                font-weight: bold; 
                display: block; 
                text-align: center;
                margin: 10px 0;
                font-size: 0.9rem;
            '>
                📤 ENVIAR CÓDIGO VIA WHATSAPP
            </a>
            """, unsafe_allow_html=True)

        # Listar e gerenciar acessos 24h OTIMIZADO PARA MOBILE
        st.markdown("#### 📋 Acessos 24h Ativos")

        acessos = carregar_acessos_24h()
        acessos_ativos = []

        for codigo, dados in acessos.items():
            if dados.get("status") == "ativo":
                data_expiracao = datetime.strptime(dados["data_expiracao"], "%Y-%m-%d %H:%M:%S")
                if datetime.now() < data_expiracao:
                    tempo_restante = data_expiracao - datetime.now()
                    horas = int(tempo_restante.total_seconds() // 3600)
                    minutos = int((tempo_restante.total_seconds() % 3600) // 60)
                    acessos_ativos.append({
                        "codigo": codigo,
                        "criacao": dados["data_criacao"],
                        "expira": dados["data_expiracao"],
                        "restante": f"{horas}h {minutos}m"
                    })

        if acessos_ativos:
            for acesso in acessos_ativos:
                # Layout otimizado para mobile
                st.markdown(f"**Código:** `{acesso['codigo']}`")
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"⏳ {acesso['restante']}")
                with col2:
                    if st.button("🗑️ Revogar", key=f"rev_{acesso['codigo']}", use_container_width=True):
                        if revogar_acesso_24h(acesso["codigo"]):
                            st.success("✅ Acesso revogado!")
                            time.sleep(1)
                            st.rerun()
                st.markdown("---")
        else:
            st.info("📭 Nenhum acesso 24h ativo no momento")

        # Instruções para controle do acesso teste
        st.markdown("#### 🔒 Controle Acesso Teste")
        st.info("""
        **Para bloquear/liberar acesso teste:**

        1. Mude `ACESSO_TESTE_ATIVO = True/False` no código
        2. Faça deploy no Streamlit Cloud
        3. O app reiniciará automaticamente
        """)


# ==============================================
# CSS PERSONALIZADO - OTIMIZADO PARA MOBILE
# ==============================================

st.markdown("""
<style>
    /* CSS OTIMIZADO PARA MOBILE */
    @media (max-width: 768px) {
        .main-header h1 {
            font-size: 1.5rem !important;
        }
        .main-header p {
            font-size: 0.9rem !important;
        }
        div[data-testid="stDataFrame"] {
            font-size: 0.8rem;
        }
        .live-indicator {
            padding: 8px 15px;
            font-size: 0.9rem;
        }
        .status-badge {
            padding: 6px 12px;
            font-size: 0.8rem;
        }
    }

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
        0% { transform: scale(1); opacity: 0.8; }
        50% { transform: scale(1.5); opacity: 1; }
        100% { transform: scale(1); opacity: 0.8; }
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

    /* Estilo para AgGrid */
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

    /* Status badge */
    .status-badge {
        padding: 8px 16px;
        border-radius: 20px;
        font-weight: bold;
        text-align: center;
    }
    .status-test {
        background: linear-gradient(135deg, #4CAF50, #45a049);
        color: white;
    }
    .status-premium {
        background: linear-gradient(135deg, #FFD700, #FFA500);
        color: black;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================
# FUNÇÕES DO FIFALGORITHM (MANTIDAS)
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
            "Over Mandante", "Over Visitante",
            "Sugestão HT", "Sugestão FT"
        ]

        return df_clean, df_display[colunas_ao_vivo_solicitadas]

    except Exception as e:
        logger.error(f"Erro ao carregar dados ao vivo: {e}")
        st.error(f"❌ Erro ao carregar e processar dados ao vivo.")
        return pd.DataFrame(), pd.DataFrame()


# ==============================================
# FUNÇÕES AUXILIARES (MANTIDAS)
# ==============================================

def calcular_estatisticas_jogador(df: pd.DataFrame, jogador: str, liga: str) -> dict:
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
    if df_resultados.empty:
        return pd.DataFrame()

    jogador_stats = defaultdict(lambda: {
        "jogos_total": 0, "vitorias": 0, "derrotas": 0, "empates": 0,
        "gols_marcados": 0, "gols_sofridos": 0, "gols_marcados_ht": 0, "gols_sofridos_ht": 0,
        "clean_sheets": 0, "over_05_ht_hits": 0, "over_15_ht_hits": 0, "over_25_ht_hits": 0,
        "btts_ht_hits": 0, "over_05_ft_hits": 0, "over_15_ft_hits": 0, "over_25_ft_hits": 0,
        "over_35_ft_hits": 0, "over_45_ft_hits": 0, "over_55_ft_hits": 0, "over_65_ft_hits": 0,
        "btts_ft_hits": 0, "under_25_ft_hits": 0, "ligas_atuantes": set()
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

    # Converter para DataFrame
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

    df_rankings_base["Ligas Atuantes"] = df_rankings_base["ligas_atuantes"].apply(lambda x: ", ".join(sorted(list(x))))

    return df_rankings_base


def get_recent_player_stats(df_resultados: pd.DataFrame, player_name: str, num_games: int) -> dict:
    player_games = df_resultados[
        (df_resultados["Mandante"] == player_name) | (df_resultados["Visitante"] == player_name)
        ].sort_values("Data", ascending=False).head(num_games).copy()

    if player_games.empty:
        return {}

    stats = {
        "jogos_recentes": len(player_games), "gols_marcados_ft": 0, "gols_sofridos_ft": 0,
        "gols_marcados_ht": 0, "gols_sofridos_ht": 0, "over_05_ht_hits": 0, "over_15_ht_hits": 0,
        "over_25_ht_hits": 0, "btts_ht_hits": 0, "over_05_ft_hits": 0, "over_15_ft_hits": 0,
        "over_25_ft_hits": 0, "over_35_ft_hits": 0, "over_45_ft_hits": 0, "over_55_ft_hits": 0,
        "over_65_ft_hits": 0, "btts_ft_hits": 0, "under_25_ft_hits": 0, "sequencia_vitorias": 0,
        "sequencia_derrotas": 0, "sequencia_empates": 0, "sequencia_btts": 0, "sequencia_over_25_ft": 0
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
    pct_m = h_m / t_m if t_m else 0
    pct_v = h_v / t_v if t_v else 0
    if pct_m >= 0.70 and pct_v >= 0.70:
        return "🟢"
    if pct_m >= 0.60 and pct_v >= 0.60:
        return "🟡"
    return "🔴"


def format_stats(h_m, t_m, h_v, t_v) -> str:
    icon = cor_icon(h_m, t_m, h_v, t_v)
    return f"{icon} {h_m}/{t_m}\n{h_v}/{t_v}"


def format_gols_ht_com_icone_para_display(gols_ht_media: float) -> str:
    if gols_ht_media >= 2.75:
        return f"🟢 {gols_ht_media:.2f}"
    elif 2.62 <= gols_ht_media <= 2.74:
        return f"🟡 {gols_ht_media:.2f}"
    return f"⚪ {gols_ht_media:.2f}"


def sugerir_over_ht(media_gols_ht: float) -> str:
    if media_gols_ht >= 2.75:
        return "Over 2.5 HT"
    elif media_gols_ht >= 2.20:
        return "Over 1.5 HT"
    elif media_gols_ht >= 1.70:
        return "Over 0.5 HT"
    else:
        return "Sem Entrada"


def sugerir_over_ft(media_gols_ft: float) -> str:
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
    global last_update_time
    current_time = time.time()
    if current_time - last_update_time >= UPDATE_INTERVAL:
        last_update_time = current_time
        return True
    return False


# ==============================================
# APLICATIVO PRINCIPAL COM AUTENTICAÇÃO
# ==============================================

def fifalgorithm_app():
    """Aplicativo principal com autenticação"""

    # Verificar autenticação
    if not st.session_state.get("authenticated", False):
        tela_login()
        return

    # Verificar se acesso premium expirou
    if st.session_state.get("tipo_acesso") == "premium_24h":
        codigo = st.session_state.get("codigo_acesso")
        if codigo:
            valido, dados = validar_acesso_24h(codigo)
            if not valido:
                st.error("⏰ Seu acesso de 24h expirou!")
                if st.button("🔄 Voltar ao Login"):
                    st.session_state.authenticated = False
                    st.rerun()
                return

    # Configurar página
    st.set_page_config(
        page_title="FIFAlgorithm - Ao Vivo",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Header com informações do acesso
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.markdown("""
        <div class="main-header">
            <h1>🦅 FIFAlgorithm</h1>
            <p>Análises Inteligentes de Partidas de E-soccer FIFA</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        tipo_acesso = st.session_state.get("tipo_acesso", "teste")
        if tipo_acesso == "premium_24h":
            st.markdown('<div class="status-badge status-premium">💎 PREMIUM 24H</div>', unsafe_allow_html=True)
            # Mostrar tempo restante
            codigo = st.session_state.get("codigo_acesso")
            if codigo:
                acessos = carregar_acessos_24h()
                if codigo in acessos:
                    data_expiracao = datetime.strptime(acessos[codigo]["data_expiracao"], "%Y-%m-%d %H:%M:%S")
                    tempo_restante = data_expiracao - datetime.now()
                    horas = int(tempo_restante.total_seconds() // 3600)
                    minutos = int((tempo_restante.total_seconds() % 3600) // 60)
                    st.write(f"⏳ {horas}h {minutos}m")
        else:
            st.markdown('<div class="status-badge status-test">🎯 ACESSO TESTE</div>', unsafe_allow_html=True)

    with col3:
        if st.button("🚪 Sair"):
            st.session_state.authenticated = False
            st.rerun()

    # Inicia a thread de atualização automática
    start_auto_update()

    brasil_timezone = pytz.timezone("America/Sao_Paulo")
    current_time_br = datetime.now(brasil_timezone).strftime("%H:%M:%S")

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
        df_resultados = pd.DataFrame()
        df_live_clean = pd.DataFrame()
        df_live_display = pd.DataFrame()
        df_stats_all_players = pd.DataFrame()

    # Sistema de abas
    tabs = st.tabs(["⚡️ Ao Vivo", "⭐️ Radar FIFA", "🧠 Alertas IA", "⚽️ Resultados"])

    # Aba 1: Ao Vivo
    with tabs[0]:
        st.header("🔥 Buscar Jogos")

        if not df_live_display.empty:
            st.markdown(f"""
            <div class="live-indicator">
                🟢 AO VIVO - {len(df_live_display)} Jogos Disponíveis
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("⏳ Nenhuma partida ao vivo no momento")

        if not df_live_display.empty:
            with st.sidebar:
                st.subheader("🔍 Filtros Rápidos")

                ligas_disponiveis = df_live_display['Liga'].unique()
                ligas_selecionadas = st.multiselect(
                    'Selecione as Ligas:',
                    options=ligas_disponiveis,
                    default=ligas_disponiveis
                )

                sugestoes_ht = df_live_display['Sugestão HT'].unique()
                ht_selecionados = st.multiselect(
                    'Sugestão HT:',
                    options=sugestoes_ht,
                    default=sugestoes_ht
                )

                sugestoes_ft = df_live_display['Sugestão FT'].unique()
                ft_selecionados = st.multiselect(
                    'Sugestão FT:',
                    options=sugestoes_ft,
                    default=sugestoes_ft
                )

            df_filtrado = df_live_display[
                (df_live_display['Liga'].isin(ligas_selecionadas)) &
                (df_live_display['Sugestão HT'].isin(ht_selecionados)) &
                (df_live_display['Sugestão FT'].isin(ft_selecionados))
                ]

            if len(df_filtrado) > 0:
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    ligas_count = df_filtrado['Liga'].nunique()
                    st.metric("🎯 Ligas", ligas_count)

                with col2:
                    over_ht_count = len(df_filtrado[df_filtrado['Sugestão HT'] != 'Sem Entrada'])
                    st.metric("⚡ Sug. HT", over_ht_count)

                with col3:
                    over_ft_count = len(df_filtrado[df_filtrado['Sugestão FT'] != 'Sem Entrada'])
                    st.metric("🚀 Sug. FT", over_ft_count)

                with col4:
                    over_total = len(df_filtrado[df_filtrado['Over Mandante'] != '']) + len(
                        df_filtrado[df_filtrado['Over Visitante'] != ''])
                    st.metric("💎 Over Jogadores", over_total)

            gb = GridOptionsBuilder.from_dataframe(df_filtrado)
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

            colunas_principais = [
                "Hora", "Liga", "Mandante", "Visitante",
                "GP", "GC", "Over Mandante", "Over Visitante",
                "Sugestão HT", "Sugestão FT"
            ]

            for col in colunas_principais:
                if col in df_filtrado.columns:
                    gb.configure_column(col,
                                        minWidth=80 if col in ["Hora", "GP", "GC"] else 120,
                                        maxWidth=150)

            gb.configure_selection(selection_mode='multiple', use_checkbox=True)
            grid_options = gb.build()

            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            height = min(800, 35 + 35 * len(df_filtrado))

            grid_response = AgGrid(
                df_filtrado[colunas_principais],
                gridOptions=grid_options,
                height=height,
                width='100%',
                theme='streamlit',
                update_mode=GridUpdateMode.MODEL_CHANGED,
                allow_unsafe_jscode=True
            )

            st.markdown('</div>', unsafe_allow_html=True)

            if grid_response['selected_rows']:
                selected_count = len(grid_response['selected_rows'])
                if st.button(f"📊 Analisar {selected_count} Jogos Selecionados", use_container_width=True):
                    st.info(f"Análise iniciada para {selected_count} jogos...")

    # Aba 2: Radar FIFA
    with tabs[1]:
        st.header("⭐️ Radar FIFA")
        st.write("Indicador de Mercados Lucrativos por Liga em tempo Real.")

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

    # Aba 3: Alertas IA
    with tabs[2]:
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

    # Aba 4: Resultados
    with tabs[3]:
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
        # Inicializar session state
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if "tipo_acesso" not in st.session_state:
            st.session_state.tipo_acesso = "teste"

        fifalgorithm_app()

    except Exception as e:
        st.error(f"Erro crítico no aplicativo: {str(e)}")
        st.info("Tente recarregar a página ou verificar sua conexão com a internet.")


if __name__ == "__main__":
    main()