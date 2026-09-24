"""
ERT Data Processor - Offline Streamlit Web App
================================================
Processes electrode location data and subsurface resistivity/conductivity/IP
data from Excel files. Runs fully offline on localhost.

Launch with:
    streamlit run app.py
(or double-click run_app.bat on Windows)
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
FONT_NAME = "Arial"
ALL_PARAMS = ["Resistivity", "Conductivity", "IP"]

st.set_page_config(page_title="ERT Data Processor", layout="wide")

# ==========================================================================
# Core data-processing functions
# (kept independent of Streamlit so they're easy to test / reuse)
# ==========================================================================

def find_header_row(raw_df, required_any_of, max_scan=10):
    """Scan the first few rows of a headerless dataframe for the row that
    contains every column name in `required_any_of` (case-insensitive)."""
    for i in range(min(max_scan, len(raw_df))):
        row_vals = {str(v).strip().lower() for v in raw_df.iloc[i].tolist() if pd.notna(v)}
        if required_any_of.issubset(row_vals):
            return i
    raise ValueError(
        f"Could not find a header row containing all of {required_any_of} "
        f"in the first {max_scan} rows."
    )


def load_electrode_location(file):
    """
    Reads an Electrode Location workbook.
    Expected columns (case-insensitive, any order): id, Name, distance, angle,
    Distance_m, Latitude, Longitude. 'id' (or any column that is entirely
    blank) is dropped automatically since it carries no information.
    Returns a DataFrame with the columns found, in their original order.
    """
    raw = pd.read_excel(file, sheet_name=0, header=None)
    hdr_row = find_header_row(raw, {"name", "distance", "angle", "distance_m", "latitude", "longitude"})
    header = [str(v).strip() if pd.notna(v) else None for v in raw.iloc[hdr_row]]
    df = raw.iloc[hdr_row + 1:].reset_index(drop=True)
    df.columns = header
    df = df.loc[:, [c for c in df.columns if c is not None]]
    df = df.dropna(axis=1, how="all")  # drop entirely-empty columns (e.g. unused 'id')
    df = df.dropna(axis=0, how="all").reset_index(drop=True)
    return df


def reverse_lat_long(df):
    """Reverses Latitude/Longitude top-to-bottom, leaving every other column
    (id, Name, distance, angle, Distance_m, ...) in its original row order."""
    df2 = df.copy()
    if "Latitude" in df2.columns:
        df2["Latitude"] = df2["Latitude"].values[::-1]
    if "Longitude" in df2.columns:
        df2["Longitude"] = df2["Longitude"].values[::-1]
    return df2


def load_resistivity_long(file):
    """
    Reads a Subsurface Data workbook in long format:
    X, Depth, Resistivity, Conductivity, [IP - optional].
    Returns (dataframe, available_params) where available_params is whichever
    of Resistivity/Conductivity/IP were actually found in the file.
    """
    raw = pd.read_excel(file, sheet_name=0, header=None)
    hdr_row = find_header_row(raw, {"x", "depth", "resistivity", "conductivity"})
    header = [str(v).strip() if pd.notna(v) else None for v in raw.iloc[hdr_row]]
    df = raw.iloc[hdr_row + 1:].reset_index(drop=True)
    df.columns = header

    available_params = [p for p in ALL_PARAMS if p in df.columns]
    keep_cols = ["X", "Depth"] + available_params
    df = df.loc[:, [c for c in keep_cols if c in df.columns]]
    df = df.dropna(subset=["X", "Depth"]).reset_index(drop=True)

    for c in ["X", "Depth"] + available_params:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df, available_params


def depth_label(depth_value):
    """Formats a depth value for the column header, e.g. -0.375 -> '0.375m'.
    No rounding is applied - the label reflects the exact Depth value found
    in the input file. Pre-round the Depth column yourself if you want clean
    labels like '0m', '1m', '2m'."""
    v = abs(depth_value)
    if float(v).is_integer():
        return f"{int(v)}m"
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return f"{s}m"


def build_resistivity_wide(df, params):
    """
    Pivots long-format resistivity data into wide format.
    Returns:
        header_row_1: depth labels, one per param-block (e.g. [None, '0m', None, '1m', None, ...])
        header_row_2: ['Ground Distance', param1, param2, ..., param1, param2, ...]
        data_rows: one row per electrode (X), sorted ascending
        depths: sorted list of unique depth values used (shallow -> deep)
    """
    electrodes = sorted(df["X"].unique())
    depths = sorted(df["Depth"].unique(), reverse=True)  # shallow (near 0) first, deep last

    lookup = {}
    for _, row in df.iterrows():
        lookup[(row["X"], row["Depth"])] = {p: row[p] for p in params}

    header_row_1 = [None]
    header_row_2 = ["Ground Distance"]
    for d in depths:
        header_row_1.append(depth_label(d))
        header_row_1.extend([None] * (len(params) - 1))
        header_row_2.extend(params)

    data_rows = []
    for x in electrodes:
        row = [x]
        for d in depths:
            vals = lookup.get((x, d))
            for p in params:
                row.append(vals[p] if vals else None)
        data_rows.append(row)

    return header_row_1, header_row_2, data_rows, depths, electrodes


def build_combined_rows(elec_header, elec_data_rows, resistivity_block_rows):
    """
    Horizontally combines the electrode table and the resistivity wide block.
    The resistivity block (which itself starts with its 2 header rows) is
    pasted starting one row below the electrode header row. Since the
    resistivity block has 2 header rows of its own, this naturally lines up
    real resistivity data with the 3rd electrode row - matching the
    convention used in this project's reference files.
    """
    n_cols_elec = len(elec_header)
    n_cols_res = len(resistivity_block_rows[0]) if resistivity_block_rows else 0

    combined = [list(elec_header) + [None] * n_cols_res]

    max_len = max(len(elec_data_rows), len(resistivity_block_rows))
    for i in range(max_len):
        e_row = list(elec_data_rows[i]) if i < len(elec_data_rows) else [None] * n_cols_elec
        r_row = list(resistivity_block_rows[i]) if i < len(resistivity_block_rows) else [None] * n_cols_res
        combined.append(e_row + r_row)

    return combined


# ==========================================================================
# Excel writing helpers
# ==========================================================================

def rows_to_excel_bytes(rows, sheet_name="Sheet1", bold_row_indices=None, center_row_indices=None):
    """Writes a list-of-lists to an in-memory .xlsx file and returns the bytes."""
    bold_row_indices = bold_row_indices or set()
    center_row_indices = center_row_indices or set()

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    bold_font = Font(name=FONT_NAME, bold=True)
    normal_font = Font(name=FONT_NAME)
    center = Alignment(horizontal="center")

    max_cols = max((len(r) for r in rows), default=0)

    for r_idx, row in enumerate(rows):
        font = bold_font if r_idx in bold_row_indices else normal_font
        for c_idx, val in enumerate(row):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            cell = ws.cell(row=r_idx + 1, column=c_idx + 1, value=val)
            cell.font = font
            if r_idx in center_row_indices:
                cell.alignment = center

    for c in range(1, max_cols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def rows_to_preview_df(rows, n_header_rows):
    """Flattens the given number of header rows into single readable column
    names, for display purposes only (st.dataframe needs one header row)."""
    if not rows:
        return pd.DataFrame()

    header_rows = rows[:n_header_rows]
    data_rows = rows[n_header_rows:]

    n_cols = max(len(r) for r in rows)
    col_names = []
    for c in range(n_cols):
        parts = []
        for hr in header_rows:
            val = hr[c] if c < len(hr) else None
            if val is not None and str(val).strip() != "":
                parts.append(str(val))
        col_names.append(" / ".join(parts) if parts else f"col{c+1}")

    # de-duplicate column names for st.dataframe
    seen = {}
    final_names = []
    for name in col_names:
        seen[name] = seen.get(name, 0) + 1
        final_names.append(name if seen[name] == 1 else f"{name}_{seen[name]}")

    padded = [list(r) + [None] * (n_cols - len(r)) for r in data_rows]
    return pd.DataFrame(padded, columns=final_names)


# ==========================================================================
# Streamlit UI
# ==========================================================================

st.title("ERT Data Processor")
st.caption("Electrode location + resistivity/conductivity/IP reshaping — fully offline")

col1, col2 = st.columns(2)
with col1:
    electrode_file = st.file_uploader("Upload Electrode Location file (.xlsx)", type=["xlsx"])
with col2:
    resistivity_file = st.file_uploader("Upload Resistivity Value file (.xlsx)", type=["xlsx"])

reverse_latlong = st.checkbox("Reverse Latitude and Longitude order?", value=False)

selected_params = None
available_params = ALL_PARAMS
if resistivity_file is not None:
    try:
        _, available_params = load_resistivity_long(resistivity_file)
    except Exception as e:
        st.error(f"Could not read the Resistivity Value file: {e}")
        available_params = []

if available_params:
    selected_params = st.multiselect(
        "Parameters to retain",
        options=available_params,
        default=available_params,
    )
else:
    st.warning("Upload a valid Resistivity Value file to choose parameters.")

process_clicked = st.button("Process", type="primary", disabled=not (electrode_file and resistivity_file and selected_params))

if process_clicked:
    try:
        # ---- Step 1: Electrode location ----
        elec_df = load_electrode_location(electrode_file)
        if reverse_latlong:
            elec_df = reverse_lat_long(elec_df)
        elec_header = list(elec_df.columns)
        elec_data_rows = elec_df.values.tolist()
        elec_rows_full = [elec_header] + elec_data_rows

        # ---- Step 2: Resistivity reshaping ----
        res_df, _ = load_resistivity_long(resistivity_file)
        h1, h2, data_rows, depths, electrodes = build_resistivity_wide(res_df, selected_params)
        resistivity_block = [h1, h2] + data_rows

        # ---- Step 3: Merge & alignment ----
        combined_rows = build_combined_rows(elec_header, elec_data_rows, resistivity_block)

        st.session_state["elec_rows_full"] = elec_rows_full
        st.session_state["resistivity_block"] = resistivity_block
        st.session_state["combined_rows"] = combined_rows
        st.success(
            f"Processed {len(electrodes)} electrode(s) with data, "
            f"{len(depths)} depth level(s), {len(selected_params)} parameter(s)."
        )
    except Exception as e:
        st.error(f"Processing failed: {e}")

# ==========================================================================
# Previews + downloads
# ==========================================================================

if "combined_rows" in st.session_state:
    st.subheader("1. Corrected / Reordered Electrode Location")
    st.dataframe(rows_to_preview_df(st.session_state["elec_rows_full"], n_header_rows=1))
    st.download_button(
        "Download Corrected_Electrode_Location.xlsx",
        data=rows_to_excel_bytes(st.session_state["elec_rows_full"], sheet_name="Electrode_Location", bold_row_indices={0}),
        file_name="Corrected_Electrode_Location.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.subheader("2. Reshaped Subsurface Parameter Data")
    st.dataframe(rows_to_preview_df(st.session_state["resistivity_block"], n_header_rows=2))
    st.download_button(
        "Download Filtered_Resistivity_Data.xlsx",
        data=rows_to_excel_bytes(st.session_state["resistivity_block"], sheet_name="Resistivity_Data", bold_row_indices={0, 1}, center_row_indices={0, 1}),
        file_name="Filtered_Resistivity_Data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.subheader("3. Final Combined Profile")
    st.dataframe(rows_to_preview_df(st.session_state["combined_rows"], n_header_rows=3))
    st.download_button(
        "Download Final_Combined_Profile.xlsx",
        data=rows_to_excel_bytes(st.session_state["combined_rows"], sheet_name="profile_1", bold_row_indices={0, 1, 2}, center_row_indices={0, 1, 2}),
        file_name="Final_Combined_Profile.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Upload both files, choose your options, and click **Process** to see previews and download links.")
