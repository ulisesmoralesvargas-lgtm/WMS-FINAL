import os
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import qrcode
from PIL import Image
from assistant_service import ask_inventory_assistant

API_URL = os.environ.get("API_URL", "").rstrip("/")

st.set_page_config(
    page_title="Inventory Management System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }

        .sub-header {
            color: #6b7280;
            font-size: 1rem;
            margin-bottom: 1.5rem;
        }

        .section-card {
            background-color: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 1rem 1.2rem;
            margin-bottom: 1rem;
        }

        .status-online {
            color: #15803d;
            font-weight: 700;
        }

        .status-warning {
            color: #b45309;
            font-weight: 700;
        }

        .small-muted {
            color: #6b7280;
            font-size: 0.9rem;
        }

        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e5e7eb;
            padding: 1rem;
            border-radius: 12px;
        }
        .status-badge {
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            font-weight: 600;
            display: inline-block;
            margin-top: 0.25rem;
        }

        .status-in-use {
            background-color: #dcfce7;
            color: #166534;
        }

        .status-checked-out {
            background-color: #fee2e2;
            color: #991b1b;
        }

        .status-storage {
            background-color: #dbeafe;
            color: #1e40af;
        }

        .status-repair {
            background-color: #fef3c7;
            color: #92400e;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# API helpers
# -----------------------------
def api_get(path: str):
    response = requests.get(f"{API_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict):
    response = requests.post(f"{API_URL}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()

def api_post(path: str, payload: dict):
    response = requests.post(
        f"{API_URL}{path}",
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


def generate_qr_code(data: str):
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=2
    )

    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer



def show_error(context: str, error: Exception):
    st.error(f"{context}: {error}")


def normalize_records(result):
    if isinstance(result, dict):
        return result.get("data", [])
    if isinstance(result, list):
        return result
    return []


def load_csv_assets():
    result = api_get("/assets/csv")
    return normalize_records(result)


def load_sql_assets():
    result = api_get("/assets")
    return normalize_records(result)


def load_dashboard_stats():
    return api_get("/dashboard/stats")


def load_maintenance_requests():
    return normalize_records(api_get("/maintenance"))


def load_transfers():
    return normalize_records(api_get("/transfers"))


def load_reports_summary():
    return api_get("/reports/summary")


def load_scan_compliance():
    return api_get("/reports/scan-compliance")


def load_audit_exceptions():
    return normalize_records(api_get("/reports/audit-exceptions"))

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.title("📦 Inventory System")
st.sidebar.caption("Cloud Run • FastAPI • Cloud SQL • Cloud Storage")

st.sidebar.divider()

st.sidebar.write("👤 Logged in as:")
st.sidebar.markdown("**ulises.mova10**")

st.sidebar.write("Environment:")
st.sidebar.markdown("**Demo / Development**")

st.sidebar.divider()

menu_options = [
    "Dashboard",
    "Gemini Assistant",
    "Reports",
    "Browse Assets CSV",
    "Asset Explorer",
    "Maintenance Tickets",
    "Transfer History",
    "Add Asset",
    "API Status",
]

default_menu_index = 0

if st.query_params.get("asset_id", None):
    default_menu_index = menu_options.index("Asset Explorer")

menu = st.sidebar.radio(
    "Navigation",
    menu_options,
    index=default_menu_index,
)

st.sidebar.divider()

if API_URL:
    st.sidebar.caption("Backend API")
    st.sidebar.code(API_URL)
else:
    st.sidebar.error("API_URL is not configured.")


if not API_URL:
    st.error("API_URL environment variable is missing. Update the Cloud Run frontend service with API_URL.")
    st.stop()


# -----------------------------
# Dashboard
# -----------------------------
if menu == "Dashboard":
    st.markdown('<div class="main-header">Inventory Management Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Central view for asset inventory across CSV source data and Cloud SQL transactional records.</div>',
        unsafe_allow_html=True,
    )

    api_status = "Unknown"

    try:
        health = api_get("/health")
        api_status = health.get("status", "online")
    except Exception:
        api_status = "offline"

    stats = {
        "total_assets": 0,
        "checked_out": 0,
        "available": 0,
        "total_scans": 0,
        "total_checkouts": 0,
    }

    try:
        stats = load_dashboard_stats()
    except Exception:
        pass

    try:
        sql_data = load_sql_assets()
    except Exception:
        sql_data = []

    reports = {
        "assets_by_location": [],
        "assets_by_department": [],
        "assets_by_status": [],
        "maintenance_count": 0,
        "transfer_count": 0,
    }

    try:
        reports = load_reports_summary()
    except Exception:
        pass

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("API Status", api_status)
    col2.metric("Total Assets", stats["total_assets"])
    col3.metric("Available", stats["available"])
    col4.metric("Checked Out", stats["checked_out"])
    col5.metric("Total Scans", stats["total_scans"])

    col6, col7, col8 = st.columns(3)

    col6.metric("Maintenance Tickets", reports.get("maintenance_count", 0))
    col7.metric("Transfers", reports.get("transfer_count", 0))
    col8.metric("Total Checkouts", stats.get("total_checkouts", 0))

    st.divider()

    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.subheader("Top Campuses")
        df_location = pd.DataFrame(reports.get("assets_by_location", []))
        if not df_location.empty:
            st.bar_chart(df_location.set_index("location"))

    with chart_right:
        st.subheader("Top Departments")
        df_department = pd.DataFrame(reports.get("assets_by_department", []))
        if not df_department.empty:
            st.bar_chart(df_department.set_index("department"))

    st.subheader("Asset Status Breakdown")
    df_status = pd.DataFrame(reports.get("assets_by_status", []))
    if not df_status.empty:
        st.dataframe(df_status, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Inventory Audit Compliance")

    scan_compliance = {
        "total_assets": 0,
        "scanned_assets": 0,
        "never_scanned": 0,
        "audit_coverage_percent": 0,
    }

    try:
        scan_compliance = load_scan_compliance()
    except Exception:
        pass

    audit_col1, audit_col2, audit_col3, audit_col4 = st.columns(4)

    audit_col1.metric("Total Assets", scan_compliance.get("total_assets", 0))
    audit_col2.metric("Scanned Assets", scan_compliance.get("scanned_assets", 0))
    audit_col3.metric("Never Scanned", scan_compliance.get("never_scanned", 0))
    audit_col4.metric(
        "Audit Coverage",
        f"{scan_compliance.get('audit_coverage_percent', 0)}%"
    )

    st.progress(
        min(
            float(scan_compliance.get("audit_coverage_percent", 0)) / 100,
            1.0,
        )
    )


    st.subheader("Assets Needing Audit")

    try:
        audit_data = load_audit_exceptions()
        audit_df = pd.DataFrame(audit_data)

        if not audit_df.empty:
            filter_col1, filter_col2, filter_col3 = st.columns(3)

            with filter_col1:
                campus_filter = st.selectbox(
                    "Campus",
                    ["All"] + sorted(audit_df["sede"].fillna("").unique().tolist())
                )

            with filter_col2:
                dept_filter = st.selectbox(
                    "Department",
                    ["All"] + sorted(audit_df["departamento"].fillna("").unique().tolist())
                )

            with filter_col3:
                status_filter = st.selectbox(
                    "Status",
                    ["All"] + sorted(audit_df["estatus"].fillna("").unique().tolist())
                )

            if campus_filter != "All":
                audit_df = audit_df[audit_df["sede"] == campus_filter]

            if dept_filter != "All":
                audit_df = audit_df[audit_df["departamento"] == dept_filter]

            if status_filter != "All":
                audit_df = audit_df[audit_df["estatus"] == status_filter]

        if audit_df.empty:
            st.success("No audit exceptions found.")
        else:
            st.caption("Showing up to 500 assets that have never been scanned.")
            st.dataframe(
                audit_df,
                use_container_width=True,
                hide_index=True,
            )

    except Exception as e:
        st.warning(f"Could not load audit exceptions: {e}")


    st.divider()

    left, right = st.columns([2, 1])

    with left:
        st.subheader("Recent SQL Assets")

        if sql_data:
            df = pd.DataFrame(sql_data)
            st.dataframe(df.tail(10), use_container_width=True, hide_index=True)
        else:
            st.info("No SQL records yet. Add an asset from the Add Asset page.")

    with right:
        st.subheader("Operational Summary")

        st.write(f"**Total Assets:** {stats['total_assets']}")
        st.write(f"**Available Assets:** {stats['available']}")
        st.write(f"**Checked Out Assets:** {stats['checked_out']}")
        st.write(f"**Total Checkouts:** {stats['total_checkouts']}")

        if api_status == "online":
            st.markdown('<p class="status-online">API is online</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="status-warning">API status needs review</p>', unsafe_allow_html=True)

    st.divider()

    st.subheader("Architecture")
    st.code(
        """
Browser
  ↓
Cloud Run: Streamlit Frontend
  ↓
Cloud Run: FastAPI Backend
  ↓
Cloud Storage CSV + Cloud SQL PostgreSQL
        """,
        language="text",
    )


# -----------------------------

# Gemini Assistant page
elif menu == "Gemini Assistant":
    st.markdown('<div class="main-header">✨ Gemini Inventory Assistant</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Ask questions about asset risk, audit issues, scan compliance, maintenance, transfers, campuses, and departments.</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "This assistant is read-only. It uses existing inventory reports and cannot modify assets, write SQL, or access database credentials."
    )

    if "assistant_messages" not in st.session_state:
        st.session_state.assistant_messages = [
            {
                "role": "assistant",
                "content": (
                    "Hi! Ask me things like: Which assets require the most attention? "
                    "Which campuses have the most risk? What should I prioritize this week?"
                ),
            }
        ]

    st.subheader("Suggested questions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Assets needing attention", use_container_width=True):
            st.session_state.pending_assistant_prompt = (
                "Which assets or areas require the most attention?"
            )

    with col2:
        if st.button("Campus risk", use_container_width=True):
            st.session_state.pending_assistant_prompt = (
                "Which campuses have the most risk or audit issues?"
            )

    with col3:
        if st.button("This week's priorities", use_container_width=True):
            st.session_state.pending_assistant_prompt = (
                "What should I prioritize this week based on the reports?"
            )

    col4, col5, col6 = st.columns(3)

    with col4:
        if st.button("Scan compliance", use_container_width=True):
            st.session_state.pending_assistant_prompt = (
                "What does the scan compliance data mean?"
            )

    with col5:
        if st.button("Department audit issues", use_container_width=True):
            st.session_state.pending_assistant_prompt = (
                "Which departments have the most audit issues?"
            )

    with col6:
        if st.button("Maintenance overview", use_container_width=True):
            st.session_state.pending_assistant_prompt = (
                "Summarize the current maintenance situation."
            )

    st.divider()

    for message in st.session_state.assistant_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    typed_prompt = st.chat_input("Ask the Gemini assistant...")

    pending_prompt = st.session_state.pop("pending_assistant_prompt", None)

    prompt = typed_prompt or pending_prompt

    if prompt:
        st.session_state.assistant_messages.append(
            {"role": "user", "content": prompt}
        )

        with st.chat_message("user"):
            st.markdown(prompt)

        history = st.session_state.assistant_messages[:-1]

        with st.chat_message("assistant"):
            with st.spinner("Reviewing inventory reports..."):
                answer = ask_inventory_assistant(prompt, history)

            st.markdown(answer)

        st.session_state.assistant_messages.append(
            {"role": "assistant", "content": answer}
        )

    if st.button("Clear assistant chat"):
        st.session_state.assistant_messages = [
            {
                "role": "assistant",
                "content": "Chat cleared. What would you like to review?",
            }
        ]
        st.rerun()


# Reports page
# -----------------------------
elif menu == "Reports":
    st.markdown('<div class="main-header">Reports & Analytics</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Inventory distribution and operational reporting.</div>',
        unsafe_allow_html=True,
    )

    try:
        reports = load_reports_summary()

        col1, col2 = st.columns(2)
        col1.metric("Maintenance Tickets", reports.get("maintenance_count", 0))
        col2.metric("Transfers", reports.get("transfer_count", 0))

        st.divider()

        left, right = st.columns(2)

        with left:
            st.subheader("Assets by Campus")
            df_location = pd.DataFrame(reports.get("assets_by_location", []))
            if not df_location.empty:
                st.bar_chart(df_location.set_index("location"))

            st.subheader("Assets by Status")
            df_status = pd.DataFrame(reports.get("assets_by_status", []))
            if not df_status.empty:
                st.dataframe(df_status, use_container_width=True, hide_index=True)

        with right:
            st.subheader("Assets by Department")
            df_department = pd.DataFrame(reports.get("assets_by_department", []))
            if not df_department.empty:
                st.bar_chart(df_department.set_index("department"))

            st.subheader("Raw Report Data")
            st.json(reports)

    except Exception as e:
        show_error("Could not load reports", e)


# -----------------------------
# CSV page
# -----------------------------
elif menu == "Browse Assets CSV":
    st.markdown('<div class="main-header">Assets from Cloud Storage CSV</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Read-only inventory source loaded from the CSV file in Cloud Storage.</div>',
        unsafe_allow_html=True,
    )

    try:
        data = load_csv_assets()
        df = pd.DataFrame(data)

        col1, col2 = st.columns([1, 3])
        col1.metric("CSV Records", len(df))

        search = col2.text_input("Search CSV records", placeholder="Search by any value...")

        if not df.empty and search:
            mask = df.astype(str).apply(
                lambda row: row.str.contains(search, case=False, na=False).any(),
                axis=1,
            )
            df = df[mask]

        if df.empty:
            st.info("No CSV records found.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        show_error("Could not load CSV data", e)


# -----------------------------
# Asset Explorer page
# -----------------------------
elif menu == "Asset Explorer":
    st.markdown('<div class="main-header">Asset Explorer</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Search, filter, and inspect asset details with live history from Cloud SQL.</div>',
        unsafe_allow_html=True,
    )

    try:
        data = load_sql_assets()
        df = pd.DataFrame(data)

        if df.empty:
            st.info("No SQL records found.")
        else:
            search = st.text_input(
                "Search assets",
                placeholder="Search by name, department, location, status, or ID..."
            )

            filtered_df = df.copy()

            if search:
                mask = filtered_df.astype(str).apply(
                    lambda row: row.str.contains(search, case=False, na=False).any(),
                    axis=1,
                )
                filtered_df = filtered_df[mask]

            col1, col2, col3 = st.columns(3)

            with col1:
                if "departamento" in filtered_df.columns:
                    departments = ["All"] + sorted(filtered_df["departamento"].fillna("").unique().tolist())
                    selected_department = st.selectbox("Department", departments)
                    if selected_department != "All":
                        filtered_df = filtered_df[filtered_df["departamento"] == selected_department]

            with col2:
                if "sede" in filtered_df.columns:
                    locations = ["All"] + sorted(filtered_df["sede"].fillna("").unique().tolist())
                    selected_location = st.selectbox("Location", locations)
                    if selected_location != "All":
                        filtered_df = filtered_df[filtered_df["sede"] == selected_location]

            with col3:
                if "estatus" in filtered_df.columns:
                    statuses = ["All"] + sorted(filtered_df["estatus"].fillna("").unique().tolist())
                    selected_status = st.selectbox("Status", statuses)
                    if selected_status != "All":
                        filtered_df = filtered_df[filtered_df["estatus"] == selected_status]

            query_asset_id = st.query_params.get("asset_id", None)

            if query_asset_id:
                st.success(f"QR Scan Mode: Asset ID {query_asset_id} loaded from QR code.")

                quick_col1, quick_col2 = st.columns([1, 3])

                with quick_col1:
                    if st.button("Record Scan Now", type="primary"):
                        try:
                            api_post(
                                f"/assets/{query_asset_id}/scan",
                                {
                                    "scanned_by": "QR User",
                                    "scan_location": "QR Scan Location",
                                    "notes": "Recorded from QR Scan Mode",
                                },

                            )
                            st.success("Scan recorded successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Scan failed: {e}")

                with quick_col2:
                    st.info("Use this button during a physical inventory audit to quickly confirm this asset was seen.")
            else:
                st.metric("Matching Assets", len(filtered_df))

                st.dataframe(
                    filtered_df.head(100),
                    use_container_width=True,
                    hide_index=True,
                )

                st.divider()

            st.subheader("Asset Detail")

            asset_options = {}

            for _, row in filtered_df.iterrows():

                asset_id = row["id"]

                asset_tag = row.get("asset_tag", "")
                asset_name = row.get("nombre", "")

                label = f"{asset_tag} - {asset_name}"

                asset_options[label] = asset_id

            if asset_options:


                query_asset_id = st.query_params.get("asset_id", None)
                default_index = 0

                if query_asset_id:
                    for i, label in enumerate(asset_options.keys()):
                        if str(asset_options[label]) == str(query_asset_id):
                            default_index = i
                            break
                selected_asset_label = st.selectbox(
                    "Select Asset",
                    list(asset_options.keys()),
                    index=default_index
                )              

                selected_asset_id = asset_options[selected_asset_label]
                try:
                    history = api_get(f"/assets/{selected_asset_id}/history")
                    asset = history.get("asset", {})

                    qr_url = f"https://inventory-frontend-271456327495.northamerica-south1.run.app/?asset_id={selected_asset_id}"

                    qr_image = generate_qr_code(qr_url)

                    st.write("### Asset QR Code")

                    st.image(
                        qr_image,
                        width=180
                    )

                    st.caption(
                        "Scan this QR code to open the asset record."
                    )


                    label_url = (
                        f"{API_URL}/assets/{selected_asset_id}/label"
                    )

                    st.markdown(
                        f"[Download Printable Label PDF]({label_url})",
                        unsafe_allow_html=True,
                    )

                    scans = history.get("scans", [])
                    checkouts = history.get("checkouts", [])

                    detail_col1, detail_col2, detail_col3 = st.columns(3)

                    with detail_col1:
                        st.write("**Asset Tag**")
                        st.write(asset.get("asset_tag", "N/A"))

                        st.write("**Name**")
                        st.write(asset.get("nombre", "N/A"))

                        st.write("**Serial Number**")
                        st.write(asset.get("serial_number", "N/A"))

                    with detail_col2:
                        st.write("**Department**")
                        st.write(asset.get("departamento", "N/A"))

                        st.write("**Location**")
                        st.write(asset.get("sede", "N/A"))

                        st.write("**Category**")
                        st.write(asset.get("category", "N/A"))



                    with detail_col3:
                        st.write("**Status**")

                        status = str(asset.get("estatus", "Unknown"))

                        badge_class = "status-storage"

                        if status.lower() == "in use":
                            badge_class = "status-in-use"
                        elif status.lower() == "checked out":
                            badge_class = "status-checked-out"
                        elif status.lower() in ["needs repair", "maintenance"]:
                            badge_class = "status-repair"

                        st.markdown(
                            f'<span class="status-badge {badge_class}">{status}</span>',
                            unsafe_allow_html=True,
                        )

                        st.write("**Checked Out**")
                        st.write("Yes" if asset.get("checked_out") else "No")

                        st.write("**Checked Out By**")
                        st.write(asset.get("checked_out_by") or "N/A")

                    st.divider()
                    st.subheader("Asset Actions")

                    action_col1, action_col2, action_col3 = st.columns(3)

                    with action_col1:
                        with st.form(f"scan_form_{selected_asset_id}"):
                            scanned_by = st.text_input("Scanned By", value="Ulises")
                            scan_location = st.text_input("Scan Location", value=asset.get("sede") or "Northridge")
                            scan_submit = st.form_submit_button("Scan Asset")

                            if scan_submit:
                                try:
                                    api_post(
                                        f"/assets/{selected_asset_id}/scan",
                                        {
                                            "scanned_by": scanned_by,
                                            "scan_location": scan_location,
                                        },
                                    )
                                    st.success("Asset scanned successfully.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Scan failed: {e}")

                    with action_col2:
                        with st.form(f"checkout_form_{selected_asset_id}"):
                            checked_out_to = st.text_input("Checked Out To", value="John Smith")
                            checked_out_by = st.text_input("Checked Out By", value="Ulises")
                            expected_return_at = st.text_input("Expected Return Date", value="2026-07-01")
                            checkout_submit = st.form_submit_button("Checkout Asset")

                            if checkout_submit:
                                try:
                                    api_post(
                                        f"/assets/{selected_asset_id}/checkout",
                                        {
                                            "checked_out_to": checked_out_to,
                                            "checked_out_by": checked_out_by,
                                            "expected_return_at": expected_return_at,
                                            "notes": "Frontend checkout",
                                        },
                                    )
                                    st.success("Asset checked out successfully.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Checkout failed: {e}")

                    with action_col3:
                        with st.form(f"checkin_form_{selected_asset_id}"):
                            checked_in_by = st.text_input("Checked In By", value="Ulises")
                            checkin_submit = st.form_submit_button("Check In Asset")

                            if checkin_submit:
                                try:
                                    api_post(
                                        f"/assets/{selected_asset_id}/checkin",
                                        {
                                            "checked_in_by": checked_in_by,
                                        },
                                    )
                                    st.success("Asset checked in successfully.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Check-in failed: {e}")




                    st.divider()
                    st.subheader("Transfer Asset")

                    with st.form(f"transfer_form_{selected_asset_id}"):
                        to_location = st.selectbox(
                            "Transfer To Location",
                            ["Northridge", "Riverside", "Round Rock", "San Marcos", "TOOF", "Lockhart", "Dobie", "Austin Campus"]
                        )
                        requested_by = st.text_input("Transfer Requested By", value="Ulises")
                        approved_by = st.text_input("Approved By", value="Inventory Manager")
                        transfer_notes = st.text_input("Transfer Notes", value="Frontend transfer")

                        transfer_submit = st.form_submit_button("Transfer Asset")

                        if transfer_submit:
                            try:
                                api_post(
                                    f"/assets/{selected_asset_id}/transfer",
                                    {
                                        "to_location": to_location,
                                        "requested_by": requested_by,
                                        "approved_by": approved_by,
                                        "notes": transfer_notes,
                                    },
                                )
                                st.success("Asset transferred successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Transfer failed: {e}")

                    st.divider()
                    st.subheader("Report Maintenance Issue")

                    with st.form(f"maintenance_form_{selected_asset_id}"):
                        issue_description = st.text_area(
                            "Issue Description",
                            value="Screen is damaged"
                        )
                        priority = st.selectbox(
                            "Priority",
                            ["Low", "Medium", "High", "Critical"],
                            index=2
                        )
                        requested_by = st.text_input("Requested By", value="Ulises")
                        assigned_to = st.text_input("Assigned To", value="Maintenance Team")
                        notes = st.text_input("Notes", value="Created from frontend")

                        maintenance_submit = st.form_submit_button("Create Maintenance Ticket")

                        if maintenance_submit:
                            try:
                                api_post(
                                    f"/assets/{selected_asset_id}/maintenance",
                                    {
                                        "issue_description": issue_description,
                                        "priority": priority,
                                        "requested_by": requested_by,
                                        "assigned_to": assigned_to,
                                        "notes": notes,
                                    },
                                )
                                st.success("Maintenance ticket created successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Maintenance request failed: {e}")

                    st.divider()

                    st.subheader("Activity History")

                    history_rows = []

                    for scan in scans:
                        history_rows.append({
                            "type": "Scan",
                            "date": scan.get("scanned_at"),
                            "person": scan.get("scanned_by"),
                            "location": scan.get("scan_location"),
                            "notes": scan.get("notes"),
                        })

                    for checkout in checkouts:
                        history_rows.append({
                            "type": "Checkout",
                            "date": checkout.get("checked_out_at"),
                            "person": checkout.get("checked_out_to"),
                            "location": "",
                            "notes": checkout.get("notes"),
                        })

                        if checkout.get("returned_at"):
                            history_rows.append({
                                "type": "Check-In",
                                "date": checkout.get("returned_at"),
                                "person": checkout.get("checked_in_by"),
                                "location": "",
                                "notes": "Returned",
                            })

                    try:
                        maintenance_items = [
                            item for item in load_maintenance_requests()
                            if int(item.get("asset_id", 0)) == int(selected_asset_id)
                        ]

                        for item in maintenance_items:
                            history_rows.append({
                                "type": "Maintenance",
                                "date": item.get("opened_at"),
                                "person": item.get("requested_by"),
                                "location": item.get("assigned_to"),
                                "notes": item.get("issue_description"),
                            })
                    except Exception:
                        pass

                    try:
                        transfer_items = [
                            item for item in load_transfers()
                            if int(item.get("asset_id", 0)) == int(selected_asset_id)
                        ]

                        for item in transfer_items:
                            history_rows.append({
                                "type": "Transfer",
                                "date": item.get("completed_at") or item.get("requested_at"),
                                "person": item.get("requested_by"),
                                "location": f"{item.get('from_location')} → {item.get('to_location')}",
                                "notes": item.get("notes"),
                            })
                    except Exception:
                        pass

                    if history_rows:
                        history_df = pd.DataFrame(history_rows)
                        history_df = history_df.sort_values("date", ascending=False)
                        st.dataframe(history_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No activity history yet for this asset.")

                except Exception as e:
                    st.error(f"Could not load asset history: {e}")

    except Exception as e:
        show_error("Could not load asset explorer", e)


# -----------------------------
# Maintenance Tickets page
# -----------------------------
elif menu == "Maintenance Tickets":
    st.markdown('<div class="main-header">Maintenance Tickets</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Open and historical maintenance requests.</div>', unsafe_allow_html=True)

    try:
        data = load_maintenance_requests()
        df = pd.DataFrame(data)

        if df.empty:
            st.info("No maintenance tickets found.")
        else:
            st.metric("Total Maintenance Tickets", len(df))
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        show_error("Could not load maintenance tickets", e)


# -----------------------------
# Transfer History page
# -----------------------------
elif menu == "Transfer History":
    st.markdown('<div class="main-header">Transfer History</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Completed asset movements between locations.</div>', unsafe_allow_html=True)

    try:
        data = load_transfers()
        df = pd.DataFrame(data)

        if df.empty:
            st.info("No transfers found.")
        else:
            st.metric("Total Transfers", len(df))
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        show_error("Could not load transfers", e)


# -----------------------------
# Add asset page
# -----------------------------
elif menu == "Add Asset":
    st.markdown('<div class="main-header">Add New Asset</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Create a new asset record in Cloud SQL PostgreSQL through FastAPI.</div>',
        unsafe_allow_html=True,
    )

    with st.form("add_asset_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            nombre = st.text_input("Asset Name", placeholder="Example: Dell Latitude 7440")
            departamento = st.selectbox(
                "Department",
                ["IT", "HVAC", "AUTO", "Facilities", "Finance", "Operations"],
            )

        with col2:
            sede = st.text_input("Campus / Sede", placeholder="Example: Austin Campus")
            estatus = st.selectbox(
                "Status",
                ["In Use", "In Storage", "Maintenance", "Retired"],
            )

        submitted = st.form_submit_button("Save Asset")

    if submitted:
        if not nombre.strip():
            st.warning("Asset Name is required.")
        else:
            payload = {
                "nombre": nombre.strip(),
                "departamento": departamento,
                "sede": sede.strip(),
                "estatus": estatus,
            }

            try:
                result = api_post("/assets", payload)
                st.success("Asset saved successfully into Cloud SQL.")
                st.json(result)
            except Exception as e:
                show_error("Could not save asset", e)

    st.divider()

    st.subheader("Current SQL Assets")

    try:
        data = load_sql_assets()
        df = pd.DataFrame(data)

        if df.empty:
            st.info("No SQL records yet.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        show_error("Could not refresh SQL assets", e)


# -----------------------------
# API Status page
# -----------------------------
elif menu == "API Status":
    st.markdown('<div class="main-header">API Status</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Health and configuration checks for the FastAPI backend.</div>',
        unsafe_allow_html=True,
    )

    st.write("Backend API URL:")
    st.code(API_URL)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Check Health"):
            try:
                st.json(api_get("/health"))
            except Exception as e:
                show_error("Health check failed", e)

    with col2:
        if st.button("Check Config"):
            try:
                st.json(api_get("/debug/config"))
            except Exception as e:
                show_error("Config check failed", e)

    with col3:
        if st.button("Check SQL Setup"):
            try:
                st.json(api_get("/setup/sql"))
            except Exception as e:
                show_error("SQL setup check failed", e)

    st.divider()

    st.subheader("Manual API Test Links")
    st.code(
        f"""
{API_URL}/health
{API_URL}/assets/csv
{API_URL}/assets
{API_URL}/setup/sql
{API_URL}/docs
        """,
        language="text",
    )
