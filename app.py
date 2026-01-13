"""
VIC Emergency Warnings Dashboard
"""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta

from src.warnings_client import WarningsClient
from src.geocoder import PostcodeGeocoder
from src.history_tracker import HistoryTracker
from src.download_log import DownloadLog

# Page config
st.set_page_config(
    page_title="VIC Emergency Warnings",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-refresh every 5 minutes
st_autorefresh(interval=300000, limit=None, key="data_refresh")

# Singletons
_geocoder = None
_history = None
_download_log = None


def get_geocoder():
    global _geocoder
    if _geocoder is None:
        _geocoder = PostcodeGeocoder()
    return _geocoder


def get_history():
    global _history
    if _history is None:
        _history = HistoryTracker()
    return _history


def get_download_log():
    global _download_log
    if _download_log is None:
        _download_log = DownloadLog()
    return _download_log


# Constants
STATUS_OPTIONS = ["Moderate", "Minor", "Unknown"]
WARNING_LEVELS = ["Emergency Warning", "Watch and Act", "Advice"]
CATEGORIES = ["Bushfire", "Flood", "Wind/Storm", "Earthquake", "Extreme Heat", "Health", "Other"]
CHANGE_TYPES = ["New Warning", "Escalated", "De-escalated", "Removed", "No Change"]

# Change type colors - readable
CHANGE_COLORS = {
    "New Warning": "#fff3cd",      # Yellow/amber background
    "Escalated": "#f8d7da",        # Light red
    "De-escalated": "#d4edda",     # Light green
    "Removed": "#cce5ff",          # Light blue
    "No Change": "#e2e3e5",        # Light gray
}

CHANGE_TEXT_COLORS = {
    "New Warning": "#856404",
    "Escalated": "#721c24",
    "De-escalated": "#155724",
    "Removed": "#004085",
    "No Change": "#383d41",
}


@st.cache_data(ttl=300)
def fetch_warnings():
    client = WarningsClient()
    warnings = client.fetch_warnings()
    client.close()
    return warnings


@st.cache_data(ttl=3600)
def resolve_postcode(suburb: str) -> str:
    geocoder = get_geocoder()
    postcode = geocoder.db.get_postcode_by_suburb(suburb.upper())
    return postcode if postcode else "Unknown"


def get_category(cat: str) -> str:
    mapping = {"Fire": "Bushfire", "Flood": "Flood", "Storm": "Wind/Storm", "Heat": "Extreme Heat", "Health": "Health"}
    for k, v in mapping.items():
        if k.lower() in cat.lower():
            return v
    return "Other"


def build_dataframe(warnings) -> pd.DataFrame:
    data = []
    for w in warnings:
        postcodes = set()
        for suburb in w.suburbs:
            pc = resolve_postcode(suburb)
            if pc != "Unknown":
                postcodes.add(pc)

        data.append({
            "ID": w.warning_id,
            "Warning Level": w.warning_level,
            "Status": w.status,
            "Category": get_category(w.category),
            "RawCategory": w.category,
            "Condition": w.condition,
            "Type": w.type,
            "Location": w.location,
            "Suburbs": w.suburbs,
            "Postcodes": list(postcodes),
            "PostcodesStr": ", ".join(sorted(postcodes)) if postcodes else "Unknown",
            "Update Time": w.last_updated,
        })
    return pd.DataFrame(data)


def expand_by_postcode(df: pd.DataFrame) -> pd.DataFrame:
    """Expand dataframe to one row per postcode"""
    rows = []
    for _, r in df.iterrows():
        for pc in r["Postcodes"]:
            if pc and pc != "Unknown":
                rows.append({
                    "Postcode": pc,
                    "Warning Level": r["Warning Level"],
                    "Status": r["Status"],
                    "Category": r["Category"],
                    "Condition": r["Condition"],
                    "Suburbs": ", ".join(r["Suburbs"][:5]) + ("..." if len(r["Suburbs"]) > 5 else ""),
                    "Location": r["Location"],
                    "Update Time": r["Update Time"],
                })
    return pd.DataFrame(rows)


def get_status_order(s): return {"Moderate": 1, "Minor": 2}.get(s, 3)
def get_level_order(l): return {"Emergency Warning": 1, "Watch and Act": 2, "Advice": 3}.get(l, 4)
def status_emoji(s): return {"Moderate": "🟠", "Minor": "🟡"}.get(s, "⚪")
def level_emoji(l): return {"Emergency Warning": "🔴", "Watch and Act": "🟠", "Advice": "🟡"}.get(l, "⚪")


def compare_with_uploaded(current_df: pd.DataFrame, uploaded_df: pd.DataFrame, end_time: datetime) -> pd.DataFrame:
    """Compare current warnings with an uploaded previous file"""
    # Current warnings expanded by postcode
    current_pc = expand_by_postcode(current_df)

    # Parse uploaded file - detect format
    # Could be: Warnings export, Postcodes export, or Comparison export
    prev_postcodes = {}

    if "Postcode" in uploaded_df.columns:
        # Postcodes or Comparison export format
        for _, row in uploaded_df.iterrows():
            pc = str(row.get("Postcode", "")).strip()
            if pc and pc != "Unknown":
                status = row.get("Status", row.get("Status (End)", "Unknown"))
                level = row.get("Warning Level", row.get("Level (End)", "Unknown"))
                suburbs = row.get("Suburbs", "")
                category = row.get("Category", "")
                if status != "None":  # Skip removed entries from comparison files
                    prev_postcodes[pc] = {
                        "Status": status,
                        "Warning Level": level,
                        "Suburbs": suburbs,
                        "Category": category,
                    }
    elif "PostcodesStr" in uploaded_df.columns:
        # Warnings export format - need to expand
        for _, row in uploaded_df.iterrows():
            postcodes_str = row.get("PostcodesStr", "")
            if postcodes_str and postcodes_str != "Unknown":
                for pc in postcodes_str.split(", "):
                    pc = pc.strip()
                    if pc:
                        prev_postcodes[pc] = {
                            "Status": row.get("Status", "Unknown"),
                            "Warning Level": row.get("Warning Level", "Unknown"),
                            "Suburbs": row.get("Location", "")[:50],
                            "Category": row.get("Category", ""),
                        }

    # Build current postcodes dict
    current_postcodes = {}
    if not current_pc.empty:
        for _, row in current_pc.iterrows():
            pc = row["Postcode"]
            current_postcodes[pc] = {
                "Status": row["Status"],
                "Warning Level": row["Warning Level"],
                "Suburbs": row["Suburbs"],
                "Category": row["Category"],
            }

    # Compare
    all_postcodes = set(prev_postcodes.keys()) | set(current_postcodes.keys())
    changes = []

    for pc in all_postcodes:
        prev = prev_postcodes.get(pc)
        curr = current_postcodes.get(pc)

        start_status = prev["Status"] if prev else None
        end_status = curr["Status"] if curr else None
        start_level = prev["Warning Level"] if prev else None
        end_level = curr["Warning Level"] if curr else None
        suburbs = curr["Suburbs"] if curr else (prev["Suburbs"] if prev else "")
        category = curr["Category"] if curr else (prev["Category"] if prev else "")

        # Determine change type
        if start_status is None and end_status is not None:
            change = "New Warning"
        elif start_status is not None and end_status is None:
            change = "Removed"
        elif start_status == end_status and start_level == end_level:
            change = "No Change"
        else:
            start_sev = get_status_order(start_status) + get_level_order(start_level) * 0.1
            end_sev = get_status_order(end_status) + get_level_order(end_level) * 0.1
            change = "Escalated" if end_sev < start_sev else "De-escalated"

        changes.append({
            "Postcode": pc,
            "Suburbs": suburbs,
            "Status (Start)": start_status or "None",
            "Status (End)": end_status or "None",
            "Level (Start)": start_level or "None",
            "Level (End)": end_level or "None",
            "Change": change,
            "Category": category,
        })

    return pd.DataFrame(changes).sort_values("Postcode")


def compare_times(df: pd.DataFrame, start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """Compare warnings between two times based on Update Time"""
    # Warnings active at start time (updated before start, or current)
    start_warnings = df[df["Update Time"] <= start_time].copy()
    end_warnings = df[df["Update Time"] <= end_time].copy()

    # Expand to postcodes
    start_pc = expand_by_postcode(start_warnings)
    end_pc = expand_by_postcode(end_warnings)

    if start_pc.empty:
        start_pc = pd.DataFrame(columns=["Postcode", "Status", "Warning Level", "Suburbs"])
    if end_pc.empty:
        end_pc = pd.DataFrame(columns=["Postcode", "Status", "Warning Level", "Suburbs"])

    # Get unique postcodes
    all_postcodes = set(start_pc["Postcode"].tolist() if not start_pc.empty else []) | \
                   set(end_pc["Postcode"].tolist() if not end_pc.empty else [])

    changes = []
    for pc in all_postcodes:
        start_row = start_pc[start_pc["Postcode"] == pc].head(1)
        end_row = end_pc[end_pc["Postcode"] == pc].head(1)

        start_status = start_row["Status"].values[0] if not start_row.empty else None
        end_status = end_row["Status"].values[0] if not end_row.empty else None
        start_level = start_row["Warning Level"].values[0] if not start_row.empty else None
        end_level = end_row["Warning Level"].values[0] if not end_row.empty else None
        suburbs = end_row["Suburbs"].values[0] if not end_row.empty else (start_row["Suburbs"].values[0] if not start_row.empty else "")

        # Determine change type
        if start_status is None and end_status is not None:
            change = "New Warning"
        elif start_status is not None and end_status is None:
            change = "Removed"
        elif start_status == end_status and start_level == end_level:
            change = "No Change"
        else:
            start_sev = get_status_order(start_status) + get_level_order(start_level) * 0.1
            end_sev = get_status_order(end_status) + get_level_order(end_level) * 0.1
            change = "Escalated" if end_sev < start_sev else "De-escalated"

        changes.append({
            "Postcode": pc,
            "Suburbs": suburbs,
            "Status (Start)": start_status or "None",
            "Status (End)": end_status or "None",
            "Level (Start)": start_level or "None",
            "Level (End)": end_level or "None",
            "Change": change,
            "Category": end_row["Category"].values[0] if not end_row.empty else (start_row["Category"].values[0] if not start_row.empty else ""),
        })

    return pd.DataFrame(changes).sort_values("Postcode")


def style_changes(df: pd.DataFrame) -> pd.DataFrame:
    """Apply styling to changes dataframe"""
    def row_style(row):
        change = row["Change"]
        bg = CHANGE_COLORS.get(change, "")
        color = CHANGE_TEXT_COLORS.get(change, "")
        return [f"background-color: {bg}; color: {color}"] * len(row)
    return df.style.apply(row_style, axis=1)


def create_map(df, geocoder):
    vic_map = folium.Map(location=[-37.0, 145.0], zoom_start=7, tiles="cartodbpositron")
    for _, row in df.iterrows():
        for suburb in row["Suburbs"][:10]:
            pc = resolve_postcode(suburb)
            if pc != "Unknown":
                coords = geocoder.db._postcode_coords.get(pc)
                if coords:
                    color = {"Moderate": "orange", "Minor": "yellow"}.get(row["Status"], "gray")
                    folium.CircleMarker(
                        location=list(coords),
                        radius=8, color=color, fill=True, fill_color=color, fill_opacity=0.7,
                        tooltip=f"{suburb} - {row['Warning Level']}",
                    ).add_to(vic_map)
    return vic_map


def main():
    st.title("🚨 VIC Emergency Warnings")

    with st.spinner("Fetching warnings..."):
        warnings = fetch_warnings()

    if not warnings:
        st.warning("No warnings found.")
        return

    df = build_dataframe(warnings)
    history = get_history()
    geocoder = get_geocoder()
    download_log = get_download_log()

    # Save snapshot
    if st.session_state.get("last_snap") != datetime.now().strftime("%Y%m%d_%H%M"):
        history.save_snapshot(df.to_dict("records"))
        st.session_state["last_snap"] = datetime.now().strftime("%Y%m%d_%H%M")

    # Stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Warnings", len(df))
    c2.metric("Moderate", len(df[df["Status"] == "Moderate"]))
    c3.metric("Minor", len(df[df["Status"] == "Minor"]))
    c4.metric("Watch and Act", len(df[df["Warning Level"] == "Watch and Act"]))

    # Tabs
    tabs = st.tabs(["📍 Map", "📋 Warnings", "🏘️ By Postcode", "🔄 Compare", "📥 Download Log", "📜 History"])

    # ===== TAB 1: MAP =====
    with tabs[0]:
        st.subheader("Warning Map")
        st_folium(create_map(df, geocoder), width=None, height=500, use_container_width=True)
        st.markdown("**Legend:** 🟠 Moderate | 🟡 Minor")

    # ===== TAB 2: ALL WARNINGS =====
    with tabs[1]:
        st.subheader("All Warnings")

        # Multi-select filters
        col1, col2, col3 = st.columns(3)
        with col1:
            sel_status = st.multiselect("Status", STATUS_OPTIONS, default=STATUS_OPTIONS, key="w_status")
        with col2:
            sel_level = st.multiselect("Warning Level", WARNING_LEVELS, default=WARNING_LEVELS, key="w_level")
        with col3:
            sel_cat = st.multiselect("Category", CATEGORIES, default=CATEGORIES, key="w_cat")

        filtered = df.copy()
        if sel_status:
            filtered = filtered[filtered["Status"].isin(sel_status)]
        if sel_level:
            filtered = filtered[filtered["Warning Level"].isin(sel_level)]
        if sel_cat:
            filtered = filtered[filtered["Category"].isin(sel_cat)]

        filtered = filtered.sort_values("Update Time", ascending=False)

        st.dataframe(
            filtered[["Warning Level", "Status", "Category", "Condition", "Location", "PostcodesStr", "Update Time"]],
            use_container_width=True, hide_index=True, height=400,
        )

        # Download with initials
        st.markdown("---")
        col_d1, col_d2 = st.columns([1, 3])
        with col_d1:
            initials = st.text_input("Your Initials", max_chars=5, key="w_initials")
        with col_d2:
            if st.button("📥 Download Warnings", key="dl_warnings"):
                if initials:
                    csv = filtered.to_csv(index=False)
                    download_log.add_entry(initials, "Warnings", f"Status: {sel_status}, Level: {sel_level}", len(filtered))
                    st.download_button("Click to Download", csv, f"warnings_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv", key="dl_w_btn")
                else:
                    st.warning("Please enter your initials")

    # ===== TAB 3: BY POSTCODE =====
    with tabs[2]:
        st.subheader("Warnings by Postcode")

        col1, col2 = st.columns(2)
        with col1:
            pc_status = st.multiselect("Status", STATUS_OPTIONS, default=STATUS_OPTIONS, key="pc_status")
        with col2:
            pc_cat = st.multiselect("Category", CATEGORIES, default=CATEGORIES, key="pc_cat")

        pc_df = expand_by_postcode(df)
        if not pc_df.empty:
            if pc_status:
                pc_df = pc_df[pc_df["Status"].isin(pc_status)]
            if pc_cat:
                pc_df = pc_df[pc_df["Category"].isin(pc_cat)]

            pc_df["StatusOrder"] = pc_df["Status"].apply(get_status_order)
            pc_df = pc_df.sort_values(["StatusOrder", "Postcode"]).drop_duplicates("Postcode", keep="first")

            st.markdown(f"**{len(pc_df)} postcodes with warnings**")

            # Download
            col_d1, col_d2 = st.columns([1, 3])
            with col_d1:
                init_pc = st.text_input("Initials", max_chars=5, key="pc_initials")
            with col_d2:
                if st.button("📥 Download Postcodes", key="dl_pc"):
                    if init_pc:
                        csv = pc_df.to_csv(index=False)
                        download_log.add_entry(init_pc, "Postcodes", f"Status: {pc_status}", len(pc_df))
                        st.download_button("Click to Download", csv, f"postcodes_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv", key="dl_pc_btn")
                    else:
                        st.warning("Please enter initials")

            # Display
            for _, row in pc_df.iterrows():
                with st.expander(f"{status_emoji(row['Status'])} **{row['Postcode']} - {row['Suburbs'][:30]}** | {row['Status']}"):
                    st.markdown(f"**Suburbs:** {row['Suburbs']}")
                    st.markdown(f"**Status:** {row['Status']} | **Level:** {row['Warning Level']}")
                    st.markdown(f"**Updated:** {row['Update Time'].strftime('%Y-%m-%d %H:%M')}")

    # ===== TAB 4: COMPARE =====
    with tabs[3]:
        st.subheader("Compare Changes")
        st.caption("Select ONE comparison mode below to compare warning changes")

        # Initialize session state for comparison mode
        if "cmp_mode" not in st.session_state:
            st.session_state.cmp_mode = None

        # Get download log times for quick selection
        log_entries = download_log.get_entries()
        log_times = [f"{e['timestamp'][:16]} ({e['initials']} - {e['report_type']})" for e in log_entries[:20]]

        # Three comparison modes in columns
        mode_col1, mode_col2, mode_col3 = st.columns(3)

        # ===== MODE 1: From Download Log =====
        with mode_col1:
            with st.container(border=True):
                st.markdown("### Option 1: From Download Log")
                st.caption("Compare from a previous download time")

                if log_times:
                    sel_log = st.selectbox("Select Download Time", ["-- Select --"] + log_times, key="cmp_log_sel")
                    if st.button("Use This Mode", key="btn_mode1", type="primary" if st.session_state.cmp_mode == "log" else "secondary"):
                        if sel_log != "-- Select --":
                            st.session_state.cmp_mode = "log"
                            st.session_state.cmp_log_time = sel_log
                            st.rerun()
                        else:
                            st.warning("Select a download time first")

                    if st.session_state.cmp_mode == "log":
                        st.success("SELECTED")
                else:
                    st.info("No download history yet")

        # ===== MODE 2: Manual Date/Time =====
        with mode_col2:
            with st.container(border=True):
                st.markdown("### Option 2: Manual Date/Time")
                st.caption("Pick a custom start date and time")

                manual_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=1), key="cmp_manual_date")
                manual_time = st.time_input("Start Time", value=datetime.now().replace(hour=9, minute=0).time(), key="cmp_manual_time")

                if st.button("Use This Mode", key="btn_mode2", type="primary" if st.session_state.cmp_mode == "manual" else "secondary"):
                    st.session_state.cmp_mode = "manual"
                    st.session_state.cmp_manual_dt = datetime.combine(manual_date, manual_time)
                    st.rerun()

                if st.session_state.cmp_mode == "manual":
                    st.success("SELECTED")

        # ===== MODE 3: Upload Previous File =====
        with mode_col3:
            with st.container(border=True):
                st.markdown("### Option 3: Upload Previous File")
                st.caption("Upload a previously downloaded report")

                uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="cmp_upload")

                if st.button("Use This Mode", key="btn_mode3", type="primary" if st.session_state.cmp_mode == "upload" else "secondary"):
                    if uploaded_file is not None:
                        st.session_state.cmp_mode = "upload"
                        st.session_state.cmp_uploaded_file = uploaded_file
                        st.rerun()
                    else:
                        st.warning("Upload a file first")

                if st.session_state.cmp_mode == "upload":
                    st.success("SELECTED")

        st.markdown("---")

        # Show current mode and end time
        if st.session_state.cmp_mode:
            mode_names = {"log": "Download Log", "manual": "Manual Date/Time", "upload": "Uploaded File"}
            st.info(f"**Active Mode:** {mode_names.get(st.session_state.cmp_mode, 'None')}")

            # End time (always now by default)
            st.markdown("**End Time (comparing to)**")
            ecol1, ecol2 = st.columns(2)
            with ecol1:
                end_date = st.date_input("End Date", value=datetime.now().date(), key="cmp_end_date")
            with ecol2:
                end_time = st.time_input("End Time", value=datetime.now().time(), key="cmp_end_time")
            end_dt = datetime.combine(end_date, end_time)

            st.markdown("---")

            # Filters for comparison results
            st.markdown("**Filter Results**")
            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                cmp_changes = st.multiselect("Change Type", CHANGE_TYPES, default=CHANGE_TYPES, key="cmp_changes")
            with fcol2:
                cmp_status = st.multiselect("Status (End)", STATUS_OPTIONS + ["None"], default=STATUS_OPTIONS + ["None"], key="cmp_status")
            with fcol3:
                cmp_cat = st.multiselect("Category", CATEGORIES + [""], default=CATEGORIES + [""], key="cmp_cat")

            # Run comparison button
            if st.button("🔄 Run Comparison", type="primary", use_container_width=True):
                changes_df = None

                # MODE 1: From download log
                if st.session_state.cmp_mode == "log":
                    log_time_str = st.session_state.get("cmp_log_time", "")
                    if log_time_str:
                        start_dt = datetime.fromisoformat(log_time_str.split(" (")[0])
                        changes_df = compare_times(df, start_dt, end_dt)
                        st.caption(f"Comparing: {start_dt.strftime('%Y-%m-%d %H:%M')} → {end_dt.strftime('%Y-%m-%d %H:%M')}")

                # MODE 2: Manual date/time
                elif st.session_state.cmp_mode == "manual":
                    start_dt = st.session_state.get("cmp_manual_dt", datetime.now() - timedelta(days=1))
                    changes_df = compare_times(df, start_dt, end_dt)
                    st.caption(f"Comparing: {start_dt.strftime('%Y-%m-%d %H:%M')} → {end_dt.strftime('%Y-%m-%d %H:%M')}")

                # MODE 3: Upload file
                elif st.session_state.cmp_mode == "upload":
                    uploaded = st.session_state.get("cmp_uploaded_file")
                    if uploaded:
                        try:
                            prev_df = pd.read_csv(uploaded)
                            changes_df = compare_with_uploaded(df, prev_df, end_dt)
                            st.caption(f"Comparing uploaded file → {end_dt.strftime('%Y-%m-%d %H:%M')}")
                        except Exception as e:
                            st.error(f"Error reading file: {e}")

                # Display results
                if changes_df is not None and not changes_df.empty:
                    # Apply filters
                    if cmp_changes:
                        changes_df = changes_df[changes_df["Change"].isin(cmp_changes)]
                    if cmp_status:
                        changes_df = changes_df[changes_df["Status (End)"].isin(cmp_status)]
                    if cmp_cat:
                        changes_df = changes_df[changes_df["Category"].isin(cmp_cat)]

                    st.markdown(f"**{len(changes_df)} postcodes**")

                    # Summary
                    summary = changes_df["Change"].value_counts().to_dict()
                    st.markdown(
                        f"🆕 New: {summary.get('New Warning', 0)} | "
                        f"⬆️ Escalated: {summary.get('Escalated', 0)} | "
                        f"⬇️ De-escalated: {summary.get('De-escalated', 0)} | "
                        f"❌ Removed: {summary.get('Removed', 0)} | "
                        f"➖ No Change: {summary.get('No Change', 0)}"
                    )

                    # Display styled table
                    st.dataframe(
                        style_changes(changes_df[["Postcode", "Suburbs", "Status (Start)", "Status (End)", "Level (Start)", "Level (End)", "Change", "Category"]]),
                        use_container_width=True, hide_index=True, height=400,
                    )

                    # Download comparison
                    st.markdown("---")
                    col_d1, col_d2 = st.columns([1, 3])
                    with col_d1:
                        cmp_init = st.text_input("Initials", max_chars=5, key="cmp_initials")
                    with col_d2:
                        if st.button("📥 Download Comparison", key="dl_cmp"):
                            if cmp_init:
                                csv = changes_df.to_csv(index=False)
                                download_log.add_entry(cmp_init, "Comparison", f"Mode: {st.session_state.cmp_mode}", len(changes_df))
                                st.download_button("Click to Download", csv, f"comparison_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv", key="dl_cmp_btn")
                            else:
                                st.warning("Please enter initials")
                elif changes_df is not None:
                    st.info("No changes found in this comparison.")

            # Reset button
            if st.button("🔄 Reset Mode Selection", key="reset_mode"):
                st.session_state.cmp_mode = None
                st.rerun()
        else:
            st.warning("Please select a comparison mode above to continue.")

    # ===== TAB 5: DOWNLOAD LOG =====
    with tabs[4]:
        st.subheader("Download Log")
        st.caption("History of report downloads")

        entries = download_log.get_entries()
        if entries:
            log_df = pd.DataFrame(entries)
            log_df["timestamp"] = pd.to_datetime(log_df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(
                log_df[["timestamp", "initials", "report_type", "filter_summary", "record_count"]],
                use_container_width=True, hide_index=True,
                column_config={
                    "timestamp": "Time",
                    "initials": "User",
                    "report_type": "Report",
                    "filter_summary": "Filters",
                    "record_count": "Records",
                }
            )
        else:
            st.info("No downloads recorded yet.")

    # ===== TAB 6: HISTORY =====
    with tabs[5]:
        st.subheader("Warning History")

        all_postcodes = sorted(set(pc for row in df["Postcodes"] for pc in row if pc != "Unknown"))
        sel_pc = st.selectbox("Select Postcode", [""] + all_postcodes, key="hist_pc")

        if sel_pc:
            pc_hist = history.get_postcode_history(sel_pc)
            if pc_hist:
                st.dataframe(pd.DataFrame(pc_hist), use_container_width=True, hide_index=True)
            else:
                st.info(f"No history for {sel_pc}")

        st.markdown("---")
        st.markdown("**Snapshots**")
        snaps = history.get_snapshots()
        if snaps:
            st.dataframe(pd.DataFrame(snaps), use_container_width=True, hide_index=True)

    # Footer
    st.markdown("---")
    st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Source: [VIC Emergency](https://emergency.vic.gov.au/public/textonly.html)")


if __name__ == "__main__":
    main()
