import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Criação da pasta de trabalho e abas
wb = openpyxl.Workbook()
ws_dash = wb.active
ws_dash.title = "Dashboard & Métricas"
ws_logs = wb.create_sheet(title="Logs de Acesso")
ws_users = wb.create_sheet(title="Cadastro Colaboradores")

# Estilos e Cores (Paleta Corporativa)
PRIMARY_DARK = "1E293B"
HEADER_BG = "0F172A"
CARD_BG = "F8FAFC"
SUCCESS_BG = "DCFCE7"
SUCCESS_FG = "166534"
DANGER_BG = "FEE2E2"
DANGER_FG = "991B1B"
BORDER_COLOR = "CBD5E1"

font_family = "Segoe UI"

font_title = Font(name=font_family, size=16, bold=True, color="FFFFFF")
font_header = Font(name=font_family, size=11, bold=True, color="FFFFFF")
font_bold = Font(name=font_family, size=11, bold=True)
font_regular = Font(name=font_family, size=10)

fill_header = PatternFill(
    start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid"
)
fill_card = PatternFill(
    start_color=CARD_BG, end_color=CARD_BG, fill_type="solid"
)
fill_success = PatternFill(
    start_color=SUCCESS_BG, end_color=SUCCESS_BG, fill_type="solid"
)
font_success = Font(name=font_family, size=10, bold=True, color=SUCCESS_FG)
fill_danger = PatternFill(
    start_color=DANGER_BG, end_color=DANGER_BG, fill_type="solid"
)
font_danger = Font(name=font_family, size=10, bold=True, color=DANGER_FG)

thin_border = Border(
    left=Side(style="thin", color=BORDER_COLOR),
    right=Side(style="thin", color=BORDER_COLOR),
    top=Side(style="thin", color=BORDER_COLOR),
    bottom=Side(style="thin", color=BORDER_COLOR),
)

# -------------------------------------------------------------
# ABA 1: Dashboard & Métricas
# -------------------------------------------------------------
ws_dash.views.sheetView[0].showGridLines = True

# Banner Principal
ws_dash.merge_cells("A1:G2")
banner_cell = ws_dash["A1"]
banner_cell.value = (
    "  SISTEMA DE CONTROLE DE ACESSO AO COFRE DE TOXINAS - MINISTÉRIO DO MEIO AMBIENTE - AUDITORIA"
)
banner_cell.font = font_title
banner_cell.fill = PatternFill(
    start_color=PRIMARY_DARK, end_color=PRIMARY_DARK, fill_type="solid"
)
banner_cell.alignment = Alignment(vertical="center", horizontal="left")

# Cards de KPIs
kpis = [
    (
        "A4:B5",
        "TOTAL DE ACESSOS",
        "=COUNTA('Logs de Acesso'!A2:A100)",
        "Total registrado",
    ),
    (
        "C4:D5",
        "ACESSOS PERMITIDOS",
        '=COUNTIF(\'Logs de Acesso\'!D2:D100, "PERMITIDO")',
        "Acessos autorizados",
    ),
    (
        "E4:F5",
        "TENTATIVAS NEGADAS",
        '=COUNTIF(\'Logs de Acesso\'!D2:D100, "NEGADO")',
        "Alertas de segurança",
    ),
]

for range_str, title, formula, sub in kpis:
    ws_dash.merge_cells(range_str)
    top_left = range_str.split(":")[0]
    cell = ws_dash[top_left]
    cell.value = f"{title}\n\n{formula}"
    cell.font = font_bold
    cell.alignment = Alignment(
        wrap_text=True, horizontal="center", vertical="center"
    )
    cell.fill = fill_card

    start_col, start_row = range_str.split(":")[0][0], int(
        range_str.split(":")[0][1]
    )
    end_col, end_row = range_str.split(":")[1][0], int(
        range_str.split(":")[1][1]
    )
    for r in range(start_row, end_row + 1):
        for c in range(ord(start_col) - 64, ord(end_col) - 64 + 1):
            ws_dash.cell(row=r, column=c).border = thin_border

# Tabela Resumo
ws_dash["A7"] = "Resumo de Acessos por Compartimento do Cofre (Nível)"
ws_dash["A7"].font = Font(
    name=font_family, size=13, bold=True, color=PRIMARY_DARK
)

headers_summary = ["Compartimento (Nível)", "Acessos Permitidos", "Acessos Negados", "% Sucesso"]
for col_num, h in enumerate(headers_summary, 1):
    c = ws_dash.cell(row=8, column=col_num)
    c.value = h
    c.font = font_header
    c.fill = fill_header
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.border = thin_border

setores = [
    "Nível 1 – Permissão Geral",
    "Nível 2 – Diretor de Divisões Específicas",
    "Nível 3 – Ministro do Meio Ambiente",
]
for idx, setor in enumerate(setores, start=9):
    ws_dash.cell(row=idx, column=1, value=setor).font = font_regular
    ws_dash.cell(
        row=idx,
        column=2,
        value=f'=COUNTIFS(\'Logs de Acesso\'!C:C, A{idx}, \'Logs de Acesso\'!D:D, "PERMITIDO")',
    ).font = font_regular
    ws_dash.cell(
        row=idx,
        column=3,
        value=f'=COUNTIFS(\'Logs de Acesso\'!C:C, A{idx}, \'Logs de Acesso\'!D:D, "NEGADO")',
    ).font = font_regular

    p_cell = ws_dash.cell(
        row=idx,
        column=4,
        value=f"=IF((B{idx}+C{idx})>0, B{idx}/(B{idx}+C{idx}), 0)",
    )
    p_cell.font = font_regular
    p_cell.number_format = "0.0%"

    for col_num in range(1, 5):
        c = ws_dash.cell(row=idx, column=col_num)
        c.border = thin_border
        if col_num > 1:
            c.alignment = Alignment(horizontal="center")

# -------------------------------------------------------------
# ABA 2: Logs de Acesso
# -------------------------------------------------------------
ws_logs.views.sheetView[0].showGridLines = True

headers_logs = [
    "ID Log",
    "Data / Hora",
    "Compartimento Solicitado",
    "Status",
    "Colaborador Detectado",
    "Nível Biométrico (Match)",
]
for col_num, h in enumerate(headers_logs, 1):
    c = ws_logs.cell(row=1, column=col_num)
    c.value = h
    c.font = font_header
    c.fill = fill_header
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.border = thin_border

sample_logs = [
    (
        1001,
        "2026-08-27 08:14:22",
        "Nível 1 – Permissão Geral",
        "PERMITIDO",
        "Carlos Eduardo Silva",
        "98.4%",
    ),
    (
        1002,
        "2026-08-27 08:30:10",
        "Nível 2 – Diretor de Divisões Específicas",
        "PERMITIDO",
        "Ana Beatriz Souza",
        "96.1%",
    ),
    (
        1003,
        "2026-08-27 09:02:45",
        "Nível 3 – Ministro do Meio Ambiente",
        "NEGADO",
        "Carlos Eduardo Silva",
        "97.8%",
    ),
    (
        1004,
        "2026-08-27 09:15:00",
        "Nível 2 – Diretor de Divisões Específicas",
        "PERMITIDO",
        "Mariana Oliveira",
        "99.1%",
    ),
    (
        1005,
        "2026-08-27 10:22:18",
        "Nível 3 – Ministro do Meio Ambiente",
        "PERMITIDO",
        "Lucas Mendes",
        "94.5%",
    ),
    (
        1006,
        "2026-08-27 11:05:33",
        "Nível 1 – Permissão Geral",
        "NEGADO",
        "Desconhecido / Visitante",
        "42.0%",
    ),
]

for row_idx, row_data in enumerate(sample_logs, start=2):
    for col_idx, val in enumerate(row_data, start=1):
        c = ws_logs.cell(row=row_idx, column=col_idx, value=val)
        c.font = font_regular
        c.border = thin_border
        c.alignment = Alignment(horizontal="center")

        if col_idx == 4:
            if val == "PERMITIDO":
                c.fill = fill_success
                c.font = font_success
            else:
                c.fill = fill_danger
                c.font = font_danger

# -------------------------------------------------------------
# ABA 3: Cadastro Colaboradores
# -------------------------------------------------------------
ws_users.views.sheetView[0].showGridLines = True

headers_users = [
    "ID",
    "Nome Completo",
    "Cargo / Função",
    "Divisão",
    "Nível de Acesso",
    "Status Cadastro",
    "Data Cadastramento",
]
for col_num, h in enumerate(headers_users, 1):
    c = ws_users.cell(row=1, column=col_num)
    c.value = h
    c.font = font_header
    c.fill = fill_header
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.border = thin_border

sample_users = [
    (
        1,
        "Carlos Eduardo Silva",
        "Analista de Segurança",
        "Divisão de Toxicologia Ambiental",
        "Nível 1 – Permissão Geral",
        "Ativo",
        "2026-01-15",
    ),
    (
        2,
        "Ana Beatriz Souza",
        "Diretora",
        "Divisão de Emergências Químicas",
        "Nível 2 – Diretor de Divisões Específicas",
        "Ativo",
        "2026-02-01",
    ),
    (
        3,
        "Mariana Oliveira",
        "Ministra do Meio Ambiente",
        "Gabinete do Ministro",
        "Nível 3 – Ministro do Meio Ambiente",
        "Ativo",
        "2026-01-10",
    ),
    (
        4,
        "Lucas Mendes",
        "Diretor",
        "Divisão de Fiscalização e Segurança Química",
        "Nível 2 – Diretor de Divisões Específicas",
        "Ativo",
        "2026-03-20",
    ),
]

for row_idx, row_data in enumerate(sample_users, start=2):
    for col_idx, val in enumerate(row_data, start=1):
        c = ws_users.cell(row=row_idx, column=col_idx, value=val)
        c.font = font_regular
        c.border = thin_border
        if col_idx in [1, 5, 6]:
            c.alignment = Alignment(horizontal="center")

# Ajuste automático das colunas
for ws in [ws_dash, ws_logs, ws_users]:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.coordinate in [
                "A1",
                "B1",
                "C1",
                "D1",
                "E1",
                "F1",
                "G1",
                "A2",
                "B2",
                "C2",
                "D2",
                "E2",
                "F2",
                "G2",
            ]:
                continue
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

# Salvar planilha
file_name = "Relatorio_Controle_Acesso_Facial.xlsx"
wb.save(file_name)
print(f"Planilha '{file_name}' gerada com sucesso!")