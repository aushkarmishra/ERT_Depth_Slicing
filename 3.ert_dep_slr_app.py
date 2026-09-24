import io
import re
import zipfile
import pandas as pd
import streamlit as st

# Streamlit Page Setup
st.set_page_config(
    page_title="ERT Data Depth Slicer",
    page_icon="🌍",
    layout="wide"
)

st.title("⚡ ERT Survey Data Depth Slicer")
st.markdown("Upload multiple ERT Excel files to extract and combine resistivity values at specific depth slices across all profiles.")

# --- Helper Functions ---

def normalize_depth_str(val_str):
    """Normalizes string inputs like '0m', '0.5m', '1', '1.5m' to a uniform '0m', '0.5m' key format."""
    cleaned = str(val_str).strip().lower().replace('m', '')
    try:
        val = float(cleaned)
        return f"{int(val)}m" if val.is_integer() else f"{val}m"
    except ValueError:
        return None

def detect_column(columns, target_keywords):
    """Finds first column matching any keyword in target_keywords list."""
    for col in columns:
        col_str = str(col).strip().lower()
        if any(kw in col_str for kw in target_keywords):
            return col
    return None

def process_ert_files(uploaded_files, target_depths_list):
    """Processes uploaded files and compiles DataFrames for each depth key."""
    # Standardize target depth keys
    depth_keys = [normalize_depth_str(d) for d in target_depths_list if normalize_depth_str(d)]
    
    # Store lists of DataFrames for each depth
    compiled_data = {key: [] for key in depth_keys}
    processing_logs = []

    for uploaded_file in uploaded_files:
        try:
            # Read first sheet of Excel
            df = pd.read_excel(uploaded_file, sheet_name=0)
            
            # Detect standard columns
            name_col = detect_column(df.columns, ['profile', 'name'])
            lat_col = detect_column(df.columns, ['lat', 'lattitude'])
            lon_col = detect_column(df.columns, ['lon', 'long'])
            
            # Fallbacks if detection fails
            if not name_col:
                name_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
            if not lat_col or not lon_col:
                processing_logs.append(f"⚠️ Skipped '{uploaded_file.name}': Missing Latitude or Longitude column.")
                continue

            # Map available depth columns in this file
            file_depth_map = {}
            for col in df.columns:
                norm_key = normalize_depth_str(col)
                if norm_key:
                    file_depth_map[norm_key] = col

            # Extract data for requested depth keys
            for d_key in depth_keys:
                if d_key in file_depth_map:
                    res_col = file_depth_map[d_key]
                    
                    sub_df = df[[name_col, lon_col, lat_col, res_col]].copy()
                    sub_df.columns = ['Name', 'Longitude', 'Latitude', 'Resistivity']
                    
                    # Convert resistivity to numeric and remove NaNs
                    sub_df['Resistivity'] = pd.to_numeric(sub_df['Resistivity'], errors='coerce')
                    sub_df = sub_df.dropna(subset=['Resistivity'])
                    
                    if not sub_df.empty:
                        compiled_data[d_key].append(sub_df)
                        
        except Exception as e:
            processing_logs.append(f"❌ Error processing '{uploaded_file.name}': {str(e)}")

    # Combine into final DataFrames
    final_dfs = {}
    for d_key, df_list in compiled_data.items():
        if df_list:
            final_dfs[d_key] = pd.concat(df_list, ignore_index=True)
        else:
            final_dfs[d_key] = pd.DataFrame(columns=['Name', 'Longitude', 'Latitude', 'Resistivity'])

    return final_dfs, processing_logs

# --- Sidebar Input Controls ---

st.sidebar.header("⚙️ Splicing Options")

# File Uploader
uploaded_files = st.sidebar.file_uploader(
    "Upload ERT Excel Files (up to 100 files)", 
    type=["xlsx", "xls"], 
    accept_multiple_files=True
)

# Default Depth Input List
default_depths = "0m, 1m, 2m, 3m, 4m, 5m, 6m, 7m, 8m, 10m, 12m, 14m, 16m, 18m, 20m"
depth_input = st.sidebar.text_area(
    "Depth Values for Splicing (comma-separated):",
    value=default_depths,
    height=120
)

# --- Main Logic & Execution ---

if uploaded_files:
    # Parse depths
    depth_list = [d.strip() for d in depth_input.split(',') if d.strip()]
    
    st.info(f"📂 **Uploaded Files:** {len(uploaded_files)} files | **Target Depth Slices:** {len(depth_list)}")
    
    if st.button("🚀 Process ERT Data", type="primary"):
        with st.spinner("Processing ERT profiles..."):
            final_results, logs = process_ert_files(uploaded_files, depth_list)
            
            st.session_state['processed'] = True
            st.session_state['results'] = final_results
            st.session_state['logs'] = logs

if st.session_state.get('processed'):
    final_results = st.session_state['results']
    logs = st.session_state['logs']
    
    if logs:
        with st.expander("⚠️ View Processing Logs/Warnings"):
            for log in logs:
                st.write(log)
                
    st.success("✅ ERT Data Splicing Complete!")
    
    # --- Data Summary Table ---
    summary_data = []
    for depth, df in final_results.items():
        summary_data.append({
            "Depth Slice": depth,
            "Total Points": len(df),
            "Unique Profiles": df['Name'].nunique() if not df.empty else 0,
            "Min Resistivity": round(df['Resistivity'].min(), 2) if not df.empty else None,
            "Max Resistivity": round(df['Resistivity'].max(), 2) if not df.empty else None,
        })
    
    summary_df = pd.DataFrame(summary_data)
    st.subheader("📊 Extraction Summary")
    st.dataframe(summary_df, use_container_width=True)

    # --- ZIP Download Section ---
    st.subheader("💾 Download Extracted Files")
    
    # Create ZIP buffer in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for depth, df in final_results.items():
            if not df.empty:
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name=depth)
                excel_buffer.seek(0)
                zip_file.writestr(f"ERT_Resistivity_{depth}.xlsx", excel_buffer.getvalue())

    zip_buffer.seek(0)
    
    st.download_button(
        label="📦 Download All Sheets as ZIP Archive",
        data=zip_buffer,
        file_name="ERT_Resistivity_Depth_Slices.zip",
        mime="application/zip",
        type="primary"
    )

    # --- Individual Depth Preview & Download ---
    st.markdown("---")
    st.subheader("🔍 Preview Individual Depth Layer")
    
    selected_depth = st.selectbox("Select Depth to Preview:", list(final_results.keys()))
    preview_df = final_results[selected_depth]
    
    st.markdown(f"**Data Preview for `{selected_depth}` slice ({len(preview_df)} points):**")
    st.dataframe(preview_df.head(20), use_container_width=True)

    # Individual Download Button
    excel_single = io.BytesIO()
    with pd.ExcelWriter(excel_single, engine='openpyxl') as writer:
        preview_df.to_excel(writer, index=False, sheet_name=selected_depth)
    excel_single.seek(0)

    st.download_button(
        label=f"📥 Download {selected_depth} Excel File",
        data=excel_single,
        file_name=f"Resistivity_{selected_depth}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("👈 Upload your ERT `.xlsx` files in the sidebar and click **Process ERT Data** to begin.")