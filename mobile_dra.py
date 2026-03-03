import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import random
import base64
from fpdf import FPDF

# --- Page Configuration ---
st.set_page_config(page_title="DRA Daily Sentinel Pro", layout="centered")

# --- Custom CSS for iPhone 15 Plus ---
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    div[data-testid="stMetricValue"] { font-size: 22px; color: #FFD700; }
    div[data-testid="stMetricLabel"] { font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

# --- Header ---
st.title("💰 DRA Daily Sentinel")
st.caption("Daily Range Accrual (Floor) with KO Logic")

# --- 1. Asset Selection ---
input_tickers = st.text_input("Enter Tickers", "NVDA, TSM, MU, 6857.T")
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
ticker = st.selectbox("🎯 Target Asset", tickers if tickers else ["NVDA"])

# --- 2. Enhanced Data Fetching (Fix for Price Error) ---
@st.cache_data(ttl=300)
def get_asset_info_robust(symbol):
    try:
        asset = yf.Ticker(symbol)
        # 優先抓取歷史收盤價 (穩定性最高)
        hist = asset.history(period="5d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
        else:
            price = asset.fast_info.get('last_price', 100.0)
            
        if price <= 0: price = 100.0
            
        info = asset.info
        return {
            "name": info.get('longName', symbol),
            "pe": info.get('trailingPE', 'N/A'),
            "low52": asset.fast_info.get('yearLow', 0),
            "high52": asset.fast_info.get('yearHigh', 0),
            "curr": price
        }
    except:
        return {"name": symbol, "pe": "N/A", "low52": 0, "high52": 0, "curr": 100.0}

asset_info = get_asset_info_robust(ticker)
current_p = asset_info['curr']

st.subheader(f"🏢 {asset_info['name']}")
st.metric("Current Market Price", f"${current_p:,.2f}")

# --- 3. DRA Strategy Settings ---
with st.container():
    st.subheader("⚙️ DRA Parameters")
    strike_pct = st.slider("Accrual Floor (Strike %)", 50, 100, 85) / 100
    ko_pct = st.slider("KO Level (Autocall %)", 85, 110, 103) / 100
    coupon_rate = st.number_input("Annualized Coupon (%)", value=15.0)

c1, c2, c3 = st.columns(3)
with c1: st.metric("Accrual Floor", f"${current_p * strike_pct:,.2f}")
with c2: st.metric("KO Level", f"${current_p * ko_pct:,.2f}")
with c3: st.metric("Max Yield", f"{coupon_rate}%")

# --- 4. Volatility Engine ---
vol_mode = st.radio("Volatility Period", ["30D (Sentinel)", "180D (Bank)"], horizontal=True)
hist_data = yf.Ticker(ticker).history(period="1mo" if "30D" in vol_mode else "6mo")
if len(hist_data) > 10:
    log_returns = np.log(hist_data['Close'] / hist_data['Close'].shift(1))
    sigma = log_returns.std(@) * np.sqrt(252)
    sigma = max(min(sigma, 0.99), 0.1)
else:
    sigma = 0.35

st.caption(f"📊 Mode: {vol_mode} | Annual Volatility: {sigma:.1%}")

# --- 5. Monte Carlo Simulation (Integrated KO/Accrual) ---
n_days, n_paths, dt, mu = 180, 100, 1/252, 0.05
paths = np.ones((n_days, n_paths))
for i in range(1, n_days):
    shocks = np.random.standard_t(df=3, size=n_paths) * 0.7 
    paths[i] = paths[i-1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks)

# 計算累積天數 (若 KO 則停止累積)
ko_count = 0
total_accrual_days = 0
for j in range(n_paths):
    path = paths[:, j]
    ko_day = n_days
    # 一個月後每日比價 KO
    for t in range(21, n_days):
        if path[t] >= ko_pct:
            ko_count += 1
            ko_day = t
            break
    # 累計到 KO 當日為止，有多少天高於 Strike
    accrual_days = np.sum(path[:ko_day] >= strike_pct)
    total_accrual_days += accrual_days

ko_prob = (ko_count / n_paths) * 100
avg_accrual_ratio = (total_accrual_days / n_paths) / n_days
expected_yield = coupon_rate * avg_accrual_ratio

# --- 6. Plotting (0% - 110% Zoom) ---
fig = go.Figure()
for j in range(n_paths):
    fig.add_trace(go.Scatter(y=paths[:, j], mode='lines', 
                             line=dict(width=0.5, color='rgba(255, 215, 0, 0.2)'), showlegend=False))

fig.add_hline(y=1.0, line_color="white", line_width=2)
fig.add_hline(y=ko_pct, line_dash="dash", line_color="#00FFA3", annotation_text="KO")
fig.add_hline(y=strike_pct, line_dash="dash", line_color="red", annotation_text="Floor")

fig.update_layout(
    height=380, template="plotly_dark",
    yaxis=dict(range=[0, 1.2], tickformat=".0%"), # 鎖定比例
    margin=dict(l=5, r=5, t=10, b=5)
)
st.plotly_chart(fig, use_container_width=True)

# --- 7. Result Card ---
st.markdown(f"""
    <div style="background-color: #1E1E1E; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; text-align: center;">
        <div style="display: flex; justify-content: space-around; margin-bottom: 10px;">
            <div>
                <p style="color: #FFD700; font-size: 14px; margin: 0;">🚀 KO Prob.</p>
                <p style="color: #FFF; font-size: 22px; font-weight: bold;">{ko_prob:.1f}%</p>
            </div>
            <div>
                <p style="color: #00FFA3; font-size: 14px; margin: 0;">📈 Exp. Yield</p>
                <p style="color: #FFF; font-size: 22px; font-weight: bold;">{expected_yield:.2f}%</p>
            </div>
        </div>
        <p style="color: #FFF; font-size: 28px; font-weight: bold;">{avg_accrual_ratio*100:.1f}% Days</p>
        <p style="color: #888; font-size: 11px;">Accrual stops if Knock-Out occurs.</p>
    </div>
    """, unsafe_allow_html=True)

# --- 8. Export PDF ---
if st.button("🚀 Export DRA Report"):
    st.balloons()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, f'DRA Audit: {ticker}', ln=True)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Current Price: ${current_p:,.2f}', ln=True)
    pdf.cell(0, 10, f'Exp. Accrual Ratio: {avg_accrual_ratio*100:.1f}% days', ln=True)
    pdf.cell(0, 10, f'Expected Annual Yield: {expected_yield:.2f}%', ln=True)
    pdf_out = pdf.output(dest='S').encode('latin-1')
    b64 = base64.b64encode(pdf_out).decode()
    st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="DRA_{ticker}.pdf">Download PDF</a>', unsafe_allow_html=True)
