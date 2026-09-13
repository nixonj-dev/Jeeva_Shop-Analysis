import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import datetime
import numpy as np
import json

def fetch_raw_data():
    """Fetches customer, location, and item data from all portfolios, plus outer shop status."""
    conn = sqlite3.connect('users.db')
    
    # 1. Fetch Loan Data including District, Post, Pincode, and Items
    queries = [
        "SELECT form_no, name, phone, address, District as district, post, pincode, items, loan_date, total_given_amount, present_amount, status, 'Gold' as item_category, 'Normal' as portfolio FROM gold_loan",
        "SELECT form_no, name, phone, address, District as district, post, pincode, items, loan_date, total_given_amount, present_amount, status, 'Silver' as item_category, 'Normal' as portfolio FROM silver_loan",
        "SELECT form_no, name, phone, address, District as district, post, pincode, items, loan_date, total_given_amount, present_amount, status, 'Gold' as item_category, 'Big' as portfolio FROM BigLoanGold",
        "SELECT form_no, name, phone, address, District as district, post, pincode, items, loan_date, total_given_amount, present_amount, status, 'Silver' as item_category, 'Big' as portfolio FROM BigLoanSilver",
        "SELECT form_no, name, phone, address, District as district, post, pincode, items, loan_date, total_given_amount, present_amount, status, 'Gold' as item_category, 'Box' as portfolio FROM BoxLoanGold",
        "SELECT form_no, name, phone, address, District as district, post, pincode, items, loan_date, total_given_amount, present_amount, status, 'Silver' as item_category, 'Box' as portfolio FROM BoxLoanSilver"
    ]
    
    dfs = []
    for q in queries:
        try:
            df = pd.read_sql_query(q, conn)
            dfs.append(df)
        except Exception:
            pass
            
    # 2. Fetch Active Outer Transactions to check Storage Status
    try:
        outer_df = pd.read_sql_query("SELECT loan_nos FROM outer_transactions WHERE LOWER(outer_loan_status) = 'active'", conn)
        active_outer = set()
        for nos in outer_df['loan_nos'].dropna():
            active_outer.update([n.strip() for n in str(nos).split(',')])
    except Exception:
        active_outer = set()
        
    conn.close()
    
    if not dfs: return pd.DataFrame(), set()
    return pd.concat(dfs, ignore_index=True), active_outer

def format_currency(val):
    if pd.isna(val): return "₹ 0"
    return f"₹ {val:,.0f}"

def render_insight(status, title, why, action):
    if status == "GOOD":
        st.success(f"✅ **{title}**\n\n**Insight:** {why}\n\n**Action:** {action}")
    elif status == "AVG":
        st.warning(f"⚠️ **{title}**\n\n**Insight:** {why}\n\n**Action:** {action}")
    else:
        st.error(f"🚨 **{title}**\n\n**Insight:** {why}\n\n**Action:** {action}")

def render():
    st.title("📊 Google Analytics: Business Intelligence Hub")
    st.info("💡 **Enterprise Mode:** Deep analytics separated into Customer Behavior, Territory Location, and Inventory Weight tracking (In-Shop vs Outer).")

    raw_data, active_outer = fetch_raw_data()
    if raw_data.empty:
        st.warning("No data found in the database.")
        return

    # --- DATA CLEANING & PARSING ---
    raw_data['total_given_amount'] = pd.to_numeric(raw_data['total_given_amount'], errors='coerce').fillna(0)
    raw_data['present_amount'] = pd.to_numeric(raw_data['present_amount'], errors='coerce').fillna(0)
    raw_data['phone'] = raw_data['phone'].astype(str).str.strip().str.replace('.0', '', regex=False)
    raw_data = raw_data[raw_data['phone'].str.len() >= 5] 
    raw_data['date_parsed'] = pd.to_datetime(raw_data['loan_date'], format='%d/%m/%Y', errors='coerce')
    raw_data = raw_data.dropna(subset=['date_parsed'])
    
    # Location Cleaning
    for col in ['address', 'post', 'district', 'pincode']:
        raw_data[col] = raw_data[col].astype(str).str.strip().str.title()
        raw_data[col] = raw_data[col].replace(['', 'Nan', 'None'], 'Unknown')

    # Storage Status (In Shop vs Outer Shop)
    raw_data['Storage'] = np.where(raw_data['form_no'].isin(active_outer), 'Outer Shop', 'In Shop')

    # --- DATE FILTER ---
    db_min = raw_data['date_parsed'].min().date()
    db_max = raw_data['date_parsed'].max().date()
    today = datetime.date.today()
    current_year_start = datetime.date(today.year, 1, 1)
    
    allowed_min = min(db_min, current_year_start)
    allowed_max = max(db_max, today)
    
    col_d1, _ = st.columns([1, 3])
    with col_d1:
        date_range = st.date_input("📅 Select Analysis Window:", value=(max(db_min, current_year_start), min(db_max, today)), min_value=allowed_min, max_value=allowed_max)

    if len(date_range) != 2: return 
    sd, ed = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

    filtered_data = raw_data[(raw_data['date_parsed'] >= sd) & (raw_data['date_parsed'] <= ed)].copy()
    if filtered_data.empty:
        st.warning("No activity found in the selected date range.")
        return

    st.write("---")

    # =====================================================================
    # TAB ROUTING
    # =====================================================================
    tab_ga, tab_loc, tab_inv = st.tabs([
        "📈 Google Analytics (Behavior)", 
        "📍 Territory & Location", 
        "⚖️ Inventory & Weight Intelligence"
    ])

    # =====================================================================
    # TAB 1: GOOGLE ANALYTICS (Customer Behavior)
    # =====================================================================
    with tab_ga:
        # 🟢 FIX: Added Customer_Place back into the aggregation!
        customer_profiles = filtered_data.groupby('phone').agg(
            Customer_Name=('name', lambda x: x.mode()[0] if not x.mode().empty else x.iloc[0]),
            Customer_Place=('address', lambda x: x.mode()[0] if not x.mode().empty else 'Unknown'),
            Total_Loans=('form_no', 'count'),
            Lifetime_Value=('total_given_amount', 'sum'),
            Current_Active_Debt=('present_amount', 'sum'),
            First_Visit=('date_parsed', 'min'),
            Last_Visit=('date_parsed', 'max'),
            Items_Used=('item_category', lambda x: ','.join(sorted(set(x.dropna()))))
        ).reset_index()

        customer_profiles['Days_Since_Last_Visit'] = (pd.to_datetime(today) - customer_profiles['Last_Visit']).dt.days
        
        # Category Definitions
        def assign_tier(amount):
            if amount >= 500000: return '👑 VIP (5L+)'
            elif amount >= 100000: return '💎 Platinum (1L - 5L)'
            elif amount >= 50000: return '🥇 Gold (50K - 1L)'
            else: return '🥈 Standard (< 50K)'
        customer_profiles['Customer_Tier'] = customer_profiles['Lifetime_Value'].apply(assign_tier)

        def assign_retention(days):
            if days <= 90: return '🟢 Active (< 3M)'
            elif days <= 180: return '🟡 Slipping (3-6M)'
            elif days <= 365: return '🟠 At Risk (6-12M)'
            else: return '🔴 Dormant (> 1Y)'
        customer_profiles['Retention_Status'] = customer_profiles['Days_Since_Last_Visit'].apply(assign_retention)

        # Tab Metrics
        t_cust = len(customer_profiles)
        rep_rate = (len(customer_profiles[customer_profiles['Total_Loans'] > 1]) / t_cust * 100) if t_cust > 0 else 0

        st.markdown("### 📊 Audience Overview")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Unique Customers", f"{t_cust:,}")
        k2.metric("Repeat Cust. Rate", f"{rep_rate:.1f}%")
        k3.metric("Avg Lifetime Value", format_currency(customer_profiles['Lifetime_Value'].mean()))
        k4.metric("Avg Active Debt", format_currency(customer_profiles['Current_Active_Debt'].mean()))
        st.write("---")

        # Nested Sub-Tabs for clean Google Analytics feel
        ga_pareto, ga_churn, ga_cross, ga_season, ga_db = st.tabs(["⚖️ Pareto (80/20)", "🚨 Churn Risk", "🔁 Cross-Sell", "📅 Seasonality", "🏆 Watchlist & DB"])

        with ga_pareto:
            c1, c2 = st.columns(2)
            with c1:
                pareto_df = customer_profiles.sort_values('Lifetime_Value', ascending=False).copy()
                pareto_df['Cumulative_Pct'] = (pareto_df['Lifetime_Value'].cumsum() / pareto_df['Lifetime_Value'].sum()) * 100
                pareto_df['Customer_Rank_Pct'] = (np.arange(1, len(pareto_df)+1) / len(pareto_df)) * 100
                top_20_share = pareto_df[pareto_df['Customer_Rank_Pct'] <= 20]['Cumulative_Pct'].max() if len(pareto_df) >= 5 else 100
                
                render_insight(
                    "GOOD" if 65 <= top_20_share <= 85 else ("AVG" if top_20_share < 65 else "BAD"),
                    "Wealth Distribution (Lorenz Curve)",
                    f"Top 20% of users generate {top_20_share:.1f}% of revenue.",
                    "Maintain VIP focus." if 65 <= top_20_share <= 85 else "Diversify acquisition marketing."
                )
                fig_pareto = px.area(pareto_df, x='Customer_Rank_Pct', y='Cumulative_Pct', title="Revenue Reliance")
                st.plotly_chart(fig_pareto, use_container_width=True)
            with c2:
                top_10_debt = pareto_df.head(max(1, int(len(pareto_df) * 0.10)))['Current_Active_Debt'].sum()
                total_debt = pareto_df['Current_Active_Debt'].sum()
                whale_risk = (top_10_debt / total_debt * 100) if total_debt > 0 else 0
                
                render_insight(
                    "GOOD" if whale_risk <= 40 else ("BAD" if whale_risk > 60 else "AVG"),
                    "Active Debt Concentration",
                    f"Top 10% VIPs hold {whale_risk:.1f}% of active debt.",
                    "Healthy distribution." if whale_risk <= 40 else "Reduce limits for specific VIPs."
                )
                fig_debt = px.pie(names=["Top 10% VIPs", "Bottom 90%"], values=[top_10_debt, total_debt - top_10_debt], hole=0.5, color_discrete_sequence=["#d62728", "#1f77b4"])
                st.plotly_chart(fig_debt, use_container_width=True)

        with ga_churn:
            high_value = customer_profiles[customer_profiles['Lifetime_Value'] >= 50000]
            flight_risk_pct = (len(high_value[high_value['Days_Since_Last_Visit'] > 180]) / len(high_value) * 100) if not high_value.empty else 0
            render_insight("GOOD" if flight_risk_pct <= 15 else "BAD", "VIP Flight Risk", f"{flight_risk_pct:.1f}% of High-Value users are dormant.", "Send re-engagement offers.")
            
            fig_scatter = px.scatter(customer_profiles, x="Days_Since_Last_Visit", y="Lifetime_Value", color="Retention_Status", hover_data=['Customer_Name', 'phone'], title="Flight Risk Matrix", color_discrete_map={'🟢 Active (< 3M)': '#2ca02c', '🟡 Slipping (3-6M)': '#bcbd22', '🟠 At Risk (6-12M)': '#ff7f0e', '🔴 Dormant (> 1Y)': '#d62728'})
            st.plotly_chart(fig_scatter, use_container_width=True)

        with ga_cross:
            customer_profiles['Affinity'] = customer_profiles['Items_Used'].apply(lambda x: 'Hybrid (Both)' if 'Gold' in str(x) and 'Silver' in str(x) else x)
            hybrid_pct = (len(customer_profiles[customer_profiles['Affinity'] == 'Hybrid (Both)']) / t_cust * 100) if t_cust > 0 else 0
            render_insight("GOOD" if hybrid_pct >= 15 else "AVG", "Cross-Sell Affinity", f"{hybrid_pct:.1f}% pledge both Gold and Silver.", "Promote Silver rates to Gold users.")
            
            aff_df = customer_profiles['Affinity'].value_counts().reset_index()
            fig_aff = px.pie(aff_df, names='Affinity', values='count', hole=0.5, color='Affinity', color_discrete_map={"Gold": "#FFD700", "Silver": "#C0C0C0", "Hybrid (Both)": "#1f77b4"})
            st.plotly_chart(fig_aff, use_container_width=True)

        with ga_season:
            customer_profiles['Month_Name'] = customer_profiles['First_Visit'].dt.month_name()
            season_df = customer_profiles.groupby('Month_Name').size().reset_index(name='Count')
            if not season_df.empty:
                months_order = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
                season_df['Month_Name'] = pd.Categorical(season_df['Month_Name'], categories=months_order, ordered=True)
                season_df = season_df.sort_values('Month_Name')
                fig_sea = px.bar(season_df, x='Month_Name', y='Count', title="User Acquisition Heatmap", color='Count', color_continuous_scale="Blues")
                st.plotly_chart(fig_sea, use_container_width=True)

        with ga_db:
            st.markdown("#### 🏆 VIP Watchlist & Master CRM")
            
            # Format Data for the final DB view
            master_disp = customer_profiles.copy()
            for col in ['Lifetime_Value', 'Current_Active_Debt']:
                master_disp[col] = master_disp[col].apply(lambda x: f"₹ {x:,.0f}")
                
            master_disp = master_disp.rename(columns={
                'phone': 'Mobile', 'Customer_Name': 'Name', 'Customer_Place': 'Location', 'Total_Loans': 'Loans',
                'Lifetime_Value': 'LTV (₹)', 'Current_Active_Debt': 'Active Debt (₹)',
                'Customer_Tier': 'Tier', 'Retention_Status': 'Status'
            })
            
            f_cols = ['Tier', 'Name', 'Mobile', 'Location', 'Status', 'Loans', 'LTV (₹)', 'Active Debt (₹)']
            st.dataframe(master_disp.sort_values('Loans', ascending=False)[f_cols], hide_index=True, use_container_width=True)


    # =====================================================================
    # TAB 2: TERRITORY & LOCATION
    # =====================================================================
    with tab_loc:
        # Grouping strictly by Post first, then Address
        loc_df = filtered_data.groupby(['post', 'address', 'district', 'pincode']).agg(
            Unique_Customers=('phone', 'nunique'),
            Total_Loans=('form_no', 'count'),
            Total_Dispersed=('total_given_amount', 'sum'),
            Active_Capital=('present_amount', 'sum')
        ).reset_index().sort_values(['Total_Dispersed'], ascending=[False])

        st.markdown("### 📍 Territory Dominance")
        
        l1, l2, l3 = st.columns(3)
        l1.metric("Top Post Office", loc_df.iloc[0]['post'] if not loc_df.empty else "N/A")
        l2.metric("Top Street/Address", loc_df.iloc[0]['address'] if not loc_df.empty else "N/A")
        l3.metric("Total Territories Reached", len(loc_df))
        st.write("---")

        c_loc1, c_loc2 = st.columns(2)
        with c_loc1:
            fig_loc_bar = px.bar(
                loc_df.head(15), 
                x='address', 
                y='Total_Dispersed',
                color='post',
                title="Top 15 Streets by Capital Dispersed (Colored by Post)",
                labels={'address': 'Address', 'Total_Dispersed': 'Capital (₹)'}
            )
            st.plotly_chart(fig_loc_bar, use_container_width=True)
            
        with c_loc2:
            fig_sun_loc = px.sunburst(
                loc_df[loc_df['Total_Dispersed'] > 0], 
                path=['district', 'post', 'address'], 
                values='Total_Dispersed',
                title="Territory Hierarchy (District -> Post -> Address)"
            )
            st.plotly_chart(fig_sun_loc, use_container_width=True)
            
        st.markdown("#### 📋 Detailed Territory Ledger")
        st.dataframe(loc_df[['district', 'post', 'address', 'pincode', 'Unique_Customers', 'Total_Loans', 'Total_Dispersed']], hide_index=True, use_container_width=True)


    # =====================================================================
    # TAB 3: INVENTORY & WEIGHT INTELLIGENCE
    # =====================================================================
    with tab_inv:
        # Advanced JSON Parsing for Items
        item_records = []
        for _, row in filtered_data.iterrows():
            if pd.notna(row['items']) and str(row['items']).strip() != "":
                try:
                    items_json = json.loads(row['items'])
                    for itm in items_json:
                        w = float(itm.get('weight', 0))
                        item_records.append({
                            'Item_Name': str(itm.get('name', '')).strip().title(),
                            'Weight_g': w,
                            'Qty': int(itm.get('qty', 1)),
                            'Category': row['item_category'],
                            'Portfolio': row['portfolio'],
                            'Storage': row['Storage'],
                            'Status': row['status']
                        })
                except Exception:
                    pass
                    
        items_df = pd.DataFrame(item_records)
        
        if items_df.empty:
            st.warning("No item weight data could be parsed for this period.")
            return

        # Filter only Active/Overdue items for accurate physical safe tracking
        live_items = items_df[items_df['Status'].str.lower().isin(['active', 'overdue'])]

        t_gold_w = live_items[live_items['Category'] == 'Gold']['Weight_g'].sum()
        t_silv_w = live_items[live_items['Category'] == 'Silver']['Weight_g'].sum()
        
        shop_items = live_items[live_items['Storage'] == 'In Shop']['Qty'].sum()
        outer_items = live_items[live_items['Storage'] == 'Outer Shop']['Qty'].sum()

        st.markdown("### ⚖️ Live Physical Inventory Tracking")
        st.info("Tracks the exact physical weight of items currently held as collateral. (Excludes Closed/Sold loans).")

        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Total Gold Weight", f"{t_gold_w:,.2f} g")
        i2.metric("Total Silver Weight", f"{t_silv_w:,.2f} g")
        i3.metric("Items In Safe", f"{shop_items} qty", delta="Shop")
        i4.metric("Items In Outer Shop", f"{outer_items} qty", delta="-Risk", delta_color="inverse")
        st.write("---")

        # Grouping: Category -> Portfolio -> Storage -> Item
        inv_summary = live_items.groupby(['Category', 'Portfolio', 'Storage', 'Item_Name']).agg(
            Total_Weight=('Weight_g', 'sum'),
            Mean_Weight=('Weight_g', 'mean'),
            Total_Qty=('Qty', 'sum')
        ).reset_index().sort_values('Total_Weight', ascending=False)

        # Format floats
        inv_summary['Total_Weight'] = inv_summary['Total_Weight'].round(3)
        inv_summary['Mean_Weight'] = inv_summary['Mean_Weight'].round(3)

        c_inv1, c_inv2 = st.columns(2)
        with c_inv1:
            fig_sun_inv = px.sunburst(
                inv_summary, 
                path=['Category', 'Portfolio', 'Storage', 'Item_Name'], 
                values='Total_Weight',
                title="Weight Distribution Hierarchy",
                color='Category',
                color_discrete_map={"Gold": "#FFD700", "Silver": "#C0C0C0"}
            )
            st.plotly_chart(fig_sun_inv, use_container_width=True)

        with c_inv2:
            storage_risk = live_items.groupby(['Category', 'Storage'])['Weight_g'].sum().reset_index()
            fig_bar_risk = px.bar(
                storage_risk, 
                x="Category", 
                y="Weight_g", 
                color="Storage", 
                barmode="group",
                title="Physical Storage Risk (In Shop vs Outer)",
                color_discrete_map={"In Shop": "#2ca02c", "Outer Shop": "#d62728"}
            )
            st.plotly_chart(fig_bar_risk, use_container_width=True)

        st.markdown("#### 📋 Detailed Inventory Ledger")
        
        st.markdown("##### 🪙 GOLD INVENTORY")
        st.dataframe(inv_summary[inv_summary['Category'] == 'Gold'].drop(columns=['Category']), hide_index=True, use_container_width=True)
        
        st.markdown("##### 🥈 SILVER INVENTORY")
        st.dataframe(inv_summary[inv_summary['Category'] == 'Silver'].drop(columns=['Category']), hide_index=True, use_container_width=True)