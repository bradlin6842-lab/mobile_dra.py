import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

# --- 頁面配置 ---
st.set_page_config(page_title="DRA Daily Sentinel Pro", layout="centered")

# --- 自定義手機版 CSS ---
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #FFD700; font-weight: bold; }
    div[data-testid="stMetricLabel"] { font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

# --- 側邊欄強制重整功能 ---
if st.sidebar.button("🧹 清除緩存並重整數據"):
    st.cache_data.clear()
    st.rerun()

st.title("💰 DRA Daily Sentinel")
st.caption("Daily Range Accrual (Floor Only) - Mobile Pro")

# --- 1. 標的選擇 ---
input_tickers = st.text_input("Enter Tickers (e.g., NVDA, TSM, 6857.T, 9988.HK)", "NVDA, TSM, 6857.T, 9988.HK")
tickers = [t.strip().upper() for t in input_tickers.split(",") if t.strip()]
ticker = st.selectbox("🎯 Target Asset", tickers if tickers else ["NVDA"])

# --- 2. 超強效數據抓取邏輯 (同步 FCN 版本) ---
@st.cache_data(ttl=60)
def get_asset_info_ultra_dra(symbol):
    try:
        asset = yf.Ticker(symbol)
        
        # 價格抓取：優先抓 1 分鐘 K 線或最近 5 天歷史
        hist = asset.history(period="5d", interval="1m")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
        else:
            hist_d = asset.history(period="5d")
            price = hist_d['Close'].iloc[-1] if not hist_d.empty else 100.0
            
        # 指標抓取：Forward P/E 與 52 週數據
        try:
            info = asset.info
            name = info.get('longName', symbol)
            fpe = info.get('forwardPE', 'N/A') # 改為 Forward PE
            low52 = info.get('trailingFiftyTwoWeekLow', asset.fast_info.get('yearLow', 'N/A'))
            high52 = info.get('trailingFiftyTwoWeekHigh', asset.fast_info.get('yearHigh', 'N/A'))
        except:
            name = symbol
            fpe = low52 = high52 = 'N/A'

        return {
            "name": name,
            "curr": price,
            "fpe": fpe,
            "low52": low52,
            "high52": high52
        }
    except:
        return {"name": symbol, "curr": 100.0, "fpe": "N/A", "low52": "N/A", "high52": "N/A"}

asset_info = get_asset_info_ultra_dra(ticker)
current_p = asset_info['curr']

# --- 顯示基本資訊卡片 ---
st.subheader(f"🏢 {asset_info['name']}")
st.metric("Current Market Price", f"${current_p:,.2f}")

m1, m2, m3 = st.columns(3)
with m1: st.metric("Forward P/E", f"{asset_info['fpe']:.2f}" if isinstance(asset_info['fpe'], (int, float)) else "N/A")
with m2: st.metric("52W Low", f"${asset_info['low52']:,.1f}" if isinstance(asset_info['low52'], (int, float)) else "N/A")
with m3: st.metric("52W High", f"${asset_info['high52']:,.1f}" if isinstance(asset_info['high52'], (int, float)) else "N/A")

st.divider()

# --- 3. DRA 策略參數 ---
with st.container():
    st.subheader("⚙️ DRA Parameters")
    
    # 支援 No Floor (No KI) 選項
    no_floor_mode = st.toggle("🛡️ No Floor Mode (Always Accrual)", value=False)
    
    if no_floor_mode:
        strike_pct = 0.0
        st.success("No Floor Mode: Yield will accrue 100% of days (unless KO).")
    else:
        strike_pct = st.slider("Accrual Floor (Strike %)", 50, 100, 85) / 100
        
    ko_pct = st.slider("KO Level (Autocall %)", 80, 110, 103) / 100
    coupon_rate = st.number_input("Annualized Coupon (%)", value=15.0)

# --- 4. 波動率與模擬 (修正語法錯誤) ---
st.write("---")
vol_mode = st.radio("Volatility Period", ["30D (Sentinel)", "180D (Bank)"], horizontal=True)
hist_all = yf.Ticker(ticker).history(period="1y")

if len(hist_all) > 10:
    lookback = 30 if "30D" in vol_mode else 180
    target_data = hist_all.tail(lookback)
    # 修正：移除錯誤的 @ 符號
    sigma = np.log(target_data['Close'] / target_data['Close'].shift(1)).std() * np.sqrt(252)
else:
    sigma = 0.40

st.caption(f"📊 {vol_mode} Annual Volatility: {sigma:.1%}")

# 蒙地卡羅模擬 (500 條路徑)
n_days, n_paths, dt, mu = 180, 500, 1/252, 0.05
paths = np.ones((n_days, n_paths))
for i in range(1, n_days):
    # 採用標準 GBM 並混合肥尾分佈模擬真實風險
    Z = 0.8 * np.random.normal(0, 1, n_paths) + 0.2 * np.random.standard_t(df=3, size=n_paths)
    paths[i] = paths[i-1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z)

# 計算累積天數與預期收益 (若 KO 則停止累積)
total_accrual_days = 0
for j in range(n_paths):
    path = paths[:, j]
    ko_day = n_days
    # 一個月 (21天) 鎖定期後每日比價
    for t in range(21, n_days):
        if path[t] >= ko_pct:
            ko_day = t
            break
    # 累計到 KO 當日為止，有多少天高於 Floor
    accrual_days = np.sum(path[:ko_day] >= strike_pct)
    total_accrual_days += accrual_days

avg_accrual_ratio = (total_accrual_days / n_paths) / n_days
expected_yield = coupon_rate * avg_accrual_ratio

# --- 5. 繪圖 (Plotly) ---
fig = go.Figure()
for j in range(min(n_paths, 120)):
    fig.add_trace(go.Scatter(y=paths[:, j], mode='lines', 
                             line=dict(width=0.4, color='rgba(255, 215, 0, 0.2)'), showlegend=False))

fig.add_hline(y=1.0, line_color="white", line_width=2)
fig.add_hline(y=ko_pct, line_dash="dash", line_color="#00FFA3", annotation_text="KO Ref")
if not no_floor_mode:
    fig.add_hline(y=strike_pct, line_dash="dash", line_color="red", annotation_text="Floor")

fig.update_layout(
    height=380, template="plotly_dark",
    yaxis=dict(range=[0, 1.5], tickformat=".0%"),
    margin=dict(l=5, r=5, t=10, b=5),
    xaxis_title="Simulation Days"
)
st.plotly_chart(fig, use_container_width=True)

# --- 6. 結果卡片 ---
st.markdown(f"""
    <div style="background-color: #1E1E1E; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; text-align: center;">
        <p style="color: #FFD700; font-size: 16px; margin: 0;">📈 Expected Annual Yield</p>
        <p style="color: #FFFFFF; font-size: 36px; font-weight: bold; margin: 10px 0;">{expected_yield:.2f}%</p>
        <p style="color: #00FFA3; font-size: 18px;">{avg_accrual_ratio*100:.1f}% Accrual Days</p>
        <p style="color: #888; font-size: 11px;">Simulation based on 500 Daily Paths.</p>
    </div>
    """, unsafe_allow_html=True)
