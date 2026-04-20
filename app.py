import os
from datetime import datetime
import json
import altair as alt
import google.generativeai as genai
import pandas as pd
import streamlit as st

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="Superstore + Gemini Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛒 Superstore Analytics + 🤖 Gemini Assistant")

# ---------- GEMINI SETUP ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using your original model name
    model = genai.GenerativeModel("models/gemini-2.5-flash")
else:
    model = None

# ---------- PROMPT TEMPLATE ----------
CHART_SYSTEM_PROMPT = """
You are a data visualization assistant.
Respond ONLY with a JSON object.
Structure:
{
  "chart_type": "bar" | "line" | "scatter" | "pie" | "donut",
  "x": "<column_name>",
  "y": "<column_name>",
  "color": "<column_name or null>",
  "aggregate": "sum" | "mean" | "count" | null
}
Constraints:
- Valid numeric columns: "Sales", "Profit", "Quantity", "Discount".
- Valid categorical columns: "Region", "Segment", "Category", "Sub-Category", "Ship Mode", "State".
- For pie/donut, 'x' is the category and 'y' is the numeric value.
"""

# ---------- LOAD DATA ----------
@st.cache_data
def load_data(path: str):
    df_local = pd.read_excel(path, sheet_name="Orders")
    df_local["Order Date"] = pd.to_datetime(df_local["Order Date"])
    df_local["Ship Date"] = pd.to_datetime(df_local["Ship Date"])
    
    # Force numeric conversion to ensure aggregation math works
    numeric_cols = ["Sales", "Profit", "Quantity", "Discount"]
    for col in numeric_cols:
        df_local[col] = pd.to_numeric(df_local[col], errors='coerce').fillna(0)
    return df_local

try:
    df = load_data("sample_superstore.xlsx")
except Exception as e:
    st.error(f"Excel file error: {e}")
    st.stop()

# ---------- SIDEBAR FILTERS ----------
st.sidebar.header("Filters")
min_date, max_date = df["Order Date"].min(), df["Order Date"].max()

date_range = st.sidebar.date_input("Order Date range", [min_date, max_date], min_value=min_date, max_value=max_date)
selected_region = st.sidebar.selectbox("Region", ["All"] + sorted(df["Region"].unique().tolist()))
selected_segment = st.sidebar.selectbox("Segment", ["All"] + sorted(df["Segment"].unique().tolist()))

filtered = df.copy()
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[(filtered["Order Date"] >= pd.to_datetime(start)) & (filtered["Order Date"] <= pd.to_datetime(end))]

if selected_region != "All":
    filtered = filtered[filtered["Region"] == selected_region]
if selected_segment != "All":
    filtered = filtered[filtered["Segment"] == selected_segment]

# ---------- KPIs ----------
st.subheader("Key Metrics")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Sales", f"${filtered['Sales'].sum():,.0f}")
k2.metric("Total Profit", f"${filtered['Profit'].sum():,.0f}")
k3.metric("Avg Discount", f"{filtered['Discount'].mean()*100:.1f}%")
k4.metric("Order Count", f"{filtered['Order ID'].nunique():,}")

# ---------- STATIC VISUALS ----------
st.markdown("---")
col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown("### Sales by Category")
    chart_cat = alt.Chart(filtered).mark_bar().encode(
        x=alt.X("Category:N", sort="-y"),
        y=alt.Y("sum(Sales):Q", title="Sales"),
        color="Category:N"
    ).properties(height=300)
    st.altair_chart(chart_cat, use_container_width=True)

with col_right:
    st.markdown("### Sales by Region")
    chart_reg = alt.Chart(filtered).mark_bar().encode(
        x=alt.X("sum(Sales):Q"),
        y=alt.Y("Region:N", sort="-x"),
        color="Region:N"
    ).properties(height=300)
    st.altair_chart(chart_reg, use_container_width=True)

# ---------- AI‑GENERATED CHART SECTION ----------
st.markdown("---")
st.markdown("## 🔧 AI Custom Chart Builder")

if "ai_chart_spec" not in st.session_state:
    st.session_state.ai_chart_spec = None
if "last_query" not in st.session_state:
    st.session_state.last_query = ""

chart_query = st.text_input("Describe the chart (e.g., 'Donut chart of Profit by State')")
create_btn = st.button("Create AI Chart")

if create_btn and chart_query:
    if not (GEMINI_API_KEY and model):
        st.error("API Key missing.")
    else:
        with st.spinner("Gemini is analyzing..."):
            try:
                prompt = f"{CHART_SYSTEM_PROMPT}\nUser request: {chart_query}"
                resp = model.generate_content(prompt)
                raw = resp.text.strip()
                s, e = raw.find("{"), raw.rfind("}")
                st.session_state.ai_chart_spec = json.loads(raw[s : e + 1])
                st.session_state.last_query = chart_query
            except Exception as ex:
                st.error(f"Error parsing Gemini response: {ex}")

if st.session_state.ai_chart_spec:
    spec = st.session_state.ai_chart_spec
    try:
        chart_type = spec.get("chart_type", "bar")
        x_raw, y_raw = spec.get("x", "Category"), spec.get("y", "Sales")
        agg = spec.get("aggregate") if spec.get("aggregate") else "sum"
        
        cols_map = {c.lower(): c for c in filtered.columns}
        real_x = cols_map.get(x_raw.lower(), x_raw)
        real_y = cols_map.get(y_raw.lower(), y_raw)

        st.info(f"**Generated:** {st.session_state.last_query}")

        if chart_type in ["pie", "donut"]:
            # Aggregation is forced here to prevent the "barcode" effect
            enc = {
                "theta": alt.Theta(f"{agg}({real_y}):Q", title=f"{agg.capitalize()} of {real_y}"),
                "color": alt.Color(f"{real_x}:N", title=real_x),
                "tooltip": [real_x, alt.Tooltip(f"{agg}({real_y}):Q", format=",.0f")]
            }
            base = alt.Chart(filtered).mark_arc(innerRadius=80 if chart_type=="donut" else 0)
        else:
            enc = {
                "x": alt.X(f"{real_x}:T") if "Date" in real_x else alt.X(f"{real_x}:N", sort='-y'),
                "y": alt.Y(f"{agg}({real_y}):Q", title=f"{agg.capitalize()} of {real_y}"),
                "tooltip": [real_x, alt.Tooltip(f"{agg}({real_y}):Q", format=",.0f")]
            }
            color_req = spec.get("color")
            if color_req and color_req.lower() in cols_map:
                enc["color"] = alt.Color(f"{cols_map[color_req.lower()]}:N")
            
            marks = {"line": alt.Chart(filtered).mark_line(point=True), 
                     "scatter": alt.Chart(filtered).mark_point()}
            base = marks.get(chart_type, alt.Chart(filtered).mark_bar())

        st.altair_chart(base.encode(**enc).properties(height=450), use_container_width=True)
    except Exception as render_err:
        st.error(f"Render Error: {render_err}")

# ---------- UNIVERSAL CHAT SECTION ----------
st.markdown("---")
st.subheader("Chat about the Dashboard")

if GEMINI_API_KEY and model:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for role, content in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(content)

    user_q = st.chat_input("Ask anything (e.g., Which sub-category has highest profit? Which date had peak sales?)")
    
    if user_q:
        st.session_state.chat_history.append(("user", user_q))
        with st.chat_message("user"):
            st.markdown(user_q)

        # 1. Dynamic Dimension Discovery
        exclude_cols = ['Row ID', 'Order ID', 'Customer ID', 'Product ID', 'Product Name']
        dimensions = [col for col in filtered.select_dtypes(include=['object']).columns if col not in exclude_cols]

        full_context = ""
        # 2. Build Categorical Summaries
        for dim in dimensions:
            summary = filtered.groupby(dim)[['Sales', 'Profit']].sum().sort_values(by='Sales', ascending=False).head(10)
            full_context += f"\n--- Top 10 by {dim} ---\n{summary.to_csv()}"

        # 3. Build Time Summary (Top 10 dates)
        time_summary = filtered.groupby('Order Date')[['Sales']].sum().sort_values(by='Sales', ascending=False).head(10)
        full_context += f"\n--- Top 10 Sales Dates ---\n{time_summary.to_csv()}"

        system_prompt = (
            "You are an expert data analyst for a Superstore. I am providing you with multiple aggregated summaries "
            "of the filtered data. Use these to answer the user's question with specific numbers.\n"
            f"{full_context}"
        )
        
        with st.chat_message("assistant"):
            try:
                chat_resp = model.generate_content(system_prompt + "\n\nUser Question: " + user_q)
                st.markdown(chat_resp.text)
                st.session_state.chat_history.append(("assistant", chat_resp.text))
            except Exception as chat_err:
                st.error(f"Chat error: {chat_err}")
