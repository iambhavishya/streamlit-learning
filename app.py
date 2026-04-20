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
    model = genai.GenerativeModel("models/gemini-2.5-flash")
else:
    model = None

# Prompt template for chart creation
CHART_SYSTEM_PROMPT = """
You are a data visualization assistant.
The user will ask for a chart based on the Superstore data.

You must respond ONLY with a small JSON object, no extra words.
Structure:
{
  "chart_type": "bar" | "line" | "scatter",
  "x": "<column_name>",
  "y": "<column_name>",
  "color": "<column_name or null>",
  "aggregate": "sum" | "mean" | "count" | null
}

Constraints:
- Valid numeric columns: "Sales", "Profit", "Quantity", "Discount".
- Valid categorical columns: "Region", "Segment", "Category", "Sub-Category", "Ship Mode".
- "Order Date" is the only date column.
"""

# ---------- LOAD DATA ----------
@st.cache_data
def load_data(path: str):
    df_local = pd.read_excel(path, sheet_name="Orders")
    df_local["Order Date"] = pd.to_datetime(df_local["Order Date"])
    df_local["Ship Date"] = pd.to_datetime(df_local["Ship Date"])
    
    # FORCE NUMERIC: This ensures Altair can actually plot the values
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

# Apply filters
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

# ---------- AI‑GENERATED CHART ----------
st.markdown("---")
st.markdown("## 🔧 Let Gemini create a custom chart")

chart_query = st.text_input("Describe the chart (e.g., 'Bar chart of Sales by Region')")
create_btn = st.button("Create chart")

if create_btn and chart_query:
    if not (GEMINI_API_KEY and model):
        st.error("API Key missing.")
    else:
        prompt = f"{CHART_SYSTEM_PROMPT}\nUser request: {chart_query}"
        try:
            resp = model.generate_content(prompt)
            raw = resp.text.strip()
            
            # Extract and parse JSON
            start_idx, end_idx = raw.find("{"), raw.rfind("}")
            spec = json.loads(raw[start_idx : end_idx + 1])

            chart_type = spec.get("chart_type", "bar")
            x_col = spec.get("x")
            y_col = spec.get("y")
            color_col = spec.get("color")
            agg = spec.get("aggregate", "sum")

            # Check if columns exist (Case-insensitive check)
            available_cols = {c.lower(): c for c in filtered.columns}
            
            if x_col.lower() in available_cols and y_col.lower() in available_cols:
                # Use exact column names from DataFrame
                real_x = available_cols[x_col.lower()]
                real_y = available_cols[y_col.lower()]
                
                # Build Encoding
                enc = {}
                if pd.api.types.is_datetime64_any_dtype(filtered[real_x]):
                    enc["x"] = alt.X(f"{real_x}:T")
                else:
                    enc["x"] = alt.X(f"{real_x}:N", sort='-y')

                # The Y encoding fix
                if agg:
                    enc["y"] = alt.Y(f"{agg}({real_y}):Q", title=f"{agg.capitalize()} of {real_y}")
                else:
                    enc["y"] = alt.Y(f"{real_y}:Q", title=real_y)

                if color_col and color_col.lower() in available_cols:
                    enc["color"] = alt.Color(f"{available_cols[color_col.lower()]}:N")

                # Create Chart
                if chart_type == "line":
                    base = alt.Chart(filtered).mark_line(point=True)
                elif chart_type == "scatter":
                    base = alt.Chart(filtered).mark_point()
                else:
                    base = alt.Chart(filtered).mark_bar()

                st.altair_chart(base.encode(**enc).properties(height=400), use_container_width=True)
            else:
                st.error(f"Columns not found: {x_col} or {y_col}")

        except Exception as e:
            st.error(f"Rendering Error: {e}")

# ---------- CHAT SECTION ----------
# (Previous chat code remains the same...)
