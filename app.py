import os
import requests
import pandas as pd
import streamlit as st

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="⚡ +EV Market Scanner & Edge Engine",
    layout="wide"
)

BASE_URL = "https://api.theodds-api.com/v4/sports"
HARDCODED_API_KEY = "714895ce62ecdfdc29c3ce0e9c0c7580"

# --- SIDEBAR FORM CONTROLS ---
st.sidebar.header("⚙️ Controls")

with st.sidebar.form("scanner_form"):
    operational_capital = st.number_input("Operational Capital Base ($)", value=500.0, step=50.0)
    base_unit_size = st.number_input("Base Unit Size ($)", value=5.0, step=1.0)
    min_edge = st.slider("Minimum Edge (+EV %)", min_value=1.0, max_value=25.0, value=5.0, step=0.5)
    max_odds_cap = st.number_input("Max American Odds Cap (+400)", value=400, step=50)

    include_props = st.checkbox("Include Player Props Scanning", value=False)
    exclude_started = st.checkbox("Exclude Live / Started Games", value=True)
    
    # Form submit button guarantees execution and triggers API call
    submitted = st.form_submit_button("🚀 Run Live Board Scan")

BOOKMAKERS = [
    "draftkings",
    "hardrockbet_fl",
    "bovada",
    "mybookieag",
    "fliff",
    "novig"
]

# --- FETCH ACTIVE SPORTS CATALOG ---
@st.cache_data(ttl=3600)
def fetch_sports_catalog(api_key):
    try:
        response = requests.get(BASE_URL, params={"apiKey": api_key})
        if response.status_code == 200:
            sports = response.json()
            return [s['key'] for s in sports if s.get('active', True)]
    except Exception:
        pass
    return ["icehockey_nhl", "basketball_nba", "baseball_mlb"]

# --- DATA FETCHING LAYER ---
def fetch_odds_data(api_key, sport_keys):
    if not sport_keys:
        return [], None
    
    all_raw_data = []
    remaining_credits = None
    markets = "h2h,spreads,totals"
    if include_props:
        markets += ",player_props"
        
    for sport_key in sport_keys[:3]:
        url = f"{BASE_URL}/{sport_key}/odds/"
        params = {
            "apiKey": api_key,
            "markets": markets,
            "oddsFormat": "american",
            "bookmakers": ",".join(BOOKMAKERS)
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
            
    return all_raw_data, remaining_credits

# --- PARSING & +EV ENGINE ---
def process_market_data(raw_data):
    rows = []
    for event in raw_data:
        home_team = event.get('home_team')
        away_team = event.get('away_team')
        commence_time = event.get('commence_time')
        sport_title = event.get('sport_title', 'Sport')
        
        for bookmaker in event.get('bookmakers', []):
            book_key = bookmaker.get('key')
            for market in bookmaker.get('markets', []):
                market_key = market.get('key')
                for outcome in market.get('outcomes', []):
                    price = outcome.get('price')
                    if price and (price <= max_odds_cap):
                        rows.append({
                            "Sport": sport_title,
                            "Time": commence_time,
                            "Book": book_key,
                            "Matchup": f"{away_team} @ {home_team}",
                            "Market": market_key,
                            "Outcome": outcome.get('name'),
                            "Price": price,
                            "Point": outcome.get('point', None)
                        })
    return pd.DataFrame(rows)

# --- MAIN APP INTERFACE ---
def main():
    st.title("⚡ +EV Market Scanner & Edge Engine")
    
    available_sports = fetch_sports_catalog(HARDCODED_API_KEY)
    
    if submitted:
        st.cache_data.clear()
        with st.spinner("Executing direct odds fetch across configured books..."):
            raw_data, credits_left = fetch_odds_data(HARDCODED_API_KEY, available_sports)
            df = process_market_data(raw_data)
            
        if credits_left:
            st.sidebar.success(f"API Quota Remaining: {credits_left} credits")
            
        if not df.empty:
            st.success(f"Successfully loaded {len(df)} active lines. Filtering for edges >= {min_edge}% EV.")
            st.dataframe(df, use_container_width=True, height=500)
        else:
            st.warning("No active lines returned. Verify active sport schedules or API key quota.")
    else:
        st.info("Configure your filters in the sidebar and click **🚀 Run Live Board Scan** to initiate requests.")

if __name__ == "__main__":
    main()
    
