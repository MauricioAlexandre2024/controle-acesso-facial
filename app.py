import os

# Desativa avisos de GPU/CUDA no terminal
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

import io
import hashlib
import base64
import glob
import json
import secrets
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
import smtplib
import sqlite3
from PIL import Image
import cv2
import numpy as np
from deepface import DeepFace
import pandas as pd
import requests
import threading
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import streamlit as st
import altair as alt
import math

from fpdf import FPDF

st.set_page_config(
    page_title="Cofre de Toxinas — Ministério do Meio Ambiente",
    page_icon="🔐",
    layout="wide",
)

# CSS responsivo para dispositivos móveis
MOBILE_CSS = """
<style>
@media (max-width: 768px) {
    div[data-testid="stHorizontalBlock"] {
        flex-direction: column;
    }
    div[data-testid="stHorizontalBlock"] > div {
        width: 100% !important;
        flex: unset !important;
        min-width: 0 !important;
    }
    div[data-testid="stSidebar"] {
        width: min(85vw, 280px) !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
    h1 {
        font-size: 1.6rem !important;
    }
    h2 {
        font-size: 1.3rem !important;
    }
    .stButton > button {
        width: 100% !important;
    }
    div[data-testid="stCameraInput"] {
        max-width: 100% !important;
    }
    div[data-testid="stDataFrame"] {
        font-size: 0.8rem !important;
    }
}
</style>
"""

st.markdown(MOBILE_CSS, unsafe_allow_html=True)

# Moldura circular visual no CSS
MOLDURA_CIRCULAR_CSS = """
<style>
div[data-testid="stCameraInput"] {
    position: relative;
    max-width: 500px;
    margin: 0 auto;
}
div[data-testid="stCameraInput"]::after {
    content: "";
    position: absolute;
    top: 45%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 250px;
    height: 300px;
    border: 3px dashed #00FF66;
    border-radius: 50%;
    pointer-events: none;
    box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.4);
    z-index: 10;
}
</style>
"""

IMAGEMHOME_DIR = "IMAGEMHOME"
EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".webp")

HOME_CSS = """
<style>
div[data-testid="stImage"] img {
    border-radius: 14px;
    box-shadow: 0 6px 22px rgba(0, 0, 0, 0.35);
}
</style>
"""

DB_FILE = "controle_acesso.db"
FOTOS_DIR = "fotos_cadastradas"

if not os.path.exists(FOTOS_DIR):
    os.makedirs(FOTOS_DIR)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cargo TEXT,
            divisao TEXT,
            nivel_acesso INTEGER NOT NULL DEFAULT 1,
            foto_path TEXT NOT NULL,
            data_cadastro TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logs_acesso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_nome TEXT,
            setor TEXT,
            data_hora TEXT,
            status TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logs_erros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            tipo TEXT,
            modulo TEXT,
            mensagem TEXT,
            descricao TEXT,
            sugerida TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tentativas_seguranca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compartimento TEXT,
            data_hora TEXT,
            motivo TEXT,
            detalhes TEXT,
            origem TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def migrar_banco_legado():
    """Migra o banco antigo (permissões por setor / níveis 1-4) para o novo
    esquema do Cofre de Toxinas: níveis cumulativos 1-3 e coluna de divisão."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        colunas = [r[1] for r in cursor.execute("PRAGMA table_info(colaboradores)")]
        if "nivel_acesso" not in colunas:
            cursor.execute(
                "ALTER TABLE colaboradores ADD COLUMN nivel_acesso INTEGER NOT NULL DEFAULT 1"
            )
        if "divisao" not in colunas:
            cursor.execute("ALTER TABLE colaboradores ADD COLUMN divisao TEXT")
        # Novo esquema de segurança: os colaboradores existentes do banco
        # antigo (permissões por setor / níveis 1-4) são reiniciados para o
        # Nível 1 (Permissão Geral) apenas na primeira execução da migração.
        cursor.execute("PRAGMA user_version")
        versao = cursor.fetchone()[0]
        if versao < 1:
            cursor.execute("UPDATE colaboradores SET nivel_acesso = 1")
            cursor.execute("PRAGMA user_version = 1")
        if versao < 2:
            cols_logs = [
                r[1] for r in cursor.execute("PRAGMA table_info(logs_acesso)")
            ]
            if "detalhes" not in cols_logs:
                cursor.execute(
                    "ALTER TABLE logs_acesso ADD COLUMN detalhes TEXT"
                )
            cursor.execute("PRAGMA user_version = 2")
        if versao < 3:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT
                )
                """
            )
            cursor.execute("PRAGMA user_version = 3")
        if versao < 4:
            # Esquema de autenticação por credenciais (usuário/senha) e
            # controle de quem pode cadastrar novos colaboradores.
            if "usuario" not in colunas:
                cursor.execute(
                    "ALTER TABLE colaboradores ADD COLUMN usuario TEXT"
                )
            if "senha_hash" not in colunas:
                cursor.execute(
                    "ALTER TABLE colaboradores ADD COLUMN senha_hash TEXT"
                )
            if "pode_cadastrar" not in colunas:
                cursor.execute(
                    "ALTER TABLE colaboradores ADD COLUMN pode_cadastrar INTEGER NOT NULL DEFAULT 0"
                )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_colaboradores_usuario "
                "ON colaboradores(usuario) WHERE usuario IS NOT NULL"
            )
            cursor.execute("PRAGMA user_version = 4")
        cursor.execute(
            "UPDATE colaboradores SET divisao = 'Sem divisão' "
            "WHERE divisao IS NULL OR divisao = ''"
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def hash_senha(senha):
    """Gera o hash da senha com salt único (PBKDF2-HMAC-SHA256)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(salt), 100_000
    )
    return f"{salt}${digest.hex()}"


def verificar_senha(senha, armazenado):
    """Confere a senha contra o valor armazenado no formato 'salt$hash'."""
    if not armazenado or "$" not in armazenado:
        return False
    try:
        salt, digest_hex = armazenado.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), bytes.fromhex(salt), 100_000
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


CHAVES_CONFIG_ALERTA = [
    "cfg_email_ativo",
    "cfg_email_provedor",
    "cfg_email_smtp_host",
    "cfg_email_smtp_port",
    "cfg_email_smtp_login",
    "cfg_email_remetente",
    "cfg_email_senha",
    "cfg_email_destinatario",
    "cfg_twilio_ativo",
    "cfg_twilio_sid",
    "cfg_twilio_token",
    "cfg_twilio_de",
    "cfg_twilio_para",
    "cfg_wagrupo_ativo",
    "cfg_wagrupo_id",
    "cfg_wagrupo_nome",
]

PRESETS_SMTP = {
    "Gmail": ("smtp.gmail.com", "587"),
    "Outlook": ("smtp-mail.outlook.com", "587"),
    "Brevo": ("smtp-relay.brevo.com", "587"),
    "Outro": ("", ""),
}


def _definir_preset_smtp():
    """Preenche host/porta da Session State conforme o provedor escolhido."""
    prov = st.session_state.get("cfg_email_provedor", "Gmail")
    if prov not in PRESETS_SMTP:
        prov = "Gmail"
    if prov == "Outro":
        return
    host, porta = PRESETS_SMTP[prov]
    st.session_state["cfg_email_smtp_host"] = host
    st.session_state["cfg_email_smtp_port"] = porta


def _carregar_config_alerta():
    """Pré-preenche a Session State com as notificações salvas no banco."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
            """
        )
        linhas = cursor.execute(
            "SELECT chave, valor FROM configuracoes"
        ).fetchall()
        conn.close()
    except Exception:
        return
    for chave, valor in linhas:
        if chave in CHAVES_CONFIG_ALERTA and chave not in st.session_state:
            st.session_state[chave] = (
                valor == "1" if chave.endswith("_ativo") else valor
            )


def _salvar_config_alerta():
    """Persiste as configurações de notificação no banco (quando houver mudança)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        atuais = dict(
            cursor.execute("SELECT chave, valor FROM configuracoes").fetchall()
        )
        for chave in CHAVES_CONFIG_ALERTA:
            valor = st.session_state.get(chave)
            if valor is None:
                continue
            texto = (
                ("1" if valor else "0")
                if isinstance(valor, bool)
                else str(valor).strip()
            )
            if atuais.get(chave) != texto:
                cursor.execute(
                    "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                    (chave, texto),
                )
        conn.commit()
        conn.close()
    except Exception:
        pass


init_db()
migrar_banco_legado()
_carregar_config_alerta()

NIVEIS_ACESSO = {
    1: {
        "nome": "Permissão Geral",
        "descricao": (
            "Acesso concedido a indivíduos com permissão geral dentro do "
            "Ministério do Meio Ambiente. Libera o catálogo público e as "
            "informações gerais sobre o cofre de toxinas."
        ),
    },
    2: {
        "nome": "Diretor de Divisões Específicas",
        "descricao": (
            "Acesso restrito aos diretores de divisões específicas do "
            "Ministério. Libera o inventário, a localização e a movimentação "
            "das toxinas dos compartimentos sob sua responsabilidade."
        ),
    },
    3: {
        "nome": "Ministro do Meio Ambiente",
        "descricao": (
            "Acesso exclusivo ao ministro do Meio Ambiente. Controle total "
            "sobre o cofre: dossiê completo, cadeia de custódia, gestão de "
            "colaboradores e auditoria."
        ),
    },
}


def nome_nivel(nivel):
    """Retorna o nome do nível de acesso."""
    info = NIVEIS_ACESSO.get(nivel)
    return info["nome"] if info else f"Nível {nivel}"


def descricao_nivel(nivel):
    """Retorna a descrição do nível de acesso."""
    info = NIVEIS_ACESSO.get(nivel)
    return info["descricao"] if info else ""


def rotulo_nivel(nivel):
    """Ex.: 'Nível 2 – Consulta Cartográfica'."""
    return f"Nível {nivel} – {nome_nivel(nivel)}"


# Mapeia rótulos legados (níveis antigos e setores) para os 3 níveis
# atuais do Cofre de Toxinas apenas para exibição nos dashboards.
COMPARTIMENTOS_LEGADOS = {
    # Níveis antigos (esquema 1-4 de dados geoespaciais)
    "Nível 1 – Consulta Básica de Imagens": rotulo_nivel(1),
    "Nível 2 – Consulta Cartográfica": rotulo_nivel(2),
    "Nível 3 – Análise Especializada": rotulo_nivel(3),
    "Nível 4 – Governança e Administração de Dados": rotulo_nivel(3),
    # Setores antigos (pré-níveis)
    "Diretoria Executiva": rotulo_nivel(3),
    "P&D / Laboratório": rotulo_nivel(3),
    "Tesouraria / Cofre": rotulo_nivel(3),
    "TI / Servidores": rotulo_nivel(1),
    "Recursos Humanos": rotulo_nivel(1),
}


def normalizar_compartimento(rotulo):
    """Converte rótulos legados de `setor` para o compartimento atual do cofre."""
    if not isinstance(rotulo, str):
        return rotulo_nivel(1)
    rotulo = rotulo.strip()
    if rotulo in COMPARTIMENTOS_LEGADOS:
        return COMPARTIMENTOS_LEGADOS[rotulo]
    import re

    m = re.search(r"Nível\s*(\d)", rotulo)
    if m:
        nivel = int(m.group(1))
        if nivel >= 3:
            return rotulo_nivel(3)
        if nivel == 2:
            return rotulo_nivel(2)
        return rotulo_nivel(1)
    return rotulo_nivel(1)


def rotulo_curto_compartimento(rotulo):
    """Ex.: 'Nível 2 – Diretor de Divisões Específicas' -> 'Diretor de Divisões Específicas'."""
    if isinstance(rotulo, str):
        import re

        return re.sub(r"^Nível\s*\d+\s*–\s*", "", rotulo)
    return str(rotulo)


DADOS_TOXINAS = [
    {
        "id_toxina": "TOX-0001",
        "nome": "Ricina",
        "classe": "Proteína",
        "tipo_acao": "Citotóxica",
        "periculosidade": 5,
        "dose_letal_mg": 0.002,
        "uso": "Pesquisa / neutralização",
        "compartimento": "Compartimento A-01",
        "divisao_responsavel": "Divisão de Toxicologia Ambiental",
        "estoque_unidades": 12,
        "data_validade": "2027-03-15",
        "temperatura_c": -20,
        "estado_conservacao": "Estável",
    },
    {
        "id_toxina": "TOX-0002",
        "nome": "Saxitoxina",
        "classe": "Biotoxina marinha",
        "tipo_acao": "Neurotóxica",
        "periculosidade": 5,
        "dose_letal_mg": 0.20,
        "uso": "Controle de efluentes",
        "compartimento": "Compartimento A-02",
        "divisao_responsavel": "Divisão de Emergências Químicas",
        "estoque_unidades": 8,
        "data_validade": "2026-11-30",
        "temperatura_c": 4,
        "estado_conservacao": "Estável",
    },
    {
        "id_toxina": "TOX-0003",
        "nome": "Tetrodotoxina",
        "classe": "Biotoxina marinha",
        "tipo_acao": "Neurotóxica",
        "periculosidade": 5,
        "dose_letal_mg": 0.05,
        "uso": "Estudos toxicológicos",
        "compartimento": "Compartimento A-03",
        "divisao_responsavel": "Divisão de Pesquisa e Laboratório",
        "estoque_unidades": 5,
        "data_validade": "2026-09-12",
        "temperatura_c": -30,
        "estado_conservacao": "Atenção",
    },
    {
        "id_toxina": "TOX-0004",
        "nome": "Microcistina-LR",
        "classe": "Cianotoxina",
        "tipo_acao": "Hepatotóxica",
        "periculosidade": 3,
        "dose_letal_mg": 0.05,
        "uso": "Análise de florações",
        "compartimento": "Compartimento B-01",
        "divisao_responsavel": "Divisão de Fiscalização e Segurança Química",
        "estoque_unidades": 40,
        "data_validade": "2027-01-20",
        "temperatura_c": -15,
        "estado_conservacao": "Estável",
    },
    {
        "id_toxina": "TOX-0005",
        "nome": "Aflatoxina B1",
        "classe": "Micotoxina",
        "tipo_acao": "Carcinogênica",
        "periculosidade": 4,
        "dose_letal_mg": 65.0,
        "uso": "Monitoramento agroquímico",
        "compartimento": "Compartimento B-02",
        "divisao_responsavel": "Divisão de Toxicologia Ambiental",
        "estoque_unidades": 25,
        "data_validade": "2026-10-05",
        "temperatura_c": 2,
        "estado_conservacao": "Estável",
    },
    {
        "id_toxina": "TOX-0006",
        "nome": "Toxina Botulínica Tipo A",
        "classe": "Proteína",
        "tipo_acao": "Neurotóxica",
        "periculosidade": 5,
        "dose_letal_mg": 0.001,
        "uso": "Produção de antitoxina",
        "compartimento": "Compartimento A-04",
        "divisao_responsavel": "Divisão de Pesquisa e Laboratório",
        "estoque_unidades": 3,
        "data_validade": "2027-06-01",
        "temperatura_c": -80,
        "estado_conservacao": "Crítico",
    },
    {
        "id_toxina": "TOX-0007",
        "nome": "Alfa-amanitina",
        "classe": "Peptídeo",
        "tipo_acao": "Citotóxica",
        "periculosidade": 4,
        "dose_letal_mg": 0.15,
        "uso": "Estudos bioquímicos",
        "compartimento": "Compartimento B-03",
        "divisao_responsavel": "Divisão de Toxicologia Ambiental",
        "estoque_unidades": 18,
        "data_validade": "2026-12-18",
        "temperatura_c": -20,
        "estado_conservacao": "Estável",
    },
    {
        "id_toxina": "TOX-0008",
        "nome": "Batracotoxina",
        "classe": "Alcaloide",
        "tipo_acao": "Cardiotóxica",
        "periculosidade": 5,
        "dose_letal_mg": 0.002,
        "uso": "Referência analítica",
        "compartimento": "Compartimento A-05",
        "divisao_responsavel": "Divisão de Emergências Químicas",
        "estoque_unidades": 2,
        "data_validade": "2027-02-14",
        "temperatura_c": -80,
        "estado_conservacao": "Crítico",
    },
    {
        "id_toxina": "TOX-0009",
        "nome": "Brevetoxina",
        "classe": "Biotoxina marinha",
        "tipo_acao": "Neurotóxica",
        "periculosidade": 3,
        "dose_letal_mg": 1.0,
        "uso": "Controle de marés vermelhas",
        "compartimento": "Compartimento B-04",
        "divisao_responsavel": "Divisão de Fiscalização e Segurança Química",
        "estoque_unidades": 30,
        "data_validade": "2027-04-09",
        "temperatura_c": -10,
        "estado_conservacao": "Estável",
    },
    {
        "id_toxina": "TOX-0010",
        "nome": "Solução padrão de cianeto",
        "classe": "Composto inorgânico",
        "tipo_acao": "Hemotóxica",
        "periculosidade": 2,
        "dose_letal_mg": 50.0,
        "uso": "Calibração de equipamentos",
        "compartimento": "Compartimento C-01",
        "divisao_responsavel": "Serviços Gerais",
        "estoque_unidades": 60,
        "data_validade": "2028-01-30",
        "temperatura_c": 25,
        "estado_conservacao": "Estável",
    },
]


DIVISOES_MMA = [
    "Gabinete do Ministro",
    "Divisão de Toxicologia Ambiental",
    "Divisão de Emergências Químicas",
    "Divisão de Fiscalização e Segurança Química",
    "Divisão de Pesquisa e Laboratório",
    "Serviços Gerais",
]


def carregar_dados_toxinas():
    """Retorna o inventário (simulado) de toxinas custodiadas no cofre do MMA."""
    return pd.DataFrame(DADOS_TOXINAS)


def serie_temporal_movimentacao():
    """Gera uma série temporal mensal (simulada) de movimentações de toxinas."""
    divisoes = [
        "Divisão de Toxicologia Ambiental",
        "Divisão de Emergências Químicas",
        "Divisão de Fiscalização e Segurança Química",
        "Divisão de Pesquisa e Laboratório",
    ]
    meses = pd.date_range("2024-01-01", "2026-08-01", freq="MS")
    linhas = []
    for i, mes in enumerate(meses):
        for idx, divisao in enumerate(divisoes):
            sazonalidade = (idx + 1) * math.sin(i / 6 * math.pi)
            tendencia = (i / len(meses)) * 4
            mov = max(0, int((idx + 1) * 8 + sazonalidade + tendencia))
            linhas.append(
                {"divisao": divisao, "mes": mes, "movimentacoes": mov}
            )
    return pd.DataFrame(linhas)


LIMITE_INATIVIDADE_S = 5 * 60  # 5 minutos sem interação => sessão expira


def _sessao_valida():
    """True se existe sessão autenticada e dentro do limite de inatividade."""
    if not st.session_state.get("autenticado", False):
        return False
    usuario = st.session_state.get("usuario_logado")
    if usuario is None:
        return False
    login_ts = usuario.get("login_ts", 0)
    if time.time() - login_ts > LIMITE_INATIVIDADE_S:
        st.session_state.pop("usuario_logado", None)
        st.session_state.pop("autenticado", None)
        st.session_state["sessao_expirada"] = True
        return False
    return True


def usuario_tem_nivel(nivel_requerido):
    """Verifica se o usuário logado possui o nível requerido (cumulativo)."""
    if not _sessao_valida():
        return False
    usuario = st.session_state.get("usuario_logado")
    return usuario is not None and usuario.get("nivel_acesso", 0) >= nivel_requerido


def usuario_pode_cadastrar():
    """True apenas se o usuário autenticado tem permissão de cadastro."""
    if not _sessao_valida():
        return False
    usuario = st.session_state.get("usuario_logado")
    return usuario is not None and bool(usuario.get("pode_cadastrar", 0))


def existe_usuario_com_credenciais():
    """True se ao menos um colaborador possui usuário cadastrado."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM colaboradores "
            "WHERE usuario IS NOT NULL AND TRIM(usuario) <> ''"
        )
        n = cur.fetchone()[0]
        conn.close()
        return int(n) > 0
    except Exception:
        return False


def _preparar_logs(df_logs=None):
    """Carrega e normaliza os logs de acesso para o esquema atual do cofre."""
    if df_logs is None:
        conn = sqlite3.connect(DB_FILE)
        df_logs = pd.read_sql_query("SELECT * FROM logs_acesso", conn)
        conn.close()
    df_logs = df_logs.rename(columns={"setor": "area_dados"})
    if df_logs.empty:
        return df_logs
    df_logs["area_dados"] = df_logs["area_dados"].apply(normalizar_compartimento)
    df_logs["nivel"] = (
        df_logs["area_dados"].astype(str).str.extract(r"Nível\s*(\d)").astype(int)
    )
    df_logs["compartimento_curto"] = df_logs["area_dados"].map(
        rotulo_curto_compartimento
    )
    df_logs["data_hora"] = pd.to_datetime(df_logs["data_hora"])
    df_logs["data"] = df_logs["data_hora"].dt.date
    df_logs["hora"] = df_logs["data_hora"].dt.hour
    return df_logs


def _chart_png(chart, largura=820, escala=2):
    """Renderiza um gráfico Altair para bytes PNG (em memória)."""
    import vl_convert as vlc

    spec = chart.to_dict()
    spec["width"] = largura
    spec["autosize"] = {"type": "fit", "contains": "padding"}
    return vlc.vegalite_to_png(spec, scale=escala)


class _RelatorioPDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font(_PDF_FONT, "", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, f"Página {self.page_no()}", align="C")


_PDF_FONT = "dejavu"
_DEJAVU_TTF = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD_TTF = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _registrar_fonte_pdf(pdf):
    """Registra a fonte Unicode (DejaVu) para suportar acentos e travessões."""
    if os.path.exists(_DEJAVU_TTF) and os.path.exists(_DEJAVU_BOLD_TTF):
        pdf.add_font(_PDF_FONT, "", fname=_DEJAVU_TTF)
        pdf.add_font(_PDF_FONT, "B", fname=_DEJAVU_BOLD_TTF)
        return True
    return False


def _secao_pdf(pdf, numero, titulo):
    if pdf.get_y() > 248:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_fill_color(30, 41, 59)
    pdf.rect(pdf.l_margin, y, 180, 8, style="F")
    pdf.set_font(_PDF_FONT, "B", 11)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(pdf.l_margin + 3, y + 0.6)
    pdf.cell(180, 6, f"{numero}. {titulo}")
    pdf.set_y(y + 10)


def _inserir_kpi(pdf, x, y, w, h, titulo, valor):
    pdf.set_fill_color(241, 245, 249)
    pdf.rect(x, y, w, h, style="F")
    pdf.set_text_color(71, 85, 105)
    pdf.set_font(_PDF_FONT, "B", 7.5)
    pdf.set_xy(x + 3, y + 3)
    pdf.multi_cell(w - 6, 3.4, titulo.upper())
    pdf.set_font(_PDF_FONT, "B", 13)
    pdf.set_text_color(15, 118, 110)
    pdf.set_xy(x + 3, y + h - 9.5)
    pdf.cell(w - 6, 6, str(valor))
    pdf.set_y(y + h + 3)


def _row_kpis(pdf, kpis):
    n = len(kpis)
    gap = 3
    w = (180 - gap * (n - 1)) / n
    h = 18
    y = pdf.get_y()
    if y + h + 8 > 262:
        pdf.add_page()
        y = pdf.get_y()
    for i, (titulo, valor) in enumerate(kpis):
        _inserir_kpi(pdf, pdf.l_margin + i * (w + gap), y, w, h, titulo, valor)
    pdf.set_y(y + h + 4)
    pdf.set_text_color(30, 41, 59)


def _inserir_grafico(pdf, png, legenda):
    imagem = Image.open(io.BytesIO(png))
    w_px, h_px = imagem.size
    w = 180
    h = w * h_px / w_px
    if pdf.get_y() + h + 14 > 278:
        pdf.add_page()
    y = pdf.get_y()
    pdf.image(io.BytesIO(png), x=pdf.l_margin, y=y, w=w, h=h)
    pdf.set_xy(pdf.l_margin, y + h + 1)
    pdf.set_font(_PDF_FONT, "", 8.5)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(0, 4, legenda)
    pdf.ln(2)


def _tabela_pdf(pdf, titulo, headers, linhas, col_destaque=None, mapa=None):
    pdf.set_font(_PDF_FONT, "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, titulo, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    if not linhas:
        pdf.set_font(_PDF_FONT, "", 9.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 6, "Nenhum registro encontrado.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        return
    n = len(headers)
    lar = [180 / n] * n
    linha_h = 7
    x0 = pdf.l_margin
    if pdf.get_y() + 12 > 270:
        pdf.add_page()
    pdf.set_fill_color(15, 23, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(_PDF_FONT, "B", 8.5)
    x = x0
    for i, h in enumerate(headers):
        pdf.set_xy(x, pdf.get_y())
        pdf.cell(lar[i], linha_h, h, border=1, fill=True, align="C")
        x += lar[i]
    pdf.ln(linha_h)
    pdf.set_font(_PDF_FONT, "", 8.5)
    for j, linha in enumerate(linhas):
        if pdf.get_y() + 7 > 282:
            pdf.add_page()
        zebra = j % 2 == 1
        x = x0
        for i, val in enumerate(linha):
            fill = (248, 250, 252) if zebra else (255, 255, 255)
            txt = (33, 37, 41)
            if col_destaque is not None and i == col_destaque and mapa:
                m = mapa.get(val)
                if m:
                    fill, txt = m
            pdf.set_fill_color(*fill)
            pdf.set_text_color(*txt)
            pdf.set_xy(x, pdf.get_y())
            pdf.cell(
                lar[i],
                linha_h,
                str(val) if i == 0 else f" {val}",
                border=1,
                fill=True,
                align="L" if i == 0 else "C",
            )
            x += lar[i]
        pdf.ln(linha_h)
    pdf.ln(3)


def gerar_relatorio_pdf(df_filtrado=None):
    """Gera um relatório PDF ilustrativo com KPIs, gráficos e tabelas.

    Se `df_filtrado` for informado, a seção de eventos de acesso reflete
    esses filtros; caso contrário usa todos os registros do banco.
    """
    df_logs = _preparar_logs(df_filtrado)
    df_toxinas = carregar_dados_toxinas()
    df_serie = serie_temporal_movimentacao()

    conn = sqlite3.connect(DB_FILE)
    df_colabs = pd.read_sql_query(
        "SELECT id, nome, cargo, divisao, nivel_acesso, data_cadastro "
        "FROM colaboradores",
        conn,
    )
    conn.close()

    total = len(df_logs)
    permitidos = int((df_logs["status"] == "PERMITIDO").sum())
    negados = int((df_logs["status"] == "NEGADO").sum())
    taxa = (permitidos / total * 100) if total else 0.0
    dias = df_logs["data"].nunique() if total else 1
    media_dia = total / dias if dias else 0.0
    criticas = int((df_toxinas["estado_conservacao"] == "Crítico").sum())

    agora = datetime.now()
    pdf = _RelatorioPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    _registrar_fonte_pdf(pdf)
    pdf.add_page()

    # --- Cabeçalho ---
    pdf.set_fill_color(15, 23, 42)
    pdf.rect(0, 0, 210, 28, style="F")
    pdf.set_fill_color(13, 148, 136)
    pdf.rect(0, 28, 210, 2, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(_PDF_FONT, "B", 15)
    pdf.set_xy(10, 7)
    pdf.cell(0, 8, "COFRE DE TOXINAS — MINISTÉRIO DO MEIO AMBIENTE")
    pdf.set_font(_PDF_FONT, "", 9)
    pdf.set_xy(10, 16)
    pdf.cell(
        0,
        5,
        "Sistema de Controle de Acesso Biométrico | Relatório de Segurança",
    )
    pdf.set_font(_PDF_FONT, "", 8)
    pdf.set_xy(10, 22)
    pdf.cell(
        0,
        5,
        f"Gerado em {agora.strftime('%d/%m/%Y')} às {agora.strftime('%H:%M:%S')}",
    )
    pdf.set_y(34)

    if df_filtrado is not None:
        pdf.set_font(_PDF_FONT, "", 8.5)
        pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(
            0,
            4,
            "Obs.: este relatório reflete os filtros ativos no Dashboard Analítico.",
        )
        pdf.ln(2)
        pdf.set_text_color(30, 41, 59)

    # --- 1. Indicadores ---
    _secao_pdf(pdf, 1, "Indicadores Executivos")
    _row_kpis(
        pdf,
        [
            ("Total de Acessos", total),
            ("Acessos Permitidos", permitidos),
            ("Tentativas Negadas", negados),
        ],
    )
    _row_kpis(
        pdf,
        [
            ("Taxa de Aprovação", f"{taxa:.1f}%"),
            ("Média / dia", f"{media_dia:.1f}"),
            ("Compartimentos monitorados", df_logs["nivel"].nunique() if total else 0),
        ],
    )
    _row_kpis(
        pdf,
        [
            ("Toxinas custodiadas", len(df_toxinas)),
            ("Unidades em estoque", int(df_toxinas["estoque_unidades"].sum())),
            ("Estado crítico (toxinas)", criticas),
        ],
    )

    # --- 2. Gráficos ---
    _secao_pdf(pdf, 2, "Dashboard de Acessos — Gráficos Ilustrativos")

    pdf.set_font(_PDF_FONT, "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 6, "2.1 Tendência temporal de acessos", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    serie_dia = (
        df_logs.groupby(["data", "status"], as_index=False)
        .size()
        .rename(columns={"size": "contagem"})
    )
    serie_dia = serie_dia.copy()
    serie_dia["data"] = serie_dia["data"].astype(str)
    chart_tendencia = (
        alt.Chart(serie_dia)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("data:T", title="Data"),
            y=alt.Y("contagem:Q", title="Nº de acessos"),
            color=alt.Color(
                "status:N",
                title="Status",
                scale=alt.Scale(
                    domain=["PERMITIDO", "NEGADO"],
                    range=["#00C853", "#D50000"],
                ),
            ),
        )
        .properties(height=300, title="Acessos ao longo do tempo por status")
    )
    _inserir_grafico(
        pdf,
        _chart_png(chart_tendencia),
        "Evolução diária dos eventos de acesso, comparando acessos permitidos e negados.",
    )

    pdf.set_font(_PDF_FONT, "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(
        0,
        6,
        "2.2 Distribuição por compartimento do cofre",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)
    dist_area = (
        df_logs.groupby(["compartimento_curto", "nivel"], as_index=False)
        .size()
        .rename(columns={"size": "contagem"})
        .sort_values(["nivel", "compartimento_curto"])
    )
    chart_dist = (
        alt.Chart(dist_area)
        .mark_bar()
        .encode(
            x=alt.X("contagem:Q", title="Nº de eventos"),
            y=alt.Y("compartimento_curto:N", title="", sort="-x"),
            color=alt.Color(
                "nivel:O",
                title="Nível",
                scale=alt.Scale(
                    domain=["1", "2", "3"],
                    range=["#2E7D32", "#F9A825", "#C62828"],
                ),
            ),
        )
        .properties(height=300, title="Eventos por nível de segurança")
    )
    _inserir_grafico(
        pdf,
        _chart_png(chart_dist),
        (
            "Eventos de acesso por nível (verde: Permissão Geral, amarelo: "
            "Diretores de Divisões, vermelho: Ministro do Meio Ambiente)."
        ),
    )

    pdf.set_font(_PDF_FONT, "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 6, "2.3 Movimentação por hora do dia", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    serie_hora = (
        df_logs.groupby(["hora", "status"], as_index=False)
        .size()
        .rename(columns={"size": "contagem"})
    )
    chart_hora = (
        alt.Chart(serie_hora)
        .mark_bar()
        .encode(
            x=alt.X("hora:O", title="Hora do dia"),
            y=alt.Y("contagem:Q", title="Nº de eventos"),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(
                    domain=["PERMITIDO", "NEGADO"],
                    range=["#00C853", "#D50000"],
                ),
            ),
        )
        .properties(height=300, title="Acessos por horário")
    )
    _inserir_grafico(
        pdf,
        _chart_png(chart_hora),
        "Volume de acessos por hora, útil para identificar horários de pico e de risco.",
    )

    pdf.set_font(_PDF_FONT, "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(
        0, 6, "2.4 Colaboradores mais ativos", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(1)
    top_colabs = (
        df_logs.groupby("colaborador_nome", as_index=False)
        .size()
        .rename(columns={"size": "contagem"})
        .sort_values("contagem", ascending=False)
        .head(10)
    )
    chart_top = (
        alt.Chart(top_colabs)
        .mark_bar()
        .encode(
            x=alt.X("contagem:Q", title="Nº de eventos"),
            y=alt.Y("colaborador_nome:N", title="", sort="-x"),
            color=alt.Color("contagem:Q", scale=alt.Scale(scheme="viridis")),
        )
        .properties(height=300, title="Top colaboradores")
    )
    _inserir_grafico(
        pdf,
        _chart_png(chart_top),
        "Os dez colaboradores com o maior número de eventos de acesso registrados.",
    )

    # --- 3. Panorama do cofre ---
    _secao_pdf(pdf, 3, "Panorama do Cofre de Toxinas")

    pdf.set_font(_PDF_FONT, "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(
        0,
        6,
        "3.1 Estoque de toxinas por classe química",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)
    est_por_classe = (
        df_toxinas.groupby("classe", as_index=False)
        .agg(estoque_unidades=("estoque_unidades", "sum"))
    )
    chart_estoque = (
        alt.Chart(est_por_classe)
        .mark_bar()
        .encode(
            x=alt.X("classe:N", title="", sort="-y"),
            y=alt.Y("estoque_unidades:Q", title="Unidades em estoque"),
            color=alt.Color("classe:N", legend=None),
        )
        .properties(height=300, title="Unidades em estoque por classe")
    )
    _inserir_grafico(
        pdf,
        _chart_png(chart_estoque),
        "Total de unidades custodiadas no cofre por classe de toxina.",
    )

    pdf.set_font(_PDF_FONT, "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(
        0,
        6,
        "3.2 Série temporal de movimentações por divisão",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)
    chart_serie = (
        alt.Chart(df_serie)
        .mark_line(point=True)
        .encode(
            x=alt.X("mes:T", title="Mês / Ano"),
            y=alt.Y("movimentacoes:Q", title="Movimentações"),
            color=alt.Color("divisao:N", title="Divisão"),
        )
        .properties(height=300, title="Movimentações mensais por divisão")
    )
    _inserir_grafico(
        pdf,
        _chart_png(chart_serie),
        "Série mensal simulada de movimentações de toxinas por divisão do ministério.",
    )

    # --- 4. Logs de Acesso ---
    _secao_pdf(pdf, 4, "Logs de Acesso")
    mapa_status = {
        "PERMITIDO": ((220, 252, 231), (22, 101, 52)),
        "NEGADO": ((254, 226, 226), (153, 27, 27)),
    }
    logs_linhas = [
        (r["data_hora"].strftime("%d/%m/%Y %H:%M"), r["colaborador_nome"],
         r["compartimento_curto"], r["nivel"], r["status"])
        for _, r in df_logs.sort_values("data_hora", ascending=False).iterrows()
    ]
    _tabela_pdf(
        pdf,
        "Eventos de acesso registrados",
        ["Data / Hora", "Colaborador", "Compartimento", "Nível", "Status"],
        logs_linhas,
        col_destaque=4,
        mapa=mapa_status,
    )

    # --- 5. Colaboradores ---
    _secao_pdf(pdf, 5, "Equipe do Cofre")
    colabs_linhas = [
        (r["nome"], r["cargo"] or "—", r["divisao"] or "Sem divisão", rotulo_nivel(r["nivel_acesso"]))
        for _, r in df_colabs.iterrows()
    ]
    _tabela_pdf(
        pdf,
        "Colaboradores cadastrados",
        ["Nome", "Cargo / Função", "Divisão", "Nível de Acesso"],
        colabs_linhas,
    )

    # --- 6. Toxinas ---
    _secao_pdf(pdf, 6, "Catálogo de Toxinas")
    tox_linhas = [
        (r["id_toxina"], r["nome"], r["classe"], r["compartimento"],
         r["estoque_unidades"], r["estado_conservacao"])
        for _, r in df_toxinas.iterrows()
    ]
    _tabela_pdf(
        pdf,
        "Substâncias custodiadas no cofre",
        ["ID", "Toxina", "Classe", "Compartimento", "Estoque", "Estado"],
        tox_linhas,
    )

    # --- 7. Cadeia de Custódia ---
    _secao_pdf(pdf, 7, "Cadeia de Custódia")
    custodia = pd.DataFrame(
        [
            {"lote": "TOX-0006/2026", "toxina": "Toxina Botulínica Tipo A",
             "de": "Compartimento A-04", "para": "Laboratório Central",
             "responsavel": "Diretor de Pesquisa", "data_hora": "2026-08-14 09:32"},
            {"lote": "TOX-0001/2026", "toxina": "Ricina",
             "de": "Compartimento A-01", "para": "Sala de Análises",
             "responsavel": "Diretor de Toxicologia", "data_hora": "2026-08-15 14:05"},
            {"lote": "TOX-0004/2026", "toxina": "Microcistina-LR",
             "de": "Compartimento B-01", "para": "Incinerador controlado",
             "responsavel": "Ministro do Meio Ambiente", "data_hora": "2026-09-02 10:12"},
        ]
    )
    custodia_linhas = [
        (r["lote"], r["toxina"], r["de"], r["para"], r["responsavel"], r["data_hora"])
        for _, r in custodia.iterrows()
    ]
    _tabela_pdf(
        pdf,
        "Movimentações de substâncias (exemplo)",
        ["Lote", "Toxina", "De", "Para", "Responsável", "Data / Hora"],
        custodia_linhas,
    )

    return bytes(pdf.output())


def recortar_centro_rosto(img_path):
    """Corta a área central focando no rosto."""
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            left = int(w * 0.20)
            top = int(h * 0.05)
            right = int(w * 0.80)
            bottom = int(h * 0.85)
            crop_img = img.crop((left, top, right, bottom))
            crop_img.save(img_path)
    except Exception as e:
        registrar_erro("IMAGEM", "Processamento de Imagem", str(e))


_DETECTOR_MTCNN = None


def _detector_mtcnn():
    global _DETECTOR_MTCNN
    if _DETECTOR_MTCNN is None:
        from mtcnn import MTCNN

        _DETECTOR_MTCNN = MTCNN()
    return _DETECTOR_MTCNN


def _imgs_bytes_para_numpy(frames_bytes):
    """Converte uma lista de bytes (JPEG) em imagens RGB (numpy)."""
    imgs = []
    for b in frames_bytes:
        arr = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        if arr is not None:
            imgs.append(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
    return imgs


def _regiao_uniao(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = min(ax, bx)
    y1 = min(ay, by)
    x2 = max(ax + aw, bx + bw)
    y2 = max(ay + ah, by + bh)
    return x1, y1, x2, y2


# ---------- Liveness V2 — anti-spoofing reforçado ----------
LIMIAR_MOVIMENTO = 0.015
LIMIAR_N_COMPOS = 4
LIMIAR_PARALAXE = 0.05
LIMIAR_PISCADA = 0.60  # abertura do olho cai abaixo de 60% do baseline = piscada
JANELA_MINIMA_S = 2.0
LIMIAR_TELA_FFT = 12.0


def _regiao_uniao(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = min(ax, bx)
    y1 = min(ay, by)
    x2 = max(ax + aw, bx + bw)
    y2 = max(ay + ah, by + bh)
    return x1, y1, x2, y2


_DLIB_DETECTOR = None
_DLIB_PREDICTOR = None


def _carregar_preditor_dlib():
    """Carrega o detector/predictor de 68 landmarks do dlib (uma vez)."""
    global _DLIB_DETECTOR, _DLIB_PREDICTOR
    if _DLIB_PREDICTOR is not None:
        return _DLIB_PREDICTOR
    import dlib
    from site import getsitepackages, getusersitepackages

    candidato = None
    for raiz in getsitepackages() + [getusersitepackages()]:
        achado = glob.glob(
            os.path.join(
                raiz, "**", "shape_predictor_68_face_landmarks.dat"
            ),
            recursive=True,
        )
        if achado:
            candidato = achado[0]
            break
    if not candidato:
        raise FileNotFoundError(
            "shape_predictor_68_face_landmarks.dat não encontrado."
        )
    _DLIB_DETECTOR = dlib.get_frontal_face_detector()
    _DLIB_PREDICTOR = dlib.shape_predictor(candidato)
    return _DLIB_PREDICTOR


def _ear_dos_olhos(cinza):
    """EAR (Eye Aspect Ratio) por olho via dlib 68 landmarks.
    Olho aberto ~0.25-0.33; piscado <-0.12. Retorna (esq, dir) ou None."""
    try:
        pred = _carregar_preditor_dlib()
    except Exception as e:
        registrar_erro("BIOMETRIA", "Dlib Landmarks", str(e))
        return None
    faces = _DLIB_DETECTOR(cinza)
    if not faces:
        return None
    face = max(faces, key=lambda r: r.width() * r.height())
    try:
        shape = pred(cinza, face)
    except Exception:
        return None

    def ear(indices):
        pts = [
            np.array((shape.part(i).x, shape.part(i).y)) for i in indices
        ]
        return (
            np.linalg.norm(pts[1] - pts[5]) + np.linalg.norm(pts[2] - pts[4])
        ) / (2.0 * np.linalg.norm(pts[0] - pts[3]) + 1e-6)

    return ear([36, 37, 38, 39, 40, 41]), ear([42, 43, 44, 45, 46, 47])


def _piscada_detectada(ears_por_quadro):
    """True se algum olho piscou (EAR caiu abaixo de 60% do baseline aberto).
    None se não houve landmarks suficientes (inconclusivo)."""
    validos = [e for e in ears_por_quadro if e is not None]
    if not validos:
        return None
    esq = [e[0] for e in validos]
    dir_ = [e[1] for e in validos]
    for serie in (esq, dir_):
        if len(serie) < 2:
            continue
        baseline = max(serie)
        if baseline < 0.20:
            continue
        if min(serie) < LIMIAR_PISCADA * baseline:
            return True
    return False


def _variacao_paralaxe(metas):
    """Variação das proporções geométricas (nariz↔olhos↔boca) ao longo dos
    quadros. Rosto real girando muda essas proporções; foto plana deslizando
    mantém as proporções constantes (pura translação 2D)."""
    of_x, dy_boca = [], []
    for meta in metas:
        kp = meta["kp"]
        le = np.array(kp["left_eye"], dtype=np.float64)
        re = np.array(kp["right_eye"], dtype=np.float64)
        nose = np.array(kp["nose"], dtype=np.float64)
        ml = np.array(kp["mouth_left"], dtype=np.float64)
        mr = np.array(kp["mouth_right"], dtype=np.float64)
        eye_w = float(np.linalg.norm(re - le))
        if eye_w < 10:
            continue
        centro_x = 0.5 * (le[0] + re[0])
        centro_y = 0.5 * (le[1] + re[1])
        of_x.append((nose[0] - centro_x) / eye_w)
        dy_boca.append((0.5 * (ml[1] + mr[1]) - centro_y) / eye_w)
    if not of_x:
        return 0.0
    return float(np.std(of_x) + np.std(dy_boca))


def _detectar_tela(cinza, face_box):
    """Força de padrão periódico de alta frequência (Moiré/grade de tela) no
    recorte do rosto via FFT. Valor alto indica imagem vinda de uma tela."""
    bx, by, bw, bh = face_box
    h, w = cinza.shape[:2]
    bx1, by1 = max(bx, 0), max(by, 0)
    bx2, by2 = min(bx + bw, w), min(by + bh, h)
    crop = cinza[by1:by2, bx1:bx2]
    if crop.size < 32 * 32:
        return 0.0
    g = cv2.resize(crop, (256, 256)).astype(np.float32)
    janela_hann = np.outer(np.hanning(256), np.hanning(256)).astype(
        np.float32
    )
    g = g * janela_hann
    mag = np.abs(np.fft.fftshift(np.fft.fft2(g)))
    H, W = mag.shape
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt((yy - H // 2) ** 2 + (xx - W // 2) ** 2)
    raio_max = 0.47 * H
    anulo = (d > 0.55 * raio_max) & (d <= raio_max)
    if anulo.sum() < 64:
        return 0.0
    an = mag[anulo]
    media = float(an.mean())
    if media <= 1e-9:
        return 0.0
    return float(an.max() / media)


def avaliar_liveness(frames):
    """V2: 6 barreiras anti-fraude. `frames` = [(bytes_do_quadro, timestamp)].

    Retorna (aprovado, motivo, detalhes, idx_melhor_quadro).
    Barreiras: janela >= 2s; movimento; padrão orgânico temporal;
    variação geométrica (parallax 3D); >= 1 piscada; ausência de tela (Moiré).
    """
    imgs, ts = [], []
    for b, t in frames:
        arr = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        if arr is not None:
            imgs.append(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
            ts.append(t)

    detalhes = {"quadros_capturados": len(imgs)}
    if len(imgs) < 3:
        return False, "É necessário capturar ao menos 3 quadros.", detalhes, 0

    if len(ts) >= 2 and (ts[-1] - ts[0]) < JANELA_MINIMA_S:
        return (
            False,
            "Captura rápida demais (menos de 2s entre o 1º e o último quadro) "
            "— típico de rajada de fotos, sem interação real.",
            detalhes,
            0,
        )

    detector = _detector_mtcnn()
    grays, boxes, metas = [], [], []
    for arr in imgs:
        hgt, wdt = arr.shape[:2]
        escala = 360.0 / float(hgt)
        pequeno = cv2.resize(arr, (int(wdt * escala), 360))
        cinza = cv2.cvtColor(pequeno, cv2.COLOR_RGB2GRAY)
        faces = detector.detect_faces(pequeno)
        meta = None
        if faces:
            face = max(faces, key=lambda f: f["box"][2] * f["box"][3])
            x, y, w, h2 = face["box"]
            if w >= 30 and h2 >= 30:
                meta = {"box": tuple(face["box"]), "kp": face["keypoints"]}
        grays.append(cinza)
        metas.append(meta)
        boxes.append(meta["box"] if meta else None)

    presentes = [i for i, m in enumerate(metas) if m is not None]
    n_req = max(2, int(round(len(imgs) * 0.6)))
    detalhes["rostos_detectados"] = len(presentes)
    if len(presentes) < n_req:
        return (
            False,
            "Rosto não detectado em quadros suficientes (imagem borrada, "
            "escura ou fora do círculo).",
            detalhes,
            0,
        )

    diffs = []
    for k in range(len(presentes) - 1):
        a, b = presentes[k], presentes[k + 1]
        x1, y1, x2, y2 = _regiao_uniao(boxes[a], boxes[b])
        mov = (
            float(np.mean(cv2.absdiff(grays[a], grays[b])[y1:y2, x1:x2]))
            / 255.0
        )
        diffs.append(mov)
    movimento_max = max(diffs)
    detalhes["movimento_máximo"] = f"{movimento_max * 100:.2f}%"

    if movimento_max < LIMIAR_MOVIMENTO:
        return (
            False,
            "**Movimento insuficiente do rosto** entre os quadros — típico de "
            "foto ou tela parada exibida à câmera. Repita o mini vídeo movendo "
            "a cabeça e piscando os olhos a cada captura.",
            detalhes,
            0,
        )

    regioes = []
    for idx in presentes:
        bx, by, bw, bh = boxes[idx]
        crop = grays[idx][by : by + bh, bx : bx + bw]
        regioes.append(cv2.resize(crop, (80, 80)))
    pilha = np.stack(regioes).astype(np.float32)
    var_map = pilha.var(axis=0)
    q75 = np.percentile(var_map, 75)
    alto = (var_map >= q75).astype(np.uint8) if q75 > 0 else None
    n_comps = 0
    if alto is not None:
        n_comps = cv2.connectedComponents(alto, connectivity=8)[0]
    detalhes["regiões_de_variação"] = int(n_comps)
    if n_comps < LIMIAR_N_COMPOS:
        detalhes["padrão_de_movimento"] = "Rígido / uniforme (possível foto)"
        return (
            False,
            "**Movimento rígido e plano** — a imagem se moveu como uma única "
            "peça (foto ou tela deslizando), sem o padrão orgânico de um rosto "
            "real. Repita girando a cabeça de verdade (olhe para os lados) e "
            "pisque.",
            detalhes,
            0,
        )

    paralaxe = (
        _variacao_paralaxe([metas[i] for i in presentes]) if presentes else 0.0
    )
    detalhes["variação_geométrica_(parallax)"] = f"{paralaxe:.3f}"
    if paralaxe < LIMIAR_PARALAXE:
        detalhes["padrão_de_movimento"] = "Rígido / uniforme (possível foto)"
        return (
            False,
            "**Sem variação 3D da face** — as proporções entre nariz/olhos/"
            "boca não mudaram durante o movimento (translação rígida, típica "
            "de foto deslizando). Gire a cabeça para os lados.",
            detalhes,
            0,
        )

    ears_por_quadro = []
    for idx in presentes:
        ears_por_quadro.append(_ear_dos_olhos(grays[idx]))
    piscou = _piscada_detectada(ears_por_quadro)
    detalhes["piscada_detectada"] = {
        True: "Sim",
        False: "Não",
        None: "Inconclusivo",
    }[piscou]
    if piscou is None:
        return (
            False,
            "**Não foi possível analisar os olhos** — aproxime o rosto do "
            "círculo, olhe de frente e em boa iluminação para repetir.",
            detalhes,
            0,
        )
    if not piscou:
        return (
            False,
            "**Nenhuma piscada detectada** — é necessário **piscar** (fechar e "
            "abrir os olhos) durante as capturas. Fotos e telas nunca piscam.",
            detalhes,
            0,
        )

    melhor = max(presentes, key=lambda i: (boxes[i][2] * boxes[i][3]))
    sinal_tela = _detectar_tela(grays[melhor], boxes[melhor])
    detalhes["sinal_de_tela_(moiré)"] = f"{sinal_tela:.1f}"
    if sinal_tela >= LIMIAR_TELA_FFT:
        return (
            False,
            "**Padrão de tela detectado (Moiré)** — a imagem parece ter sido "
            "exibida em um monitor/celular diante da câmera. Aproxime-se "
            "iluminando o rosto diretamente e evite telas.",
            detalhes,
            melhor,
        )

    detalhes["padrão_de_movimento"] = "Orgânico (faces reais)"
    return True, "Movimento 3D do rosto + piscada detectados.", detalhes, melhor


def _melhor_match_biometrico(temp_test_path):
    """Busca o colaborador cadastrado mais próximo (VGG-Face / cosine)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, nome, foto_path FROM colaboradores")
    cadastrados = cur.fetchall()
    conn.close()

    melhor_candidato = None
    menor_distancia = 1.0
    for cid, cnome, cpath in cadastrados:
        if not os.path.exists(cpath):
            continue
        try:
            res = DeepFace.verify(
                img1_path=temp_test_path,
                img2_path=cpath,
                model_name="VGG-Face",
                detector_backend="skip",
                distance_metric="cosine",
                enforce_detection=False,
            )
            distancia = res.get("distance", 1.0)
            if distancia < menor_distancia:
                menor_distancia = distancia
                melhor_candidato = (cid, cnome)
        except Exception as e:
            registrar_erro(
                "BIOMETRIA", f"Validação Biométrica ({cnome})", str(e)
            )
    return melhor_candidato, menor_distancia


def _conceder_ou_negar(
    colab_id, colab_nome, menor_distancia, nivel_requerido, area_requerida
):
    """Decisão final pós-reconhecimento: nível, login, logs e alertas."""
    estava_autenticado = st.session_state.get("autenticado", False)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT nivel_acesso, usuario, pode_cadastrar "
        "FROM colaboradores WHERE id = ?",
        (colab_id,),
    )
    linha_nivel = cur.fetchone()
    conn.close()
    nivel_colab = int(linha_nivel[0]) if linha_nivel else 1
    usuario_credencial = linha_nivel[1] if linha_nivel else None
    pode_cadastrar = int(linha_nivel[2] or 0) if linha_nivel else 0

    if nivel_colab >= nivel_requerido:
        st.success(
            f"✅ **ACESSO AUTORIZADO!**\n\nBem-vindo(a), **{colab_nome}**! "
            f"(Distância: {menor_distancia:.3f})\nCompartimento liberado: "
            f"**{area_requerida}**"
        )
        registrar_log(colab_nome, area_requerida, "PERMITIDO")
        st.session_state.pop("sessao_expirada", None)
        st.session_state["usuario_logado"] = {
            "id": colab_id,
            "nome": colab_nome,
            "nivel_acesso": nivel_colab,
            "usuario": usuario_credencial,
            "pode_cadastrar": pode_cadastrar,
            "login_ts": time.time(),
            "metodo": "biometria",
        }
        st.session_state["autenticado"] = True
        st.toast(
            "🔓 Sessão iniciada. Compartimentos liberados conforme o nível do colaborador.",
            icon="🔓",
        )
        if not estava_autenticado:
            st.session_state["redirecionar_para"] = "🔐 Cofre de Toxinas do MMA"
            st.rerun()
        if not usuario_credencial:
            st.info(
                "ℹ️ **Acesso por biometria.** Este colaborador ainda não possui "
                "usuário/senha definidos. Solicite ao nível 3 (Ministro) que "
                "defina as credenciais na aba 🛡️ **Gestão de Acessos**."
            )
        return True

    st.error(
        f"🚫 **ACESSO NEGADO!**\n\nColaborador identificado (**{colab_nome}**), "
        f"porém com nível `{nivel_colab}` (não possui o nível `{nivel_requerido}` "
        f"exigido para o compartimento `{area_requerida}`)."
    )
    registrar_log(
        colab_nome,
        area_requerida,
        "NEGADO",
        {"motivo": "Nível insuficiente", "nivel_colab": nivel_colab},
    )
    _registrar_e_verificar_bloqueio(
        area_requerida,
        f"Acesso indevido: {colab_nome} (nível {nivel_colab}) tentou o "
        f"compartimento de nível {nivel_requerido}.",
        origem="foto",
    )
    enviar_alerta_seguranca(
        area_requerida,
        f"Colaborador {colab_nome} tentou acessar o compartimento de nível "
        f"{nivel_requerido} sem permissão (possui nível {nivel_colab}).",
    )
    return False


# ---------- Política de bloqulo temporário por compartimento ----------
JANELA_FRAUDE_S = 10 * 60      # janela de contagem de tentativas (10 min)
DURACAO_BLOQUEIO_S = 15 * 60   # bloqueio após limite (15 min)
MAX_TENTATIVAS = 3             # tentativas de fraude/negadas p/ disparar bloqueio


def _registrar_tentativa_fraude(compartimento, motivo, detalhes=None,
                                origem="mini_video"):
    """Registra uma tentativa de fraude/negada e retorna o nº na janela."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    dh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO tentativas_seguranca "
        "(compartimento, data_hora, motivo, detalhes, origem) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            compartimento,
            dh,
            motivo,
            json.dumps(detalhes or {}, ensure_ascii=False),
            origem,
        ),
    )
    conn.commit()
    desde = (datetime.now() - timedelta(seconds=JANELA_FRAUDE_S)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur.execute(
        "SELECT COUNT(*) FROM tentativas_seguranca "
        "WHERE compartimento = ? AND data_hora >= ?",
        (compartimento, desde),
    )
    n = cur.fetchone()[0]
    conn.close()
    return int(n)


def _bloqueio_ativo(compartimento):
    """Retorna (bloqueado, minutos_restantes) para o compartimento."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    desde = (datetime.now() - timedelta(seconds=JANELA_FRAUDE_S)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur.execute(
        "SELECT COUNT(*) FROM tentativas_seguranca "
        "WHERE compartimento = ? AND data_hora >= ?",
        (compartimento, desde),
    )
    n = cur.fetchone()[0]
    encerra_em = None
    if n >= MAX_TENTATIVAS:
        cur.execute(
            "SELECT data_hora FROM tentativas_seguranca "
            "WHERE compartimento = ? AND data_hora >= ? ORDER BY id DESC LIMIT 1",
            (compartimento, desde),
        )
        ultima = cur.fetchone()
        if ultima:
            t_ultima = datetime.strptime(ultima[0], "%Y-%m-%d %H:%M:%S")
            encerra_em = t_ultima + timedelta(seconds=DURACAO_BLOQUEIO_S)
    conn.close()
    if encerra_em is None:
        return False, 0
    restantes = (encerra_em - datetime.now()).total_seconds()
    if restantes <= 0:
        return False, 0
    minutos = int(restantes // 60) + (1 if restantes % 60 else 0)
    return True, minutos


def _tentativas_recentes(compartimento, limite=8):
    """Lista das últimas tentativas de fraude/negadas do compartimento."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT data_hora, motivo, origem FROM tentativas_seguranca "
        "WHERE compartimento = ? ORDER BY id DESC LIMIT ?",
        (compartimento, limite),
    )
    linhas = [
        {"Data/Hora": dh, "Motivo": m, "Origem": o}
        for dh, m, o in cur.fetchall()
    ]
    conn.close()
    return linhas


def _registrar_e_verificar_bloqueio(compartimento, motivo, detalhes=None,
                                    origem="mini_video"):
    """Registra a tentativa; se atingiu o limite, dispara alerta e bloqueia."""
    n = _registrar_tentativa_fraude(
        compartimento, motivo, detalhes, origem
    )
    bloq, minutos = _bloqueio_ativo(compartimento)
    if bloq and st.session_state.get("alertou_bloqueio") != compartimento:
        st.session_state["alertou_bloqueio"] = compartimento
        enviar_alerta_seguranca(
            compartimento,
            f"⛔ **BLOQUEIO TEMPORÁRIO ATIVADO** no compartimento "
            f"{compartimento} após {n} tentativas de fraude/acesso indevido. "
            f"Validação suspensa por {minutos} min. Motivo: {motivo}",
        )
    return bloq, minutos


def _render_mini_video(nivel_requerido, area_requerida):
    """UI do mini vídeo anti-fraude (liveness) + validação biométrica."""
    st.info(
        "🎥 **Mini vídeo anti-fraude.** Posicione o rosto no círculo e capture "
        "**de 4 a 8 quadros**, **girando a cabeça** para os lados/cima-baixo e "
        "**piscando** durante as capturas (as fotos nunca piscam). O sistema "
        "exige >2s de captura, movimento orgânico 3D, ao menos uma piscada e "
        "ausência de tela (Moiré) — **fotos na tela do celular serão bloqueadas**."
    )

    if "live_frames" not in st.session_state:
        st.session_state["live_frames"] = []

    frame = st.camera_input(
        "🎥 Capture os quadros do mini vídeo (mova o rosto entre as capturas)",
        key="live_cam_webcam",
    )

    if frame is not None:
        novo = frame.getvalue()
        fichas = st.session_state["live_frames"]
        if len(fichas) < 8 and (
            not fichas
            or hashlib.sha1(novo).hexdigest()
            != hashlib.sha1(fichas[-1][0]).hexdigest()
        ):
            fichas.append((novo, time.time()))
            st.toast(
                f"📸 Quadro {len(fichas)} capturado — mova a cabeça e capture mais!",
                icon="🎥",
            )

    n = len(st.session_state["live_frames"])
    c1, c2 = st.columns([1, 1])
    c1.metric("Quadros capturados", f"{n}/8")
    if c2.button("🧹 Limpar quadros", use_container_width=True):
        st.session_state["live_frames"] = []
        st.session_state["alertou_bloqueio"] = None
        st.rerun()

    if st.session_state["live_frames"]:
        thumbs = [
            Image.open(io.BytesIO(b)).copy()
            for b, _ in st.session_state["live_frames"]
        ]
        thumbs = [t.resize((90, int(90 * t.height / t.width))) for t in thumbs]
        st.image(
            thumbs,
            caption=[f"Q{i+1}" for i in range(len(thumbs))],
            width=90,
        )

    if st.button(
        "🔍 Analisar Mini Vídeo e Validar Acesso",
        type="primary",
        disabled=(n < 3),
    ):
        aprovado, motivo, detalhes, idx_melhor = avaliar_liveness(
            st.session_state["live_frames"]
        )
        if not aprovado:
            st.error(
                f"🚨 **ACESSO NEGADO — FRAUDE SUSPEITA!**\n\n{motivo}\n\n"
                f"Detalhes: {detalhes}"
            )
            registrar_log(
                "Desconhecido",
                area_requerida,
                "NEGADO",
                {"motivo": motivo, **detalhes},
            )
            bloq, minutos = _registrar_e_verificar_bloqueio(
                area_requerida,
                f"Mini vídeo bloqueado: {motivo}",
                detalhes,
                origem="mini_video",
            )
            if bloq:
                st.error(
                    f"⛔ **BLOQUEIO TEMPORÁRIO ATIVADO** neste compartimento. "
                    f"Nova validação permitida em até {minutos} min."
                )
            else:
                enviar_alerta_seguranca(
                    area_requerida,
                    "Tentativa de acesso bloqueada pelo mini vídeo anti-fraude: "
                    f"{motivo}",
                )
            return

        st.success(
            f"✅ **Liveness aprovado!** {motivo}\n\nDetalhes: {detalhes}"
        )

        temp_test_path = "temp_test.jpg"
        with open(temp_test_path, "wb") as f:
            f.write(st.session_state["live_frames"][idx_melhor][0])
        recortar_centro_rosto(temp_test_path)

        try:
            carregar_modelo_facial()
            with st.spinner("Validando biometria facial no melhor quadro..."):
                melhor_candidato, menor_distancia = _melhor_match_biometrico(
                    temp_test_path
                )
            if os.path.exists(temp_test_path):
                os.remove(temp_test_path)

            if melhor_candidato is not None and menor_distancia <= 0.35:
                colab_id, colab_nome = melhor_candidato
                _conceder_ou_negar(
                    colab_id,
                    colab_nome,
                    menor_distancia,
                    nivel_requerido,
                    area_requerida,
                )
            else:
                st.error(
                    f"🚨 **ACESSO NEGADO!** Biometria não bateu com nenhum "
                    f"cadastrado. (Menor distância: {menor_distancia:.3f})"
                )
                registrar_log(
                    "Desconhecido",
                    area_requerida,
                    "NEGADO",
                    {"motivo": "Biometria não reconhecida (mini vídeo)"},
                )
                _registrar_e_verificar_bloqueio(
                    area_requerida,
                    "Biometria não reconhecida (mini vídeo).",
                    origem="mini_video",
                )
                enviar_alerta_seguranca(
                    area_requerida,
                    "Pessoa não identificada/desconhecida (mini vídeo).",
                )
        except Exception as e:
            registrar_erro("GERAL", "Validação de Acesso (Mini Vídeo)", str(e))
            st.error(
                f"❌ Ocorreu um erro inesperado na validação. Veja a aba 🐞 "
                f"Registro de Erros para ajuda. ({e})"
            )


def registrar_log(nome, area, status, detalhes=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    dh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO logs_acesso "
        "(colaborador_nome, setor, data_hora, status, detalhes) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            nome,
            area,
            dh,
            status,
            json.dumps(detalhes, ensure_ascii=False) if detalhes else None,
        ),
    )
    conn.commit()
    conn.close()


def obter_ajuda_erro(tipo, mensagem):
    """Retorna (descricao, sugerida) amigáveis para o tipo/mensagem do erro."""
    m = (mensagem or "").lower()
    generica = (
        "Ocorreu um erro inesperado durante a operação.",
        "Verifique o texto técnico abaixo e, se persistir, revise a "
        "configuração do sistema ou contate o suporte técnico.",
    )

    ajuda = {
        "EMAIL": [
            (
                ("authenticationfailed", "auth", "535", "invalid credentials",
                 "usernametoken"),
                "As credenciais do e-mail remetente estão incorretas ou a "
                "'Senha de App' não foi configurada para o Gmail.",
                "No Gmail: ative a verificação em 2 etapas e crie uma "
                "'Senha de App' em https://myaccount.google.com/apppasswords. "
                "Cole essa senha no campo 'Senha de App' das configurações.",
            ),
            (
                ("errno -2", "name or service not known", "dns",
                 "getaddrinfo", "temporarily unable", "connection"),
                "Não foi possível conectar ao servidor de e-mail (SMTP). "
                "Provavelmente falta conexão com a internet.",
                "Verifique sua conexão com a internet. Se o problema "
                "persistir, teste em outra rede.",
            ),
            (
                ("timed out", "timeout", "slow"),
                "O servidor de e-mail demorou demais para responder (timeout).",
                "Tente novamente mais tarde. Verifique se o firewall/antivírus "
                "não está bloqueando a porta SMTP (587).",
            ),
        ],
        "TWILIO": [
            (
                ("401", "unauthorized", "authenticate", "credentials"),
                "As credenciais da Twilio (Account SID / Auth Token) estão "
                "inválidas.",
                "Revise o Account SID e o Auth Token em "
                "https://console.twilio.com e atualize as configurações.",
            ),
            (
                ("errno -2", "name or service not known", "dns",
                 "getaddrinfo", "temporarily unable", "connection"),
                "Não foi possível conectar à API da Twilio. Provavelmente "
                "falta conexão com a internet.",
                "Verifique sua conexão com a internet.",
            ),
            (
                ("timed out", "timeout", "slow"),
                "A API da Twilio demorou demais para responder (timeout).",
                "Tente novamente mais tarde.",
            ),
        ],
        "IMAGEM": [
            (
                ("cannot identify", "not an image", "cannot open",
                 "unidentified image"),
                "O arquivo enviado não é uma imagem válida ou está corrompido "
                "(uso do formato JPG/PNG esperado).",
                "Utilize uma imagem JPG ou PNG válida e nítida.",
            ),
        ],
        "BIOMETRIA": [
            (
                ("verify", "no face", "face", "detect", "enforce_detection"),
                "Não foi possível processar a identificação facial da imagem "
                "(rosto pouco nítido ou ausente).",
                "Centralize o rosto na câmera com boa iluminação e tente "
                "novamente.",
            ),
        ],
        "BANCO": [
            (
                ("no such table", "database is locked", "operationalerror",
                 "unable to open database"),
                "Problema ao acessar o banco de dados local "
                "(controle_acesso.db).",
                "Verifique se o arquivo existe e não está bloqueado por outro "
                "processo. Reinicie a aplicação se necessário.",
            ),
        ],
    }

    for tipo_chave, regras in ajuda.items():
        if tipo != tipo_chave:
            continue
        for (padroes, desc, sug) in regras:
            if any(p in m for p in padroes):
                return desc, sug
    return generica


def registrar_erro(tipo, modulo, mensagem):
    """Registra um erro na tabela logs_erros com ajuda amigável associada."""
    try:
        descricao, sugerida = obter_ajuda_erro(tipo, mensagem)
        dh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logs_erros (data_hora, tipo, modulo, mensagem, "
            "descricao, sugerida) VALUES (?, ?, ?, ?, ?, ?)",
            (dh, tipo, modulo, mensagem, descricao, sugerida),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def limpar_logs_erros():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logs_erros")
        conn.commit()
        conn.close()
    except Exception:
        pass


def _msg_padrao_whatsapp(area, motivo, dh):
    """Mensagem padrão do alerta de segurança (enviada ao grupo)."""
    return (
        "🚨 *ALERTA DE SEGURANÇA*\n\n"
        "Tentativa de acesso negada!\n"
        f"- *Compartimento do Cofre:* {area}\n"
        f"- *Data/Hora:* {dh}\n"
        f"- *Motivo:* {motivo}"
    )


def _normalizar_grupo_id(raw):
    """Extrai o código do grupo de um link de convite ou de um código puro."""
    raw = (raw or "").strip()
    if "chat.whatsapp.com/" in raw:
        raw = raw.split("chat.whatsapp.com/", 1)[1]
    raw = raw.split("?", 1)[0].strip("/")
    return raw


WA_PROFILE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".waprofile"
)

MSG_INPUT_SELECTOR = (
    'div[data-testid="conversation-panel-message-input"], '
    'div[contenteditable="true"][role="textbox"], '
    'footer div[contenteditable="true"]'
)


def _limpar_chromes_perfil():
    """Encerra Chomes órfãos que ficaram presos no perfil de automação.

    Sem isso, uma tentativa anterior interrompida prende o diretório
    .waprofile e o Chrome novo falha com 'session not created'.
    """
    padrao = os.path.abspath(WA_PROFILE_DIR)
    try:
        saida = subprocess.run(
            ["pgrep", "-f", padrao], capture_output=True, timeout=10
        )
        pids = saida.stdout.decode().split()
        for pid in pids:
            try:
                os.kill(int(pid), 9)
            except Exception:
                pass
    except Exception:
        pass
    time.sleep(1)


def _wa_driver():
    """Inicia o Chrome com o perfil de automação do WhatsApp Web."""
    opts = Options()
    opts.add_argument(f"--user-data-dir={WA_PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--window-size=1280,800")
    return webdriver.Chrome(options=opts)


def _abrir_whatsapp(tentativas=3):
    """Abre o Chrome no perfil e navega ao WhatsApp Web, com retry."""
    _limpar_chromes_perfil()
    for i in range(tentativas):
        drv = None
        try:
            drv = _wa_driver()
            drv.get("https://web.whatsapp.com/")
            return drv
        except Exception as e:
            try:
                if drv is not None:
                    drv.quit()
            except Exception:
                pass
            registrar_erro(
                "WHATSAPP",
                "Abrir WhatsApp Web",
                f"Tentativa {i + 1} de {tentativas} falhou: {e}",
            )
            time.sleep(3)
    return None


def _wa_estado(driver, tempo=25):
    """Retorna 'logado', 'qr' ou None conforme a tela do WhatsApp Web."""
    fim = time.time() + tempo
    while time.time() < fim:
        try:
            if driver.find_elements(
                By.CSS_SELECTOR,
                'div[data-testid="chat-list"], '
                'div[data-testid="conversation-panel-header"]',
            ):
                return "logado"
        except Exception:
            pass
        try:
            if driver.find_elements(
                By.CSS_SELECTOR,
                'canvas[aria-label*="Scan this QR"], '
                'canvas[aria-label*="Digitalize"]',
            ):
                return "qr"
        except Exception:
            pass
        time.sleep(2)
    return None


def _aguardar_login(driver, tempo=300):
    """Aguarda o usuário escanear o QR e o WhatsApp Web carregar."""
    fim = time.time() + tempo
    while time.time() < fim:
        try:
            if driver.find_elements(
                By.CSS_SELECTOR,
                'div[data-testid="chat-list"], '
                'div[data-testid="conversation-panel-header"]',
            ):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _esperar_elemento(driver, seletor, tempo):
    """Espera um elemento visível aparecer e o retorna (ou None)."""
    fim = time.time() + tempo
    while time.time() < fim:
        try:
            el = driver.find_element(By.CSS_SELECTOR, seletor)
            if el.is_displayed():
                return el
        except Exception:
            pass
        time.sleep(0.5)
    return None


def _abrir_grupo_clicando(driver):
    """Clica em 'Abrir grupo'/'Entrar'/'Open group' na tela do convite."""
    PALAVRAS = ("abrir", "open", "entrar", "join", "participar")
    try:
        for b in driver.find_elements(
            By.CSS_SELECTOR, 'div[role="button"], button'
        ):
            if not b.is_displayed():
                continue
            t = (
                (b.text or "")
                + " "
                + (b.get_attribute("aria-label") or "")
            ).lower()
            if any(p in t for p in PALAVRAS):
                try:
                    b.click()
                    return True
                except Exception:
                    driver.execute_script("arguments[0].click();", b)
                    return True
    except Exception:
        pass
    try:
        return bool(
            driver.execute_script(
                """
                var PALAVRAS = ['abrir', 'open', 'entrar', 'join', 'participar'];
                var els = document.querySelectorAll('div[role="button"], button');
                for (var b of els) {
                    var t = ((b.innerText || '') + ' ' +
                             (b.getAttribute('aria-label') || '')).toLowerCase();
                    for (var p of PALAVRAS) {
                        if (t.indexOf(p) !== -1) { b.click(); return true; }
                    }
                }
                return false;
                """
            )
        )
    except Exception:
        return False


def _buscar_por_nome(driver, nome):
    """Digita o nome do grupo na busca do WhatsApp Web e abre a conversa."""
    try:
        caixa_busca = driver.find_element(
            By.CSS_SELECTOR, 'div[data-testid="chat-list-search"]'
        )
        caixa_busca.click()
    except Exception:
        try:
            driver.find_element(
                By.CSS_SELECTOR, 'button[aria-label*="Pesquisar"]'
            ).click()
        except Exception:
            return False
    try:
        inp = driver.find_element(
            By.CSS_SELECTOR, 'input[data-testid="search-input"]'
        )
    except Exception:
        return False
    inp.send_keys(nome)
    if not _esperar_elemento(
        driver,
        'div[data-testid="conversation-list-item"], div[role="row"]',
        8,
    ):
        return False
    try:
        abriu = driver.execute_script(
            """
            var nome = arguments[0].toLowerCase();
            var els = document.querySelectorAll(
                'div[data-testid="conversation-list-item"], div[role="row"]'
            );
            for (var el of els) {
                var txt = (el.innerText || '').toLowerCase();
                if (txt.indexOf(nome) !== -1) {
                    el.click();
                    return true;
                }
            }
            return false;
            """,
            nome,
        )
        if not abriu:
            inp.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def _ir_para_grupo(driver, grupo_id, nome):
    """Abre o chat do grupo e retorna a caixa de mensagem (ou None)."""
    try:
        driver.get(f"https://web.whatsapp.com/accept?code={grupo_id}")
    except Exception:
        return None
    caixa = _esperar_elemento(driver, MSG_INPUT_SELECTOR, 15)
    if caixa is not None:
        return caixa
    if _abrir_grupo_clicando(driver):
        caixa = _esperar_elemento(driver, MSG_INPUT_SELECTOR, 15)
        if caixa is not None:
            return caixa
    nome = (nome or "").strip()
    if not nome:
        return None
    try:
        driver.get("https://web.whatsapp.com/")
        time.sleep(3)
    except Exception:
        return None
    if _buscar_por_nome(driver, nome):
        return _esperar_elemento(driver, MSG_INPUT_SELECTOR, 20)
    return None


def _enviar_msg_grupo(driver, grupo_id, nome, mensagem):
    """Abre o grupo e envia a mensagem. Retorna True/False."""
    caixa = _ir_para_grupo(driver, grupo_id, nome)
    if caixa is None:
        return False
    try:
        caixa.click()
    except Exception:
        pass
    time.sleep(1)
    caixa.send_keys(mensagem)
    caixa.send_keys(Keys.ENTER)
    time.sleep(2)
    return True


def conectar_whatsapp_web():
    """Abre o perfil de automação para escanear o QR (setup único)."""
    st.info(
        "📲 Abrindo o WhatsApp Web para conectar. "
        "Escaneie o QR com o celular."
    )

    def _t():
        drv = None
        try:
            drv = _abrir_whatsapp()
            if drv is None:
                registrar_erro(
                    "WHATSAPP",
                    "Conectar WhatsApp Web",
                    "Não foi possível abrir o WhatsApp Web no perfil de "
                    "automação após 3 tentativas.",
                )
                st.session_state["wa_feedback"] = (
                    "erro",
                    "Não foi possível abrir o WhatsApp Web no perfil de "
                    "automação. Veja o log na aba 🐞 Registro de Erros.",
                )
                st.session_state["wa_status"] = "erro"
                return
            st.session_state["wa_feedback"] = (
                "info",
                "🕒 Escaneie o **QR code** com o celular. A janela fica por "
                "até 5 minutos aguardando a conexão.",
            )
            if not _aguardar_login(drv, 300):
                registrar_erro(
                    "WHATSAPP",
                    "Conectar WhatsApp Web",
                    "Timeout: QR não escaneado em 5 minutos.",
                )
                st.session_state["wa_feedback"] = (
                    "erro",
                    "Timeout na conexão. Escaneie o QR em até 5 minutos.",
                )
                st.session_state["wa_status"] = "nao_conectado"
            else:
                registrar_erro(
                    "WHATSAPP",
                    "Conectar WhatsApp Web",
                    "Perfil conectado com sucesso.",
                )
                st.session_state["wa_feedback"] = (
                    "ok",
                    "📲 WhatsApp Web conectado no perfil de automação!",
                )
                st.session_state["wa_status"] = "conectado"
        except Exception as e:
            registrar_erro("WHATSAPP", "Conectar WhatsApp Web", str(e))
            st.session_state["wa_feedback"] = ("erro", f"Erro ao conectar: {e}")
            st.session_state["wa_status"] = "erro"
        finally:
            try:
                if drv is not None:
                    drv.quit()
            except Exception:
                pass

    threading.Thread(target=_t, daemon=True).start()


def _checar_estado_perfil():
    """Thread leve: verifica se o perfil de automação está logado."""

    def _t():
        drv = None
        try:
            drv = _abrir_whatsapp()
            if drv is None:
                st.session_state["wa_status"] = "erro"
                return
            estado = _wa_estado(drv, 20)
            st.session_state["wa_status"] = (
                "conectado"
                if estado == "logado"
                else "nao_conectado"
                if estado == "qr"
                else "erro"
            )
        except Exception as e:
            registrar_erro("WHATSAPP", "Verificar perfil", str(e))
            st.session_state["wa_status"] = "erro"
        finally:
            try:
                if drv is not None:
                    drv.quit()
            except Exception:
                pass

    threading.Thread(target=_t, daemon=True).start()


def enviar_whatsapp_grupo(area, motivo):
    """Envia a mensagem padrão ao grupo via WhatsApp Web (Selenium)."""
    dh = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    grupo_id = _normalizar_grupo_id(
        st.session_state.get("cfg_wagrupo_id", "")
    )
    if not grupo_id:
        st.warning(
            "⚠️ Alerta do grupo WhatsApp Web ativado, mas o **ID do grupo** "
            "não foi preenchido. Informe o código do link de convite "
            "(chat.whatsapp.com/<ID>) em ⚙️ Configurar Notificações."
        )
        return

    st.info(
        "🕒 **Abrindo o WhatsApp Web e enviando ao grupo...** "
        "(Rode novamente a tela em alguns instantes para ver o resultado.)"
    )
    registrar_erro(
        "WHATSAPP",
        "Alerta grupo WhatsApp",
        f"Início do envio para o grupo (ID: {grupo_id}). "
        "Aguardando o navegador abrir o WhatsApp Web...",
    )

    def _envio():
        drv = None
        try:
            drv = _abrir_whatsapp()
            if drv is None:
                registrar_erro(
                    "WHATSAPP",
                    "Alerta grupo WhatsApp",
                    "Não foi possível abrir o WhatsApp Web no perfil de "
                    "automação após 3 tentativas.",
                )
                st.session_state["wa_feedback"] = (
                    "erro",
                    "Não foi possível abrir o WhatsApp Web no perfil de "
                    "automação. Veja o log na aba 🐞 Registro de Erros.",
                )
                st.session_state["wa_status"] = "erro"
                return
            estado = _wa_estado(drv, 40)
            if estado == "qr":
                registrar_erro(
                    "WHATSAPP",
                    "Alerta grupo WhatsApp",
                    "WhatsApp Web não conectado. Mantendo a janela aberta para "
                    "escanear o QR; envio continua após a conexão.",
                )
                st.session_state["wa_feedback"] = (
                    "info",
                    "🕒 O WhatsApp Web ainda não está conectado. **Escaneie o "
                    "QR code** com o celular — a janela fica aberta por até 5 "
                    "min e, ao conectar, o alerta é enviado.",
                )
                st.session_state["wa_status"] = "nao_conectado"
                if not _aguardar_login(drv, 300):
                    registrar_erro(
                        "WHATSAPP",
                        "Alerta grupo WhatsApp",
                        "Timeout: QR não escaneado em 5 minutos.",
                    )
                    st.session_state["wa_feedback"] = (
                        "erro",
                        "Timeout: o QR não foi escaneado em 5 minutos. "
                        "Clique em testar novamente.",
                    )
                    return
                registrar_erro(
                    "WHATSAPP",
                    "Alerta grupo WhatsApp",
                    "Perfil conectado. Prosseguindo com o envio.",
                )
                st.session_state["wa_status"] = "conectado"
            elif estado != "logado":
                registrar_erro(
                    "WHATSAPP",
                    "Alerta grupo WhatsApp",
                    "Não foi possível acessar o WhatsApp Web no perfil "
                    "de automação.",
                )
                st.session_state["wa_feedback"] = (
                    "erro",
                    "Não foi possível acessar o WhatsApp Web no perfil "
                    "de automação.",
                )
                st.session_state["wa_status"] = "erro"
                return

            nome_grupo = st.session_state.get("cfg_wagrupo_nome", "").strip()
            sucesso = _enviar_msg_grupo(
                drv,
                grupo_id,
                nome_grupo,
                _msg_padrao_whatsapp(area, motivo, dh),
            )
            if sucesso:
                registrar_erro(
                    "WHATSAPP",
                    "Alerta grupo WhatsApp",
                    "Mensagem enviada ao grupo.",
                )
                st.session_state["wa_feedback"] = (
                    "ok",
                    "Alerta enviado ao grupo WhatsApp!",
                )
            else:
                registrar_erro(
                    "WHATSAPP",
                    "Alerta grupo WhatsApp",
                    "Não foi possível abrir o grupo com o link de convite "
                    "informado.",
                )
                st.session_state["wa_feedback"] = (
                    "erro",
                    "Não foi possível abrir o grupo. Confira se o link de "
                    "convite está ativo e se o **Nome do grupo** está correto "
                    "em ⚙️ Configurar Notificações.",
                )
        except Exception as e:
            registrar_erro("WHATSAPP", "Alerta grupo WhatsApp", str(e))
            st.session_state["wa_feedback"] = ("erro", f"Erro ao enviar: {e}")
            st.session_state["wa_status"] = "erro"
        finally:
            try:
                if drv is not None:
                    drv.quit()
            except Exception:
                pass

    threading.Thread(target=_envio, daemon=True).start()


def enviar_alerta_seguranca(area, motivo):
    """Envia alertas por E-mail e WhatsApp/SMS se os dados estiverem preenchidos."""
    dh = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    # Recupera credenciais da Session State
    email_ativo = st.session_state.get("cfg_email_ativo", False)
    email_remetente = st.session_state.get("cfg_email_remetente", "").strip()
    email_senha = st.session_state.get("cfg_email_senha", "").strip()
    email_destinatario = st.session_state.get(
        "cfg_email_destinatario", ""
    ).strip()

    twilio_ativo = st.session_state.get("cfg_twilio_ativo", False)
    twilio_sid = st.session_state.get("cfg_twilio_sid", "").strip()
    twilio_token = st.session_state.get("cfg_twilio_token", "").strip()
    twilio_de = st.session_state.get("cfg_twilio_de", "").strip()
    twilio_para = st.session_state.get("cfg_twilio_para", "").strip()

    provedor = st.session_state.get("cfg_email_provedor", "Gmail")
    smtp_host = st.session_state.get("cfg_email_smtp_host", "").strip()
    smtp_port = st.session_state.get("cfg_email_smtp_port", "").strip()
    smtp_login = st.session_state.get("cfg_email_smtp_login", "").strip()
    host, port_padrao = PRESETS_SMTP.get(provedor, PRESETS_SMTP["Gmail"])
    if not smtp_host:
        smtp_host = host
    if not smtp_port:
        smtp_port = port_padrao
    if not smtp_login:
        smtp_login = email_remetente

    # 1. Disparo por E-mail (SMTP Gmail/Outlook/Brevo)
    if (
        email_ativo
        and email_remetente
        and email_senha
        and email_destinatario
    ):
        try:
            corpo_email = f"ALERTA DE SEGURANÇA - FALHA DE ACESSO AO COFRE\n\nCompartimento do Cofre: {area}\nData/Hora: {dh}\nDetalhes: {motivo}"
            msg = MIMEText(corpo_email)
            msg["Subject"] = f"🚨 ALERTA: Falha de Acesso ao compartimento do cofre {area}"
            msg["From"] = email_remetente
            msg["To"] = email_destinatario

            server = smtplib.SMTP(smtp_host, int(smtp_port))
            server.starttls()
            server.login(smtp_login, email_senha)
            server.sendmail(
                email_remetente, [email_destinatario], msg.as_string()
            )
            server.quit()
            st.toast("📩 Alerta enviado por E-mail!", icon="📧")
        except Exception as e:
            registrar_erro("EMAIL", "Alerta E-mail", str(e))
            msg_erro = str(e).lower()
            if "535" in msg_erro or "badcredentials" in msg_erro:
                if provedor == "Brevo":
                    dica = (
                        "\n\n💡 **Credenciais inválidas**: no **Brevo**, confira se "
                        "copiou a **SMTP key** no campo *Senha de App*, se o **SMTP "
                        "Login** está preenchido e se o **Remetente** foi confirmado "
                        "(e-mail de verificação enviado pelo Brevo)."
                    )
                elif provedor == "Outlook":
                    dica = (
                        "\n\n💡 **Credenciais inválidas**: no **Outlook**, use a senha "
                        "da conta ou uma senha de aplicativo e confira o **Remetente** "
                        "e o **SMTP Login**."
                    )
                else:
                    dica = (
                        "\n\n💡 **Credenciais inválidas**: confira se a **Senha de App "
                        "do Gmail** (16 caracteres) foi gerada em Conta Google → "
                        "Segurança → Verificação em 2 etapas → **Senhas de App** e "
                        "colada corretamente, e se o **Remetente** é a conta que criou "
                        "essa senha."
                    )
            elif (
                "connection" in msg_erro
                or "timed out" in msg_erro
                or "refused" in msg_erro
                or "socket" in msg_erro
            ):
                dica = (
                    f"\n\n💡 **Falha de conexão** com o servidor SMTP "
                    f"({smtp_host}:{smtp_port}). Verifique sua conexão com a internet "
                    "e as configurações de Host/Porta."
                )
            else:
                dica = ""
            st.warning(
                f"Erro ao enviar e-mail de alerta: {e}{dica}\n\n"
                "Registrado na aba 🐞 Registro de Erros para ajuda."
            )
    elif email_ativo:
        faltam = []
        if not email_remetente:
            faltam.append("Seu E-mail (Remetente)")
        if not email_senha:
            faltam.append("Senha de App")
        if not email_destinatario:
            faltam.append("E-mail do Responsável")
        st.warning(
            "⚠️ Alerta E-mail ativado, mas a configuração está incompleta. "
            f"Faltam: {', '.join(faltam)}. Preencha em ⚙️ Configurar Notificações."
        )

    # 2. Disparo por WhatsApp/SMS (Twilio API)
    if twilio_ativo and twilio_sid and twilio_token and twilio_de and twilio_para:
        try:
            msg_txt = f"🚨 *ALERTA DE SEGURANÇA*\n\nTentativa de acesso negada!\n- *Compartimento do Cofre:* {area}\n- *Data/Hora:* {dh}\n- *Motivo:* {motivo}"
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
            data = {"From": twilio_de, "To": twilio_para, "Body": msg_txt}
            resp = requests.post(
                url, data=data, auth=(twilio_sid, twilio_token)
            )
            if resp.status_code in [200, 201]:
                st.toast("📱 Alerta enviado por WhatsApp/SMS!", icon="📲")
            else:
                registrar_erro(
                    "TWILIO",
                    "Alerta WhatsApp/SMS",
                    f"HTTP {resp.status_code}: {resp.text}",
                )
                st.warning("Erro na resposta da Twilio (registrado nos logs).")
        except Exception as e:
            registrar_erro("TWILIO", "Alerta WhatsApp/SMS", str(e))
            st.warning(
                f"Erro ao enviar mensagem Twilio: {e}\n\n"
                "Registrado na aba 🐞 Registro de Erros para ajuda."
            )
    elif twilio_ativo:
        faltam_t = []
        if not twilio_sid:
            faltam_t.append("Account SID")
        if not twilio_token:
            faltam_t.append("Auth Token")
        if not twilio_de:
            faltam_t.append("Número Twilio (De)")
        if not twilio_para:
            faltam_t.append("Seu WhatsApp (Para)")
        st.warning(
            "⚠️ Alerta Twilio ativado, mas a configuração está incompleta. "
            f"Faltam: {', '.join(faltam_t)}. Preencha em ⚙️ Configurar Notificações."
        )

    # 3. Disparo por WhatsApp Web (Selenium) — grupo pessoal logado no PC
    if st.session_state.get("cfg_wagrupo_ativo", False):
        enviar_whatsapp_grupo(area, motivo)


def _canais_ativos():
    """Lista os canais de notificação ativados na configuração."""
    canais = []
    if st.session_state.get("cfg_email_ativo", False):
        canais.append("E-mail")
    if st.session_state.get("cfg_twilio_ativo", False):
        canais.append("WhatsApp/SMS (Twilio)")
    if st.session_state.get("cfg_wagrupo_ativo", False):
        canais.append("Grupo WhatsApp (Web)")
    return canais


def salvar_colaborador():
    nome = st.session_state.get("reg_nome", "").strip()
    cargo = st.session_state.get("reg_cargo", "").strip()
    divisao = st.session_state.get("reg_divisao", "Sem divisão")
    nivel = st.session_state.get("reg_nivel", 1)
    usuario = st.session_state.get("reg_usuario", "").strip()
    senha = st.session_state.get("reg_senha", "")
    foto_bytes = st.session_state.get("foto_capturada_bytes", None)

    if not nome or foto_bytes is None:
        st.session_state["msg_status"] = (
            "error",
            "⚠️ Preencha o Nome e tire/envie a Foto antes de cadastrar.",
        )
        return
    if not usuario:
        st.session_state["msg_status"] = (
            "error",
            "⚠️ Defina o Usuário (login) do colaborador.",
        )
        return
    if len(senha) < 6:
        st.session_state["msg_status"] = (
            "error",
            "⚠️ A senha deve ter ao menos 6 caracteres.",
        )
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM colaboradores WHERE usuario = ? COLLATE NOCASE",
            (usuario,),
        )
        if cursor.fetchone()[0] > 0:
            conn.close()
            st.session_state["msg_status"] = (
                "error",
                "⚠️ Este usuário já está em uso por outro colaborador.",
            )
            return

        filename = (
            f"{nome.replace(' ', '_').lower()}_{int(datetime.now().timestamp())}.jpg"
        )
        foto_path = os.path.join(FOTOS_DIR, filename)

        with open(foto_path, "wb") as f:
            f.write(foto_bytes)

        recortar_centro_rosto(foto_path)

        senha_hash = hash_senha(senha)
        data_hoje = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO colaboradores "
            "(nome, cargo, divisao, nivel_acesso, usuario, senha_hash, pode_cadastrar, "
            "foto_path, data_cadastro) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (nome, cargo, divisao, nivel, usuario, senha_hash, foto_path, data_hoje),
        )

        conn.commit()
        conn.close()

        st.session_state["reg_nome"] = ""
        st.session_state["reg_cargo"] = ""
        st.session_state["reg_divisao"] = "Sem divisão"
        st.session_state["reg_nivel"] = 1
        st.session_state["reg_usuario"] = ""
        st.session_state["reg_senha"] = ""
        st.session_state.pop("foto_capturada_bytes", None)

        st.session_state["msg_status"] = (
            "success",
            f"✅ Colaborador **{nome}** cadastrado com sucesso! "
            f"Nível de acesso: **{rotulo_nivel(nivel)}**. Credenciais criadas "
            f"para o usuário **{usuario}**.",
        )
    except Exception as e:
        registrar_erro("BANCO", "Cadastro de Colaborador", str(e))
        st.session_state["msg_status"] = (
            "error",
            f"❌ Erro ao cadastrar colaborador. Veja a aba 🐞 Registro de Erros para ajuda. ({e})",
        )


@st.cache_resource(show_spinner=False)
def carregar_modelo_facial():
    """Carrega o modelo VGG-Face uma única vez (evita recarregar a cada validação)."""
    try:
        return DeepFace.build_model("VGG-Face")
    except Exception as e:
        registrar_erro("BIOMETRIA", "Carregamento do Modelo Facial", str(e))
        return None


# ---------------------------------------------------------------------------
# AUTENTICAÇÃO POR CREDENCIAIS (usuário/senha)
# ---------------------------------------------------------------------------
def _autenticar(dados):
    """Valida as credenciais no banco e inicia a sessão. Retorna (ok, msg)."""
    usuario = dados.get("login").strip()
    senha = dados.get("senha")
    if not usuario or not senha:
        return False, "Informe usuário e senha."
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, cargo, divisao, nivel_acesso, usuario, pode_cadastrar, senha_hash "
            "FROM colaboradores "
            "WHERE usuario = ? COLLATE NOCASE",
            (usuario,),
        )
        linha = cur.fetchone()
        conn.close()
    except Exception as e:
        registrar_erro("AUTENTICACAO", "Login", str(e))
        return False, "Erro interno ao validar o login."
    if linha is None or not verificar_senha(senha, linha[7]):
        registrar_log(
            "Desconhecido",
            "Sistema – Login",
            "NEGADO",
            {"motivo": "Credenciais inválidas", "usuario_tentado": usuario},
        )
        return False, "Usuário ou senha inválidos."
    _id, _nome, _cargo, _divisao, _nivel, _usuario, _pode_cad, _ = linha
    st.session_state.pop("sessao_expirada", None)
    st.session_state["usuario_logado"] = {
        "id": _id,
        "nome": _nome,
        "cargo": _cargo,
        "divisao": _divisao,
        "nivel_acesso": int(_nivel),
        "usuario": _usuario,
        "pode_cadastrar": int(_pode_cad or 0),
        "login_ts": time.time(),
        "metodo": "credenciais",
    }
    st.session_state["autenticado"] = True
    registrar_log(
        f"{_nome} (login)",
        rotulo_nivel(_nivel),
        "PERMITIDO",
        {"motivo": "Login por credenciais"},
    )
    return True, f"Bem-vindo(a), {_nome}!"


def _encontrar_imagem_home():
    """Retorna o caminho da primeira imagem encontrada em IMAGEMHOME/ (ou None)."""
    if not os.path.isdir(IMAGEMHOME_DIR):
        return None
    for f in os.listdir(IMAGEMHOME_DIR):
        if f.lower().endswith(EXTENSOES_IMAGEM):
            return os.path.join(IMAGEMHOME_DIR, f)
    return None


@st.cache_data
def _imagem_home_base64(_caminho):
    """Codifica a imagem da home em base64 (cacheado)."""
    with open(_caminho, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _zonas_home_default():
    """Zonas clicáveis padrão (percentuais sobre a imagem da home)."""
    return [
        {"chave": "campo", "rotulo": "Usuário e Senha", "acao": "login",
         "x": 62.0, "y": 40.0, "w": 22.0, "h": 17.0},
        {"chave": "acesso", "rotulo": "Acesso", "acao": "acesso",
         "x": 61.0, "y": 57.0, "w": 23.0, "h": 10.0},
        {"chave": "cadastro", "rotulo": "Cadastro", "acao": "cadastro",
         "x": 68.0, "y": 67.0, "w": 13.0, "h": 10.0},
        {"chave": "admin", "rotulo": "Criar Administrador", "acao": "admin",
         "x": 68.0, "y": 77.0, "w": 13.0, "h": 10.0},
    ]


def _carregar_zonas_home():
    """Zonas salvas no banco (com fallback nos padrões)."""
    zonas = _zonas_home_default()
    linhas = []
    try:
        conexao = sqlite3.connect(DB_FILE)
        linhas = conexao.execute(
            "SELECT chave, valor FROM configuracoes"
        ).fetchall()
        conexao.close()
    except Exception:
        pass
    por_chave = {z["chave"]: z for z in zonas}
    for chave, valor in linhas:
        if not valor or not chave.startswith("home_zona_"):
            continue
        k = chave[len("home_zona_"):]
        if k not in por_chave:
            continue
        partes = valor.split(";")
        if len(partes) != 4:
            continue
        try:
            x, y, w, h = (float(p.strip()) for p in partes)
        except ValueError:
            continue
        z = por_chave[k]
        z["x"], z["y"], z["w"], z["h"] = x, y, w, h
    return zonas


def _salvar_zonas_home(zonas):
    """Persiste as zonas ajustadas na tabela configuracoes."""
    conexao = None
    try:
        conexao = sqlite3.connect(DB_FILE)
        for z in zonas:
            conexao.execute(
                "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (
                    f"home_zona_{z['chave']}",
                    f"{z['x']};{z['y']};{z['w']};{z['h']}",
                ),
            )
        conexao.commit()
    finally:
        if conexao:
            conexao.close()


def _montar_html_mascaras(b64, zonas, ajuste=False, valores=None):
    """Monta a imagem da home com as máscaras (links transparentes) sobre ela."""
    partes = [
        "<style>"
        ".home-zona{position:absolute;cursor:pointer;z-index:5;border-radius:10px;}"
        ".home-zona:hover{box-shadow:0 0 0 3px rgba(255,255,255,.5),"
        "0 0 0 7px rgba(0,255,102,.4);}"
        ".home-ajuste{position:absolute;z-index:6;border:2px dashed #00FF66;"
        "background:rgba(0,255,102,.10);border-radius:10px;}"
        ".home-ajuste span{position:absolute;top:-1.3em;left:0;font-size:.72rem;"
        "color:#00FF66;background:rgba(0,0,0,.65);padding:1px 8px;border-radius:6px;"
        "white-space:nowrap;}"
        "</style>",
        "<div style='position:relative;width:100%;max-width:1250px;margin:0 auto;'>",
    ]
    if b64:
        partes.append(
            "<img src='data:image/png;base64,%s' style='width:100%%;border-radius:14px;"
            "display:block;box-shadow:0 8px 30px rgba(0,0,0,.35);'>" % b64
        )
    for z in zonas:
        if valores and z["chave"] in valores:
            x, y, w, h = valores[z["chave"]]
        else:
            x, y, w, h = z["x"], z["y"], z["w"], z["h"]
        estilo = (
            "position:absolute;left:%.1f%%;top:%.1f%%;width:%.1f%%;height:%.1f%%"
            % (x, y, w, h)
        )
        if ajuste:
            partes.append(
                "<div class='home-ajuste' style='%s'>"
                "<span>%s</span></div>" % (estilo, z["rotulo"])
            )
        else:
            partes.append(
                "<a href='?acao=%s' class='home-zona' style='%s' "
                "aria-label='%s' title='%s'></a>"
                % (z["acao"], estilo, z["rotulo"], z["rotulo"])
            )
    partes.append("</div>")
    return "".join(partes)


def _tratar_acao_home():
    """Processa cliques das máscaras e do modo de ajuste (via query param)."""
    _acao = st.query_params.get("acao") or st.session_state.pop("acao_home", None)
    _ajustar = st.query_params.get("ajustar")
    _sair = st.query_params.get("ajuste_sair")
    if _acao:
        if _acao == "acesso":
            st.session_state["home_tela"] = "acesso"
        elif _acao in ("cadastro", "login"):
            st.session_state["home_tela"] = "cadastro"
        elif _acao == "admin":
            st.session_state["home_tela"] = "criar_admin"
        st.session_state.pop("modo_ajuste", None)
        st.query_params.clear()
        st.rerun()
        return
    if _ajustar:
        st.session_state["modo_ajuste"] = True
        st.query_params.clear()
        st.rerun()
        return
    if _sair:
        st.session_state["modo_ajuste"] = False
        st.query_params.clear()
        st.rerun()


def _render_home_fallback():
    """Home sem imagem: botões textuais (fallback seguro)."""
    st.markdown(
        "<h1 style='text-align:center'>🔐 Cofre de Toxinas</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:#888'>Ministério do Meio Ambiente — "
        "controle de acesso ao cofre de segurança máxima.</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    _sem_creds = not existe_usuario_com_credenciais()
    _cols = st.columns(3) if _sem_creds else st.columns(2)

    with _cols[0]:
        with st.container(border=True):
            st.markdown("### 📸 Cadastro")
            st.caption(
                "Registre colaboradores, fotos e permissões. **Somente** "
                "colaboradores autorizados (❌ permissão de cadastro)."
            )
            if st.button("Cadastrar", width="stretch", type="primary", key="home_cadastro"):
                st.session_state["home_tela"] = "cadastro"
                st.rerun()

    with _cols[1]:
        with st.container(border=True):
            st.markdown("### 🔐 Acesso")
            st.caption(
                "Valide o acesso ao cofre por reconhecimento facial. "
                "Colaboradores com cadastro entram conforme o nível."
            )
            if st.button("Acessar", width="stretch", type="primary", key="home_acesso"):
                st.session_state["home_tela"] = "acesso"
                st.rerun()

    if _sem_creds:
        with _cols[2]:
            with st.container(border=True):
                st.markdown("### 🛡️ Primeiro Acesso")
                st.caption(
                    "Nenhuma credencial cadastrada: crie a conta do "
                    "administrador do sistema (nível 3)."
                )
                if st.button(
                    "Criar Administrador", width="stretch", type="secondary", key="home_admin"
                ):
                    st.session_state["home_tela"] = "criar_admin"
                    st.rerun()


def _render_ajuste_mascaras():
    """Modo de ajuste visual das máscaras sobre a imagem da home."""
    st.title("⚙️ Ajuste da Home (áreas clicáveis)")
    st.caption(
        "Use os controles abaixo para mover/redimensionar cada máscara até ela "
        "cobrir o elemento correspondente na imagem. Depois clique em "
        "**💾 Salvar posições**."
    )
    _img = _encontrar_imagem_home()
    _b64 = _imagem_home_base64(_img) if _img else None

    _sem_creds = not existe_usuario_com_credenciais()
    zonas = [
        z for z in _carregar_zonas_home()
        if z["chave"] != "admin" or _sem_creds
    ]

    for z in zonas:
        _base = f"mask_{z['chave']}"
        st.session_state.setdefault(f"{_base}_x", z["x"])
        st.session_state.setdefault(f"{_base}_y", z["y"])
        st.session_state.setdefault(f"{_base}_w", z["w"])
        st.session_state.setdefault(f"{_base}_h", z["h"])

    valores = {}
    for z in zonas:
        _base = f"mask_{z['chave']}"
        valores[z["chave"]] = (
            st.session_state[f"{_base}_x"],
            st.session_state[f"{_base}_y"],
            st.session_state[f"{_base}_w"],
            st.session_state[f"{_base}_h"],
        )

    if _b64:
        st.markdown(
            _montar_html_mascaras(_b64, zonas, ajuste=True, valores=valores),
            unsafe_allow_html=True,
        )
    else:
        st.warning(
            "⚠️ Nenhuma imagem encontrada em `IMAGEMHOME/`. As áreas de ajuste "
            "não têm referência visual."
        )

    st.divider()
    defaults = {z["chave"]: z for z in _zonas_home_default()}
    for u in zonas:
        _base = f"mask_{u['chave']}"
        with st.container(border=True):
            st.markdown(f"**{u['rotulo']}**")
            c1, c2, c3, c4 = st.columns(4)
            c1.slider("X (%)", 0.0, 100.0, key=f"{_base}_x", step=0.5)
            c2.slider("Y (%)", 0.0, 100.0, key=f"{_base}_y", step=0.5)
            c3.slider("Largura (%)", 0.0, 100.0, key=f"{_base}_w", step=0.5)
            c4.slider("Altura (%)", 0.0, 100.0, key=f"{_base}_h", step=0.5)
            if st.button("↺ Restaurar padrão desta zona", key=f"{_base}_reset"):
                st.session_state[f"{_base}_x"] = defaults[u["chave"]]["x"]
                st.session_state[f"{_base}_y"] = defaults[u["chave"]]["y"]
                st.session_state[f"{_base}_w"] = defaults[u["chave"]]["w"]
                st.session_state[f"{_base}_h"] = defaults[u["chave"]]["h"]
                st.rerun()

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 Salvar posições", type="primary", width="stretch"):
            _novas = []
            for u in zonas:
                _base = f"mask_{u['chave']}"
                _novas.append({
                    "chave": u["chave"], "rotulo": u["rotulo"], "acao": u["acao"],
                    "x": float(st.session_state[f"{_base}_x"]),
                    "y": float(st.session_state[f"{_base}_y"]),
                    "w": float(st.session_state[f"{_base}_w"]),
                    "h": float(st.session_state[f"{_base}_h"]),
                })
            _salvar_zonas_home(_novas)
            st.success("✅ Posições salvas!")
    with c2:
        if st.button("↩ Restaurar padrão e salvar", width="stretch"):
            _novas = []
            for u in zonas:
                p = defaults[u["chave"]]
                _novas.append({
                    "chave": u["chave"], "rotulo": u["rotulo"], "acao": u["acao"],
                    "x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"],
                })
            _salvar_zonas_home(_novas)
            st.success("✅ Padrão restaurado e salvo!")
    with c3:
        if st.button("✅ Concluir", width="stretch"):
            st.session_state["modo_ajuste"] = False
            st.rerun()


def _render_home():
    """Tela inicial (pré-login) com máscaras clicáveis sobre a imagem."""
    st.markdown(HOME_CSS, unsafe_allow_html=True)
    _tratar_acao_home()
    if st.session_state.get("modo_ajuste"):
        _render_ajuste_mascaras()
        return
    _img = _encontrar_imagem_home()
    if not _img:
        _render_home_fallback()
        return
    _b64 = _imagem_home_base64(_img)
    _sem_creds = not existe_usuario_com_credenciais()
    zonas = [
        z for z in _carregar_zonas_home()
        if z["chave"] != "admin" or _sem_creds
    ]
    st.markdown(_montar_html_mascaras(_b64, zonas), unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center;font-size:.85rem;color:#888'>"
        "Clique sobre os elementos da tela para acessar o sistema.</p>",
        unsafe_allow_html=True,
    )
    st.caption(
        "[⚙️ Ajustar áreas clicáveis](?ajustar=1) — "
        "para administradores; requer cuidado."
    )


def _render_login(destino=None):
    """Tela de login por usuário/senha."""
    if st.button("← Voltar ao Início", key="voltar_login"):
        st.session_state["home_tela"] = "home"
        st.rerun()
    st.markdown(
        "<h1 style='text-align:center'>🔐 Cofre de Toxinas — Ministério do Meio Ambiente</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:#888'>Acesso restrito — identifique-se "
        "para continuar.</p>",
        unsafe_allow_html=True,
    )
    st.divider()
    with st.form("login_credenciais", clear_on_submit=False):
        usuario = st.text_input("Usuário:", key="login_usuario")
        senha = st.text_input("Senha:", type="password", key="login_senha")
        enviar = st.form_submit_button("🔓 Entrar no Sistema", type="primary")
    if enviar:
        ok, msg = _autenticar({"login": usuario, "senha": senha})
        if ok:
            _aut = st.session_state.get("usuario_logado", {})
            if destino == "cadastro" and not _aut.get("pode_cadastrar"):
                st.session_state["home_aviso"] = (
                    "⚠️ Você não possui **permissão de cadastro**. Ela é "
                    "concedida pelo nível 3 na aba 🛡️ Gestão de Acessos."
                )
                st.session_state["redirecionar_para"] = "🔐 Cofre de Toxinas do MMA"
            elif destino == "cadastro":
                st.session_state["redirecionar_para"] = "📸 Cadastro de Colaboradores"
            else:
                st.session_state["redirecionar_para"] = "🔐 Cofre de Toxinas do MMA"
            st.rerun()
        else:
            st.error(f"🚫 **Acesso negado.** {msg}")


def _render_criar_admin():
    """Primeira execução: cria o usuário administrador inicial (nível 3)."""
    if st.button("← Voltar ao Início", key="voltar_admin"):
        st.session_state["home_tela"] = "home"
        st.rerun()
    st.markdown(
        "<h1 style='text-align:center'>🛡️ Criar Primeiro Administrador</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:#888'>Nenhum usuário com credenciais "
        "foi encontrado. Crie a conta inicial do administrador do sistema "
        "(nível 3 — Ministro, com permissão de cadastro).</p>",
        unsafe_allow_html=True,
    )
    st.divider()
    with st.form("criar_admin_form", clear_on_submit=False):
        nome = st.text_input("Nome Completo do Administrador:*", key="adm_nome")
        cargo = st.text_input("Cargo / Função:", key="adm_cargo")
        usuario = st.text_input("Usuário (login):*", key="adm_usuario")
        senha = st.text_input("Senha:*", type="password", key="adm_senha")
        senha2 = st.text_input("Confirmar Senha:*", type="password", key="adm_senha2")
        criar = st.form_submit_button("✅ Criar Administrador", type="primary")

    if criar:
        nome = nome.strip()
        usuario = (usuario or "").strip()
        if not nome or not usuario:
            st.error("⚠️ Preencha Nome Completo e Usuário.")
            return
        if len(senha) < 6:
            st.error("⚠️ A senha deve ter ao menos 6 caracteres.")
            return
        if senha != senha2:
            st.error("⚠️ As senhas não conferem.")
            return
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM colaboradores WHERE usuario = ? COLLATE NOCASE",
                (usuario,),
            )
            if cur.fetchone()[0] > 0:
                conn.close()
                st.error("⚠️ Este usuário já está em uso.")
                return
            senha_hash = hash_senha(senha)
            data_hoje = datetime.now().strftime("%Y-%m-%d")
            cur.execute(
                "INSERT INTO colaboradores "
                "(nome, cargo, divisao, nivel_acesso, usuario, senha_hash, pode_cadastrar, "
                "foto_path, data_cadastro) "
                "VALUES (?, ?, 'Sem divisão', 3, ?, ?, 1, '', ?)",
                (nome, cargo, usuario, senha_hash, data_hoje),
            )
            novo_id = cur.lastrowid
            conn.commit()
            conn.close()
            st.session_state.pop("sessao_expirada", None)
            st.session_state["usuario_logado"] = {
                "id": novo_id,
                "nome": nome,
                "cargo": cargo,
                "divisao": "Sem divisão",
                "nivel_acesso": 3,
                "usuario": usuario,
                "pode_cadastrar": 1,
                "login_ts": time.time(),
                "metodo": "credenciais",
            }
            st.session_state["autenticado"] = True
            st.success(
                f"✅ Administrador **{nome}** criado e autenticado! "
                "Você já pode cadastrar os demais colaboradores."
            )
            st.rerun()
        except Exception as e:
            registrar_erro("AUTENTICACAO", "Criar Administrador", str(e))
            st.error(
                f"❌ Erro ao criar o administrador. Veja a aba 🐞 Registro de "
                f"Erros para ajuda. ({e})"
            )


def _encerrar_sessao():
    st.session_state.pop("usuario_logado", None)
    st.session_state.pop("autenticado", None)
    st.session_state.pop("sessao_expirada", None)
    st.session_state.pop("live_frames", None)
    st.session_state.pop("redirecionar_para", None)
    st.session_state.pop("home_aviso", None)
    st.session_state["home_tela"] = "home"


def _aba_simulacao():
    """Validação biométrica / login ao cofre (acessível com ou sem credenciais)."""
    st.markdown(MOLDURA_CIRCULAR_CSS, unsafe_allow_html=True)
    st.title("📹 Validação Biométrica / Login ao Cofre de Toxinas")

    if not _sessao_valida():
        st.info(
            "Registro facial reconhecido inicia sua sessão no sistema "
            "(colaboradores cadastrados antes do novo esquema de credenciais "
            "ainda podem acessar por aqui)."
        )

    nivel_requerido = st.selectbox(
        "Selecione o nível do compartimento do cofre sendo acessado:",
        options=list(NIVEIS_ACESSO.keys()),
        format_func=rotulo_nivel,
    )
    area_requerida = rotulo_nivel(nivel_requerido)
    st.markdown(
        f"**Status da Câmera:** Monitorando o acesso ao compartimento "
        f"**[{area_requerida}]** do cofre."
    )

    bloq, minutos = _bloqueio_ativo(area_requerida)
    if bloq:
        st.error(
            f"⛔ **BLOQUEIO TEMPORÁRIO ATIVADO**\n\nO compartimento "
            f"**{area_requerida}** está com a validação **suspensa por "
            f"~{minutos} min** após tentativas repetidas de fraude ou "
            f"acesso indevido. O responsável foi notificado."
        )
        tent_linhas = _tentativas_recentes(area_requerida)
        if tent_linhas:
            st.dataframe(pd.DataFrame(tent_linhas), width="stretch")
        return

    metodo_leitura = st.radio(
        "Origem da imagem:",
        [
            "Tirar Foto pela Webcam",
            "🎥 Mini Vídeo Anti-Fraude (mova o rosto)",
        ],
        key="metodo_leitura_radio",
    )

    if metodo_leitura == "🎥 Mini Vídeo Anti-Fraude (mova o rosto)":
        _render_mini_video(nivel_requerido, area_requerida)
        return

    input_test = st.camera_input(
        "Centralize o rosto no círculo para leitura"
    )

    if input_test is not None:
        test_bytes = input_test.getvalue()
        temp_test_path = "temp_test.jpg"
        with open(temp_test_path, "wb") as f:
            f.write(test_bytes)

        recortar_centro_rosto(temp_test_path)

        try:
            carregar_modelo_facial()
            with st.spinner("Validando biometria facial..."):
                melhor_candidato, menor_distancia = _melhor_match_biometrico(
                    temp_test_path
                )

            if os.path.exists(temp_test_path):
                os.remove(temp_test_path)

            if melhor_candidato is not None and menor_distancia <= 0.35:
                colab_id, colab_nome = melhor_candidato
                _conceder_ou_negar(
                    colab_id,
                    colab_nome,
                    menor_distancia,
                    nivel_requerido,
                    area_requerida,
                )
            else:
                st.error(
                    f"🚨 **ACESSO NEGADO!** Biometria não bateu com nenhum cadastrado. (Menor distância calculada: {menor_distancia:.3f})"
                )
                registrar_log(
                    "Desconhecido",
                    area_requerida,
                    "NEGADO",
                    {"motivo": "Biometria não reconhecida (foto)"},
                )
                _registrar_e_verificar_bloqueio(
                    area_requerida,
                    "Biometria não reconhecida (foto).",
                    origem="foto",
                )

                enviar_alerta_seguranca(
                    area_requerida, "Pessoa não identificada/desconhecida."
                )

        except Exception as e:
            registrar_erro("GERAL", "Validação de Acesso", str(e))
            st.error(
                f"❌ Ocorreu um erro inesperado na validação de acesso. Veja "
                f"a aba 🐞 Registro de Erros para ajuda. ({e})"
            )


st.sidebar.title("🔐 Cofre de Toxinas")

_sessao_ok = _sessao_valida()
_usuario_sidebar = st.session_state.get("usuario_logado")

if not _sessao_ok:
    if _usuario_sidebar and st.session_state.get("sessao_expirada"):
        st.sidebar.warning(
            "⏱️ **Sessão expirada por inatividade.**\nFaça login novamente."
        )
        st.session_state.pop("sessao_expirada", None)
    else:
        st.sidebar.info("🔴 Nenhuma sessão ativa.")
    st.sidebar.caption(
        "🔒 Áreas sensíveis seguem as permissões por nível. Colaboradores "
        "cadastrados antes do novo esquema entram pela biometria."
    )

    if "home_tela" not in st.session_state:
        st.session_state["home_tela"] = "home"
    _tela = st.session_state["home_tela"]

    if _tela == "home":
        _render_home()
    elif _tela == "cadastro":
        _render_login(destino="cadastro")
    elif _tela == "acesso":
        if st.button("← Voltar ao Início", key="voltar_acesso"):
            st.session_state["home_tela"] = "home"
            st.rerun()
        st.divider()
        _aba_simulacao()
    else:
        _render_criar_admin()
    st.stop()

# ---------------------------------------------------------------------------
# USUÁRIO AUTENTICADO — Navegação, sessão e notificações
# ---------------------------------------------------------------------------
_opcoes_nav = [
    "🔐 Cofre de Toxinas do MMA",
    "📹 Validar Acesso / Login Biométrico",
    "📈 Dashboard Analítico de Acessos",
    "📊 Dashboard e Relatórios",
    "🐞 Registro de Erros / Logs",
    "📸 Cadastro de Colaboradores",
]
if usuario_tem_nivel(3):
    _opcoes_nav.insert(5, "🛡️ Gestão de Acessos")

_destino_inicial = st.session_state.get("redirecionar_para")
if _destino_inicial in _opcoes_nav:
    _idx_nav = _opcoes_nav.index(_destino_inicial)
else:
    _idx_nav = 0

opcao = st.sidebar.radio(
    "Navegação:",
    _opcoes_nav,
    index=_idx_nav,
)
st.session_state.pop("redirecionar_para", None)

_usuario_sidebar = st.session_state.get("usuario_logado")
if _usuario_sidebar:
    st.sidebar.success(
        f"🟢 **{_usuario_sidebar['nome']}**\n{rotulo_nivel(_usuario_sidebar['nivel_acesso'])}"
    )
    if _usuario_sidebar.get("pode_cadastrar"):
        st.sidebar.caption("📝 Permissão de cadastro de colaboradores")
    if st.sidebar.button("🔓 Encerrar Sessão", use_container_width=True):
        _encerrar_sessao()
        st.rerun()
st.sidebar.divider()

# --- CONFIGURAÇÕES DE ALERTAS NA SIDEBAR ---
with st.sidebar.expander("⚙️ Configurar Notificações"):
    st.markdown("**📧 E-mail (SMTP)**")
    st.checkbox("Ativar Alerta E-mail", key="cfg_email_ativo")
    st.selectbox(
        "Provedor de e-mail (SMTP):",
        list(PRESETS_SMTP.keys()),
        key="cfg_email_provedor",
        on_change=_definir_preset_smtp,
    )
    c1, c2 = st.columns([2, 1])
    c1.text_input("Host SMTP:", key="cfg_email_smtp_host")
    c2.text_input("Porta:", key="cfg_email_smtp_port")
    st.text_input(
        "SMTP Login (opcional; padrão: remetente):",
        key="cfg_email_smtp_login",
        placeholder="ex.: seu@dominio.com.br (necessário no Brevo)",
    )
    st.text_input(
        "Seu E-mail (Remetente):",
        key="cfg_email_remetente",
        placeholder="seu@gmail.com",
    )
    st.text_input(
        "Senha de App:",
        type="password",
        key="cfg_email_senha",
        help="Crie uma Senha de App no Gmail",
    )
    st.text_input(
        "E-mail do Responsável:",
        key="cfg_email_destinatario",
        placeholder="destino@empresa.com",
    )

    st.divider()
    st.markdown("**📱 WhatsApp / SMS (Twilio)**")
    st.checkbox("Ativar Alerta Twilio", key="cfg_twilio_ativo")
    st.text_input("Account SID:", key="cfg_twilio_sid")
    st.text_input("Auth Token:", type="password", key="cfg_twilio_token")
    st.text_input(
        "Número Twilio (De):",
        key="cfg_twilio_de",
        placeholder="whatsapp:+14155238886",
    )
    st.text_input(
        "Seu WhatsApp (Para):",
        key="cfg_twilio_para",
        placeholder="whatsapp:+5511999999999",
    )

    st.divider()
    st.markdown("**📱 Grupo WhatsApp (Web)**")
    st.checkbox(
        "Ativar alerta no grupo WhatsApp Web",
        key="cfg_wagrupo_ativo",
        help="Envia a mensagem padrão ao grupo usando o WhatsApp Web "
        "(perfil de automação próprio, via Selenium).",
    )
    st.text_input(
        "ID do grupo:",
        key="cfg_wagrupo_id",
        placeholder="AB123CDEFGHijklmn (código do link de convite)",
        help="Abra o grupo no WhatsApp → 'Adicionar participantes' → 'Convidar "
        "via link' → copie só o código após chat.whatsapp.com/<código>.",
    )
    st.text_input(
        "Nome do grupo:",
        key="cfg_wagrupo_nome",
        placeholder="Ex.: Envio de alerta de segurança",
        help="Nome exato do grupo como aparece na lista de conversas. Usado "
        "para abrir o grupo pela busca do WhatsApp Web (mais confiável).",
    )
    st.caption(
        "Primeiro uso: clique em **📲 Conectar WhatsApp Web** abaixo e "
        "escaneie o QR com o celular (feito uma vez)."
    )
    _status_wa = st.session_state.get("wa_status")
    if _status_wa == "conectado":
        st.success("🟢 Perfil WhatsApp **conectado**")
    elif _status_wa == "nao_conectado":
        st.warning("🟡 Perfil WhatsApp **não conectado** — escaneie o QR")
    elif _status_wa == "erro":
        st.error("🔴 Falha ao verificar o perfil WhatsApp")
    else:
        st.caption("🟡 Status do perfil: não verificado")
    if st.button("🔄 Verificar estado do perfil", use_container_width=True):
        _checar_estado_perfil()
    if st.button(
        "📲 Conectar WhatsApp Web (escanear QR)", use_container_width=True
    ):
        conectar_whatsapp_web()

    st.divider()
    _salvar_config_alerta()
    if "wa_feedback" in st.session_state:
        _tipo_fb, _msg_fb = st.session_state.pop("wa_feedback")
        if _tipo_fb == "ok":
            st.success(f"📱 {_msg_fb}")
        elif _tipo_fb == "info":
            st.info(_msg_fb)
        else:
            st.error(f"{_msg_fb}\n\nConfira se o WhatsApp Web está **conectado "
                     "no perfil de automação** (botão 📲 Conectar WhatsApp Web, "
                     "acima, para escanear o QR). "
                     "Registrado na aba 🐞 Registro de Erros.")
    if st.button("🔔 Enviar alerta de teste", use_container_width=True):
        comp_ativa = _canais_ativos()
        if not comp_ativa:
            st.warning(
                "⚠️ Nenhum canal de alerta ativado. Marque/Configure "
                "**E-mail**, **Twilio** ou **Grupo WhatsApp (Web)** acima."
            )
        else:
            enviar_alerta_seguranca(
                "🔧 TESTE",
                "Teste de notificação — configuração de alertas verificada com sucesso!",
            )
    if st.button("🚨 Simular acesso negado (gatilho)", use_container_width=True):
        comp_ativa = _canais_ativos()
        if not comp_ativa:
            st.warning(
                "⚠️ Nenhum canal de alerta ativado. Marque/Configure "
                "**E-mail**, **Twilio** ou **Grupo WhatsApp (Web)** acima."
            )
        else:
            enviar_alerta_seguranca(
                "Nível 3 – Ministro do Meio Ambiente",
                "Tentativa de acesso negada (simulação de teste) — biometria não reconhecida.",
            )
    if st.button("📱 Testar envio ao grupo (WhatsApp Web)", use_container_width=True):
        if not st.session_state.get("cfg_wagrupo_ativo", False):
            st.warning(
                "⚠️ Marque **Ativar alerta no grupo WhatsApp Web** acima "
                "para testar o envio."
            )
        elif not _normalizar_grupo_id(
            st.session_state.get("cfg_wagrupo_id", "")
        ):
            st.warning(
                "⚠️ Preencha o **ID do grupo** (código do link de convite) "
                "antes de testar."
            )
        else:
            st.session_state.pop("wa_feedback", None)
            enviar_whatsapp_grupo(
                "🔧 TESTE",
                "Teste de notificação — configuração de alertas verificada com sucesso!",
            )


def ao_trocar_aba_guard(fn, modulo):
    """Envolve a lógica de uma aba em try/except para capturar erros inesperados."""
    try:
        fn()
    except Exception as e:
        registrar_erro("GERAL", modulo, str(e))
        st.error(
            f"❌ Ocorreu um erro inesperado nesta tela. Veja a aba 🐞 "
            f"Registro de Erros para ajuda. ({e})"
        )


if "home_aviso" in st.session_state:
    _aviso = st.session_state.pop("home_aviso")
    st.warning(_aviso)


if opcao == "📸 Cadastro de Colaboradores":
    def _aba_cadastro():
        if not usuario_pode_cadastrar():
            st.title("📸 Cadastro de Colaboradores")
            st.warning(
                "🔒 **Acesso restrito.** Apenas colaboradores autorizados "
                "(com permissão de cadastro, definida na aba 🛡️ Gestão de "
                "Acessos pelo nível 3) podem cadastrar novos colaboradores."
            )
            return

        st.markdown(MOLDURA_CIRCULAR_CSS, unsafe_allow_html=True)
        st.title("📸 Cadastro de Colaboradores e Permissões")

        if "msg_status" in st.session_state:
            tipo, msg = st.session_state.pop("msg_status")
            if tipo == "success":
                st.success(msg)
            else:
                st.error(msg)

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("Dados Pessoais")
            st.text_input("Nome Completo:*", key="reg_nome")
            st.text_input("Cargo / Função:", key="reg_cargo")
            st.selectbox(
                "Divisão do Ministério:",
                options=["Sem divisão"] + DIVISOES_MMA,
                key="reg_divisao",
                help=(
                    "Diretores (nível 2) e o ministro (nível 3) pertencem a "
                    "divisões específicas do MMA."
                ),
            )
            st.selectbox(
                "Nível de Acesso ao Cofre:*",
                options=list(NIVEIS_ACESSO.keys()),
                format_func=rotulo_nivel,
                key="reg_nivel",
                help=(
                    "Níveis **cumulativos**: um colaborador de nível N acessa "
                    "tudo dos níveis anteriores (1 a N)."
                ),
            )
            st.caption(descricao_nivel(st.session_state.get("reg_nivel", 1)))

            st.divider()
            st.subheader("Credenciais de Acesso")
            st.text_input(
                "Usuário (login):*",
                key="reg_usuario",
                placeholder="ex.: maria.silva",
                help="Este usuário será usado para entrar no sistema.",
            )
            st.text_input(
                "Senha:*",
                type="password",
                key="reg_senha",
                help="Senha inicial (mínimo 6 caracteres).",
            )

        with col2:
            st.subheader("Captura da Foto")
            metodo_foto = st.radio(
                "Origem da imagem:",
                ["Tirar Foto pela Webcam", "Fazer Upload de Imagem"],
                key="metodo_foto_radio",
            )

            if metodo_foto == "Tirar Foto pela Webcam":
                foto_input = st.camera_input(
                    "Centralize o rosto no círculo verde antes de tirar a foto"
                )
            else:
                foto_input = st.file_uploader(
                    "Escolha um arquivo JPG/PNG", type=["jpg", "jpeg", "png"]
                )

            if foto_input is not None:
                st.session_state["foto_capturada_bytes"] = foto_input.getvalue()

        st.button(
            "💾 Cadastrar Colaborador",
            type="primary",
            on_click=salvar_colaborador,
        )

        st.divider()
        st.subheader("👥 Colaboradores Já Cadastrados")

        try:
            conn = sqlite3.connect(DB_FILE)
            df_colabs = pd.read_sql_query(
                "SELECT id, nome, cargo, divisao, nivel_acesso, usuario, "
                "pode_cadastrar, data_cadastro FROM colaboradores",
                conn,
            )

            if not df_colabs.empty:
                df_colabs["nivel"] = df_colabs["nivel_acesso"].map(rotulo_nivel)
                df_colabs["pde_cadastrar"] = df_colabs["pode_cadastrar"].map(
                    {1: "✅ Sim", 0: "—"}
                )
                st.dataframe(
                    df_colabs[
                        [
                            "id",
                            "nome",
                            "cargo",
                            "divisao",
                            "nivel",
                            "usuario",
                            "pde_cadastrar",
                            "data_cadastro",
                        ]
                    ].rename(
                        columns={
                            "id": "ID",
                            "nome": "Nome",
                            "cargo": "Cargo",
                            "divisao": "Divisão",
                            "nivel": "Nível de Acesso",
                            "usuario": "Usuário",
                            "pde_cadastrar": "Pode Cadastrar",
                            "data_cadastro": "Data Cadastro",
                        }
                    ),
                    width="stretch",
                )
            else:
                st.info("Nenhum colaborador cadastrado ainda.")
            conn.close()
        except Exception as e:
            registrar_erro("BANCO", "Lista de Colaboradores", str(e))
            st.error(
                f"Erro ao carregar colaboradores. Veja a aba 🐞 Registro de Erros "
                f"para ajuda. ({e})"
            )

    ao_trocar_aba_guard(_aba_cadastro, "Cadastro de Colaboradores")

elif opcao == "📹 Validar Acesso / Login Biométrico":
    ao_trocar_aba_guard(_aba_simulacao, "Validar Acesso / Login Biométrico")

elif opcao == "📈 Dashboard Analítico de Acessos":
    def _aba_dash_analitico():
        if not usuario_tem_nivel(2):
            st.title("📈 Dashboard Analítico de Acessos")
            st.warning(
                "🔒 **Acesso restrito.** O dashboard analítico de acessos só é "
                "liberado para colaboradores de **nível 2 ou 3** (Diretores de "
                "Divisões Específicas e Ministro do Meio Ambiente)."
            )
            return

        st.title("📈 Dashboard Analítico de Acessos ao Cofre")
        st.caption(
            "Visão consolidada dos eventos de acesso ao **Cofre de Toxinas**: "
            "tendências temporais, distribuição por compartimento do cofre, "
            "colaboradores mais ativos e diagnóstico de segurança."
        )

        df_logs = _preparar_logs()

        if df_logs.empty:
            st.info("Nenhum registro de acesso encontrado.")
            return

        data_min = df_logs["data"].min()
        data_max = df_logs["data"].max()

        st.divider()
        st.subheader("🔎 Filtros")

        c1, c2 = st.columns([1, 1])
        with c1:
            periodo = st.selectbox(
                "Período rápido:",
                ["Tudo", "Hoje", "Últimos 7 dias", "Últimos 30 dias"],
            )
        with c2:
            data_range = st.date_input(
                "Intervalo de datas:",
                value=(data_min, data_max),
                min_value=data_min,
                max_value=data_max,
            )

        compartimentos_opcoes = sorted(
            df_logs["area_dados"].unique(),
            key=lambda s: (
                int(s.split("–")[0].replace("Nível", "").strip())
                if "Nível" in s
                else 99
            ),
        )
        f1, f2, f3 = st.columns(3)
        with f1:
            area_filter = st.multiselect(
                "Filtrar por Compartimento do Cofre:",
                options=compartimentos_opcoes,
                default=compartimentos_opcoes,
            )
        with f2:
            status_filter = st.multiselect(
                "Filtrar por Status:",
                options=sorted(df_logs["status"].unique()),
                default=sorted(df_logs["status"].unique()),
            )
        with f3:
            nome_filter = st.text_input("Buscar por Colaborador:")

        if len(data_range) == 2:
            data_inicio, data_fim = data_range
        else:
            data_inicio, data_fim = data_min, data_max

        df = df_logs[
            (df_logs["data"] >= data_inicio)
            & (df_logs["data"] <= data_fim)
            & (df_logs["area_dados"].isin(area_filter))
            & (df_logs["status"].isin(status_filter))
        ]
        if nome_filter:
            df = df[
                df["colaborador_nome"].str.contains(
                    nome_filter, case=False, na=False
                )
            ]

        if df.empty:
            st.warning("Nenhum evento no período/filtros selecionados.")
            return

        total = len(df)
        permitidos = len(df[df["status"] == "PERMITIDO"])
        negados = len(df[df["status"] == "NEGADO"])
        taxa = (permitidos / total * 100) if total else 0.0
        dias_periodo = max((data_fim - data_inicio).days, 1)
        media_dia = total / dias_periodo

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total de Acessos", total)
        m2.metric("Permitidos", permitidos)
        m3.metric("Negados", negados)
        m4.metric("Taxa de Aprovação", f"{taxa:.1f}%")
        m5.metric("Média / dia", f"{media_dia:.1f}")

        st.divider()
        st.subheader("📅 Tendências Temporais")

        serie_dia = (
            df.groupby(["data", "status"], as_index=False)
            .size()
            .rename(columns={"size": "contagem"})
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            chart_linha = (
                alt.Chart(serie_dia)
                .mark_line(point=True, strokeWidth=2)
                .encode(
                    x=alt.X("data:T", title="Data"),
                    y=alt.Y("contagem:Q", title="Nº de acessos"),
                    color=alt.Color(
                        "status:N",
                        title="Status",
                        scale=alt.Scale(
                            domain=["PERMITIDO", "NEGADO"],
                            range=["#00C853", "#D50000"],
                        ),
                    ),
                    tooltip=["data:T", "status:N", "contagem:Q"],
                )
                .properties(height=320)
            )
            st.altair_chart(chart_linha, use_container_width=True)

        with c2:
            status_tot = (
                df.groupby("status", as_index=False)
                .size()
                .rename(columns={"size": "contagem"})
            )
            chart_status = (
                alt.Chart(status_tot)
                .mark_arc()
                .encode(
                    theta=alt.Theta("contagem:Q", stack=True),
                    color=alt.Color(
                        "status:N",
                        scale=alt.Scale(
                            domain=["PERMITIDO", "NEGADO"],
                            range=["#00C853", "#D50000"],
                        ),
                    ),
                    tooltip=["status:N", "contagem:Q"],
                )
                .properties(height=320)
            )
            st.altair_chart(chart_status, use_container_width=True)

        st.divider()
        st.subheader("🏢 Distribuição por Compartimento do Cofre")

        dist_area = (
            df.groupby(["compartimento_curto", "nivel"], as_index=False)
            .size()
            .rename(columns={"size": "contagem"})
            .sort_values(["nivel", "compartimento_curto"])
        )
        chart_area = (
            alt.Chart(dist_area)
            .mark_bar()
            .encode(
                x=alt.X("contagem:Q", title="Nº de eventos"),
                y=alt.Y("compartimento_curto:N", title="", sort="-x"),
                color=alt.Color(
                    "nivel:O",
                    title="Nível de segurança",
                    scale=alt.Scale(
                        domain=["1", "2", "3"],
                        range=["#2E7D32", "#F9A825", "#C62828"],
                    ),
                ),
                tooltip=["compartimento_curto:N", "nivel:O", "contagem:Q"],
            )
            .properties(height=320)
        )
        st.altair_chart(chart_area, use_container_width=True)
        st.caption(
            "Níveis cumulativos do cofre de toxinas — "
            "🟢 Nível 1: **Permissão Geral** · "
            "🟡 Nível 2: **Diretores de Divisões Específicas** · "
            "🔴 Nível 3: **Ministro do Meio Ambiente** (acesso exclusivo)."
        )

        st.divider()
        st.subheader("🎖️ Equipe do Cofre")
        try:
            conn2 = sqlite3.connect(DB_FILE)
            df_colabs = pd.read_sql_query(
                "SELECT id, nome, cargo, divisao, nivel_acesso "
                "FROM colaboradores",
                conn2,
            )
            conn2.close()
            if not df_colabs.empty:
                e1, e2, e3, e4 = st.columns(4)
                e1.metric("Colaboradores no cofre", len(df_colabs))
                e2.metric("Nível 1 (Permissão Geral)", int((df_colabs["nivel_acesso"] == 1).sum()))
                e3.metric("Nível 2 (Diretores)", int((df_colabs["nivel_acesso"] == 2).sum()))
                e4.metric("Nível 3 (Ministro)", int((df_colabs["nivel_acesso"] == 3).sum()))
                df_colabs["nivel"] = df_colabs["nivel_acesso"].map(rotulo_nivel)
                st.dataframe(
                    df_colabs[
                        ["nome", "cargo", "divisao", "nivel"]
                    ].rename(
                        columns={
                            "nome": "Nome",
                            "cargo": "Cargo",
                            "divisao": "Divisão",
                            "nivel": "Nível de Acesso",
                        }
                    ),
                    width="stretch",
                )
            else:
                st.info("Nenhum colaborador cadastrado no cofre ainda.")
        except Exception as e:
            st.caption(f"Equipe indisponível: {e}")

        st.divider()
        st.subheader("👥 Colaboradores Mais Ativos")

        top_colabs = (
            df.groupby("colaborador_nome", as_index=False)
            .size()
            .rename(columns={"size": "contagem"})
            .sort_values("contagem", ascending=False)
            .head(10)
        )
        chart_top = (
            alt.Chart(top_colabs)
            .mark_bar()
            .encode(
                x=alt.X("contagem:Q", title="Nº de eventos"),
                y=alt.Y("colaborador_nome:N", title="", sort="-x"),
                color=alt.Color(
                    "contagem:Q", scale=alt.Scale(scheme="viridis")
                ),
                tooltip=["colaborador_nome:N", "contagem:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart_top, use_container_width=True)

        st.divider()
        st.subheader("🕐 Movimentação por Hora do Dia")

        serie_hora = (
            df.groupby(["hora", "status"], as_index=False)
            .size()
            .rename(columns={"size": "contagem"})
        )
        chart_hora = (
            alt.Chart(serie_hora)
            .mark_bar()
            .encode(
                x=alt.X("hora:O", title="Hora do dia"),
                y=alt.Y("contagem:Q", title="Nº de eventos"),
                color=alt.Color(
                    "status:N",
                    scale=alt.Scale(
                        domain=["PERMITIDO", "NEGADO"],
                        range=["#00C853", "#D50000"],
                    ),
                ),
                tooltip=["hora:O", "status:N", "contagem:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart_hora, use_container_width=True)

        st.divider()
        st.subheader("🚨 Diagnóstico de Segurança do Cofre")

        negados_df = df[df["status"] == "NEGADO"]
        if not negados_df.empty:
            top_negados_area = (
                negados_df.groupby("area_dados")
                .size()
                .sort_values(ascending=False)
                .head(3)
            )
            st.warning(
                f"**{len(negados_df)} tentativas negadas** no período. "
                "Compartimentos mais visados: "
                + ", ".join(
                    f"`{s}` ({n})" for s, n in top_negados_area.items()
                )
                + "."
            )
            desconhecidos = negados_df[
                negados_df["colaborador_nome"] == "Desconhecido"
            ]
            if not desconhecidos.empty:
                st.warning(
                    f"**{len(desconhecidos)} eventos** de pessoa não "
                    "identificada (possível tentativa de intrusão ao cofre)."
                )
            tentativa_sem_perm = negados_df[
                negados_df["colaborador_nome"] != "Desconhecido"
            ]
            if not tentativa_sem_perm.empty:
                st.warning(
                    f"**{len(tentativa_sem_perm)} eventos** de colaboradores "
                    "identificados sem permissão para o compartimento do cofre."
                )
        else:
            st.success("✅ Nenhuma tentativa negada no período selecionado.")

        st.divider()
        st.subheader("📄 Auditoria Detalhada dos Eventos")
        st.dataframe(
            df[
                [
                    "data_hora",
                    "colaborador_nome",
                    "compartimento_curto",
                    "nivel",
                    "status",
                ]
            ]
            .sort_values("data_hora", ascending=False)
            .rename(
                columns={
                    "data_hora": "Data / Hora",
                    "colaborador_nome": "Colaborador",
                    "compartimento_curto": "Compartimento",
                    "nivel": "Nível",
                    "status": "Status",
                }
            ),
            width="stretch",
        )

        df_export = df.rename(
            columns={"area_dados": "compartimento"}
        ).drop(columns=["compartimento_curto"])
        csv_data = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Exportar Eventos Filtrados (CSV)",
            data=csv_data,
            file_name=(
                f"eventos_cofre_{datetime.now().strftime('%Y%m%d')}.csv"
            ),
            mime="text/csv",
        )

        st.divider()
        st.subheader("📄 Relatório PDF")
        st.caption(
            "Gera um relatório executivo em PDF com os indicadores dos filtros "
            "ativos, gráficos ilustrativos e as tabelas de auditoria."
        )
        with st.spinner("Gerando relatório PDF com gráficos..."):
            pdf_bytes = gerar_relatorio_pdf(df)
        st.download_button(
            label="📄 Baixar Relatório PDF (Dados Filtrados + Gráficos)",
            data=pdf_bytes,
            file_name=(
                f"relatorio_cofre_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            ),
            mime="application/pdf",
        )

    ao_trocar_aba_guard(_aba_dash_analitico, "Dashboard Analítico de Acessos")

elif opcao == "📊 Dashboard e Relatórios":
    def _aba_dash_relatorios():
        if not usuario_tem_nivel(2):
            st.title("📊 Dashboard e Relatórios")
            st.warning(
                "🔒 **Acesso restrito.** O dashboard e relatórios de auditoria "
                "só é liberado para colaboradores de **nível 2 ou 3** "
                "(Diretores de Divisões Específicas e Ministro)."
            )
            return

        st.title("📊 Auditoria e Métricas de Controle de Acesso ao Cofre")

        df_logs = _preparar_logs()

        if df_logs.empty:
            st.info("Nenhum registro de acesso encontrado.")
            return

        total_acessos = len(df_logs)
        permitidos = len(df_logs[df_logs["status"] == "PERMITIDO"])
        negados = len(df_logs[df_logs["status"] == "NEGADO"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total de Acessos", total_acessos)
        m2.metric("Acessos Permitidos", permitidos)
        m3.metric(
            "Tentativas Negadas / Alertas",
            negados,
            delta_color="inverse" if negados > 0 else "normal",
        )
        m4.metric("Compartimentos monitorados", df_logs["nivel"].nunique())

        st.divider()

        st.subheader("🔍 Filtros de Consulta")
        f1, f2, f3 = st.columns(3)

        compartimentos_opcoes = sorted(
            df_logs["area_dados"].unique(),
            key=lambda s: (
                int(s.split("–")[0].replace("Nível", "").strip())
                if "Nível" in s
                else 99
            ),
        )
        with f1:
            area_filter = st.multiselect(
                "Filtrar por Compartimento do Cofre:",
                options=compartimentos_opcoes,
                default=compartimentos_opcoes,
            )
        with f2:
            status_filter = st.multiselect(
                "Filtrar por Status:",
                options=df_logs["status"].unique(),
                default=df_logs["status"].unique(),
            )
        with f3:
            nome_filter = st.text_input("Buscar por Colaborador:")

        df_filtered = df_logs[
            (df_logs["area_dados"].isin(area_filter))
            & (df_logs["status"].isin(status_filter))
        ]
        if nome_filter:
            df_filtered = df_filtered[
                df_filtered["colaborador_nome"].str.contains(
                    nome_filter, case=False, na=False
                )
            ]

        st.subheader("📄 Histórico de Acessos")
        st.dataframe(
            df_filtered[
                [
                    "data_hora",
                    "colaborador_nome",
                    "compartimento_curto",
                    "nivel",
                    "status",
                ]
            ]
            .rename(
                columns={
                    "data_hora": "Data / Hora",
                    "colaborador_nome": "Colaborador",
                    "compartimento_curto": "Compartimento",
                    "nivel": "Nível",
                    "status": "Status",
                }
            ),
            width="stretch",
        )

        df_export = df_filtered.rename(
            columns={"area_dados": "compartimento"}
        ).drop(columns=["compartimento_curto"])
        csv_data = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Exportar Relatório Filtrado (CSV)",
            data=csv_data,
            file_name=(
                f'relatorio_cofre_{datetime.now().strftime("%Y%m%d")}.csv'
            ),
            mime="text/csv",
        )

        st.divider()
        st.subheader("📄 Relatório PDF")
        st.caption(
            "Gera um relatório executivo completo em PDF com todos os "
            "indicadores, gráficos ilustrativos e as tabelas de auditoria."
        )
        with st.spinner("Gerando relatório PDF com gráficos..."):
            pdf_bytes = gerar_relatorio_pdf()
        st.download_button(
            label="📄 Baixar Relatório PDF (Completo + Gráficos)",
            data=pdf_bytes,
            file_name=(
                f"relatorio_cofre_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            ),
            mime="application/pdf",
        )

    ao_trocar_aba_guard(_aba_dash_relatorios, "Dashboard e Relatórios")

elif opcao == "🐞 Registro de Erros / Logs":
    def _aba_logs():
        if not usuario_tem_nivel(2):
            st.title("🐞 Registro de Erros / Logs")
            st.warning(
                "🔒 **Acesso restrito.** O registro de erros/logs do sistema "
                "só é liberado para colaboradores de **nível 2 ou 3**."
            )
            return

        st.title("🐞 Registro de Erros / Logs")
        st.caption(
            "Registros automáticos de erros capturados pela aplicação. Use os "
            "filtros para localizar um erro e veja abaixo como entender e resolver."
        )

        conn = sqlite3.connect(DB_FILE)
        df_erros = pd.read_sql_query("SELECT * FROM logs_erros", conn)
        conn.close()

        if df_erros.empty:
            st.info("Nenhum erro registrado até o momento. 🎉")
            return

        df_erros["data_hora"] = pd.to_datetime(df_erros["data_hora"])
        df_erros["data"] = df_erros["data_hora"].dt.date

        st.divider()
        st.subheader("🔎 Filtros de Erros")

        f1, f2, f3 = st.columns(3)
        with f1:
            tipo_filter = st.multiselect(
                "Filtrar por Tipo de Erro:",
                options=sorted(df_erros["tipo"].unique()),
                default=sorted(df_erros["tipo"].unique()),
            )
        with f2:
            modulo_filter = st.multiselect(
                "Filtrar por Módulo:",
                options=sorted(df_erros["modulo"].unique()),
                default=sorted(df_erros["modulo"].unique()),
            )
        with f3:
            busca_filter = st.text_input("Buscar na mensagem:")

        data_min = df_erros["data"].min()
        data_max = df_erros["data"].max()
        data_range = st.date_input(
            "Intervalo de datas:",
            value=(data_min, data_max),
            min_value=data_min,
            max_value=data_max,
        )
        if len(data_range) == 2:
            data_inicio, data_fim = data_range
        else:
            data_inicio, data_fim = data_min, data_max

        df = df_erros[
            (df_erros["data"] >= data_inicio)
            & (df_erros["data"] <= data_fim)
            & (df_erros["tipo"].isin(tipo_filter))
            & (df_erros["modulo"].isin(modulo_filter))
        ]
        if busca_filter:
            df = df[
                df["mensagem"].str.contains(
                    busca_filter, case=False, na=False
                )
            ]

        st.divider()
        st.subheader("📊 Resumo")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Erros (filtrado)", len(df))

        if not df.empty:
            tipo_counts = (
                df.groupby("tipo", as_index=False)
                .size()
                .rename(columns={"size": "contagem"})
            )
            c2.metric("Tipos Distintos", len(tipo_counts))
            mais_frequente = (
                tipo_counts.sort_values("contagem", ascending=False).iloc[0]
            )
            c3.metric("Erro mais Frequente", str(mais_frequente["tipo"]))

            st.write("**Distribuição por tipo de erro:**")

            chart_tipos = (
                alt.Chart(tipo_counts)
                .mark_bar()
                .encode(
                    x=alt.X("tipo:N", title="Tipo"),
                    y=alt.Y("contagem:Q", title="Nº de erros"),
                    color=alt.Color("tipo:N", legend=None),
                    tooltip=["tipo:N", "contagem:Q"],
                )
                .properties(height=250)
            )
            st.altair_chart(chart_tipos, use_container_width=True)

        st.divider()
        st.subheader("🧾 Lista de Erros Registrados")

        if df.empty:
            st.warning("Nenhum erro atende aos filtros selecionados.")
            return

        st.dataframe(
            df[["data_hora", "tipo", "modulo", "mensagem"]].sort_values(
                "data_hora", ascending=False
            ),
            width="stretch",
        )

        st.divider()
        st.subheader("❓ Selecione um erro para ver a Ajuda / Como Resolver")

        opcoes = {
            f"{r['data_hora']} | {r['tipo']} | {r['modulo']}": r["id"]
            for _, r in df.sort_values("data_hora", ascending=False).iterrows()
        }
        escolha = st.selectbox(
            "Erros (data/hora | tipo | módulo):",
            options=list(opcoes.keys()),
        )
        escolhido_id = opcoes[escolha]
        linha = df[df["id"] == escolhido_id].iloc[0]

        with st.expander(
            "🔑 Entender o erro (em linguagem simples)", expanded=True
        ):
            st.write(f"**Explicação:** {linha['descricao']}")
        with st.expander("🛠️ Como resolver / Sugestão", expanded=True):
            st.write(f"**Sugestão:** {linha['sugerida']}")
        with st.expander("🖥️ Detalhe técnico", expanded=False):
            st.code(linha["mensagem"], language="text")

        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Exportar Logs Filtrados (CSV)",
            data=csv_data,
            file_name=(
                f"logs_erros_{datetime.now().strftime('%Y%m%d')}.csv"
            ),
            mime="text/csv",
        )

        st.divider()
        if st.button(
            "🧹 Limpar todos os logs de erro",
            type="secondary",
            help="Remove permanentemente todos os registros de erro.",
        ):
            limpar_logs_erros()
            st.rerun()

    ao_trocar_aba_guard(_aba_logs, "Registro de Erros / Logs")

elif opcao == "🛡️ Gestão de Acessos":
    def _aba_gestao_acessos():
        if not usuario_tem_nivel(3):
            st.title("🛡️ Gestão de Acessos")
            st.warning(
                "🔒 **Acesso restrito ao nível 3** — Ministro do Meio Ambiente."
            )
            return

        st.title("🛡️ Gestão de Acessos e Permissões")
        st.caption(
            "Gerencie as credenciais (usuário/senha), o nível de acesso e a "
            "permissão de cadastro dos colaboradores. A permissão de cadastro "
            "deve ser concedida a apenas 1 ou 2 colaboradores de confiança."
        )

        try:
            conn = sqlite3.connect(DB_FILE)
            df_colabs = pd.read_sql_query(
                "SELECT id, nome, cargo, divisao, nivel_acesso, usuario, "
                "pode_cadastrar, foto_path, data_cadastro FROM colaboradores "
                "ORDER BY nome",
                conn,
            )
            conn.close()
            df_colabs["usuario"] = df_colabs["usuario"].fillna("").astype(str)
        except Exception as e:
            registrar_erro("BANCO", "Gestão de Acessos", str(e))
            st.error(
                f"Erro ao carregar colaboradores. Veja a aba 🐞 Registro de "
                f"Erros para ajuda. ({e})"
            )
            return

        if df_colabs.empty:
            st.info("Nenhum colaborador cadastrado ainda.")
            return

        df_show = df_colabs.copy()
        df_show["nivel"] = df_show["nivel_acesso"].map(rotulo_nivel)
        df_show["pode_cadastrar_txt"] = df_show["pode_cadastrar"].map(
            {1: "✅ Sim", 0: "—"}
        )
        df_show["credenciais"] = df_show["usuario"].fillna("—").replace("", "—")
        st.dataframe(
            df_show[
                ["id", "nome", "cargo", "divisao", "nivel", "credenciais",
                 "pode_cadastrar_txt"]
            ].rename(
                columns={
                    "id": "ID",
                    "nome": "Nome",
                    "cargo": "Cargo",
                    "divisao": "Divisão",
                    "nivel": "Nível de Acesso",
                    "credenciais": "Usuário",
                    "pode_cadastrar_txt": "Pode Cadastrar",
                }
            ),
            width="stretch",
        )

        st.divider()
        st.subheader("✏️ Editar Colaborador")

        opcoes = {
            f"{r['nome']} (ID {r['id']})": r["id"]
            for _, r in df_colabs.iterrows()
        }
        escolha = st.selectbox(
            "Selecione o colaborador:",
            options=list(opcoes.keys()),
            key="gestao_escolha",
        )
        colab_id = opcoes[escolha]
        linha = df_colabs[df_colabs["id"] == colab_id].iloc[0]

        with st.form("gestao_editar"):
            novo_usuario = st.text_input(
                "Usuário (login):",
                value=linha.get("usuario") or "",
                key="gestao_usuario",
            )
            nova_senha = st.text_input(
                "Nova Senha (deixe em branco para manter):",
                type="password",
                key="gestao_senha",
            )
            novo_nivel = st.selectbox(
                "Nível de Acesso:",
                options=list(NIVEIS_ACESSO.keys()),
                format_func=rotulo_nivel,
                index=int(linha["nivel_acesso"]) - 1,
                key="gestao_nivel",
            )
            pode_cadastrar = st.checkbox(
                "Permitir que este colaborador cadastre novos colaboradores",
                value=bool(linha.get("pode_cadastrar")),
                key="gestao_pode_cadastrar",
                help="Conceda esta permissão a apenas 1 ou 2 colaboradores de confiança.",
            )
            salvar = st.form_submit_button("💾 Salvar Alterações", type="primary")

        if salvar:
            novo_usuario = (novo_usuario or "").strip()
            if not novo_usuario:
                st.error("⚠️ O usuário não pode ficar vazio.")
                return
            try:
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM colaboradores "
                    "WHERE usuario = ? COLLATE NOCASE AND id <> ?",
                    (novo_usuario, colab_id),
                )
                if cur.fetchone()[0] > 0:
                    conn.close()
                    st.error("⚠️ Este usuário já está em uso por outro colaborador.")
                    return
                if nova_senha:
                    if len(nova_senha) < 6:
                        conn.close()
                        st.error("⚠️ A nova senha deve ter ao menos 6 caracteres.")
                        return
                    senha_hash = hash_senha(nova_senha)
                    cur.execute(
                        "UPDATE colaboradores SET usuario = ?, senha_hash = ? "
                        "WHERE id = ?",
                        (novo_usuario, senha_hash, colab_id),
                    )
                else:
                    cur.execute(
                        "UPDATE colaboradores SET usuario = ? WHERE id = ?",
                        (novo_usuario, colab_id),
                    )
                cur.execute(
                    "UPDATE colaboradores SET nivel_acesso = ?, pode_cadastrar = ? "
                    "WHERE id = ?",
                    (novo_nivel, 1 if pode_cadastrar else 0, colab_id),
                )
                conn.commit()
                conn.close()

                user_atual = st.session_state.get("usuario_logado")
                if user_atual and user_atual.get("id") == colab_id:
                    user_atual["nivel_acesso"] = novo_nivel
                    user_atual["pode_cadastrar"] = 1 if pode_cadastrar else 0
                    user_atual["usuario"] = novo_usuario
                    st.session_state["usuario_logado"] = user_atual

                st.success(
                    f"✅ Alterações salvas para **{linha['nome']}**. "
                    f"Nível: {rotulo_nivel(novo_nivel)}. "
                    f"Pode cadastrar: {'✅ Sim' if pode_cadastrar else '—'}."
                )
                st.rerun()
            except Exception as e:
                registrar_erro("BANCO", "Gestão de Acessos (Editar)", str(e))
                st.error(
                    f"❌ Erro ao salvar alterações. Veja a aba 🐞 Registro de "
                    f"Erros para ajuda. ({e})"
                )

    ao_trocar_aba_guard(_aba_gestao_acessos, "Gestão de Acessos")

elif opcao == "🔐 Cofre de Toxinas do MMA":
    def _aba_dados_geo():
        st.title("🔐 Cofre de Toxinas — Ministério do Meio Ambiente")
        st.caption(
            "Painel do cofre de segurança máxima que guarda informações sobre "
            "o uso de toxinas. O acesso a cada compartimento é controlado pelo "
            "nível do colaborador autenticado (níveis cumulativos)."
        )

        usuario = st.session_state.get("usuario_logado")
        if not _sessao_valida():
            expirou = st.session_state.get("sessao_expirada", False)
            st.warning(
                "⏱️ **Sessão expirada ou nenhuma sessão ativa.** " if expirou
                else "⚠️ **Nenhuma sessão ativa.** "
                + "Faça login com **usuário e senha** para visualizar o cofre. "
                "Use a aba 📹 **Validar Acesso / Login Biométrico** para "
                "liberar compartimentos conforme o seu nível."
            )
            return

        st.success(
            f"🟢 Sessão ativa: **{usuario['nome']}** — {rotulo_nivel(usuario['nivel_acesso'])}"
        )

        df_toxinas = carregar_dados_toxinas()

        # ---------------- NÍVEL 1 ----------------
        st.divider()
        st.subheader("🗂️ 1. Catálogo Público de Toxinas (Permissão Geral)")
        st.caption(descricao_nivel(1))
        if not usuario_tem_nivel(1):
            st.info("🔒 **Bloqueado para o seu nível.** O catálogo exige nível 1.")
        else:
            cols_catalogo = [
                "id_toxina",
                "nome",
                "classe",
                "tipo_acao",
                "periculosidade",
                "uso",
                "divisao_responsavel",
            ]
            st.dataframe(df_toxinas[cols_catalogo], width="stretch")
            st.caption(
                f"Total de **{len(df_toxinas)}** toxinas registradas no catálogo do cofre."
            )

            st.markdown("#### 🛡️ Missão da Sala do Cofre")
            st.markdown(
                "Este cofre, oculto nas profundezas do **Ministério do Meio Ambiente**, "
                "guarda os segredos mais sensíveis sobre o uso de toxinas. As substâncias "
                "registradas aqui são tão poderosas que, se manuseadas de forma inadequada, "
                "poderiam provocar uma nova pandemia mundial, devastar ecossistemas e "
                "colocar em risco a vida na Terra. **Apenas pessoas devidamente "
                "autorizadas** têm acesso, em um esquema de permissões dividido em "
                "três níveis de segurança."
            )

        # ---------------- NÍVEL 2 ----------------
        st.divider()
        st.subheader("🗺️ 2. Inventário e Localização (Diretores de Divisões)")
        st.caption(descricao_nivel(2))
        if not usuario_tem_nivel(2):
            st.info("🔒 **Bloqueado para o seu nível.** O inventário exige nível 2.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                chart_classe = (
                    alt.Chart(df_toxinas)
                    .mark_bar()
                    .encode(
                        x=alt.X("classe:N", title="", sort="-y"),
                        y=alt.Y("estoque_unidades:Q", title="Unidades em estoque"),
                        color=alt.Color("estado_conservacao:N", title="Estado"),
                        tooltip=[
                            "classe:N",
                            "estoque_unidades:Q",
                            "estado_conservacao:N",
                        ],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart_classe, use_container_width=True)
            with c2:
                chart_comp = (
                    alt.Chart(df_toxinas)
                    .mark_circle(size=90)
                    .encode(
                        x=alt.X("compartimento:N", title=""),
                        y=alt.Y("periculosidade:Q", title="Periculosidade (1-5)"),
                        size=alt.Size("estoque_unidades:Q", title="Estoque"),
                        color=alt.Color("classe:N", title="Classe"),
                        tooltip=[
                            "id_toxina:N",
                            "nome:N",
                            "compartimento:N",
                            "periculosidade:Q",
                        ],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart_comp, use_container_width=True)
            st.caption(
                "Distribuição simulada das toxinas entre os compartimentos do cofre."
            )

            st.markdown("#### 🗄️ Estoque e conservação")
            cols_estoque = [
                "id_toxina",
                "nome",
                "compartimento",
                "divisao_responsavel",
                "estoque_unidades",
                "temperatura_c",
                "data_validade",
                "estado_conservacao",
            ]
            st.dataframe(
                df_toxinas[cols_estoque].sort_values(
                    "estoque_unidades", ascending=False
                ),
                width="stretch",
            )
            csv_inventario = df_toxinas.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar Inventário (CSV)",
                data=csv_inventario,
                file_name="inventario_toxinas.csv",
                mime="text/csv",
            )

        # ---------------- NÍVEL 3 ----------------
        st.divider()
        st.subheader("🧪 3. Dossiê Completo e Movimentação (Ministro do Meio Ambiente)")
        st.caption(descricao_nivel(3))
        if not usuario_tem_nivel(3):
            st.info(
                "🔒 **Bloqueado para o seu nível.** O dossiê exige nível 3."
            )
        else:
            df_serie = serie_temporal_movimentacao()
            divisoes = list(df_serie["divisao"].unique())
            selecao = st.multiselect(
                "Divisões do Ministério:",
                options=divisoes,
                default=divisoes,
            )
            if selecao:
                df_serie = df_serie[df_serie["divisao"].isin(selecao)]
            chart_serie = (
                alt.Chart(df_serie)
                .mark_line(point=True)
                .encode(
                    x=alt.X("mes:T", title="Mês / Ano"),
                    y=alt.Y("movimentacoes:Q", title="Movimentações"),
                    color=alt.Color("divisao:N", title="Divisão"),
                    tooltip=["divisao:N", "mes:T", "movimentacoes:Q"],
                )
                .properties(height=320)
            )
            st.altair_chart(chart_serie, use_container_width=True)
            st.caption(
                "Série temporal simulada de movimentações de toxinas por divisão."
            )

            st.markdown("#### 🕵️ Cadeia de custódia (exemplo)")
            custodia = pd.DataFrame(
                [
                    {"lote": "TOX-0006/2026", "toxina": "Toxina Botulínica Tipo A",
                     "de": "Compartimento A-04", "para": "Laboratório Central",
                     "responsavel": "Diretor de Pesquisa", "data_hora": "2026-08-14 09:32"},
                    {"lote": "TOX-0001/2026", "toxina": "Ricina",
                     "de": "Compartimento A-01", "para": "Sala de Análises",
                     "responsavel": "Diretor de Toxicologia", "data_hora": "2026-08-15 14:05"},
                    {"lote": "TOX-0004/2026", "toxina": "Microcistina-LR",
                     "de": "Compartimento B-01", "para": "Incinerador controlado",
                     "responsavel": "Ministro do Meio Ambiente", "data_hora": "2026-09-02 10:12"},
                ]
            )
            st.dataframe(custodia, width="stretch")

        # ---------------- GOVERNANÇA ----------------
        st.divider()
        st.subheader("🏛️ Gestão e Auditoria do Cofre")
        st.caption("Painel executivo de governança, acessível pelo nível 3 (ministro).")
        if not usuario_tem_nivel(3):
            st.info(
                "🔒 **Bloqueado para o seu nível.** A governança exige nível 3."
            )
        else:
            conn = sqlite3.connect(DB_FILE)
            df_colabs = pd.read_sql_query(
                "SELECT id, nome, cargo, divisao, nivel_acesso, data_cadastro "
                "FROM colaboradores",
                conn,
            )
            df_logs_area = pd.read_sql_query("SELECT * FROM logs_acesso", conn)
            conn.close()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toxinas custodiadas", len(df_toxinas))
            c2.metric(
                "Unidades em estoque", int(df_toxinas["estoque_unidades"].sum())
            )
            c3.metric("Colaboradores cadastrados", len(df_colabs))
            c4.metric("Eventos de acesso registrados", len(df_logs_area))
            criticas = (df_toxinas["estado_conservacao"] == "Crítico").sum()
            if criticas:
                st.warning(
                    f"⚠️ {criticas} toxina(s) em estado de conservação **CRÍTICO** "
                    "exigem inspeção imediata."
                )
            else:
                st.success("✅ Todas as toxinas em estado de conservação estável.")

            if not df_colabs.empty:
                df_colabs["nivel"] = df_colabs["nivel_acesso"].map(rotulo_nivel)
                st.dataframe(
                    df_colabs[
                        ["id", "nome", "cargo", "divisao", "nivel", "data_cadastro"]
                    ],
                    width="stretch",
                )
            csv_full = df_toxinas.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Exportar Base do Cofre (CSV)",
                data=csv_full,
                file_name="dados_cofre_toxinas.csv",
                mime="text/csv",
            )

    ao_trocar_aba_guard(_aba_dados_geo, "Cofre de Toxinas (Dados)")
