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
    # Reverted to your requested model name
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
- If user mentions time or date, use "Order Date" as x with chart_type "line" and aggregate "sum" on Sales.
- If unsure, default to bar chart of sum of Sales by Category.
"""

# ---------- LOAD DATA ----------
@st.cache_data
def load_data(path: str):
    df_local = pd.read_excel(path, sheet_name="Orders")
    df_local["Order Date"] = pd.to_datetime(df_local["Order Date"])
    df_local["Ship Date"] = pd.to_datetime(df_local["Ship Date"])
    return df_local

# Ensure your Excel file is in the same directory
try:
    df = load_data("sample_superstore.xlsx")
except Exception as e:
    st.error(f"Excel file error: {e}")
    st.stop()

# ---------- SIDEBAR FILTERS ----------
st.sidebar.header("Filters")

min_date = df["Order Date"].min()
max_date = df["Order Date"].max()

date_range = st.sidebar.date_input(
    "Order Date range",
    [min_date, max_date],
    min_value=min_date,
    max_value=max_date,
)

regions = ["All"] + sorted(df["Region"].dropna().unique().tolist())
selected_region = st.sidebar.selectbox("Region", regions)

segments = ["All"] + sorted(df["Segment"].dropna().unique().tolist())
selected_segment = st.sidebar.selectbox("Segment", segments)

# Apply filters
filtered = df.copy()
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (filtered["Order Date"] >= pd.to_datetime(start))
        & (filtered["Order Date"] <= pd.to_datetime(end))
    ]

if selected_region != "All":
    filtered = filtered[filtered["Region"] == selected_region]

if selected_segment != "All":
    filtered = filtered[filtered["Segment"] == selected_segment]

st.sidebar.markdown(f"**Rows after filter:** {len(filtered):,}")

# ---------- KPIs ----------
st.subheader("Key Metrics")

total_sales = filtered["Sales"].sum()
total_profit = filtered["Profit"].sum()
avg_discount = filtered["Discount"].mean()
order_count = filtered["Order ID"].nunique()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total Sales", f"${total_sales:,.0f}")
kpi2.metric("Total Profit", f"${total_profit:,.0f}")
kpi3.metric("Avg Discount", f"{avg_discount*100:.1f}%")
kpi4.metric("Order Count", f"{order_count:,}")

# ---------- STATIC VISUALS ----------
left, right = st.columns([2, 1])

with left:
    st.markdown("### Sales by Category")
    chart_cat = (
        alt.Chart(filtered)
        .mark_bar()
        .encode(
            x=alt.X("Category:N", sort="-y"),
            y=alt.Y("sum(Sales):Q", title="Sales"),
            color="Category:N",
            tooltip=["Category", "Sales", "Profit"],
        )
        .properties(height=300)
    )
    st.altair_chart(chart_cat, use_container_width=True)

    st.markdown("### Monthly Sales Trend")
    temp = filtered.copy()
    temp["Order Month"] = temp["Order Date"].dt.to_period("M").dt.to_timestamp()
    chart_month = (
        alt.Chart(temp)
        .mark_line(point=True)
        .encode(
            x="Order Month:T",
            y=alt.Y("sum(Sales):Q", title="Sales"),
            tooltip=["Order Month", "Sales"],
        )
        .properties(height=300)
    )
    st.altair_chart(chart_month, use_container_width=True)

with right:
    st.markdown("### Sales by Region")
    chart_region = (
        alt.Chart(filtered)
        .mark_bar()
        .encode(
            x=alt.X("sum(Sales):Q", title="Sales"),
            y=alt.Y("Region:N", sort="-x"),
            color="Region:N",
            tooltip=["Region", "Sales", "Profit"],
        )
        .properties(height=300)
    )
    st.altair_chart(chart_region, use_container_width=True)

# ---------- AI‑GENERATED CHART ----------
st.markdown("---")
st.markdown("## 🔧 Let Gemini create a custom chart")

chart_query = st.text_input(
    "Describe the chart you want (example: 'Bar chart of total Sales by Region sorted descending')"
)
create_btn = st.button("Create chart")

if create_btn and chart_query:
    if not (GEMINI_API_KEY and model):
        st.error("Gemini API key not set; cannot create chart.")
    else:
        prompt = CHART_SYSTEM_PROMPT + "\nUser request: " + chart_query
        try:
            resp = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=200,
                    temperature=0.2,
                ),
            )

            raw = resp.text.strip()
            
            # Clean JSON extraction
            start_idx = raw.find("{")
            end_idx = raw.rfind("}")
            
            if start_idx == -1 or end_idx == -1:
                st.error("No valid JSON found in model response.")
            else:
                raw_json = raw[start_idx : end_idx + 1]
                spec = json.loads(raw_json)

                chart_type = spec.get("chart_type", "bar")
                x = spec.get("x", "Category")
                y = spec.get("y", "Sales")
                color = spec.get("color", None)
                agg = spec.get("aggregate", "sum")

                if x not in filtered.columns or y not in filtered.columns:
                    st.error(f"Invalid fields from model: x={x}, y={y}")
                else:
                    enc = {}

                    # X encoding
                    if pd.api.types.is_datetime64_any_dtype(filtered[x]):
                        enc["x"] = alt.X(f"{x}:T")
                    elif filtered[x].dtype == "object":
                        enc["x"] = alt.X(f"{x}:N")
                    else:
                        enc["x"] = alt.X(f"{x}:Q")

                    # Y encoding with aggregation - FIXED SYNTAX
                    if agg:
                        enc["y"] = alt.Y(f"{agg}({y}):Q", title=f"{agg.capitalize()} of {y}")
                    else:
                        # Removed the extra parenthesis that was causing the blank chart
                        enc["y"] = alt.Y(f"{y}:Q", title=y)

                    if color and color in filtered.columns:
                        enc["color"] = alt.Color(f"{color}:N")

                    # Base mark selection
                    if chart_type == "line":
                        base_chart = alt.Chart(filtered).mark_line(point=True)
                    elif chart_type == "scatter":
                        base_chart = alt.Chart(filtered).mark_point()
                    else:
                        base_chart = alt.Chart(filtered).mark_bar()

                    dynamic_chart = (
                        base_chart.encode(**enc)
                        .properties(
                            height=350,
                            title=f"Gemini chart: {chart_query}",
                        )
                    )

                    st.altair_chart(dynamic_chart, use_container_width=True)

        except Exception as e:
            st.error(f"Could not create chart: {e}")

# ---------- CHAT ABOUT DATA ----------
st.markdown("---")
st.subheader("Ask Gemini about this dashboard")

if not (GEMINI_API_KEY and model):
    st.info("Set GEMINI_API_KEY environment variable to enable chat.")
else:
    sample_rows = min(200, len(filtered))
    data_snippet = filtered.head(sample_rows)[
        [
            "Order Date", "Region", "Segment", "Category", 
            "Sub-Category", "Ship Mode", "Sales", "Profit", 
            "Quantity", "Discount"
        ]
    ]

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for role, content in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(content)

    user_q = st.chat_input("Ask a question, e.g. 'Which category is most profitable?'")
    
    if user_q:
        st.session_state.chat_history.append(("user", user_q))
        with st.chat_message("user"):
            st.markdown(user_q)

        system_prompt = (
            "You are a helpful data analyst working on Superstore sales data. "
            "You are given a sample of the currently filtered dataset as CSV. "
            "Use only this data to answer. Be concise and mention numbers.\n\n"
            "Here is the data sample:\n"
            f"{data_snippet.to_csv(index=False)}\n"
        )

        with st.chat_message("assistant"):
            try:
                resp = model.generate_content(system_prompt + "\nUser question: " + user_q)
                answer = resp.text
            except Exception as e:
                answer = f"Error from Gemini: {e}"

            st.markdown(answer)
            st.session_state.chat_history.append(("assistant", answer))
