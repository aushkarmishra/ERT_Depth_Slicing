"""
ERT Depth-Slice Heatmap Generator
==================================
A Streamlit web application for processing Electrical Resistivity Tomography (ERT)
depth-slice CSV data and producing publication-quality spatial resistivity heatmaps,
GeoTIFF rasters (.tif), Vector Layers (.gpkg/.shp), and KML Ground Overlays (.kml/.kmz).

Author: Senior GIS Specialist / Geophysical Data Engineer

Run with:
    streamlit run app.py
"""

import io
import os
import zipfile
import tempfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize, BoundaryNorm
from scipy.interpolate import Rbf
from scipy.spatial import cKDTree
from pyproj import Transformer
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
import geopandas as gpd
from shapely.geometry import Polygon
import streamlit as st

# --------------------------------------------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="ERT Resistivity Heatmap Generator", layout="wide")
st.title("⚡ ERT Depth-Slice Resistivity Heatmap & GIS Export Generator")
st.caption(
    "Upload an ERT depth-slice CSV (Name, Longitude, Latitude, Resistivity) to generate "
    "a georeferenced resistivity heatmap with GeoTIFF (.tif), Vector (.gpkg/.shp), and KML export options."
)

# --------------------------------------------------------------------------------------
# SIDEBAR CONTROLS
# --------------------------------------------------------------------------------------
st.sidebar.header("1. Data Input")
uploaded_file = st.sidebar.file_uploader("Upload ERT CSV file", type=["csv"])

st.sidebar.header("2. Interpolation Settings")
buffer_preset_values = [0.5, 1, 1.5, 2, 3, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200]
buffer_choice = st.sidebar.selectbox(
    "Buffer Distance around electrodes (m)",
    options=[f"{v} m" for v in buffer_preset_values] + ["Custom..."],
    index=buffer_preset_values.index(40),
    help="Interpolated heatmap is fully opaque within this distance of the nearest electrode point."
)
if buffer_choice == "Custom...":
    buffer_distance = st.sidebar.number_input(
        "Custom buffer distance (m)", min_value=0.1, value=40.0, step=0.5
    )
else:
    buffer_distance = float(buffer_choice.replace(" m", ""))

fade_fraction = st.sidebar.slider(
    "Edge fade width (fraction of buffer)", min_value=0.1, max_value=2.0, value=0.6, step=0.1
)
grid_resolution = st.sidebar.slider(
    "Grid resolution (pixels per side)", min_value=200, max_value=1200, value=600, step=50
)
rbf_function = st.sidebar.selectbox(
    "RBF kernel", ["linear", "multiquadric", "gaussian", "inverse", "thin_plate", "cubic"],
    index=0
)
rbf_smooth = st.sidebar.slider("RBF smoothing factor", 0.0, 5.0, 0.0, 0.1)

st.sidebar.header("3. Visualization Settings")

classification_mode = st.sidebar.radio(
    "Resistivity scale type",
    ["Continuous (Log)", "Continuous (Linear)", "Manual Classes"],
    index=0
)
scale_mode = "Logarithmic" if classification_mode == "Continuous (Log)" else "Linear"

cmap_base_options = {
    "Jet": "jet",
    "Spectral": "Spectral",
    "RdYlBu": "RdYlBu",
    "RdYlGn": "RdYlGn",
    "Turbo": "turbo",
    "Viridis": "viridis",
    "Plasma": "plasma",
    "Coolwarm": "coolwarm",
    "Rainbow": "gist_rainbow",
    "Nipy Spectral": "nipy_spectral",
    "Terrain": "terrain",
    "Earth Tones": "gist_earth",
}
cmap_label = st.sidebar.selectbox("Colour ramp", list(cmap_base_options.keys()), index=0)
invert_cmap = st.sidebar.checkbox("Invert colour ramp", value=True)
cmap_base = cmap_base_options[cmap_label]
cmap_name = f"{cmap_base}_r" if invert_cmap else cmap_base

if classification_mode == "Manual Classes":
    default_breaks = "0,20,200,600,1200,3000,7000,30000"
    breaks_text = st.sidebar.text_input(
        "Class breakpoints (Ω·m, comma-separated)",
        value=default_breaks
    )
    try:
        class_breaks = sorted(float(v.strip()) for v in breaks_text.split(",") if v.strip() != "")
        if len(class_breaks) < 2:
            raise ValueError("Need at least 2 breakpoints to form one class.")
    except ValueError as e:
        st.sidebar.error(f"Invalid breakpoints: {e}")
        class_breaks = [0, 20, 200, 600, 1200, 3000, 7000, 30000]
    vmin, vmax = class_breaks[0], class_breaks[-1]
else:
    class_breaks = None
    vmin = st.sidebar.number_input("Color scale min (Ω·m)", value=0.0 if scale_mode == "Linear" else 1.0)
    vmax = st.sidebar.number_input("Color scale max (Ω·m)", value=30000.0)

show_points = st.sidebar.checkbox("Show electrode points", value=True)
show_lines = st.sidebar.checkbox("Show profile lines", value=True)
point_size = st.sidebar.slider("Electrode point size", 1, 30, 6)
white_background = st.sidebar.checkbox("White background (no basemap)", value=True)

st.sidebar.header("4. Export Settings")
dpi = st.sidebar.slider("Export DPI", min_value=100, max_value=1200, value=800, step=50)
export_format = st.sidebar.radio("Export format", ["PNG", "PDF"], index=0)

# --------------------------------------------------------------------------------------
# CORE PROCESSING & EXPORT FUNCTIONS
# --------------------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_and_reproject(file_bytes):
    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = [c.strip() for c in df.columns]
    required = {"Name", "Longitude", "Latitude", "Resistivity"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    df = df.dropna(subset=["Longitude", "Latitude", "Resistivity"]).copy()
    df["Resistivity"] = df["Resistivity"].astype(float)
    df = df[df["Resistivity"] > 0]

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)
    x, y = transformer.transform(df["Longitude"].values, df["Latitude"].values)
    df["X"], df["Y"] = x, y
    return df


def build_heatmap(df, buffer_distance, fade_fraction, grid_res, rbf_function, rbf_smooth):
    x, y, z = df["X"].values, df["Y"].values, df["Resistivity"].values
    pad = buffer_distance * 1.5
    xmin, xmax = x.min() - pad, x.max() + pad
    ymin, ymax = y.min() - pad, y.max() + pad

    span = max(xmax - xmin, ymax - ymin)
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    xmin, xmax = cx - span / 2.0, cx + span / 2.0
    ymin, ymax = cy - span / 2.0, cy + span / 2.0

    grid_x, grid_y = np.meshgrid(
        np.linspace(xmin, xmax, grid_res),
        np.linspace(ymin, ymax, grid_res),
    )

    rbf = Rbf(x, y, np.log10(z), function=rbf_function, smooth=rbf_smooth)

    flat_gx, flat_gy = grid_x.ravel(), grid_y.ravel()
    chunk = 20000
    out = np.empty_like(flat_gx)
    for i in range(0, len(flat_gx), chunk):
        out[i:i + chunk] = rbf(flat_gx[i:i + chunk], flat_gy[i:i + chunk])
    grid_log_z = out.reshape(grid_x.shape)
    grid_z = np.power(10, grid_log_z)

    tree = cKDTree(np.column_stack([x, y]))
    grid_points = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    dist, _ = tree.query(grid_points)
    dist = dist.reshape(grid_x.shape)

    fade_width = max(buffer_distance * fade_fraction, 1e-6)
    alpha = np.clip(1.0 - (dist - buffer_distance) / fade_width, 0.0, 1.0)

    return grid_x, grid_y, grid_z, alpha, dist, (xmin, xmax, ymin, ymax)


def render_figure(df, grid_x, grid_y, grid_z, alpha, extent, cmap_name, scale_mode,
                  vmin, vmax, show_points, show_lines, point_size, white_bg, class_breaks=None):
    fig, ax = plt.subplots(figsize=(10, 10))
    if white_bg:
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

    if class_breaks is not None:
        n_classes = len(class_breaks) - 1
        base_cmap = plt.get_cmap(cmap_name, n_classes)
        norm = BoundaryNorm(class_breaks, ncolors=n_classes)
        cmap_used = base_cmap
    else:
        norm = LogNorm(vmin=max(vmin, 0.1), vmax=vmax) if scale_mode == "Logarithmic" else Normalize(vmin=vmin, vmax=vmax)
        cmap_used = cmap_name

    im = ax.imshow(
        grid_z, extent=extent, origin="lower", cmap=cmap_used, norm=norm, alpha=alpha,
        interpolation="nearest" if class_breaks is not None else "bilinear", zorder=2
    )

    if show_lines:
        for name, grp in df.groupby("Name", sort=False):
            ax.plot(grp["X"], grp["Y"], color="black", linewidth=0.6, linestyle=":", alpha=0.7, zorder=3)

    if show_points:
        ax.scatter(df["X"], df["Y"], s=point_size, c="black", edgecolors="white", linewidths=0.3, zorder=4)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m) — UTM Zone 44N")
    ax.set_ylabel("Northing (m) — UTM Zone 44N")
    ax.set_title("ERT Resistivity Depth-Slice Heatmap")

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Resistivity (Ω·m)")
    if class_breaks is not None:
        cbar.set_ticks(class_breaks)
        cbar.set_ticklabels([f"{b:g}" for b in class_breaks])

    fig.tight_layout()
    return fig


def generate_geotiff(grid_z, dist, buffer_distance, extent):
    """Generates a georeferenced GeoTIFF raster in EPSG:32644 (UTM Zone 44N)."""
    masked_z = grid_z.copy()
    masked_z[dist > buffer_distance] = np.nan

    xmin, xmax, ymin, ymax = extent
    height, width = grid_z.shape
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)

    memfile = io.BytesIO()
    with rasterio.open(
        memfile,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=rasterio.float32,
        crs="EPSG:32644",
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(np.flipud(masked_z).astype(np.float32), 1)

    memfile.seek(0)
    return memfile.getvalue()


def generate_kmz(grid_z, dist, buffer_distance, extent, cmap_name, scale_mode, vmin, vmax, class_breaks=None):
    """Generates a Google Earth KMZ file with transparent RGBA Ground Overlay."""
    transformer = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True)
    west, south = transformer.transform(extent[0], extent[2])
    east, north = transformer.transform(extent[1], extent[3])

    if class_breaks is not None:
        n_classes = len(class_breaks) - 1
        cmap = plt.get_cmap(cmap_name, n_classes)
        norm = BoundaryNorm(class_breaks, ncolors=n_classes)
    else:
        cmap = plt.get_cmap(cmap_name)
        norm = LogNorm(vmin=max(vmin, 0.1), vmax=vmax) if scale_mode == "Logarithmic" else Normalize(vmin=vmin, vmax=vmax)

    rgba = cmap(norm(grid_z))

    fade_width = max(buffer_distance * 0.6, 1e-6)
    alpha_mask = np.clip(1.0 - (dist - buffer_distance) / fade_width, 0.0, 1.0)
    rgba[..., 3] = rgba[..., 3] * alpha_mask

    rgba_uint8 = (rgba * 255).astype(np.uint8)
    rgba_uint8 = np.flipud(rgba_uint8)

    img = Image.fromarray(rgba_uint8, mode="RGBA")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>ERT Resistivity Overlay</name>
    <GroundOverlay>
      <name>ERT Resistivity Heatmap</name>
      <Icon>
        <href>overlay.png</href>
      </Icon>
      <LatLonBox>
        <north>{north}</north>
        <south>{south}</south>
        <east>{east}</east>
        <west>{west}</west>
      </LatLonBox>
    </GroundOverlay>
  </Document>
</kml>"""

    kmz_buffer = io.BytesIO()
    with zipfile.ZipFile(kmz_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_content)
        zf.writestr("overlay.png", img_bytes.getvalue())

    kmz_buffer.seek(0)
    return kmz_buffer.getvalue()


def generate_qml_style(levels, cmap_name="jet_r"):
    """Generates a QGIS .qml style file for auto-coloring vector polygons."""
    try:
        cmap = plt.get_cmap(cmap_name)
    except ValueError:
        cmap = plt.get_cmap("jet_r")
    num_classes = len(levels) - 1
    
    ranges_xml, symbols_xml = [], []
    for i in range(num_classes):
        low, high = levels[i], levels[i+1]
        norm_val = i / max(num_classes - 1, 1)
        r, g, b, a = [int(255 * c) for c in cmap(norm_val)]
        
        ranges_xml.append(f'<range symbol="{i}" lower="{low}" upper="{high}" label="{low:g} - {high:g} Ωm"/>')
        symbols_xml.append(f'''
      <symbol alpha="1" type="fill" name="{i}">
        <layer class="SimpleFill" enabled="1" pass="0">
          <prop k="color" v="{r},{g},{b},{a}"/>
          <prop k="outline_color" v="0,0,0,255"/>
          <prop k="outline_style" v="solid"/>
          <prop k="outline_width" v="0.1"/>
        </layer>
      </symbol>''')

    return f'''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <renderer-v2 type="graduatedSymbol" attr="Resistivity" symbollevels="0" grad_method="GraduatedColor">
    <ranges>{"".join(ranges_xml)}</ranges>
    <symbols>{"".join(symbols_xml)}</symbols>
  </renderer-v2>
</qgis>'''


def generate_sld_style(levels, cmap_name="jet_r"):
    """Generates an OGC .sld style file compatible with ArcGIS Pro and QGIS."""
    try:
        cmap = plt.get_cmap(cmap_name)
    except ValueError:
        cmap = plt.get_cmap("jet_r")
    num_classes = len(levels) - 1
    
    rules_xml = []
    for i in range(num_classes):
        low, high = levels[i], levels[i+1]
        norm_val = i / max(num_classes - 1, 1)
        r, g, b, _ = [int(255 * c) for c in cmap(norm_val)]
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        
        rules_xml.append(f'''
        <se:Rule>
          <se:Name>{low:g} - {high:g} Ωm</se:Name>
          <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
            <ogc:And>
              <ogc:PropertyIsGreaterThanOrEqualTo>
                <ogc:PropertyName>Resistivity</ogc:PropertyName>
                <ogc:Literal>{low}</ogc:Literal>
              </ogc:PropertyIsGreaterThanOrEqualTo>
              <ogc:PropertyIsLessThan>
                <ogc:PropertyName>Resistivity</ogc:PropertyName>
                <ogc:Literal>{high}</ogc:Literal>
              </ogc:PropertyIsLessThan>
            </ogc:And>
          </ogc:Filter>
          <se:PolygonSymbolizer>
            <se:Fill><se:SvgParameter name="fill">{hex_color}</se:SvgParameter></se:Fill>
            <se:Stroke>
              <se:SvgParameter name="stroke">#000000</se:SvgParameter>
              <se:SvgParameter name="stroke-width">0.2</se:SvgParameter>
            </se:Stroke>
          </se:PolygonSymbolizer>
        </se:Rule>''')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.1.0" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:se="http://www.opengis.net/se" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <se:Name>ERT_Resistivity_Vector</se:Name>
    <UserStyle>
      <se:Name>ERT_Resistivity_Vector</se:Name>
      <se:FeatureTypeStyle>{"".join(rules_xml)}</se:FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>'''


def generate_vectors(grid_x, grid_y, grid_z, dist, buffer_distance, cmap_name, class_breaks=None, num_levels=15):
    """Generates vector contours and bundles .gpkg, .shp, .qml (QGIS), and .sld (ArcGIS Pro) files into a ZIP."""
    fig, ax = plt.subplots()
    if class_breaks is not None:
        contour_set = ax.contourf(grid_x, grid_y, grid_z, levels=class_breaks)
        levels_used = class_breaks
    else:
        levels_used = np.logspace(np.log10(max(grid_z.min(), 0.1)), np.log10(grid_z.max()), num_levels)
        contour_set = ax.contourf(grid_x, grid_y, grid_z, levels=levels_used)
    plt.close(fig)

    polygons, resistivity_vals = [], []

    if hasattr(contour_set, "collections") and len(contour_set.collections) > 0:
        for i, collection in enumerate(contour_set.collections):
            level_value = contour_set.levels[i]
            for path in collection.get_paths():
                for poly_coords in path.to_polygons():
                    if len(poly_coords) >= 3:
                        poly = Polygon(poly_coords)
                        if poly.is_valid and not poly.is_empty:
                            polygons.append(poly)
                            resistivity_vals.append(level_value)
    else:
        paths = contour_set.get_paths()
        levels = contour_set.levels
        for i, path in enumerate(paths):
            level_value = levels[i] if i < len(levels) else levels[-1]
            for poly_coords in path.to_polygons():
                if len(poly_coords) >= 3:
                    poly = Polygon(poly_coords)
                    if poly.is_valid and not poly.is_empty:
                        polygons.append(poly)
                        resistivity_vals.append(level_value)

    if not polygons:
        return None

    gdf = gpd.GeoDataFrame({"Resistivity": resistivity_vals, "geometry": polygons}, crs="EPSG:32644")

    mask_fig, mask_ax = plt.subplots()
    mask_contour = mask_ax.contourf(grid_x, grid_y, dist, levels=[0, buffer_distance])
    plt.close(mask_fig)

    mask_paths = mask_contour.collections[0].get_paths() if hasattr(mask_contour, "collections") and len(mask_contour.collections) > 0 else mask_contour.get_paths()
    mask_polys = [Polygon(p) for path in mask_paths for p in path.to_polygons() if len(p) >= 3 and Polygon(p).is_valid]
    if mask_polys:
        gdf = gpd.clip(gdf, gpd.GeoDataFrame({"geometry": mask_polys}, crs="EPSG:32644"))

    qml_content = generate_qml_style(levels_used, cmap_name)
    sld_content = generate_sld_style(levels_used, cmap_name)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg_path = os.path.join(tmpdir, "ERT_Resistivity_Vector.gpkg")
            gdf.to_file(gpkg_path, driver="GPKG")
            zf.write(gpkg_path, "ERT_Resistivity_Vector.gpkg")

            shp_path = os.path.join(tmpdir, "ERT_Resistivity_Vector.shp")
            gdf.to_file(shp_path, driver="ESRI Shapefile")
            for ext in [".shp", ".shx", ".dbf", ".prj"]:
                f_path = os.path.join(tmpdir, "ERT_Resistivity_Vector" + ext)
                if os.path.exists(f_path):
                    zf.write(f_path, "ERT_Resistivity_Vector" + ext)

            zf.writestr("ERT_Resistivity_Vector.qml", qml_content)
            zf.writestr("ERT_Resistivity_Vector.sld", sld_content)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# --------------------------------------------------------------------------------------
# MAIN APP LOGIC
# --------------------------------------------------------------------------------------
if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.getvalue()
        df = load_and_reproject(file_bytes)
        st.success(f"Loaded {len(df)} electrode points across {df['Name'].nunique()} profiles.")

        with st.spinner("Interpolating resistivity surface..."):
            grid_x, grid_y, grid_z, alpha, dist, extent = build_heatmap(
                df, buffer_distance, fade_fraction, grid_resolution, rbf_function, rbf_smooth
            )

        fig = render_figure(
            df, grid_x, grid_y, grid_z, alpha, extent, cmap_name, scale_mode,
            vmin, vmax, show_points, show_lines, point_size, white_background,
            class_breaks=class_breaks
        )

        st.pyplot(fig, use_container_width=True)

        st.subheader("📥 Export Options")
        col1, col2, col3 = st.columns(3)

        buf = io.BytesIO()
        fmt = "png" if export_format == "PNG" else "pdf"
        fig.savefig(buf, format=fmt, dpi=dpi, facecolor="white", bbox_inches="tight")
        buf.seek(0)

        with col1:
            st.download_button(
                label=f"🖼️ Download Plot ({export_format})",
                data=buf,
                file_name=f"ERT_Resistivity_Heatmap_{dpi}dpi.{fmt}",
                mime="image/png" if fmt == "png" else "application/pdf",
                use_container_width=True
            )

        geotiff_data = generate_geotiff(grid_z, dist, buffer_distance, extent)
        with col2:
            st.download_button(
                label="🗺️ Download GeoTIFF (.tif)",
                data=geotiff_data,
                file_name="ERT_Resistivity_Raster.tif",
                mime="image/tiff",
                use_container_width=True
            )

        kmz_data = generate_kmz(grid_z, dist, buffer_distance, extent, cmap_name, scale_mode, vmin, vmax, class_breaks)
        with col3:
            st.download_button(
                label="🌐 Download Google Earth (.kmz)",
                data=kmz_data,
                file_name="ERT_Resistivity_Overlay.kmz",
                mime="application/vnd.google-earth.kmz",
                use_container_width=True
            )

        st.write("---")
        st.markdown("### 📐 Vector Exports with QGIS & ArcGIS Pro Design Files")
        
        with st.spinner("Generating vector contours & style files..."):
            vector_zip_bytes = generate_vectors(
                grid_x, grid_y, grid_z, dist, buffer_distance, cmap_name, class_breaks=class_breaks
            )

        if vector_zip_bytes:
            st.download_button(
                label="📦 Download Vector Package with Styles (.zip)",
                data=vector_zip_bytes,
                file_name="ERT_Resistivity_Vector_Package.zip",
                mime="application/zip",
                use_container_width=True,
                help="Contains .gpkg, .shp, .qml (QGIS style), and .sld (ArcGIS Pro style) files."
            )

        with st.expander("Preview data table"):
            st.dataframe(df[["Name", "Longitude", "Latitude", "Resistivity", "X", "Y"]])

    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("👈 Upload a CSV file with columns: Name, Longitude, Latitude, Resistivity to begin.")