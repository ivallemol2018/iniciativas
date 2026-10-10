import re
import unicodedata
import pandas as pd
from pathlib import Path

from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.utils import get_column_letter


# ===============================================
# CONFIGURATION
# ===============================================
OUTPUT_EXCEL_FILE = "iniciativas_apis.xlsx"
PRODUCTIVO_FILE = ".github/workflows/data/reporte_api_productivo.xlsx"
SSB_CR_BQ_FILE = ".github/workflows/data/reporte_ssb_cr_bq_interno.xlsx"

FINAL_COLUMNS = [
    "API",
    "Metodo",
    "Endpoint"
]


# ===============================================
# UTILITY FUNCTIONS
# ===============================================
def normalize_text(value) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def normalize_endpoint(value) -> str:
    text = normalize_text(value)
    # Reemplaza cualquier path parameter (ej. {id}, {clienteId}) por un comodin generico
    text = re.sub(r"\{[^}]*\}", "{}", text)
    return text


def load_productive_apis(path: str) -> pd.DataFrame:
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"No se encontro el reporte productivo: {path}")

    df = pd.read_excel(file)

    missing = [c for c in FINAL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en '{path}': {missing}")

    df = df[FINAL_COLUMNS].dropna(subset=["API"])
    for col in FINAL_COLUMNS:
        df[col] = df[col].astype(str).str.strip()

    return df.drop_duplicates().reset_index(drop=True)


def load_ssb_cr_bq_df(path: str):
    file = Path(path)
    if not file.exists():
        return pd.DataFrame(columns=["ssb", "tipo", "cr/bqs"])

    return pd.read_excel(file)


def find_ssb_cr_bq_match(api_value, metodo_value, endpoint_value, ssb_df):
    norm_api = normalize_text(api_value)
    norm_metodo = normalize_text(metodo_value)
    norm_endpoint = normalize_endpoint(endpoint_value)

    for _, row in ssb_df.iterrows():
        row_api = normalize_text(row.get("Api"))
        if not row_api or row_api != norm_api:
            continue

        if normalize_text(row.get("Metodo")) != norm_metodo:
            continue

        if normalize_endpoint(row.get("endpoint")) != norm_endpoint:
            continue

        return row.get("ssb"), row.get("tipo"), row.get("cr/bqs"), row.get("origen")

    return None, None, None, None


def style_worksheet(ws, dataframe: pd.DataFrame):
    """Aplica el mismo estilo (header azul, bordes, autofiltro, ancho de
    columna) usado para la hoja 'APIs' a cualquier hoja generada a partir de
    un DataFrame."""
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")

    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r in range(2, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(row=r, column=c).border = border
            ws.cell(row=r, column=c).alignment = Alignment(vertical="center")

    for idx, col_name in enumerate(dataframe.columns, start=1):
        col_letter = get_column_letter(idx)
        max_len = max(
            len(col_name),
            dataframe[col_name].fillna("").astype(str).map(len).max()
        )
        ws.column_dimensions[col_letter].width = min(max_len + 4, 80)


def build_ssb_cr_bq_consolidado(ssb_cr_bq_df: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Consolida reporte_ssb_cr_bq_interno por (ssb, cr/bqs): 'Esperado' es el
    conteo de filas registradas en ese reporte, 'Real' es el conteo de filas
    del reporte productivo que efectivamente cruzaron con esa combinacion."""
    esperado_df = (
        ssb_cr_bq_df.dropna(subset=["ssb", "cr/bqs"])
        .groupby(["ssb", "cr/bqs"])
        .size()
        .reset_index(name="Esperado")
    )

    real_df = (
        df.dropna(subset=["SBB", "Nombre CR/BQ"])
        .groupby(["SBB", "Nombre CR/BQ"])
        .size()
        .reset_index(name="Real")
        .rename(columns={"SBB": "ssb", "Nombre CR/BQ": "cr/bqs"})
    )

    consolidado_df = esperado_df.merge(real_df, on=["ssb", "cr/bqs"], how="left")
    consolidado_df["Real"] = consolidado_df["Real"].fillna(0).astype(int)
    consolidado_df = consolidado_df.sort_values(["ssb", "cr/bqs"]).reset_index(drop=True)

    return consolidado_df


# ===============================================
# MAIN PROCESS
# ===============================================
df = load_productive_apis(PRODUCTIVO_FILE)

ssb_cr_bq_df = load_ssb_cr_bq_df(SSB_CR_BQ_FILE)
ssb_matches = df.apply(
    lambda row: find_ssb_cr_bq_match(row["API"], row["Metodo"], row["Endpoint"], ssb_cr_bq_df),
    axis=1
)
df["SBB"] = ssb_matches.apply(lambda m: m[0])
df["Tipo CR"] = ssb_matches.apply(lambda m: m[1])
df["Nombre CR/BQ"] = ssb_matches.apply(lambda m: m[2])
df["Origen"] = ssb_matches.apply(lambda m: m[3])

ssb_cr_bq_consolidado_df = build_ssb_cr_bq_consolidado(ssb_cr_bq_df, df)


# ===============================================
# EXPORT TO EXCEL (EXECUTE STYLE)
# ===============================================
with pd.ExcelWriter(OUTPUT_EXCEL_FILE, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="APIs")
    style_worksheet(writer.book["APIs"], df)

    ssb_cr_bq_consolidado_df.to_excel(writer, index=False, sheet_name="SSB CR-BQ")
    style_worksheet(writer.book["SSB CR-BQ"], ssb_cr_bq_consolidado_df)

print(f"Excel generado exitosamente: {OUTPUT_EXCEL_FILE}")
