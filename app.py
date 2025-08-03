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
import base64  # <--- ADICIONE ESTA LINHA AQUI

# ==============================================
# CONFIGURAÇÕES INICIAIS
# ==============================================

# Configurações de diretório e arquivos
DATA_DIR = Path("auth_data")
DATA_DIR.mkdir(exist_ok=True)

KEYS_FILE = DATA_DIR / "keys.json"
USAGE_FILE = DATA_DIR / "usage.json"
SALES_FILE = DATA_DIR / "sales.json"

# Configuração de segurança
SECRET_KEY = "bl220586"  # Chave para acesso admin (altere para uma chave segura)

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


# ==============================================
# FUNÇÕES DE AUTENTICAÇÃO E GERENCIAMENTO
# ==============================================

def hash_key(key: str) -> str:
    """Cria hash SHA256 da chave para armazenamento seguro"""
    return hashlib.sha256((key + SECRET_KEY).encode()).hexdigest()


def load_keys() -> dict:
    """Carrega as chaves existentes do arquivo"""
    if KEYS_FILE.exists():
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_keys(keys: dict) -> None:
    """Salva as chaves no arquivo"""
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f)


def load_usage() -> dict:
    """Carrega os dados de uso"""
    if USAGE_FILE.exists():
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_usage(usage: dict) -> None:
    """Salva os dados de uso"""
    with open(USAGE_FILE, "w") as f:
        json.dump(usage, f)


def load_sales() -> list:
    """Carrega o histórico de vendas"""
    if SALES_FILE.exists():
        with open(SALES_FILE, "r") as f:
            return json.load(f)
    return []


def save_sales(sales: list) -> None:
    """Salva o histórico de vendas"""
    with open(SALES_FILE, "w") as f:
        json.dump(sales, f)


def generate_key(days_valid: int, owner: str = "admin", notes: str = "") -> str:
    """Gera uma nova chave de acesso"""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    key = ''.join(secrets.choice(alphabet) for _ in range(16))

    creation_date = datetime.now(pytz.utc).isoformat()
    expiration_date = (datetime.now(pytz.utc) + timedelta(days=days_valid)).isoformat()

    keys = load_keys()
    hashed_key = hash_key(key)

    keys[hashed_key] = {
        "owner": owner,
        "notes": notes,
        "days_valid": days_valid,
        "created": creation_date,
        "expires": expiration_date,
        "active": True
    }

    save_keys(keys)
    return key


def validate_key(key: str) -> Optional[dict]:
    """Valida uma chave de acesso"""
    hashed_key = hash_key(key)
    keys = load_keys()

    if hashed_key not in keys:
        return None

    key_data = keys[hashed_key]

    if not key_data.get("active", True):
        return None

    expiration_date = datetime.fromisoformat(key_data["expires"])
    if datetime.now(pytz.utc) > expiration_date:
        return None

    # Registra o uso
    usage = load_usage()
    if hashed_key not in usage:
        usage[hashed_key] = {
            "first_used": datetime.now(pytz.utc).isoformat(),
            "last_used": datetime.now(pytz.utc).isoformat(),
            "usage_count": 1
        }
    else:
        usage[hashed_key]["last_used"] = datetime.now(pytz.utc).isoformat()
        usage[hashed_key]["usage_count"] += 1

    save_usage(usage)

    return {
        "key": key,
        "hashed_key": hashed_key,
        "owner": key_data["owner"],
        "created": key_data["created"],
        "expires": key_data["expires"],
        "days_valid": key_data["days_valid"],
        "notes": key_data["notes"],
        "remaining_days": (expiration_date - datetime.now(pytz.utc)).days
    }


def revoke_key(hashed_key: str) -> bool:
    """Revoga uma chave de acesso"""
    keys = load_keys()
    if hashed_key in keys:
        keys[hashed_key]["active"] = False
        save_keys(keys)
        return True
    return False


def get_all_keys() -> list:
    """Obtém todas as chaves com informações de uso"""
    keys = load_keys()
    usage = load_usage()

    result = []
    for hashed_key, key_data in keys.items():
        key_info = {
            "hashed_key": hashed_key,
            "owner": key_data["owner"],
            "created": key_data["created"],
            "expires": key_data["expires"],
            "days_valid": key_data["days_valid"],
            "notes": key_data["notes"],
            "active": key_data["active"],
            "usage_count": 0,
            "first_used": "Nunca",
            "last_used": "Nunca"
        }

        if hashed_key in usage:
            key_info.update({
                "usage_count": usage[hashed_key]["usage_count"],
                "first_used": usage[hashed_key]["first_used"],
                "last_used": usage[hashed_key]["last_used"]
            })

        result.append(key_info)

    return result


def register_sale(days: int, price: float, buyer_info: dict, key_generated: str) -> None:
    """Registra uma venda no histórico"""
    sales = load_sales()

    sale_record = {
        "date": datetime.now(pytz.utc).isoformat(),
        "days": days,
        "price": price,
        "buyer": buyer_info,
        "key": hash_key(key_generated),
        "status": "pending"
    }

    sales.append(sale_record)
    save_sales(sales)


# ==============================================
# FUNÇÕES DE PAGAMENTO PIX
# ==============================================

def generate_pix_qr(payment_info: str) -> Optional[BytesIO]:
    """Gera QR Code para pagamento PIX"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(payment_info)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Erro ao gerar QR Code: {e}")
        return None


def generate_pix_payment(payer_name: str, amount: float) -> dict:
    """Gera os dados para pagamento via PIX com tratamento de erros"""
    try:
        # Formata o valor
        amount_str = f"{amount:.2f}"

        # Código PIX
        pix_code = (
            f"00020126580014BR.GOV.BCB.PIX0136{PIX_CPF}52040000530398654{amount_str[:5]}"
            f"5802BR5925FIFALGORITHM6005LAGES62070503***6304"
        )

        # Gera QR Code
        qr_img = generate_pix_qr(pix_code)

        return {
            "qr_code": qr_img if qr_img else None,  # Já é BytesIO, não precisa converter
            "pix_code": pix_code,
            "pix_key": PIX_CPF,
            "amount": amount_str,
            "beneficiary": "FIFAlgorithm"
        }
    except Exception as e:
        st.error(f"Erro no pagamento PIX: {e}")
        return {
            "qr_code": None,
            "pix_code": "",
            "pix_key": PIX_CPF,
            "amount": f"{amount:.2f}",
            "beneficiary": "FIFAlgorithm"
        }
    except Exception as e:
        st.error(f"Erro no pagamento PIX: {e}")
        return {
            "qr_code": None,
            "pix_code": "",
            "pix_key": PIX_CPF,
            "amount": f"{amount:.2f}",
            "beneficiary": "FIFAlgorithm"
        }


# ==============================================
# INTERFACES DE USUÁRIO
# ==============================================

def login_page() -> None:
    """Página de login e compra de acesso"""
    st.title("⚡️ Acesso ao FIFAlgorithm 🎮")

    # CSS personalizado
    st.markdown("""
    <style>
        .stTextInput input {
            font-size: 18px !important;
            padding: 10px !important;
        }
        .stButton button {
            width: 100%;
            padding: 10px;
            font-size: 18px;
        }
        .plan-box {
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            background-color: #f9f9f9;
        }
        .plan-title {
            font-weight: bold;
            font-size: 18px;
            color: #2e86de;
        }
        .plan-price {
            font-size: 24px;
            font-weight: bold;
            color: #10ac84;
        }
        .pix-container {
            border: 2px solid #32CD32;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
            background-color: #f0fff0;
        }
        .whatsapp-btn {
            background-color: #25D366;
            color: white;
            border-radius: 5px;
            padding: 10px 15px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            margin-top: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Formulário de login
    with st.form("login_form"):
        key = st.text_input("Digite sua chave de acesso:", type="password")
        submitted = st.form_submit_button("Acessar Sistema")

        if submitted:
            if not key:
                st.error("Por favor, insira uma chave de acesso")
            else:
                key_info = validate_key(key)
                if key_info:
                    st.session_state["authenticated"] = True
                    st.session_state["key_info"] = key_info
                    st.session_state["current_tab"] = "⚡️ Ao Vivo"
                    st.rerun()
                else:
                    st.error("Chave inválida ou expirada. Compre um novo acesso abaixo.")

    # Seção de compra de acesso via PIX (só mostra se não estiver autenticado)
    if not st.session_state.get("authenticated", False):
        st.markdown("---")
        st.header("🔑 Comprar Novo Acesso via PIX")

        # Inicializa os dados do cliente se não existirem
        if "dados_cliente" not in st.session_state:
            st.session_state.dados_cliente = {
                "nome": "",
                "email": "",
                "whatsapp": "",
                "plano": None
            }

        # Planos disponíveis
        planos = [
            {"dias": 1, "preco": 15, "nome": "1 Dia"},
            {"dias": 7, "preco": 30, "nome": "7 Dias"},
            {"dias": 15, "preco": 45, "nome": "15 Dias"},
            {"dias": 30, "preco": 70, "nome": "30 Dias"}
        ]

        # Mostra os planos em colunas
        cols = st.columns(4)
        for i, plano in enumerate(planos):
            with cols[i]:
                with st.container():
                    st.markdown(f'<div class="plan-title">{plano["nome"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="plan-price">R$ {plano["preco"]},00</div>', unsafe_allow_html=True)
                    if st.button(f"Selecionar {plano['nome']}", key=f"plano_{i}"):
                        st.session_state.plano_selecionado = plano
                        st.session_state.dados_cliente["plano"] = plano
                        st.rerun()

        # Mostrar detalhes do PIX se um plano foi selecionado
        if "plano_selecionado" in st.session_state:
            plano = st.session_state["plano_selecionado"]
            st.markdown("---")
            st.subheader("💰 Pagamento via PIX")

            # Formulário de dados do cliente
            with st.form("dados_cliente_form"):
                st.write(f"Plano selecionado: {plano['nome']} - R$ {plano['preco']},00")

                nome = st.text_input("Nome Completo*", value=st.session_state.dados_cliente["nome"])
                email = st.text_input("E-mail*", value=st.session_state.dados_cliente["email"])
                whatsapp = st.text_input("WhatsApp (com DDD)*",
                                         placeholder="49991663166",
                                         value=st.session_state.dados_cliente["whatsapp"])

                if st.form_submit_button("Confirmar Dados"):
                    # Atualiza os dados de forma segura
                    novos_dados = {
                        "nome": nome,
                        "email": email,
                        "whatsapp": whatsapp,
                        "plano": plano
                    }
                    st.session_state.dados_cliente.update(novos_dados)
                    st.rerun()

            # Mostrar instruções de pagamento se os dados estiverem completos
            if all([st.session_state.dados_cliente["nome"],
                    st.session_state.dados_cliente["email"],
                    st.session_state.dados_cliente["whatsapp"]]):

                cliente = st.session_state.dados_cliente

                # Container com informações do PIX
                st.markdown(f"""
                <div class="pix-container">
                    <h3 style="color: #006400;">⚡️ Pagamento via PIX</h3>
                    <div style="margin-top: 15px;">
                        <p style="font-size: 18px;"><strong>Chave PIX (CPF):</strong></p>
                        <div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">
                            <code style="font-size: 20px;">019.059.900-65</code>
                        </div>
                        <p style="font-size: 16px;"><strong>Valor:</strong> R$ {cliente["plano"]["preco"]},00</p>
                        <p style="font-size: 16px; margin-top: 15px;">Após o pagamento, envie o comprovante para:</p>
                        <div style="margin-top: 10px;">
                            <p style="font-size: 16px;"><strong>Telegram:</strong> @vagsembrani</p>
                            <p style="font-size: 16px;"><strong>WhatsApp:</strong> (49) 99166-3166</p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Link para WhatsApp
                whatsapp_url = f"https://wa.me/5549991663166?text=Olá! Enviei o comprovante PIX para o FIFAlgorithm - Plano: {cliente['plano']['nome']} - Valor: R$ {cliente['plano']['preco']}"
                st.markdown(
                    f'<a href="{whatsapp_url}" class="whatsapp-btn" target="_blank">'
                    '📱 Enviar Comprovante no WhatsApp'
                    '</a>',
                    unsafe_allow_html=True
                )

                # Botão para simular pagamento (apenas para teste)
                if st.button("✅ Simular Pagamento (Apenas para Testes)", type="primary"):
                    new_key = generate_key(
                        cliente["plano"]["dias"],
                        owner=cliente["nome"],
                        notes=f"Comprado via PIX - WhatsApp: {cliente['whatsapp']}"
                    )
                    register_sale(
                        days=cliente["plano"]["dias"],
                        price=cliente["plano"]["preco"],
                        buyer_info={
                            "nome": cliente["nome"],
                            "email": cliente["email"],
                            "whatsapp": cliente["whatsapp"],
                            "metodo": "PIX"
                        },
                        key_generated=new_key
                    )
                    st.success("✅ Pagamento confirmado! Sua chave de acesso é:")
                    st.code(new_key)
                    st.warning("Anote esta chave em um local seguro! Ela não será exibida novamente.")
                    del st.session_state["plano_selecionado"]
                    del st.session_state["dados_cliente"]

def admin_panel() -> None:
    """Painel administrativo"""
    st.title("🔧 Painel Administrativo")

    # Menu de navegação
    if "admin_mode" not in st.session_state:
        st.session_state["admin_mode"] = "gerar"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Gerar Chaves"):
            st.session_state["admin_mode"] = "gerar"
    with col2:
        if st.button("Gerenciar Chaves"):
            st.session_state["admin_mode"] = "gerenciar"
    with col3:
        if st.button("Estatísticas"):
            st.session_state["admin_mode"] = "estatisticas"
    with col4:
        if st.button("Histórico de Vendas"):
            st.session_state["admin_mode"] = "vendas"

    st.markdown("---")

    # Modo: Gerar Chaves
    if st.session_state["admin_mode"] == "gerar":
        with st.form("generate_key_form"):
            st.subheader("Gerar Nova Chave")
            days_valid = st.selectbox("Validade da chave:", [1, 7, 15, 30], index=2)
            owner = st.text_input("Proprietário (opcional):")
            notes = st.text_area("Observações (opcional):")

            if st.form_submit_button("Gerar Chave"):
                key = generate_key(days_valid, owner, notes)
                st.success(f"Chave gerada com sucesso! Válida por {days_valid} dias.")
                st.code(key)
                st.warning("Esta é a única vez que a chave será exibida. Salve-a em um local seguro!")

    # Modo: Gerenciar Chaves
    elif st.session_state["admin_mode"] == "gerenciar":
        st.subheader("Chaves Existentes")

        keys = get_all_keys()
        if not keys:
            st.info("Nenhuma chave cadastrada ainda.")
        else:
            df = pd.DataFrame(keys)
            df["created"] = pd.to_datetime(df["created"]).dt.strftime("%d/%m/%Y %H:%M")
            df["expires"] = pd.to_datetime(df["expires"]).dt.strftime("%d/%m/%Y %H:%M")
            df["first_used"] = pd.to_datetime(df["first_used"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
            df["last_used"] = pd.to_datetime(df["last_used"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
            df["first_used"] = df["first_used"].replace("NaT", "Nunca")
            df["last_used"] = df["last_used"].replace("NaT", "Nunca")

            df = df.sort_values("expires", ascending=True)
            st.dataframe(df)

            st.subheader("Revogar Chave")
            key_to_revoke = st.selectbox("Selecione uma chave para revogar:",
                                         [""] + list(df["hashed_key"]))

            if key_to_revoke and st.button("Revogar Chave"):
                if revoke_key(key_to_revoke):
                    st.success("Chave revogada com sucesso!")
                    st.rerun()
                else:
                    st.error("Erro ao revogar chave.")

    # Modo: Estatísticas
    elif st.session_state["admin_mode"] == "estatisticas":
        st.subheader("Estatísticas de Uso")

        keys = get_all_keys()
        if not keys:
            st.info("Nenhuma chave cadastrada ainda.")
        else:
            df = pd.DataFrame(keys)
            used_keys = df[df["usage_count"] > 0]

            if len(used_keys) == 0:
                st.info("Nenhuma chave foi usada ainda.")
            else:
                col1, col2, col3 = st.columns(3)
                col1.metric("Total de Chaves", len(df))
                col2.metric("Chaves Ativas", len(df[df["active"]]))
                col3.metric("Chaves Usadas", len(used_keys))

                st.subheader("Chaves Mais Utilizadas")
                top_keys = used_keys.sort_values("usage_count", ascending=False).head(10)
                st.dataframe(top_keys[["owner", "usage_count", "first_used", "last_used"]])

                st.subheader("Ativações por Dia")
                usage_dates = pd.to_datetime(used_keys["first_used"])
                usage_by_day = usage_dates.dt.floor("D").value_counts().sort_index()
                st.line_chart(usage_by_day)

    # Modo: Histórico de Vendas
    elif st.session_state["admin_mode"] == "vendas":
        st.subheader("Histórico de Vendas PIX")
        sales = load_sales()

        if not sales:
            st.info("Nenhuma venda registrada ainda.")
        else:
            df_sales = pd.DataFrame(sales)

            # Processa os dados de vendas
            df_sales["Nome"] = df_sales["buyer"].apply(lambda x: x.get("nome", "N/A"))
            df_sales["WhatsApp"] = df_sales["buyer"].apply(lambda x: x.get("whatsapp", "N/A"))
            df_sales["E-mail"] = df_sales["buyer"].apply(lambda x: x.get("email", "N/A"))
            df_sales["Data"] = pd.to_datetime(df_sales["date"]).dt.strftime("%d/%m/%Y %H:%M")
            df_sales["Expiração"] = (
                        pd.to_datetime(df_sales["date"]) + pd.to_timedelta(df_sales["days"], unit="d")).dt.strftime(
                "%d/%m/%Y")

            # Filtra apenas vendas PIX
            df_sales = df_sales[df_sales["buyer"].apply(lambda x: x.get("metodo", "") == "PIX")]
            df_sales = df_sales.sort_values("date", ascending=False)

            # Mostra tabela de vendas
            st.dataframe(df_sales[["Data", "Nome", "WhatsApp", "E-mail", "days", "price", "Expiração"]],
                         use_container_width=True)

            # Estatísticas financeiras
            st.subheader("Resumo Financeiro")
            total_vendas = df_sales["price"].sum()
            vendas_30d = df_sales[pd.to_datetime(df_sales["date"]) > (datetime.now() - timedelta(days=30))][
                "price"].sum()

            col1, col2 = st.columns(2)
            col1.metric("Total de Vendas PIX", f"R$ {total_vendas:.2f}")
            col2.metric("Vendas PIX (30 dias)", f"R$ {vendas_30d:.2f}")


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

    brasil_timezone = pytz.timezone("America/Sao_Paulo")
    current_time_br = datetime.now(brasil_timezone).strftime("%H:%M:%S")
    st.title("💀 FIFAlgorithm")
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
    # Barra lateral com informações da conta
    with st.sidebar:
        st.subheader(f"⭐️ Conta: {st.session_state['key_info']['owner']}")
        st.write(f"⌛️ Validade: {datetime.fromisoformat(st.session_state['key_info']['expires']).strftime('%d/%m/%Y')}")
        st.write(f"⚠️ Dias restantes: {st.session_state['key_info']['remaining_days']}")

        if st.button("🔺 Sair"):
            st.session_state.clear()
            st.rerun()

    # Sistema de abas
    if "current_tab" not in st.session_state:
        st.session_state["current_tab"] = "⚡️ Ao Vivo"

    tabs = st.tabs(["⚡️ Ao Vivo", "⭐️ Radar FIFA", "⭐️ Dicas Inteligentes", "⭐️ Previsão IA", "⭐️ Análise Manual",
                    "💰 Ganhos & Perdas", "✅ Salvar Jogos"])

    # Aba 1: Ao Vivo
    with tabs[0]:
        st.header("🎮 𝐋𝐢𝐬𝐭𝐚 𝐝𝐞 𝐉𝐨𝐠𝐨𝐬")

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
            # Configuração da tabela interativa
            gb = GridOptionsBuilder.from_dataframe(df_live_display)

            # Configuração padrão
            gb.configure_default_column(
                flex=1,
                minWidth=100,
                wrapText=True,
                autoHeight=True,
                cellClass="hide-on-mobile"
            )

            # Configurar colunas essenciais
            essential_columns = ['Hora', 'Liga', 'Mandante', 'Visitante', 'GP', 'GC', 'Sugestão HT', 'Sugestão FT']
            for col in essential_columns:
                if col in df_live_display.columns:
                    gb.configure_column(col, cellClass=None, minWidth=80)

            # Configurar coluna de seleção
            if "Selecionar" not in df_live_display.columns:
                df_live_display["Selecionar"] = False

            gb.configure_column("Selecionar",
                                header_name="✓",
                                editable=True,
                                cellRenderer='agCheckboxCellRenderer',
                                width=50,
                                cellClass=None)

            grid_options = gb.build()

            # Renderizar tabela
            grid_response = AgGrid(
                df_live_display,
                gridOptions=grid_options,
                height=min(500, 35 + 35 * len(df_live_display)),
                width='100%',
                fit_columns_on_grid_load=False,
                theme='streamlit',
                update_mode=GridUpdateMode.MODEL_CHANGED,
                allow_unsafe_jscode=True,
                key='live_matches_grid'
            )

            # Botão de salvamento
            if st.button("💾 Salvar Jogos Selecionados", type="primary"):
                try:
                    selected_rows = grid_response['data'][grid_response['data']['Selecionar'] == True]
                    if not selected_rows.empty:
                        # Adiciona data de salvamento
                        selected_rows['Data Salvamento'] = datetime.now().strftime("%d/%m/%Y %H:%M")

                        # Atualiza jogos salvos
                        if 'saved_games' not in st.session_state:
                            st.session_state.saved_games = selected_rows[essential_columns + ['Data Salvamento']]
                        else:
                            # Evita duplicatas
                            new_games = selected_rows[essential_columns + ['Data Salvamento']]
                            existing_games = st.session_state.saved_games

                            # Filtra jogos que já existem
                            mask = ~new_games.apply(lambda row:
                                                    (existing_games['Mandante'] == row['Mandante']) &
                                                    (existing_games['Visitante'] == row['Visitante']) &
                                                    (existing_games['Hora'] == row['Hora']), axis=1).any(axis=1)

                            new_unique_games = new_games[mask]

                            if not new_unique_games.empty:
                                st.session_state.saved_games = pd.concat(
                                    [existing_games, new_unique_games]
                                ).drop_duplicates()
                                st.success(f"✅ {len(new_unique_games)} novos jogos salvos!")
                            else:
                                st.warning("Nenhum jogo novo para salvar (todos já estão na lista)")
                    else:
                        st.warning("Nenhum jogo selecionado")
                except Exception as e:
                    st.error(f"Erro ao salvar: {str(e)}")
        else:
            st.warning("⏳ Nenhuma partida ao vivo no momento")
            st.info("As partidas aparecerão aqui quando estiverem disponíveis")

    # Aba 2: Radar FIFA
    with tabs[1]:
        st.header("🎯 Radar FIFA")
        st.write("Análise das porcentagens para mercados Over nas ligas ao vivo")

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
    with tabs[5]:
        st.header("💰 Ganhos & Perdas por Jogador")
        if not df_stats_all_players.empty:
            player_names_for_selectbox = sorted([
                re.sub(r'^[🥇🥈🥉]\s', '', p)
                for p in df_stats_all_players["Jogador"].unique()
            ])
            selected_player = st.selectbox(
                "Selecione um Jogador para Análise:",
                [""] + player_names_for_selectbox
            )
            if selected_player:
                default_odds = st.slider(
                    "Defina as odds médias para cálculo:",
                    min_value=1.50,
                    max_value=3.00,
                    value=1.90,
                    step=0.05
                )
                display_metrics_for_player(df_stats_all_players, selected_player, default_odds)
            else:
                st.info("Por favor, selecione um jogador para ver a análise.")
        else:
            st.info("Nenhum dado de jogador disponível para análise.")

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
    st.set_page_config(page_title="FIFAlgorithm", layout="wide")

    # Verificação de acesso admin
    if st.query_params.get("admin") == SECRET_KEY:
        st.session_state["admin"] = True
        st.session_state["authenticated"] = True
        admin_panel()
    elif not st.session_state.get("authenticated"):
        login_page()
    else:
        fifalgorithm_app()


if __name__ == "__main__":
    main()