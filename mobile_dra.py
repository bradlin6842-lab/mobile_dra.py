import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import random
import base64
from fpdf import FPDF

# --- Page Configuration ---
st.set_page_config(page_title="DRA Sentinel Pro", layout="centered")

# --- Custom CSS for iPhone 15 Plus Display ---
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    div[data-testid="stMetricValue"] { font-size: 22px; color: #FFD700; }
    div[data-testid="stMetricLabel"] { font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

# --- Header ---
st.title("💰 DRA Daily Sentinel")
st.caption("Daily Range Accrual (Floor Only) - Mobile Pro")

# --- 1. Asset Selection ---
input_tickers = st.text_input("Enter Tickers (e.g., NVDA, TSM, 6857.T, 9988.HK)", "NVDA, TSM, 6857.T, 9988.HK")
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
if not tickers: tickers = ["NVDA"]
ticker = st.selectbox("🎯 Target Asset", tickers)

# --- 2. Robust Data Fetching ---
@st.cache_data(ttl=60)
def get_asset_info_safe(symbol):
    try:
        asset = yf.Ticker(symbol)
        
        # 1. 優先抓取最近 1 分鐘 K 線 (解決日、港、美股現價出錯問題)
        hist = asset.history(period="1d", interval="1m")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
        else:
            # 2. 備案：fast_info
            price = asset.fast_info.get('last_price')
            
        # 3. 最終保險：regularMarketPrice
        if price is None or price <= 0 or price == 100.0:
            price = asset.info.get('regularMarketPrice', 100.0)

        # 抓取基本資訊
        full_info = asset.info
        return {
            "name": full_info.get('longName', symbol),
            "pe": full_info.get('trailingPE', 'N/A'),
            "low52": asset.fast_info.get('yearLow', 0),
            "high52": asset.fast_info.get('yearHigh', 0),
            "curr": price
        }
    except:
        return {"name": symbol, "pe": "N/A", "low52": 0, "high52": 0, "curr": 100.0}

# 抓取資料後的調用邏輯 (對應你原本的 54-59 行)
asset_info = get_asset_info_safe(ticker) if ticker else {"name": "Select Asset", "pe": "N/A", "low52": 0, "high52": 0, "curr": 100.0}
current_p = asset_info['curr']

# Display Asset Info Card
st.subheader(f"🏢 {asset_info['name']}")
m1, m2, m3 = st.columns(3)
with m1: st.metric("P/E Ratio", f"{asset_info['pe']:.2f}" if isinstance(asset_info['pe'], (int, float)) else "N/A")
with m2: st.metric("52W Low", f"${asset_info['low52']:,.1f}")
with m3: st.metric("52W High", f"${asset_info['high52']:,.1f}")

st.divider()

# --- 3. DRA Strategy Settings ---
with st.container():
    st.subheader("⚙️ DRA Parameters")
    strike_pct = st.slider("Accrual Floor (Strike %)", 50, 100, 85) / 100
    coupon_rate = st.number_input("Annualized Coupon (%)", value=15.0)
    st.metric("Accrual Price Floor", f"${current_p * strike_pct:,.2f}")

# --- 4. Volatility Engine (Updated to match FCN style) ---
st.subheader("📉 Risk Path Simulation")
vol_mode = st.radio("Volatility Period", ["30D (Sentinel)", "180D (Bank)"], horizontal=True)
period_map = {"30D (Sentinel)": "1mo", "180D (Bank)": "6mo"}

hist_data = yf.Ticker(ticker).history(period=period_map[vol_mode])
if len(hist_data) > 10:
    log_returns = np.log(hist_data['Close'] / hist_data['Close'].shift(1))
    sigma = log_returns.std() * np.sqrt(252)
    sigma = max(min(sigma, 0.9), 0.1) # 限制範圍防異常
else:
    sigma = 0.35

# 重要：在畫面上秀出 Volatility
st.caption(f"📊 Mode: {vol_mode} | Annual Volatility: {sigma:.1%}")

# --- 5. Monte Carlo Simulation ---
n_days, n_paths, dt, mu = 180, 100, 1/252, 0.05
paths = np.ones((n_days, n_paths))
for i in range(1, n_days):
    shocks = np.random.standard_t(df=3, size=n_paths) * 0.7 
    paths[i] = paths[i-1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks)

# --- 6. Plotting (Fixed Y-Axis 0% - 100%+) ---
fig = go.Figure()
for j in range(n_paths):
    fig.add_trace(go.Scatter(y=paths[:, j], mode='lines', 
                             line=dict(width=0.5, color='rgba(255, 215, 0, 0.2)'), showlegend=False))

fig.add_hline(y=1.0, line_color="white", line_width=2)
fig.add_hline(y=strike_pct, line_dash="dash", line_color="red", 
              annotation_text="Floor", annotation_position="bottom right")

fig.update_layout(
    height=350, template="plotly_dark",
    xaxis_title="Forward Days", yaxis_title="Price Ratio",
    yaxis=dict(range=[0, 1.1], tickformat=".0%"), # 鎖定 Y 軸範圍在 0% 到 110%
    margin=dict(l=5, r=5, t=10, b=5)
)
st.plotly_chart(fig, use_container_width=True)

# --- 7. Accrual Calculation & Result Card ---
daily_accrual = paths >= strike_pct
accrual_days_per_path = np.sum(daily_accrual, axis=0)
avg_accrual_ratio = np.mean(accrual_days_per_path) / n_days
expected_yield = coupon_rate * avg_accrual_ratio

st.markdown(f"""
    <div style="background-color: #1E1E1E; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; text-align: center; margin-bottom: 20px;">
        <p style="color: #FFD700; font-size: 16px; margin: 0;">📊 Expected Accrual Performance</p>
        <p style="color: #FFFFFF; font-size: 32px; font-weight: bold; margin: 10px 0;">{avg_accrual_ratio*100:.1f}% Days</p>
        <p style="color: #FFFFFF; font-size: 18px;">Exp. Annual Yield: <span style="color: #00FFA3;">{expected_yield:.2f}%</span></p>
        <p style="color: #888888; font-size: 11px;">Simulation: 100 paths | Student's t-dist</p>
    </div>
    """, unsafe_allow_html=True)
