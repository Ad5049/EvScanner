import os
import requests
import pandas as pd
import streamlit as st
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="⚡ +EV Personal Bookie Matcher",
    layout="wide"
)

BASE_URL = "https://api.theodds-api.com/v4/sports"
HARDCODED_API_KEY = "aa80562ae5fb97cfd71d78bc63a0cb1e"

# --- SIDEBAR SETTINGS ---
st.sidebar.header("⚙️ Bankroll & Filters")
operational_capital = st.sidebar.number_input("Operational Capital Base ($)", value=500.0, step=50.0)
base_unit_size = st.sidebar.number_input("Base Unit Size ($)", value=5.0, step=1.0)
min_edge = st.sidebar.slider("Minimum Edge (+EV %)", min_value=1.0, max_value=25.0, value=2.0, step=0.5)
max_odds_cap = st.sidebar.number_input("Max American Odds Cap (+400)", value=400, step=50)

include_props = st.checkbox("Include Player Props Scanning", value=False)
exclude_started = st.checkbox("Exclude Live / Started Games", value=True)
debug_mode = st.sidebar.checkbox("Show Raw Diagnostic Feed", value=True)

PERSONAL_BOOKS = [
    "draftkings",
    "hardrockbet_fl",
    "bovada",
    "mybookieag",
    "fliff",
    "novig"
]

# --- GUARANTEED ACTIVE SPORTS SLUGS ---
TARGET_SPORTS = [
    "baseball_mlb",
    "icehockey_nhl",
    "basketball_nba",
    "americanfootball_nfl"
]

# --- DATA FETCHING LAYER ---
def fetch_odds_data(api_key, sport_keys, progress_bar, status_text):
    if not sport_keys:
        return [], None
    
    all_raw_data = []
    remaining_credits = None
    markets = "h2h,spreads,totals"
    if include_props:
        markets += ",player_props"
        
    total_steps = len(sport_keys)
    for idx, sport_key in enumerate(sport_keys):
        status_text.text(f"Scanning sport feed [{idx + 1}/{total_steps}]: querying {sport_key}...")
        progress_bar.progress((idx + 1) / total_steps)
        
        url = f"{BASE_URL}/{sport_key}/odds/"
        params = {
            "apiKey": api_key,
            - "markets": markets,
            "oddsFormat": "american",
        }
        try:
            response = requests.get(url, params=params)
            if 'x-requests-remaining' in response.headers:
                remaining_credits = response.headers['x-requests-remaining']
                
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    all_raw_data.extend(data)
        except Exception:
            continue
            
    time.sleep(0.3)
    status_text.text(f"Scan complete! Downloaded {len(all_raw_data)} raw market events.")
    return all_raw_data, remaining_credits

# --- CONVERT AMERICAN ODDS TO PROBABILITY ---
def american_to_prob(odds):
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

# --- +EV ENGINE & PERSONAL BOOK MATCHER ---
def process_and_filter_markets(raw_data):
    rows = []
    debug_rows = []
    
    for event in raw_data:
        home_team = event.get('home_team')
        away_team = event.get('away_team')
        commence_time = event.get('commence_time')
        sport_title = event.get('sport_title', 'Sport')
        
        bookmakers = event.get('bookmakers', [])
        if not bookmakers:
            continue
            
        outcome_prices = {}
        for book in bookmakers:
            book_key = book.get('key')
            for market in book.get('markets', []):
                m_key = market.get('key')
                for outcome in market.get('outcomes', []):
                    name = outcome.get('name')
                    price = outcome.get('price')
                    point = outcome.get('point', None)
                    key_id = (m_key, name, point)
                    
                    if key_id not in outcome_prices:
                        outcome_prices[key_id] = []
                    if price:
                        outcome_prices[key_id].append(price)
                        
                    if book_key in PERSONAL_BOOKS and price:
                        debug_rows.append({
                            "Sport": sport_title,
                            "Book": book_key.upper(),
                            "Matchup": f"{away_team} @ {home_team}",
                            "Market": m_key.upper(),
                            "Selection": name,
                            "Price": price
                        })
                        
        for bookmaker in bookmakers:
            book_key = bookmaker.get('key')
            if book_key not in PERSONAL_BOOKS:
                continue
                
            for market in bookmaker.get('markets', []):
                market_key = market.get('key')
                for outcome in market.get('outcomes', []):
                    price = outcome.get('price')
                    point = outcome.get('point', None)
                    name = outcome.get('name')
                    key_id = (market_key, name, point)
                    
                    if price and (price <= max_odds_cap):
                        all_prices = outcome_prices.get(key_id, [])
                        if len(all_prices) >= 2:
                            probs = [american_to_prob(p) for p in all_prices if p]
                            if not probs:
                                continue
                            avg_market_prob = sum(probs) / len(probs)
                            book_prob = american_to_prob(price)
                            
                            ev_edge = round((avg_market_prob - book_prob) * 100, 2)
                            avg_price = sum(all_prices) / len(all_prices)
                            price_edge = round(((price - avg_price) / abs(avg_price)) * 100, 2) if avg_price != 0 else 0.0
                            effective_edge = max(ev_edge, price_edge)
                            
                            if effective_edge >= min_edge:
                                rows.append({
                                    "Sport": sport_title,
                                    "Time": commence_time,
                                    "Actionable Book": book_key.upper(),
                                    "Matchup": f"{away_team} @ {home_team}",
                                    "Market": market_key.upper(),
                                    "Selection": name,
                                    "Price": price,
                                    "Point": point if point is not None else "-",
                                    "Est. Edge (%)": f"+{effective_edge}%",
                                    "Unit Stake": f"${base_unit_size:.2f}"
                                })
                                
    return pd.DataFrame(rows).drop_duplicates(), pd.DataFrame(debug_rows).drop_duplicates()

# --- MAIN APP INTERFACE ---
def main():
    st.title("⚡ +EV Personal Bookie Matcher")
    
    st.markdown("### Actionable Board Controls")
    col1, col2 = st.columns([1, 4])
    with col1:
        run_scan = st.button("🚀 Scan All Books & Match Plays", type="primary", use_container_width=True)
    with col2:
        st.write("Scans all available bookmaker lines, computes market consensus value, and isolates bets available on **DraftKings, Hard Rock FL, Bovada, MyBookie, Fliff, and Novig**.")
        
    st.markdown("---")
    
    if run_scan:
        st.cache_data.clear()
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        raw_data, credits_left = fetch_odds_data(HARDCODED_API_KEY, TARGET_SPORTS, progress_bar, status_text)
        
        progress_bar.empty()
        status_text.empty()
        
        df_plays, df_debug = process_and_filter_markets(raw_data)
        
        if credits_left:
            st.sidebar.success(f"API Quota Remaining: {credits_left} credits")
            
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Raw Events Downloaded", len(raw_data))
        col_m2.metric("Personal Book Lines Scanned", len(df_debug))
        col_m3.metric("Actionable +EV Plays Found", len(df_plays))
        
        if not df_plays.empty:
            st.success(f"Found {len(df_plays)} actionable plays matching your criteria.")
            st.dataframe(df_plays, use_container_width=True, height=400)
        else:
            st.warning("Scan completed successfully, but no lines cleared the minimum edge threshold across your personal books.")
            
        if debug_mode and not df_debug.empty:
            with st.expander("🔍 Raw Personal Book Lines Feed (Debug View)"):
                st.dataframe(df_debug, use_container_width=True, height=300)
    else:
        st.info("Ready. Click **🚀 Scan All Books & Match Plays** above to execute the board sweep.")

if __name__ == "__main__":
    main()
    
