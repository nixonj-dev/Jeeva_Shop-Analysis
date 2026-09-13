import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import datetime
import numpy as np
import json

def fetch_tally_data():
    """Fetches data from the FinalTally table in the database."""
    conn = sqlite3.connect('users.db')
    try:
        # Fetching the exact columns needed for the analysis
        query = """
        SELECT tally_date, capital_by_system, capital_by_owner, 
               gpay_by_system, denomination_details, final_tally_amount
        FROM FinalTally
        """
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        st.error(f"Database error: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()
        
    return df

def format_currency(val):
    """Formats numbers into Indian Rupee currency format."""
    if pd.isna(val): return "₹ 0"
    return f"₹ {val:,.0f}"

def render():
    st.title("🏦 Master Final Tally & Capital Analytics")
    st.info("💡 **Cash Flow Intelligence:** This dashboard analyzes your physical cash drawer (Own Capital), your digital balance (GPay), and exactly which currency notes you hold.")

    raw_data = fetch_tally_data()
    if raw_data.empty:
        st.warning("No Final Tally data found in the database.")
        return

    # --- 1. DATA CLEANING & PREPARATION ---
    # Convert string dates to actual datetime objects for time-based analysis
    raw_data['date_parsed'] = pd.to_datetime(raw_data['tally_date'], format='%d/%m/%Y', errors='coerce')
    raw_data = raw_data.dropna(subset=['date_parsed'])
    
    # Ensure numeric columns are floats
    for col in ['capital_by_system', 'capital_by_owner', 'gpay_by_system', 'final_tally_amount']:
        raw_data[col] = pd.to_numeric(raw_data[col], errors='coerce').fillna(0)

    # Calculate Cash Difference (Over/Short)
    raw_data['cash_difference'] = raw_data['capital_by_owner'] - raw_data['capital_by_system']

    # --- 2. DATE FILTER ---
    db_min = raw_data['date_parsed'].min().date()
    db_max = raw_data['date_parsed'].max().date()
    today = datetime.date.today()
    
    col_d1, _ = st.columns([1, 3])
    with col_d1:
        date_range = st.date_input(
            "📅 Select Analysis Window:", 
            value=(max(db_min, datetime.date(today.year, 1, 1)), min(db_max, today)), 
            min_value=db_min, 
            max_value=today
        )

    if len(date_range) != 2: return 
    sd, ed = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

    df = raw_data[(raw_data['date_parsed'] >= sd) & (raw_data['date_parsed'] <= ed)].copy()
    if df.empty:
        st.warning("No tally activity found in the selected date range.")
        return

    st.write("---")

    # --- 3. GLOBAL KPIs ---
    st.markdown("### 📊 Global Capital Overview (Selected Period)")
    
    avg_own_cap = df['capital_by_owner'].mean()
    avg_gpay = df['gpay_by_system'].mean()
    net_difference = df['cash_difference'].sum()
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Avg Own Capital (Drawer)", format_currency(avg_own_cap))
    k2.metric("Avg System GPay Balance", format_currency(avg_gpay))
    k3.metric("Highest Cash Held", format_currency(df['capital_by_owner'].max()))
    
    # Highlight if the drawer is generally short or over
    diff_color = "normal" if net_difference == 0 else ("inverse" if net_difference < 0 else "normal")
    k4.metric("Net Cash Over/Short", format_currency(net_difference), delta=f"{net_difference:,.0f} Discrepancy", delta_color=diff_color)
    
    st.write("---")

    # --- 4. ANALYTICS TABS ---
    t_avg, t_denom, t_future, t_data = st.tabs([
        "📈 Time Averages (Daily/Wk/Mo)", 
        "💵 Denomination Breakdown", 
        "🔮 1-Year Forecast & Needs", 
        "📋 Raw Tally Ledger"
    ])

    # ==========================================
    # TAB 1: TIME AVERAGES
    # ==========================================
    with t_avg:
        st.markdown("### 📈 Capital Averages over Time")
        st.info("See exactly how much physical cash vs digital GPay you rely on across different timeframes.")

        # Create time periods
        df['Week'] = df['date_parsed'].dt.to_period('W').dt.start_time
        df['Month'] = df['date_parsed'].dt.to_period('M').dt.start_time

        # Calculate Averages
        daily_avg = df.groupby('date_parsed')[['capital_by_owner', 'gpay_by_system']].mean().reset_index()
        weekly_avg = df.groupby('Week')[['capital_by_owner', 'gpay_by_system']].mean().reset_index()
        monthly_avg = df.groupby('Month')[['capital_by_owner', 'gpay_by_system']].mean().reset_index()

        c1, c2 = st.columns(2)
        with c1:
            fig_daily = px.line(daily_avg, x='date_parsed', y=['capital_by_owner', 'gpay_by_system'], 
                                title="Daily Capital Trends",
                                labels={'value': 'Amount (₹)', 'date_parsed': 'Date', 'variable': 'Capital Type'},
                                color_discrete_map={'capital_by_owner': '#2ca02c', 'gpay_by_system': '#1f77b4'})
            st.plotly_chart(fig_daily, use_container_width=True)

        with c2:
            fig_monthly = px.bar(monthly_avg, x='Month', y=['capital_by_owner', 'gpay_by_system'], 
                                 barmode='group',
                                 title="Monthly Average Capital Holdings",
                                 labels={'value': 'Average Amount (₹)', 'Month': 'Month', 'variable': 'Capital Type'},
                                 color_discrete_map={'capital_by_owner': '#2ca02c', 'gpay_by_system': '#1f77b4'})
            st.plotly_chart(fig_monthly, use_container_width=True)

    # ==========================================
    # TAB 2: DENOMINATION BREAKDOWN
    # ==========================================
    with t_denom:
        st.markdown("### 💵 Physical Denomination Intelligence")
        st.info("Unpacks your JSON tally data to show exactly which notes take up space in your safe.")

        denom_counts = {}
        # Iterate through the JSON data to sum up all notes
        for _, row in df.iterrows():
            if pd.notna(row['denomination_details']) and row['denomination_details'].strip():
                try:
                    notes = json.loads(row['denomination_details'])
                    for note, count in notes.items():
                        # Only process keys that are standard numeric Indian denominations
                        if note.isdigit() and int(note) in [500, 200, 100, 50, 20, 10, 5, 2, 1]:
                            denom_counts[note] = denom_counts.get(note, 0) + int(float(count))
                except Exception:
                    pass
        
        if denom_counts:
            # Create a DataFrame for the notes
            denom_df = pd.DataFrame(list(denom_counts.items()), columns=['Note_Value', 'Total_Count'])
            denom_df['Note_Value'] = denom_df['Note_Value'].astype(int)
            denom_df['Total_Cash_Value'] = denom_df['Note_Value'] * denom_df['Total_Count']
            denom_df = denom_df.sort_values('Note_Value', ascending=False)

            c3, c4 = st.columns(2)
            with c3:
                fig_note_count = px.bar(denom_df, x='Note_Value', y='Total_Count',
                                        title="Total Volume of Notes (Quantity)",
                                        labels={'Note_Value': 'Note Denomination (₹)', 'Total_Count': 'Number of Notes'},
                                        color='Note_Value', color_continuous_scale="Blues")
                fig_note_count.update_xaxes(type='category')
                st.plotly_chart(fig_note_count, use_container_width=True)

            with c4:
                fig_note_value = px.pie(denom_df, names='Note_Value', values='Total_Cash_Value', hole=0.5,
                                        title="Cash Value by Denomination",
                                        labels={'Note_Value': 'Note Denomination (₹)'})
                fig_note_value.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_note_value, use_container_width=True)
                
            st.dataframe(denom_df.rename(columns={'Note_Value': 'Denomination (₹)', 'Total_Count': 'Total Notes Count', 'Total_Cash_Value': 'Total Value (₹)'}), hide_index=True, use_container_width=True)
        else:
            st.warning("No valid denomination data found in the selected timeframe.")

    # ==========================================
    # TAB 3: FUTURE PREDICTIONS & REQUIRED CAPITAL
    # ==========================================
    # ==========================================
    # TAB 3: FUTURE PREDICTIONS & REQUIRED CAPITAL
    # ==========================================
    with t_future:
        st.markdown("### 🔮 1-Year Capital Requirement Forecasting")
        st.info("Since today's closing amount is tomorrow's opening amount, this algorithm projects your **Total Liquid Capital (Cash in Drawer + GPay Balance)** to predict exactly how much extra money you will need to inject into the shop.")

        if len(df['date_parsed'].unique()) < 5:
            st.warning("⚠️ Need at least 5 days of tally data to generate an accurate mathematical prediction.")
        else:
            # Default to 365 Days (1 Year)
            forecast_days = st.slider("Select Forecast Horizon (Days):", min_value=30, max_value=365, value=365, step=15)
            
            # 🟢 FIX: Calculate Total Liquid Capital (Cash + GPay) to act as the true "Closing Amount"
            trend_data = df.groupby('date_parsed')[['capital_by_owner', 'gpay_by_system']].mean().reset_index()
            trend_data['Total_Closing_Amount'] = trend_data['capital_by_owner'] + trend_data['gpay_by_system']
            
            # Convert dates to numerical 'days since start' for algebra
            x_historical = (trend_data['date_parsed'] - trend_data['date_parsed'].min()).dt.days.values
            last_date = trend_data['date_parsed'].max()
            future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_days)
            x_future = np.arange(x_historical[-1] + 1, x_historical[-1] + 1 + forecast_days)
            
            # Predictive Algebra (Linear Regression)
            def get_projection(y_vals):
                z = np.polyfit(x_historical, y_vals, 1) # Find slope/intercept
                p = np.poly1d(z) 
                return p(x_future), z[0] # Apply equation to future without blocking negative values
            
            fut_closing_cap, slope_total = get_projection(trend_data['Total_Closing_Amount'].values)
            
            current_capital = trend_data['Total_Closing_Amount'].iloc[-1]
            projected_final_capital = fut_closing_cap[-1]
            
            c5, c6, c7 = st.columns(3)
            c5.metric("Current Shop Closing Amount", format_currency(current_capital))
            c6.metric(f"Projected Balance (Day {forecast_days})", format_currency(projected_final_capital), f"{slope_total:,.0f} ₹/day trend")
            
            # 🟢 FIX: Calculate exactly how much money is needed ONLY if the balance drops below zero
            if projected_final_capital < 0:
                shortfall = abs(projected_final_capital)
                c7.metric(f"⚠️ EXTRA MONEY NEEDED", format_currency(shortfall), "Will run out of money", delta_color="inverse")
                st.error(f"🚨 **Warning:** The shop is lending out more than it collects. The balance will drop below zero! You must inject exactly **{format_currency(shortfall)}** to run the shop for the next {forecast_days} days.")
            else:
                c7.metric(f"✅ Safe Runway", "No extra cash needed", "Balance stays above zero")
                st.success(f"🌟 **Excellent:** Your daily closing amounts are stable. You have enough capital to safely run the shop for the next {forecast_days} days without injecting any external money!")
                
            st.write("---")

            # Plotting the prediction
            hist_plot = pd.DataFrame({'Date': trend_data['date_parsed'], 'Capital Amount': trend_data['Total_Closing_Amount'], 'Type': 'Historical (Actual Closing Amount)'})
            fut_plot = pd.DataFrame({'Date': future_dates, 'Capital Amount': fut_closing_cap, 'Type': 'Projected (Mathematical Forecast)'})
            combined_plot = pd.concat([hist_plot, fut_plot])

            fig_pred = px.line(combined_plot, x='Date', y='Capital Amount', color='Type', 
                               title=f"Shop Closing Amount Forecast (Next {forecast_days} Days)",
                               color_discrete_map={'Historical (Actual Closing Amount)': '#1f77b4', 'Projected (Mathematical Forecast)': '#FF8C00'})
            fig_pred.update_traces(line=dict(dash="dot"), selector=dict(name='Projected (Mathematical Forecast)'))
            
            # Add a zero line to visually show bankruptcy/zero capital risk
            fig_pred.add_hline(y=0, line_dash="solid", line_color="red", annotation_text="Zero Balance (Shop Empty)")

            st.plotly_chart(fig_pred, use_container_width=True)

    # ==========================================
    # TAB 4: RAW LEDGER
    # ==========================================
    with t_data:
        st.markdown("### 📋 Daily Tally Ledger")
        display_df = df[['tally_date', 'capital_by_system', 'capital_by_owner', 'cash_difference', 'gpay_by_system', 'final_tally_amount']].copy()
        
        # Format currency for viewing
        for col in ['capital_by_system', 'capital_by_owner', 'cash_difference', 'gpay_by_system', 'final_tally_amount']:
            display_df[col] = display_df[col].apply(format_currency)
            
        display_df = display_df.rename(columns={
            'tally_date': 'Date',
            'capital_by_system': 'System Calculated Cash',
            'capital_by_owner': 'Actual Cash (Owner)',
            'cash_difference': 'Over / Short',
            'gpay_by_system': 'System GPay',
            'final_tally_amount': 'Grand Total'
        })
        
        st.dataframe(display_df.sort_values('Date', ascending=False), hide_index=True, use_container_width=True)