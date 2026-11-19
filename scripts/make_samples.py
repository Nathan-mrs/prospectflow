"""Gera as planilhas de exemplo em ``samples/`` (com sujeira proposital).

Uso::

    python -m scripts.make_samples

A planilha simula uma coleta manual no Google Maps e inclui casos que a
importação precisa tratar: telefones em vários formatos, nomes em CAIXA ALTA,
cidades com "- SP", notas com vírgula, duplicatas e linhas inválidas.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

COLUMNS = [
    "Nome", "Categoria", "Telefone", "Nota", "Nº de avaliações", "Site",
    "Instagram", "Endereço", "Bairro", "Cidade", "Link Maps", "Observações",
]

# fmt: off
ROWS: list[list[str]] = [
    # --- Barbearias
    ["BARBEARIA NAVALHA DE OURO", "Barbearia", "(11) 98765-4321", "4,9", "312", "", "@navalhadeouro", "Rua Augusta, 1200", "Consolação", "São Paulo - SP", "https://maps.app.goo.gl/nav01", ""],
    ["Barber King", "Barbearia", "11 91234-5678", "4.7", "201", "instagram.com/barberking", "barberking", "Av. Paulista, 900", "Bela Vista", "São Paulo", "https://maps.app.goo.gl/bk02", "Dono se chama Rafael"],
    ["barbearia do zé", "Barbearia", "+55 11 97654-3210", "4,6", "87", "Não", "", "", "Tatuapé", "SÃO PAULO", "", ""],
    ["Studio Barber Vintage", "", "98877-6655", "4,8", "1.034", "", "@vintagebarber", "", "Centro", "Guarulhos/SP", "", "Telefone veio sem DDD"],
    # --- Salões de Beleza
    ["Espaço Bella", "Salão de beleza", "(11) 99654-1122", "4,8", "156", "", "@espacobella", "", "Moema", "São Paulo", "", ""],
    ["ESMALTERIA DIVAS", "Manicure e pedicure", "11 3456-7890", "4,5", "64", "ruim", "", "", "Santana", "São Paulo - SP", "", "Fixo — confirmar WhatsApp"],
    ["Instituto de Beleza Aurora", "Cabeleireiro", "(11) 98123-4567", "5,0", "29", "www.institutoaurora.com.br", "", "", "Centro", "Osasco (SP)", "", ""],
    ["Salão Charme", "Salão de beleza", "(11) 97000-1111", "4,4", "45", "", "", "", "Vila Galvão", "Guarulhos", "", ""],
    # --- Pet Shops
    ["Pet Shop Amigo Fiel", "Pet shop", "(11) 99888-7766", "4,9", "540", "", "@amigofielpet", "", "Lapa", "São Paulo", "https://maps.app.goo.gl/pet01", ""],
    ["Banho e Tosa Patinhas", "Banho e tosa", "11987001122", "4,7", "98", "linktr.ee/patinhas", "", "", "Centro", "Santo André - SP", "", ""],
    ["CLÍNICA VETERINÁRIA AU AU", "Clínica veterinária", "(11) 3222-1100", "4,3", "211", "Sim", "", "", "Vila Assunção", "Santo André", "", ""],
    ["Casa do Bichinho", "", "(11) 96655-4433", "4,6", "73", "", "@casadobichinho", "", "Pinheiros", "São Paulo", "", "Sem categoria — nicho pelo nome? não tem palavra-chave"],
    # --- Oficinas Mecânicas
    ["Auto Center São Jorge", "Oficina mecânica", "(11) 95544-3322", "4,6", "389", "", "", "", "Km 18", "Osasco", "", ""],
    ["Mecânica Turbo", "Oficina mecânica", "11 94433-2211", "4,2", "51", "Não tem", "", "", "Macedo", "Guarulhos - SP", "", ""],
    ["Funilaria Pit Stop", "Funilaria", "(11) 8765-4321", "4,5", "120", "", "", "", "Jardim", "Santo André", "", "Celular antigo sem o 9"],
    ["Borracharia Rota", "Borracharia", "(11) 93322-1100", "4,1", "33", "", "", "", "Centro", "São Paulo", "", ""],
    # --- Restaurantes
    ["Pizzaria Bella Napoli", "Pizzaria", "(11) 99111-2233", "4,8", "2.310", "facebook.com/bellanapoli", "@bellanapoli", "", "Mooca", "São Paulo", "", ""],
    ["Marmitaria Sabor Caseiro", "Restaurante", "11 98222-3344", "4,6", "143", "", "", "", "Centro", "Osasco", "", ""],
    ["HAMBURGUERIA BRASA", "Hamburgueria", "(11) 97333-4455", "4,7", "876", "Desatualizado", "@brasaburger", "", "Vila Mariana", "São Paulo - SP", "", ""],
    ["Açaí Ponto Certo", "Açaí", "(11) 96444-5566", "4,9", "65", "", "", "", "Bonsucesso", "Guarulhos", "", ""],
    # --- Clínicas de Estética
    ["Clínica Renova", "Clínica de estética", "(11) 95555-6677", "4,9", "188", "", "@clinicarenova", "", "Itaim Bibi", "São Paulo", "", ""],
    ["Espaço Pele de Seda", "Depilação", "(11) 94666-7788", "4,7", "92", "", "", "", "Centro", "Santo André", "", ""],
    ["Studio Sobrancelhas Lumière", "Design de sobrancelhas", "11 93777-8899", "4,8", "301", "", "@lumiere.studio", "", "Presidente Altino", "Osasco - SP", "", ""],
    # --- Academias
    ["Academia Força Total", "Academia", "(11) 92888-9900", "4,5", "640", "", "@forcatotal", "", "Tatuapé", "São Paulo", "", ""],
    ["CrossFit Iron", "Box de CrossFit", "(11) 91999-0011", "4,9", "158", "Sim, mas ruim", "", "", "Centro", "Guarulhos", "", ""],
    ["Studio Pilates Movimento", "Pilates", "(11) 99000-1122", "5,0", "47", "", "@pilatesmovimento", "", "Jardim Bussocaba", "Osasco", "", ""],
    # --- Duplicatas propositais
    ["Barber King", "Barbearia", "(11) 91234-5678", "4,7", "201", "", "", "", "Bela Vista", "São Paulo", "", "Duplicata: mesmo telefone em outro formato"],
    ["PIZZARIA BELLA NAPOLI", "Pizzaria", "", "4,8", "2310", "", "", "", "Mooca", "são paulo", "", "Duplicata: mesmo nome e cidade"],
    # --- Linhas com erro
    ["", "Barbearia", "(11) 98000-0000", "4,5", "10", "", "", "", "Centro", "São Paulo", "", "Erro: sem nome"],
    ["Lanchonete do Tio", "Lanchonete", "1234", "4,0", "15", "", "", "", "Centro", "Osasco", "", "Erro: telefone inválido"],
    ["Academia Atitude", "Academia", "(00) 99999-9999", "4,4", "80", "", "", "", "Centro", "Guarulhos", "", "Erro: DDD inválido"],
]
# fmt: on


def build_dataframe() -> pd.DataFrame:
    """DataFrame da planilha de exemplo."""
    return pd.DataFrame(ROWS, columns=COLUMNS)


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    df = build_dataframe()
    xlsx_path = SAMPLES_DIR / "leads_exemplo.xlsx"
    csv_path = SAMPLES_DIR / "leads_exemplo.csv"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")
        sheet = writer.sheets["Leads"]
        for column_cells in sheet.columns:
            width = max(len(str(c.value or "")) for c in column_cells) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(width, 45)
    # CSV no padrão do Excel brasileiro: ponto e vírgula + UTF-8 com BOM
    df.to_csv(csv_path, index=False, sep=";", encoding="utf-8-sig")
    print(f"Gerado: {xlsx_path}\nGerado: {csv_path}\nLinhas: {len(df)}")


if __name__ == "__main__":
    main()
