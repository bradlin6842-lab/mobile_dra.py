import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import random
import base64
from fpdf import FPDF

# --- Page Configuration ---
st.set_page_config(page_title="DRA Sentinel", layout="centered")

# --- Custom CSS ---
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    div[data-testid="stMetricValue"] { font-size: 22px; color: #FFD700; }
    </style>
    """, unsafe_allow_html=True)

# --- Header ---
st.title("💰 DRA Daily Sentinel")
st.caption("Daily Range Accrual Analysis (Floor Only)")

# --- 1. Asset Selection ---
input_tickers = st.text_input("Enter Tickers", "NVDA, TSM, MSFT")
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
if not tickers: tickers = ["NVDA"]
ticker = st.selectbox("🎯 Target Asset", tickers)

# --- 2. Safe Data Fetching ---
@st.cache_data(ttl=3600)
def get_asset_info(symbol):
    try:
        asset = yf.Ticker(symbol)
        fast = asset.fast_info
        try:
            name = asset.info.get('longName', symbol)
            pe = asset.info.get('trailingPE', 'N/A')
        except:
            name = symbol
            pe = 'N/A'
        return {
            "name": name, "pe": pe,
            "low52": fast.get('yearLow', 0),
            "high52": fast.get('yearHigh', 0),
            "curr": fast.get('last_price') or 100.0
        }
    except:
        return {"name": symbol, "pe": "N/A", "low52": 0, "high52": 0, "curr": 100.0}

asset_info = get_asset_info(ticker)
current_p = asset_info['curr']

st.subheader(f"🏢 {asset_info['name']}")
c_a, c_b, c_c = st.columns(3)
with c_a: st.metric("P/E Ratio", f"{asset_info['pe']:.2f}" if isinstance(asset_info['pe'], (int,float)) else "N/A")
with c_b: st.metric("52W Low", f"${asset_info['low52']:,.1f}")
with c_c: st.metric("52W High", f"${asset_info['high52']:,.1f}")

st.divider()

# --- 3. DRA Parameters ---
st.subheader("⚙️ DRA Parameters")
strike_pct = st.slider("Accrual Floor (Strike %)", 50, 100, 85) / 100
coupon_rate = st.number_input("Annualized Coupon (%)", value=15.0)
st.metric("Accrual Price Floor", f"${current_p * strike_pct:,.2f}")

# --- 4. Volatility & Simulation ---
vol_mode = st.radio("Volatility Period", ["30D (Sentinel)", "180D (Bank)"], horizontal=True)
hist = yf.Ticker(ticker).history(period="1mo" if "30D" in vol_mode else "6mo")
if len(hist) > 10:
    sigma = np.log(hist['Close']/hist['Close'].shift(1)).std() * np.sqrt(252)
else:
    sigma = 0.30

# Monte Carlo with t-distribution for tail risk
n_days, n_paths, mu = 180, 100, 0.05
dt = 1/252
paths = np.ones((n_days, n_paths))
for i in range(1, n_days):
    shocks = np.random.standard_t(df=3, size=n_paths) * 0.7
    paths[i] = paths[i-1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks)

# --- 5. Accrual Calculation ---
# 只要價格 >= strike_pct 就算一天利息
daily_accrual = paths >= strike_pct
accrual_days_per_path = np.sum(daily_accrual, axis=0)
avg_accrual_ratio = np.mean(accrual_days_per_path) / n_days
expected_yield = coupon_rate * avg_accrual_ratio

# --- 6. Plotting ---
fig = go.Figure()
for j in range(n_paths):
    fig.add_trace(go.Scatter(y=paths[:, j], mode='lines', line=dict(width=0.5, color='rgba(255, 215, 0, 0.2)'), showlegend=False))

fig.add_hline(y=1.0, line_color="white", line_width=2)
fig.add_hline(y=strike_pct, line_dash="dash", line_color="red", label=dict(text="Accrual Floor"))

fig.update_layout(height=350, template="plotly_dark", xaxis_title="Days", yaxis_title="Price Ratio", margin=dict(l=5,r=5,t=10,b=5))
st.plotly_chart(fig, use_container_width=True)

# --- 7. Result Card ---
st.markdown(f"""
    <div style="background-color: #1E1E1E; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; text-align: center;">
        <p style="color: #FFD700; font-size: 16px; margin: 0;">📊 Expected Accrual Performance</p>
        <p style="color: #FFFFFF; font-size: 32px; font-weight: bold; margin: 10px 0;">{avg_accrual_ratio*100:.1f}% Days</p>
        <p style="color: #FFFFFF; font-size: 18px;">Exp. Annual Yield: <span style="color: #00FFA3;">{expected_yield:.2f}%</span></p>
        <p style="color: #888888; font-size: 11px;">(Based on {n_days} days simulation)</p>
    </div>
    """, unsafe_allow_html=True)

# --- 8. PDF Report ---
if st.button("🚀 Export DRA Audit Report"):
    st.balloons()
    audit_no = random.randint(100000, 999999)
    class PDF(FPDF):
        def header(self):
            self.set_fill_color(30, 30, 30); self.rect(0, 0, 210, 40, 'F')
            self.set_text_color(255, 255, 255); self.set_font('Arial', 'B', 16)
            self.cell(0, 20, 'DRA PERFORMANCE AUDIT', 0, 1, 'C')
            self.ln(20)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f' [I] ASSET: {asset_info["name"]} ({ticker})', 0, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f'  - Current Price: ${current_p:,.2f}', ln=True)
    pdf.cell(0, 8, f'  - Annualized Volatility: {sigma:.1%}', ln=True)
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, ' [II] DRA SETUP & EXPECTATION', 0, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f'  - Accrual Floor (Strike): {strike_pct*100:.1f}% (${current_p*strike_pct:,.2f})', ln=True)
    pdf.cell(0, 8, f'  - Potential Max Coupon: {coupon_rate:.2f}%', ln=True)
    pdf.cell(0, 8, f'  - Est. Accrual Ratio: {avg_accrual_ratio*100:.1f}% of days', ln=True)
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(0, 150, 0)
    pdf.cell(0, 10, f'  >>> EXPECTED ANNUAL YIELD: {expected_yield:.2f}%', ln=True)
    
    pdf_out = pdf.output(dest='S').encode('latin-1')
    b64 = base64.b64encode(pdf_out).decode()
    st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="DRA_{ticker}_{audit_no}.pdf" style="text-decoration:none;"><div style="background-color:#FFD700;color:black;padding:15px;border-radius:10px;text-align:center;font-weight:bold;">⬇️ Download DRA Report</div></a>', unsafe_allow_html=True)
