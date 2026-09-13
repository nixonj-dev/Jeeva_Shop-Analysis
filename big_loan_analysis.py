import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def render(data, ao_data, outer_data=None, outer_closed_data=None):
    st.title("📊 Big Loan Analysis")
    
    if data.empty:
        st.warning("No loan data found in the database. Please ensure your date range is correct.")
        return

    import datetime

    # --- DATE FILTER ---
    db_min = data['date'].min().date()
    db_max = data['date'].max().date()
    
    today = datetime.date.today()
    current_year_start = datetime.date(today.year, 1, 1)
    
    allowed_min = min(db_min, current_year_start)
    allowed_max = max(db_max, today)
    default_start = max(db_min, current_year_start)
    default_end = min(db_max, today)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        date_range = st.date_input(
            "Select Date Range:",
            value=(default_start, default_end),
            min_value=allowed_min,
            max_value=allowed_max
        )
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        filtered_data = data[(data['date'] >= pd.to_datetime(start_date)) & (data['date'] <= pd.to_datetime(end_date))].copy()
    else:
        filtered_data = data.copy()

    # --- SUB-PAGE NAVIGATION ---
    st.write("---")
    sub_page = st.radio(
        "Select Analysis View:", 
        [
            "💰 Amount & Growth", 
            "💸 Interest Analysis", 
            "📄 Doc & Paper Charges", 
            "⚠️ Active & Overdue", 
            "🏢 Outer Loan Analysis",
            "⚖️ Shop vs Outer (Live)",   # <--- NEW PAGE ADDED HERE
            "🏆 Final Executive Report"   
        ],
        horizontal=True
    )
    st.write("---")

    # PRE-CALCULATE BASELINES AND SPLITS FOR ALL CHARTS
    if not filtered_data.empty:
        # Safely find the first non-zero day for Principal baselines so growth calculates correctly even if Day 1 is 0
        first_gold = filtered_data.loc[filtered_data['gold_amount'] > 0, 'gold_amount'].iloc[0] if (filtered_data['gold_amount'] > 0).any() else 0
        first_silver = filtered_data.loc[filtered_data['silver_amount'] > 0, 'silver_amount'].iloc[0] if (filtered_data['silver_amount'] > 0).any() else 0
        first_total = filtered_data.loc[filtered_data['total_loan_amount'] > 0, 'total_loan_amount'].iloc[0] if (filtered_data['total_loan_amount'] > 0).any() else 0

        filtered_data['gold_baseline_pct'] = np.where(first_gold > 0, ((filtered_data['gold_amount'] - first_gold) / first_gold) * 100, 0)
        filtered_data['silver_baseline_pct'] = np.where(first_silver > 0, ((filtered_data['silver_amount'] - first_silver) / first_silver) * 100, 0)
        filtered_data['total_baseline_pct'] = np.where(first_total > 0, ((filtered_data['total_loan_amount'] - first_total) / first_total) * 100, 0)
        
        filtered_data['gold_daily_split_pct'] = (filtered_data['gold_amount'] / filtered_data['total_loan_amount'] * 100).fillna(0)
        filtered_data['silver_daily_split_pct'] = (filtered_data['silver_amount'] / filtered_data['total_loan_amount'] * 100).fillna(0)

        # Safely find the first non-zero day for Interest baselines so growth calculates correctly
        first_1m = filtered_data.loc[filtered_data['total_1m_int'] > 0, 'total_1m_int'].iloc[0] if (filtered_data['total_1m_int'] > 0).any() else 0
        first_due = filtered_data.loc[filtered_data['total_due_int'] > 0, 'total_due_int'].iloc[0] if (filtered_data['total_due_int'] > 0).any() else 0
        first_extra = filtered_data.loc[filtered_data['total_extra_int'] > 0, 'total_extra_int'].iloc[0] if (filtered_data['total_extra_int'] > 0).any() else 0
        first_close = filtered_data.loc[filtered_data['total_close_int'] > 0, 'total_close_int'].iloc[0] if (filtered_data['total_close_int'] > 0).any() else 0

        filtered_data['1m_baseline_pct'] = np.where(first_1m > 0, ((filtered_data['total_1m_int'] - first_1m) / first_1m) * 100, 0)
        filtered_data['due_baseline_pct'] = np.where(first_due > 0, ((filtered_data['total_due_int'] - first_due) / first_due) * 100, 0)
        filtered_data['extra_baseline_pct'] = np.where(first_extra > 0, ((filtered_data['total_extra_int'] - first_extra) / first_extra) * 100, 0)
        filtered_data['close_baseline_pct'] = np.where(first_close > 0, ((filtered_data['total_close_int'] - first_close) / first_close) * 100, 0)
    # --- NEW: PAPER CHARGE BASELINE ---
        if 'total_paper' in filtered_data.columns:
            first_paper = filtered_data['total_paper'].iloc[0]
            filtered_data['paper_baseline_pct'] = np.where(first_paper > 0, ((filtered_data['total_paper'] - first_paper) / first_paper) * 100, 0)


    # ==========================================
    # SECTION 1: AMOUNT & GROWTH (Now includes DOW and Counts!)
    # ==========================================
    if sub_page in ["💰 Amount & Growth", "📑 All Summary (Everything)"]:
        if sub_page == "📑 All Summary (Everything)": st.header("💰 Amount & Growth")
        
        if not filtered_data.empty:
            # --- NEW: TOP METRICS FOR AMOUNT & GROWTH ---
            st.markdown("### Top Metrics Summary")
            
            t_amt = filtered_data['total_loan_amount'].sum()
            t_gold_amt = filtered_data['gold_amount'].sum()
            t_silver_amt = filtered_data['silver_amount'].sum()
            
            c_gold = filtered_data['gold_count'].sum()
            c_silver = filtered_data['silver_count'].sum()
            c_total = filtered_data['total_count'].sum()
            
            total_days = len(filtered_data['date'].unique())

            ma1, ma2, ma3, ma4 = st.columns(4)
            with ma1:
                st.metric("Total Loan Dispersal", f"₹ {t_amt:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>📊 Avg/Day: ₹{(t_amt/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with ma2:
                st.metric("Gold Dispersal", f"₹ {t_gold_amt:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Count: {c_gold:,.0f} loans</div>", unsafe_allow_html=True)
            with ma3:
                st.metric("Silver Dispersal", f"₹ {t_silver_amt:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥈 Count: {c_silver:,.0f} loans</div>", unsafe_allow_html=True)
            with ma4:
                st.metric("Total Loan Count", f"{c_total:,.0f} loans")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>📊 Avg/Day: {(c_total/total_days) if total_days > 0 else 0:,.1f} loans</div>", unsafe_allow_html=True)
            
            st.write("---")

        
        tab_exec, tab1, tab2, tab3, tab_dow, tab_vol, tab4, tab_future = st.tabs([
            "👑 Executive Summary", "📈 Daily Amounts", "🚀 Baseline Growth", "🥧 Daily Split", "📅 Day of Week", "🔢 Loan Volume", "📋 Data Table", "🔮 Future Analysis"
        ])
        with tab_exec:
            st.markdown("### 👑 Capital Dispersal Executive Summary")
            st.info("💡 **Overview:** A high-level visualization of where your capital is flowing and how your loan portfolio is expanding.")
            
            e_col1, e_col2 = st.columns(2)
            with e_col1:
                # Composition Donut
                df_pie_amt = pd.DataFrame({"Asset": ["Gold Loans", "Silver Loans"], "Amount": [filtered_data['gold_amount'].sum(), filtered_data['silver_amount'].sum()]})
                fig_exec_pie = px.pie(df_pie_amt, names="Asset", values="Amount", hole=0.5, title="Capital Distribution (Gold vs Silver)", color="Asset", color_discrete_map={"Gold Loans": "#FFD700", "Silver Loans": "#C0C0C0"})
                fig_exec_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_exec_pie, use_container_width=True)
            with e_col2:
                # Cumulative Growth Area
                exec_trend = filtered_data.groupby('date')['total_loan_amount'].sum().cumsum().reset_index()
                fig_exec_area = px.area(exec_trend, x='date', y='total_loan_amount', title="Cumulative Capital Lent Over Time", color_discrete_sequence=['#1f77b4'])
                fig_exec_area.update_layout(yaxis_title="Total Dispersed (₹)", hovermode="x unified")
                st.plotly_chart(fig_exec_area, use_container_width=True)
            st.write("---")
        
        with tab1:
            fig1_split = px.line(filtered_data, x='date', y=['gold_amount', 'silver_amount'],
                           title="Gold vs Silver Amounts (with Day 1 Center Line)", markers=True,
                           color_discrete_map={'gold_amount': '#FFD700', 'silver_amount': '#C0C0C0'})
            if not filtered_data.empty:
                fig1_split.add_hline(y=first_gold, line_dash="dot", line_color="#FFD700", opacity=0.5)
                fig1_split.add_hline(y=first_silver, line_dash="dot", line_color="#C0C0C0", opacity=0.5)
            fig1_split.update_layout(hovermode="x unified")
            st.plotly_chart(fig1_split, use_container_width=True)

            fig1_total = px.line(filtered_data, x='date', y=['total_loan_amount'],
                           title="Total Loan Amount (with Day 1 Center Line)", markers=True,
                           color_discrete_map={'total_loan_amount': '#FF4B4B'})
            if not filtered_data.empty:
                fig1_total.add_hline(y=first_total, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
            fig1_total.update_layout(hovermode="x unified")
            st.plotly_chart(fig1_total, use_container_width=True)

        with tab2:
            fig2_total = px.line(filtered_data, x='date', y=['total_baseline_pct'],
                           title="Final Total Growth % (Single Line)", markers=True,
                           color_discrete_map={'total_baseline_pct': '#1f77b4'})
            fig2_total.add_hline(y=0, line_dash="solid", line_color="black", annotation_text="0% Baseline (Day 1)")
            fig2_total.update_layout(hovermode="x unified")
            st.plotly_chart(fig2_total, use_container_width=True)

            fig2_split = px.line(filtered_data, x='date', y=['gold_baseline_pct', 'silver_baseline_pct'],
                           title="Gold vs Silver Growth %", markers=True,
                           color_discrete_map={'gold_baseline_pct': '#FFD700', 'silver_baseline_pct': '#C0C0C0'})
            fig2_split.add_hline(y=0, line_dash="solid", line_color="black")
            fig2_split.update_layout(hovermode="x unified")
            st.plotly_chart(fig2_split, use_container_width=True)

        with tab3:
            fig3 = px.bar(filtered_data, x='date', y=['gold_daily_split_pct', 'silver_daily_split_pct'],
                          title="Daily Composition: Gold vs Silver Share", barmode='stack',
                          color_discrete_map={'gold_daily_split_pct': '#FFD700', 'silver_daily_split_pct': '#C0C0C0'})
            fig3.update_layout(hovermode="x unified")
            st.plotly_chart(fig3, use_container_width=True)

        # --- MOVED: DAY OF WEEK NOW LIVES HERE ---
        with tab_dow:
            st.markdown("### Day of Week Dispersal Pattern")
            if not filtered_data.empty:
                dow_data = filtered_data.groupby('day_of_week')[['gold_amount', 'silver_amount']].sum().reset_index()
                dow_data['total_amount'] = dow_data['gold_amount'] + dow_data['silver_amount']
                dow_data['gold_pct'] = (dow_data['gold_amount'] / dow_data['total_amount'] * 100).fillna(0)
                dow_data['silver_pct'] = (dow_data['silver_amount'] / dow_data['total_amount'] * 100).fillna(0)
                
                days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                dow_data['day_of_week'] = pd.Categorical(dow_data['day_of_week'], categories=days_order, ordered=True)
                dow_data = dow_data.sort_values('day_of_week')

                col_dow1, col_dow2 = st.columns([2, 1])
                with col_dow1:
                    fig_dow = px.bar(dow_data, x='day_of_week', y=['gold_pct', 'silver_pct'],
                                  title="Split by Day of Week (%)", barmode='stack',
                                  color_discrete_map={'gold_pct': '#FFD700', 'silver_pct': '#C0C0C0'})
                    fig_dow.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_dow, use_container_width=True)
                with col_dow2:
                    display_dow = dow_data[['day_of_week', 'gold_pct', 'silver_pct']].copy()
                    display_dow['gold_pct'] = display_dow['gold_pct'].round(2).astype(str) + '%'
                    display_dow['silver_pct'] = display_dow['silver_pct'].round(2).astype(str) + '%'
                    display_dow = display_dow.rename(columns={'day_of_week': 'Day', 'gold_pct': 'Gold %', 'silver_pct': 'Silver %'})
                    st.dataframe(display_dow, hide_index=True, use_container_width=True)

        # --- MOVED: LOAN VOLUME NOW LIVES HERE ---
        with tab_vol:
            st.markdown("### Number of Loans Given Over Time")
            if not filtered_data.empty:
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    fig_counts_split = px.line(filtered_data, x='date', y=['gold_count', 'silver_count'],
                                   title="Gold vs Silver Loan Count", markers=True,
                                   color_discrete_map={'gold_count': '#FFD700', 'silver_count': '#C0C0C0'})
                    fig_counts_split.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_counts_split, use_container_width=True)
                
                with col_chart2:
                    fig_counts_total = px.line(filtered_data, x='date', y=['total_count'],
                                   title="Combined Loan Count", markers=True,
                                   color_discrete_map={'total_count': '#FF4B4B'})
                    fig_counts_total.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_counts_total, use_container_width=True)

        with tab4:
            st.subheader("Dispersal Analysis & Data Breakdown")
            if not filtered_data.empty:
                
                # --- NEW: GRAND TOTALS TABLE ---
                st.markdown("##### 💰 GRAND TOTALS (For Selected Dates)")
                total_amt_data = {
                    "Metric": ["Overall Total"],
                    "Gold Amt (₹)": [f"₹ {filtered_data['gold_amount'].sum():,.2f}"],
                    "Silver Amt (₹)": [f"₹ {filtered_data['silver_amount'].sum():,.2f}"],
                    "Total Amt (₹)": [f"₹ {filtered_data['total_loan_amount'].sum():,.2f}"]
                }
                st.dataframe(pd.DataFrame(total_amt_data), hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)
                
                # 📌 OVERALL AVERAGES TABLE
                st.markdown("##### 📌 OVERALL AVERAGES (For Selected Dates)")
                avg_data = {
                    "Metric": ["Daily Average"],
                    "Gold Amt": [f"₹ {filtered_data['gold_amount'].mean():,.2f}"],
                    "Silver Amt": [f"₹ {filtered_data['silver_amount'].mean():,.2f}"],
                    "Total Amt": [f"₹ {filtered_data['total_loan_amount'].mean():,.2f}"],
                    "Gold Growth": [f"{filtered_data['gold_baseline_pct'].mean():.2f}%"],
                    "Silver Growth": [f"{filtered_data['silver_baseline_pct'].mean():.2f}%"],
                    "Total Growth": [f"{filtered_data['total_baseline_pct'].mean():.2f}%"],
                    "Gold Share": [f"{filtered_data['gold_daily_split_pct'].mean():.2f}%"],
                    "Silver Share": [f"{filtered_data['silver_daily_split_pct'].mean():.2f}%"]
                }
                st.dataframe(pd.DataFrame(avg_data), hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)

                # --- 📊 NEW ANALYSIS IDEA: MONTHLY DISPERSAL TRENDS ---
                st.markdown("##### 📊 MONTHLY DISPERSAL TRENDS & COMPOSITION")
                st.info("💡 Shows how your loan dispersal volume and Gold vs Silver composition shifts month-over-month.")
                monthly_data = filtered_data.copy()
                monthly_data['Month-Year'] = monthly_data['date'].dt.to_period('M')
                
                # Aggregate by Month
                m_trend = monthly_data.groupby('Month-Year').agg(
                    Gold_Amt=('gold_amount', 'sum'),
                    Silver_Amt=('silver_amount', 'sum'),
                    Total_Amt=('total_loan_amount', 'sum'),
                    Loan_Days=('date', 'count')
                ).reset_index()
                
                # Calculate Monthly Splits and Month-over-Month Growth
                m_trend['Gold_Share_%'] = (m_trend['Gold_Amt'] / m_trend['Total_Amt'] * 100).fillna(0).round(2).astype(str) + '%'
                m_trend['Silver_Share_%'] = (m_trend['Silver_Amt'] / m_trend['Total_Amt'] * 100).fillna(0).round(2).astype(str) + '%'
                
                m_trend['MoM_Growth_%'] = m_trend['Total_Amt'].pct_change() * 100
                m_trend['MoM_Growth_%'] = m_trend['MoM_Growth_%'].fillna(0).round(2).astype(str) + '%'
                
                # Format amounts
                for col in ['Gold_Amt', 'Silver_Amt', 'Total_Amt']:
                    m_trend[col] = m_trend[col].apply(lambda x: f"₹ {x:,.0f}")
                
                m_trend['Month-Year'] = m_trend['Month-Year'].dt.strftime('%b %Y')
                m_trend = m_trend.rename(columns={'Gold_Amt': 'Gold Amount', 'Silver_Amt': 'Silver Amount', 'Total_Amt': 'Total Amount', 'Loan_Days': 'Active Days'})
                
                st.dataframe(m_trend, hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)
                
                # 📅 DAILY BREAKDOWN TABLE
                st.markdown("##### 📅 DAILY BREAKDOWN")
                display_df = filtered_data[['date', 'gold_amount', 'silver_amount', 'total_loan_amount', 'gold_baseline_pct', 'silver_baseline_pct', 'total_baseline_pct', 'gold_daily_split_pct', 'silver_daily_split_pct']].copy()
                display_df['date'] = display_df['date'].dt.strftime('%d-%m-%Y')
                
                for col in ['gold_baseline_pct', 'silver_baseline_pct', 'total_baseline_pct', 'gold_daily_split_pct', 'silver_daily_split_pct']:
                    display_df[col] = display_df[col].round(2).astype(str) + '%'
                
                display_df = display_df.rename(columns={
                    'date': 'Date', 'gold_amount': 'Gold Amt (₹)', 'silver_amount': 'Silver Amt (₹)',
                    'total_loan_amount': 'Total Amt (₹)', 'gold_baseline_pct': 'Gold Growth %',
                    'silver_baseline_pct': 'Silver Growth %', 'total_baseline_pct': 'Total Growth %',
                    'gold_daily_split_pct': 'Gold Share %', 'silver_daily_split_pct': 'Silver Share %'
                })
                st.dataframe(display_df, hide_index=True, use_container_width=True)

        # --- NEW: FUTURE ANALYSIS SUB-TAB FOR AMOUNT & GROWTH ---
        with tab_future:
            st.subheader("🔮 Mathematical Future Projections (Amount & Volume)")
            st.info("💡 This tool analyzes your historical dispersal data to mathematically predict future trends. **Requirement:** Ensure your selected Date Filter includes at least 5 days of data for an accurate trendline.")
            
            if len(filtered_data['date'].unique()) < 5:
                st.warning("⚠️ Not enough historical data selected. Please widen your Date Filter to include at least 5 distinct days of loan activity.")
            else:
                forecast_months = st.slider("Select Forecast Horizon (Months):", min_value=1, max_value=12, value=3, key="amt_growth_forecast")
                forecast_days = forecast_months * 30
                
                # Group data for mathematical modeling
                trend_data = filtered_data.groupby('date')[['total_loan_amount', 'gold_amount', 'silver_amount', 'total_count']].sum().reset_index()
                
                # Convert dates to numerical 'days since start' for algebra
                x_historical = (trend_data['date'] - trend_data['date'].min()).dt.days.values
                last_date = trend_data['date'].max()
                future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_days)
                x_future = np.arange(x_historical[-1] + 1, x_historical[-1] + 1 + forecast_days)
                
                # --- PREDICTIVE ALGEBRA (Linear Regression) ---
                def get_projection(y_vals):
                    z = np.polyfit(x_historical, y_vals, 1) # Find the slope/intercept
                    p = np.poly1d(z) # Create equation
                    future_vals = np.maximum(p(x_future), 0) # Apply equation to future, prevent negatives
                    return future_vals, z[0] # Return predictions and the slope
                
                fut_total_amt, slope_total = get_projection(trend_data['total_loan_amount'].values)
                fut_gold_amt, slope_gold = get_projection(trend_data['gold_amount'].values)
                fut_silver_amt, slope_silver = get_projection(trend_data['silver_amount'].values)
                fut_count, slope_count = get_projection(trend_data['total_count'].values)
                
                # --- TRAJECTORY ANALYSIS (Is the business growing?) ---
                st.markdown("##### 🚀 Trajectory Analysis")
                c1, c2, c3 = st.columns(3)
                
                def render_slope(col, title, slope_val, is_count=False):
                    direction = "📈 Growing" if slope_val > 0 else ("📉 Shrinking" if slope_val < 0 else "➡️ Flat")
                    color = "green" if slope_val > 0 else ("red" if slope_val < 0 else "gray")
                    unit = "loans/day" if is_count else "₹/day"
                    col.markdown(f"**{title} Trajectory:**")
                    col.markdown(f"<h4 style='color: {color}; margin-top: -10px;'>{direction} ({slope_val:,.1f} {unit})</h4>", unsafe_allow_html=True)
                
                render_slope(c1, "Overall Volume", slope_total)
                render_slope(c2, "Gold Portfolio", slope_gold)
                render_slope(c3, "Silver Portfolio", slope_silver)
                st.write("---")
                
                # --- FUTURE METRICS ---
                st.markdown(f"##### 🎯 Expected Results (Next {forecast_months} Months)")
                m1, m2, m3 = st.columns(3)
                m1.metric("Est. Total Money Dispersed", f"₹ {fut_total_amt.sum():,.0f}")
                m2.metric("Est. Total Gold Dispersed", f"₹ {fut_gold_amt.sum():,.0f}")
                m3.metric("Est. Total Silver Dispersed", f"₹ {fut_silver_amt.sum():,.0f}")
                st.write("---")
                
                # --- PREDICTIVE GRAPHS ---
                st.markdown("##### 📈 Growth Projection Visualizations")
                g_col1, g_col2 = st.columns(2)
                
                with g_col1:
                    hist_plot = pd.DataFrame({'Date': trend_data['date'], 'Value': trend_data['total_loan_amount'].values, 'Type': 'Historical (Actual)'})
                    fut_plot = pd.DataFrame({'Date': future_dates, 'Value': fut_total_amt, 'Type': 'Projected (Mathematical)'})
                    combined_plot = pd.concat([hist_plot, fut_plot])
                    
                    fig_fut_amt = px.line(combined_plot, x='Date', y='Value', color='Type', title="Total Loan Dispersal Prediction",
                                          color_discrete_map={'Historical (Actual)': '#1f77b4', 'Projected (Mathematical)': '#FF8C00'})
                    fig_fut_amt.update_traces(line=dict(dash="dot"), selector=dict(name='Projected (Mathematical)'))
                    fig_fut_amt.update_layout(hovermode="x unified", yaxis_title="Amount (₹)")
                    st.plotly_chart(fig_fut_amt, use_container_width=True)
                    
                with g_col2:
                    hist_cnt = pd.DataFrame({'Date': trend_data['date'], 'Value': trend_data['total_count'].values, 'Type': 'Historical (Actual)'})
                    fut_cnt = pd.DataFrame({'Date': future_dates, 'Value': fut_count, 'Type': 'Projected (Mathematical)'})
                    combined_cnt = pd.concat([hist_cnt, fut_cnt])
                    
                    fig_fut_cnt = px.line(combined_cnt, x='Date', y='Value', color='Type', title="Total Loan Count Prediction",
                                          color_discrete_map={'Historical (Actual)': '#2ca02c', 'Projected (Mathematical)': '#d62728'})
                    fig_fut_cnt.update_traces(line=dict(dash="dot"), selector=dict(name='Projected (Mathematical)'))
                    fig_fut_cnt.update_layout(hovermode="x unified", yaxis_title="Number of Loans")
                    st.plotly_chart(fig_fut_cnt, use_container_width=True)

        if sub_page == "📑 All Summary (Everything)": st.write("---")

    # ==========================================
    # SECTION 2: INTEREST ANALYSIS
    # ==========================================
    if sub_page in ["💸 Interest Analysis", "📑 All Summary (Everything)"]:
        if sub_page == "📑 All Summary (Everything)": st.header("💸 Interest Analysis")
        else: st.subheader("Interest Generation Breakdown")

        if not filtered_data.empty:
            st.markdown("### Top Metrics Summary")
            
            t_1m = filtered_data['total_1m_int'].sum()
            t_due = filtered_data['total_due_int'].sum()
            t_extra = filtered_data['total_extra_int'].sum()
            t_close = filtered_data['total_close_int'].sum()
            t_overall = filtered_data['total_overall_interest'].sum()
            
            c_1m = filtered_data['total_1m_count'].sum()
            c_due = filtered_data['total_due_count'].sum()
            c_extra = filtered_data['total_extra_count'].sum()
            c_close = filtered_data['total_close_count'].sum()
            c_overall = filtered_data['total_overall_count'].sum()
            
            total_days = len(filtered_data['date'].unique())

            mi1, mi2, mi3, mi4, mi5 = st.columns(5)
            with mi1:
                st.metric("Expected 1-Month", f"₹ {t_1m:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{filtered_data['gold_1m_int'].sum():,.0f}<br>🥈 Silver: ₹{filtered_data['silver_1m_int'].sum():,.0f}<br>🔢 Count: {c_1m:,.0f} loans<br>📊 Avg/Day: ₹{(t_1m/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with mi2:
                st.metric("Due Accumulated", f"₹ {t_due:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{filtered_data['gold_due_int'].sum():,.0f}<br>🥈 Silver: ₹{filtered_data['silver_due_int'].sum():,.0f}<br>🔢 Count: {c_due:,.0f} loans<br>📊 Avg/Day: ₹{(t_due/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with mi3:
                st.metric("Extra Interest", f"₹ {t_extra:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{filtered_data['gold_extra_int'].sum():,.0f}<br>🥈 Silver: ₹{filtered_data['silver_extra_int'].sum():,.0f}<br>🔢 Count: {c_extra:,.0f} loans<br>📊 Avg/Day: ₹{(t_extra/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with mi4:
                st.metric("Realized Closing", f"₹ {t_close:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{filtered_data['gold_close_int'].sum():,.0f}<br>🥈 Silver: ₹{filtered_data['silver_close_int'].sum():,.0f}<br>🔢 Count: {c_close:,.0f} loans<br>📊 Avg/Day: ₹{(t_close/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with mi5:
                st.metric("Overall Int Collected", f"₹ {t_overall:,.0f}")
                total_g_all = filtered_data['gold_1m_int'].sum() + filtered_data['gold_due_int'].sum() + filtered_data['gold_extra_int'].sum() + filtered_data['gold_close_int'].sum()
                total_s_all = filtered_data['silver_1m_int'].sum() + filtered_data['silver_due_int'].sum() + filtered_data['silver_extra_int'].sum() + filtered_data['silver_close_int'].sum()
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{total_g_all:,.0f}<br>🥈 Silver: ₹{total_s_all:,.0f}<br>🔢 Count: {c_overall:,.0f} loans<br>📊 Avg/Day: ₹{(t_overall/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)

            st.write("---")

            f_1m_tot, f_1m_g, f_1m_s = filtered_data['total_1m_int'].iloc[0], filtered_data['gold_1m_int'].iloc[0], filtered_data['silver_1m_int'].iloc[0]
            f_due_tot, f_due_g, f_due_s = filtered_data['total_due_int'].iloc[0], filtered_data['gold_due_int'].iloc[0], filtered_data['silver_due_int'].iloc[0]
            f_cl_tot, f_cl_g, f_cl_s = filtered_data['total_close_int'].iloc[0], filtered_data['gold_close_int'].iloc[0], filtered_data['silver_close_int'].iloc[0]
            f_ex_tot, f_ex_g, f_ex_s = filtered_data['total_extra_int'].iloc[0], filtered_data['gold_extra_int'].iloc[0], filtered_data['silver_extra_int'].iloc[0]
            f_over_tot = filtered_data['total_overall_interest'].iloc[0]

            itab_exec, itab1, itab2, itab3, itab4, itab5, itab_dow, itab6, itab_future = st.tabs([
                "👑 Executive Summary", "📊 1-Month", "📈 Due Interest", "📉 Closing", "➕ Extra Interest", "💰 Total Overall Graph", "📅 Day of Week", "📋 Interest Data Table", "🔮 Future Analysis"
            ])
            with itab_exec:
                st.markdown("### 👑 Interest Revenue Executive Summary")
                st.info("💡 **Overview:** A quick breakdown of how your interest revenue is generated and its daily collection trend.")
                
                ei_col1, ei_col2 = st.columns(2)
                with ei_col1:
                    rev_sources = pd.DataFrame({
                        "Source": ["1-Month Advance", "Due Monthly", "Closing", "Extra/Penalty"],
                        "Revenue": [filtered_data['total_1m_int'].sum(), filtered_data['total_due_int'].sum(), filtered_data['total_close_int'].sum(), filtered_data['total_extra_int'].sum()]
                    })
                    fig_rev_donut = px.pie(rev_sources, names="Source", values="Revenue", hole=0.4, title="Revenue Stream Breakdown", color="Source", color_discrete_map={"1-Month Advance": "#1f77b4", "Due Monthly": "#ff7f0e", "Closing": "#2ca02c", "Extra/Penalty": "#d62728"})
                    st.plotly_chart(fig_rev_donut, use_container_width=True)
                with ei_col2:
                    fig_daily_rev = px.bar(filtered_data, x='date', y='total_overall_interest', title="Daily Total Interest Collected", color_discrete_sequence=['#2ca02c'])
                    fig_daily_rev.update_layout(yaxis_title="Interest Collected (₹)", hovermode="x unified")
                    st.plotly_chart(fig_daily_rev, use_container_width=True)

            with itab1:
                fig_1m = px.area(filtered_data, x='date', y=['gold_1m_int', 'silver_1m_int'], title="Daily 1-Month Interest Expectation", color_discrete_map={'gold_1m_int': '#FFD700', 'silver_1m_int': '#C0C0C0'})
                fig_1m.add_hline(y=f_1m_g, line_dash="dot", line_color="#FFD700", opacity=0.5); fig_1m.add_hline(y=f_1m_s, line_dash="dot", line_color="#C0C0C0", opacity=0.5)
                fig_1m.update_layout(hovermode="x unified"); st.plotly_chart(fig_1m, use_container_width=True)
                fig_1m_tot = px.line(filtered_data, x='date', y=['total_1m_int'], title="Total 1-Month Interest", markers=True, color_discrete_map={'total_1m_int': '#FF4B4B'})
                fig_1m_tot.add_hline(y=f_1m_tot, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
                fig_1m_tot.update_layout(hovermode="x unified"); st.plotly_chart(fig_1m_tot, use_container_width=True)

            with itab2:
                fig_due_split = px.line(filtered_data, x='date', y=['gold_due_int', 'silver_due_int'], title="Daily Due Interest Accumulated", markers=True, color_discrete_map={'gold_due_int': '#FFD700', 'silver_due_int': '#C0C0C0'})
                fig_due_split.add_hline(y=f_due_g, line_dash="dot", line_color="#FFD700", opacity=0.5); fig_due_split.add_hline(y=f_due_s, line_dash="dot", line_color="#C0C0C0", opacity=0.5)
                fig_due_split.update_layout(hovermode="x unified"); st.plotly_chart(fig_due_split, use_container_width=True)
                fig_due_tot = px.line(filtered_data, x='date', y=['total_due_int'], title="Total Due Interest", markers=True, color_discrete_map={'total_due_int': '#FF4B4B'})
                fig_due_tot.add_hline(y=f_due_tot, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
                fig_due_tot.update_layout(hovermode="x unified"); st.plotly_chart(fig_due_tot, use_container_width=True)

            with itab3:
                fig_close_split = px.line(filtered_data, x='date', y=['gold_close_int', 'silver_close_int'], title="Daily Closing Interest Realized", markers=True, color_discrete_map={'gold_close_int': '#FFD700', 'silver_close_int': '#C0C0C0'})
                fig_close_split.add_hline(y=f_cl_g, line_dash="dot", line_color="#FFD700", opacity=0.5); fig_close_split.add_hline(y=f_cl_s, line_dash="dot", line_color="#C0C0C0", opacity=0.5)
                fig_close_split.update_layout(hovermode="x unified"); st.plotly_chart(fig_close_split, use_container_width=True)
                fig_close_tot = px.line(filtered_data, x='date', y=['total_close_int'], title="Total Closing Interest", markers=True, color_discrete_map={'total_close_int': '#FF4B4B'})
                fig_close_tot.add_hline(y=f_cl_tot, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
                fig_close_tot.update_layout(hovermode="x unified"); st.plotly_chart(fig_close_tot, use_container_width=True)

            with itab4:
                fig_extra_split = px.line(filtered_data, x='date', y=['gold_extra_int', 'silver_extra_int'], title="Daily Extra Interest Collected", markers=True, color_discrete_map={'gold_extra_int': '#FFD700', 'silver_extra_int': '#C0C0C0'})
                fig_extra_split.add_hline(y=f_ex_g, line_dash="dot", line_color="#FFD700", opacity=0.5); fig_extra_split.add_hline(y=f_ex_s, line_dash="dot", line_color="#C0C0C0", opacity=0.5)
                fig_extra_split.update_layout(hovermode="x unified"); st.plotly_chart(fig_extra_split, use_container_width=True)
                fig_extra_tot = px.line(filtered_data, x='date', y=['total_extra_int'], title="Total Extra Interest", markers=True, color_discrete_map={'total_extra_int': '#FF4B4B'})
                fig_extra_tot.add_hline(y=f_ex_tot, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
                fig_extra_tot.update_layout(hovermode="x unified"); st.plotly_chart(fig_extra_tot, use_container_width=True)

            with itab5:
                fig_overall = px.line(filtered_data, x='date', y=['total_overall_interest'], title="Total Generated Interest (1M + Due + Extra + Close) Per Day", markers=True, color_discrete_map={'total_overall_interest': '#2ca02c'})
                fig_overall.add_hline(y=f_over_tot, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
                fig_overall.update_traces(line=dict(width=4)); fig_overall.update_layout(hovermode="x unified")
                st.plotly_chart(fig_overall, use_container_width=True)
                
                st.markdown("### Interest Baseline Growth (Starts at 0%)")
                fig_int_base = px.line(filtered_data, x='date', y=['1m_baseline_pct', 'due_baseline_pct', 'extra_baseline_pct', 'close_baseline_pct'], title="Baseline Growth for Each Interest Type", markers=True)
                fig_int_base.add_hline(y=0, line_dash="solid", line_color="black")
                fig_int_base.update_layout(hovermode="x unified")
                st.plotly_chart(fig_int_base, use_container_width=True)
                
            with itab_dow:
                st.markdown("### Day of Week Interest Pattern (Amount & Percentages)")
                dow_int_data = filtered_data.groupby('day_of_week')[['total_1m_int', 'total_due_int', 'total_extra_int', 'total_close_int', 'total_overall_interest']].sum().reset_index()
                days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                dow_int_data['day_of_week'] = pd.Categorical(dow_int_data['day_of_week'], categories=days_order, ordered=True)
                dow_int_data = dow_int_data.sort_values('day_of_week')
                
                dow_int_data['1M %'] = (dow_int_data['total_1m_int'] / dow_int_data['total_overall_interest'] * 100).fillna(0)
                dow_int_data['Due %'] = (dow_int_data['total_due_int'] / dow_int_data['total_overall_interest'] * 100).fillna(0)
                dow_int_data['Extra %'] = (dow_int_data['total_extra_int'] / dow_int_data['total_overall_interest'] * 100).fillna(0)
                dow_int_data['Close %'] = (dow_int_data['total_close_int'] / dow_int_data['total_overall_interest'] * 100).fillna(0)

                colA, colB = st.columns(2)
                with colA:
                    fig_dow_int = px.bar(dow_int_data, x='day_of_week', y=['total_1m_int', 'total_due_int', 'total_extra_int', 'total_close_int'], title="Total Amounts by Day (₹)", barmode='stack')
                    fig_dow_int.update_layout(hovermode="x unified"); st.plotly_chart(fig_dow_int, use_container_width=True)
                with colB:
                    fig_dow_pct = px.bar(dow_int_data, x='day_of_week', y=['1M %', 'Due %', 'Extra %', 'Close %'], title="Percentage Split by Day (%)", barmode='stack')
                    fig_dow_pct.update_layout(hovermode="x unified"); st.plotly_chart(fig_dow_pct, use_container_width=True)
                
                disp_dow_int = dow_int_data.copy()
                disp_dow_int = disp_dow_int.rename(columns={'day_of_week': 'Day', 'total_1m_int': '1-Month (₹)', 'total_due_int': 'Due (₹)', 'total_extra_int': 'Extra (₹)', 'total_close_int': 'Close (₹)', 'total_overall_interest': 'Overall (₹)'})
                for col in ['1-Month (₹)', 'Due (₹)', 'Extra (₹)', 'Close (₹)', 'Overall (₹)']: disp_dow_int[col] = disp_dow_int[col].round(2)
                for col in ['1M %', 'Due %', 'Extra %', 'Close %']: disp_dow_int[col] = disp_dow_int[col].round(2).astype(str) + '%'
                st.dataframe(disp_dow_int, hide_index=True, use_container_width=True)

            with itab6:
                st.markdown("### 📊 Comprehensive Interest Revenue Analysis")
                st.info("💡 This view breaks down where your interest revenue is coming from, tracking monthly trends and product splits.")

                # --- 1. GRAND TOTALS ---
                st.markdown("##### 💰 GRAND TOTALS (For Selected Dates)")
                total_int_data = {
                    "Metric": ["Overall Collected Interest"],
                    "1-Month (₹)": [f"₹ {filtered_data['total_1m_int'].sum():,.2f}"],
                    "Due Int (₹)": [f"₹ {filtered_data['total_due_int'].sum():,.2f}"],
                    "Extra Int (₹)": [f"₹ {filtered_data['total_extra_int'].sum():,.2f}"],
                    "Close Int (₹)": [f"₹ {filtered_data['total_close_int'].sum():,.2f}"],
                    "Grand Total (₹)": [f"₹ {filtered_data['total_overall_interest'].sum():,.2f}"]
                }
                st.dataframe(pd.DataFrame(total_int_data), hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)

                # --- 2. REVENUE COMPOSITION (What drives the revenue?) ---
                st.markdown("##### 🥧 REVENUE COMPOSITION (By Interest Type)")
                tot_overall = filtered_data['total_overall_interest'].sum()
                if tot_overall > 0:
                    comp_data = {
                        "Interest Source": ["1-Month Advance", "Due (Monthly) Interest", "Extra Penalties", "Closing Interest"],
                        "Amount (₹)": [
                            f"₹ {filtered_data['total_1m_int'].sum():,.0f}",
                            f"₹ {filtered_data['total_due_int'].sum():,.0f}",
                            f"₹ {filtered_data['total_extra_int'].sum():,.0f}",
                            f"₹ {filtered_data['total_close_int'].sum():,.0f}"
                        ],
                        "Share % of Revenue": [
                            f"{(filtered_data['total_1m_int'].sum() / tot_overall * 100):.1f}%",
                            f"{(filtered_data['total_due_int'].sum() / tot_overall * 100):.1f}%",
                            f"{(filtered_data['total_extra_int'].sum() / tot_overall * 100):.1f}%",
                            f"{(filtered_data['total_close_int'].sum() / tot_overall * 100):.1f}%"
                        ]
                    }
                    st.dataframe(pd.DataFrame(comp_data), hide_index=True, use_container_width=True)
                else:
                    st.write("No interest revenue in selected period.")
                st.markdown("<br>", unsafe_allow_html=True)

                # --- 3. GOLD VS SILVER REVENUE SPLIT ---
                st.markdown("##### 🥇🥈 PRODUCT PERFORMANCE (Gold vs Silver Interest)")
                total_g_all = filtered_data['gold_1m_int'].sum() + filtered_data['gold_due_int'].sum() + filtered_data['gold_extra_int'].sum() + filtered_data['gold_close_int'].sum()
                total_s_all = filtered_data['silver_1m_int'].sum() + filtered_data['silver_due_int'].sum() + filtered_data['silver_extra_int'].sum() + filtered_data['silver_close_int'].sum()
                
                prod_data = {
                    "Product Type": ["🥇 Gold Loans", "🥈 Silver Loans"],
                    "Total Interest Collected (₹)": [f"₹ {total_g_all:,.0f}", f"₹ {total_s_all:,.0f}"],
                    "Share %": [
                        f"{(total_g_all / tot_overall * 100):.1f}%" if tot_overall > 0 else "0%",
                        f"{(total_s_all / tot_overall * 100):.1f}%" if tot_overall > 0 else "0%"
                    ]
                }
                st.dataframe(pd.DataFrame(prod_data), hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)

                # --- 4. MONTHLY INTEREST COLLECTION TRENDS ---
                st.markdown("##### 📊 MONTHLY REVENUE TRENDS")
                st.info("💡 Tracks how much interest you collect month-over-month. Helps identify seasonal peaks in loan closings or due payments.")
                
                m_int_data = filtered_data.copy()
                m_int_data['Month-Year'] = m_int_data['date'].dt.to_period('M')
                
                m_trend = m_int_data.groupby('Month-Year').agg(
                    Total_1M=('total_1m_int', 'sum'),
                    Total_Due=('total_due_int', 'sum'),
                    Total_Extra=('total_extra_int', 'sum'),
                    Total_Close=('total_close_int', 'sum'),
                    Overall_Int=('total_overall_interest', 'sum')
                ).reset_index()
                
                m_trend['MoM_Growth_%'] = m_trend['Overall_Int'].pct_change() * 100
                m_trend['MoM_Growth_%'] = m_trend['MoM_Growth_%'].fillna(0).round(2).astype(str) + '%'
                
                for col in ['Total_1M', 'Total_Due', 'Total_Extra', 'Total_Close', 'Overall_Int']:
                    m_trend[col] = m_trend[col].apply(lambda x: f"₹ {x:,.0f}")
                
                m_trend['Month-Year'] = m_trend['Month-Year'].dt.strftime('%b %Y')
                m_trend = m_trend.rename(columns={
                    'Total_1M': '1-Month (₹)', 'Total_Due': 'Due (₹)', 
                    'Total_Extra': 'Extra (₹)', 'Total_Close': 'Close (₹)', 
                    'Overall_Int': 'Total Revenue (₹)', 'MoM_Growth_%': 'MoM Growth'
                })
                
                st.dataframe(m_trend, hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)

                # --- 5. RAW DAILY LOG ---
                st.markdown("##### 📅 DAILY INTEREST RECORD (RAW DATA)")
                int_df = filtered_data[['date', 'total_1m_int', 'total_due_int', 'total_extra_int', 'total_close_int', 'total_overall_interest', '1m_baseline_pct', 'due_baseline_pct', 'close_baseline_pct']].copy()
                int_df['date'] = int_df['date'].dt.strftime('%d-%m-%Y')
                
                for col in ['1m_baseline_pct', 'due_baseline_pct', 'close_baseline_pct']:
                    int_df[col] = int_df[col].round(2).astype(str) + '%'
                    
                int_df = int_df.rename(columns={
                    'date': 'Date', 'total_1m_int': '1-Month (₹)', 'total_due_int': 'Due (₹)', 
                    'total_extra_int': 'Extra (₹)', 'total_close_int': 'Close (₹)', 
                    'total_overall_interest': 'Total (₹)', 
                    '1m_baseline_pct': '1M Growth', 'due_baseline_pct': 'Due Growth', 'close_baseline_pct': 'Close Growth'
                })
                st.dataframe(int_df, hide_index=True, use_container_width=True)

        # --- NEW: FUTURE ANALYSIS SUB-TAB FOR INTEREST ---
            with itab_future:
                st.subheader("🔮 Mathematical Future Projections (Interest Revenue)")
                st.info("💡 This tool analyzes your historical interest collection to mathematically predict future cash flow trends. It helps you see if your revenue will rely more on new dispersals (1-Month) or backend collections (Due/Close).")
                
                if len(filtered_data['date'].unique()) < 5:
                    st.warning("⚠️ Not enough historical data selected. Please widen your Date Filter to include at least 5 distinct days of loan activity.")
                else:
                    forecast_months = st.slider("Select Forecast Horizon (Months):", min_value=1, max_value=12, value=3, key="int_growth_forecast")
                    forecast_days = forecast_months * 30
                    
                    trend_data = filtered_data.groupby('date')[['total_overall_interest', 'total_1m_int', 'total_due_int', 'total_close_int']].sum().reset_index()
                    
                    x_historical = (trend_data['date'] - trend_data['date'].min()).dt.days.values
                    last_date = trend_data['date'].max()
                    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_days)
                    x_future = np.arange(x_historical[-1] + 1, x_historical[-1] + 1 + forecast_days)
                    
                    def get_projection(y_vals):
                        z = np.polyfit(x_historical, y_vals, 1)
                        p = np.poly1d(z)
                        return np.maximum(p(x_future), 0), z[0]
                    
                    fut_tot, slope_tot = get_projection(trend_data['total_overall_interest'].values)
                    fut_1m, slope_1m = get_projection(trend_data['total_1m_int'].values)
                    fut_due, slope_due = get_projection(trend_data['total_due_int'].values)
                    fut_close, slope_close = get_projection(trend_data['total_close_int'].values)
                    
                    st.markdown("##### 🚀 Revenue Trajectory Analysis")
                    c1, c2, c3, c4 = st.columns(4)
                    
                    def render_slope(col, title, slope_val):
                        direction = "📈 Growing" if slope_val > 0 else ("📉 Shrinking" if slope_val < 0 else "➡️ Flat")
                        color = "green" if slope_val > 0 else ("red" if slope_val < 0 else "gray")
                        col.markdown(f"**{title}:**")
                        col.markdown(f"<h5 style='color: {color}; margin-top: -10px;'>{direction} ({slope_val:,.1f} ₹/day)</h5>", unsafe_allow_html=True)
                    
                    render_slope(c1, "Overall Interest", slope_tot)
                    render_slope(c2, "1-Month (Advance)", slope_1m)
                    render_slope(c3, "Due Interest", slope_due)
                    render_slope(c4, "Closing Interest", slope_close)
                    st.write("---")
                    
                    st.markdown(f"##### 🎯 Expected Revenue (Next {forecast_months} Months)")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Est. Total Interest Revenue", f"₹ {fut_tot.sum():,.0f}")
                    m2.metric("Est. Advance Collection (1-Month)", f"₹ {fut_1m.sum():,.0f}")
                    m3.metric("Est. Backend Collection (Due+Close)", f"₹ {(fut_due.sum() + fut_close.sum()):,.0f}")
                    st.write("---")
                    
                    st.markdown("##### 📈 Interest Projection Visualizations")
                    g_col1, g_col2 = st.columns(2)
                    
                    with g_col1:
                        hist_plot = pd.DataFrame({'Date': trend_data['date'], 'Value': trend_data['total_overall_interest'].values, 'Type': 'Historical (Actual)'})
                        fut_plot = pd.DataFrame({'Date': future_dates, 'Value': fut_tot, 'Type': 'Projected (Mathematical)'})
                        combined_plot = pd.concat([hist_plot, fut_plot])
                        
                        fig_fut_int = px.line(combined_plot, x='Date', y='Value', color='Type', title="Overall Interest Revenue Prediction",
                                              color_discrete_map={'Historical (Actual)': '#2ca02c', 'Projected (Mathematical)': '#FF8C00'})
                        fig_fut_int.update_traces(line=dict(dash="dot"), selector=dict(name='Projected (Mathematical)'))
                        fig_fut_int.update_layout(hovermode="x unified", yaxis_title="Interest (₹)")
                        st.plotly_chart(fig_fut_int, use_container_width=True)
                        
                    with g_col2:
                        hist_split = pd.DataFrame({'Date': trend_data['date'], '1-Month Advance': trend_data['total_1m_int'].values, 'Backend (Due+Close)': trend_data['total_due_int'].values + trend_data['total_close_int'].values})
                        fut_split = pd.DataFrame({'Date': future_dates, '1-Month Advance': fut_1m, 'Backend (Due+Close)': fut_due + fut_close})
                        combined_split = pd.concat([hist_split, fut_split]).melt(id_vars=['Date'], var_name='Revenue Type', value_name='Amount')
                        
                        fig_split = px.area(combined_split, x='Date', y='Amount', color='Revenue Type', title="Future Revenue Composition",
                                            color_discrete_map={'1-Month Advance': '#1f77b4', 'Backend (Due+Close)': '#d62728'})
                        fig_split.update_layout(hovermode="x unified", yaxis_title="Interest (₹)")
                        st.plotly_chart(fig_split, use_container_width=True)

        if sub_page == "📑 All Summary (Everything)": st.write("---")
    
    # ==========================================
    # SECTION 2B: PAPER CHARGES
    # ==========================================
    if sub_page in ["📄 Doc & Paper Charges", "📑 All Summary (Everything)"]:
        if sub_page == "📑 All Summary (Everything)": st.header("📄 Paper Charges")
        else: st.subheader("Paper Charge Collection Analysis")

        if not filtered_data.empty and 'total_paper' in filtered_data.columns:
            st.markdown("### Top Metrics Summary")
            t_paper = filtered_data['total_paper'].sum()
            t_paper_g = filtered_data['gold_paper'].sum()
            t_paper_s = filtered_data['silver_paper'].sum()
            total_days = len(filtered_data['date'].unique())

            p1, p2, p3 = st.columns(3)
            with p1:
                st.metric("Total Gold Paper Charge", f"₹ {t_paper_g:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>📊 Avg/Day: ₹{(t_paper_g/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with p2:
                st.metric("Total Silver Paper Charge", f"₹ {t_paper_s:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>📊 Avg/Day: ₹{(t_paper_s/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)
            with p3:
                st.metric("Overall Paper Charge", f"₹ {t_paper:,.0f}")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>📊 Avg/Day: ₹{(t_paper/total_days) if total_days > 0 else 0:,.0f}</div>", unsafe_allow_html=True)

            st.write("---")

            # Safely calculate baseline centers
            f_p_tot = filtered_data.loc[filtered_data['total_paper'] > 0, 'total_paper'].iloc[0] if (filtered_data['total_paper'] > 0).any() else 0
            f_p_g = filtered_data.loc[filtered_data['gold_paper'] > 0, 'gold_paper'].iloc[0] if (filtered_data['gold_paper'] > 0).any() else 0
            f_p_s = filtered_data.loc[filtered_data['silver_paper'] > 0, 'silver_paper'].iloc[0] if (filtered_data['silver_paper'] > 0).any() else 0

            filtered_data['paper_baseline_pct'] = np.where(f_p_tot > 0, ((filtered_data['total_paper'] - f_p_tot)/f_p_tot)*100, 0)

            ptab_exec, ptab1, ptab2, ptab3, ptab4, tab_future = st.tabs(["👑 Executive Summary", "📊 Split Charges", "💰 Total Overall", "🚀 Growth %", "📋 Data Table", "🔮 Future Analysis"])
            with ptab_exec:
                st.markdown("### 👑 Operational Income Executive Summary")
                st.info("💡 **Overview:** Tracking your secondary income from documentation and paper charges.")
                
                ep_col1, ep_col2 = st.columns(2)
                with ep_col1:
                    pap_df = pd.DataFrame({"Type": ["Gold Paper Charges", "Silver Paper Charges"], "Amount": [filtered_data['gold_paper'].sum(), filtered_data['silver_paper'].sum()]})
                    fig_pap_donut = px.pie(pap_df, names="Type", values="Amount", hole=0.5, title="Paper Charge Composition", color="Type", color_discrete_map={"Gold Paper Charges": "#FFD700", "Silver Paper Charges": "#C0C0C0"})
                    st.plotly_chart(fig_pap_donut, use_container_width=True)
                with ep_col2:
                    fig_pap_trend = px.area(filtered_data, x='date', y='total_paper', title="Daily Operational Income Trend", color_discrete_sequence=['#8c564b'])
                    fig_pap_trend.update_layout(yaxis_title="Paper Charges (₹)", hovermode="x unified")
                    st.plotly_chart(fig_pap_trend, use_container_width=True)

            with ptab1:
                st.markdown("#### Split Charges (Gold vs Silver)")
                fig_p_split = px.line(filtered_data, x='date', y=['gold_paper', 'silver_paper'], title="Gold vs Silver Paper Charges", markers=True, color_discrete_map={'gold_paper': '#FFD700', 'silver_paper': '#C0C0C0'})
                if f_p_g > 0: fig_p_split.add_hline(y=f_p_g, line_dash="dot", line_color="#FFD700", opacity=0.5)
                if f_p_s > 0: fig_p_split.add_hline(y=f_p_s, line_dash="dot", line_color="#C0C0C0", opacity=0.5)
                fig_p_split.update_layout(hovermode="x unified"); st.plotly_chart(fig_p_split, use_container_width=True)

            with ptab2:
                st.markdown("#### Total Overall Paper Charges")
                fig_p_tot = px.line(filtered_data, x='date', y=['total_paper'], title="Total Paper Charges (Single Line)", markers=True, color_discrete_map={'total_paper': '#FF4B4B'})
                if f_p_tot > 0: fig_p_tot.add_hline(y=f_p_tot, line_dash="dot", line_color="black", annotation_text="Day 1 Center Line")
                fig_p_tot.update_layout(hovermode="x unified"); st.plotly_chart(fig_p_tot, use_container_width=True)

            with ptab3:
                st.markdown("#### Growth Percentage (Starts at 0%)")
                fig_p_base = px.line(filtered_data, x='date', y=['paper_baseline_pct'], title="Paper Charge Baseline Growth %", markers=True, color_discrete_map={'paper_baseline_pct': '#1f77b4'})
                fig_p_base.add_hline(y=0, line_dash="solid", line_color="black")
                fig_p_base.update_layout(hovermode="x unified"); st.plotly_chart(fig_p_base, use_container_width=True)

            with ptab4:
                st.markdown("##### 📌 PAPER CHARGE AVERAGES")
                avg_p_data = {
                    "Metric": ["Daily Average"],
                    "Gold Paper (₹)": [f"₹ {filtered_data['gold_paper'].mean():,.2f}"],
                    "Silver Paper (₹)": [f"₹ {filtered_data['silver_paper'].mean():,.2f}"],
                    "Total Paper (₹)": [f"₹ {filtered_data['total_paper'].mean():,.2f}"],
                    "Growth (%)": [f"{filtered_data['paper_baseline_pct'].mean():.2f}%"]
                }
                st.dataframe(pd.DataFrame(avg_p_data), hide_index=True, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown("##### 📅 DAILY BREAKDOWN")
                p_df = filtered_data[['date', 'gold_paper', 'silver_paper', 'total_paper', 'paper_baseline_pct']].copy()
                p_df['date'] = p_df['date'].dt.strftime('%d-%m-%Y')
                p_df['paper_baseline_pct'] = p_df['paper_baseline_pct'].round(2).astype(str) + '%'
                for col in ['gold_paper', 'silver_paper', 'total_paper']: p_df[col] = p_df[col].round(2)
                p_df = p_df.rename(columns={'date': 'Date', 'gold_paper': 'Gold Charge (₹)', 'silver_paper': 'Silver Charge (₹)', 'total_paper': 'Total Charge (₹)', 'paper_baseline_pct': 'Growth %'})
                st.dataframe(p_df, hide_index=True, use_container_width=True)

            with tab_future:
                st.subheader("🔮 Mathematical Future Projections (Paper Charges)")
                st.info("💡 This tool analyzes your historical Paper Charges to mathematically predict future cash flow from these operational fees.")
                
                if len(filtered_data['date'].unique()) < 5:
                    st.warning("⚠️ Not enough historical data selected. Please widen your Date Filter to include at least 5 distinct days of activity.")
                else:
                    forecast_months = st.slider("Select Forecast Horizon (Months):", min_value=1, max_value=12, value=3, key="paper_growth_forecast")
                    forecast_days = forecast_months * 30
                    
                    trend_data = filtered_data.groupby('date')[['total_paper', 'gold_paper', 'silver_paper']].sum().reset_index()
                    
                    x_historical = (trend_data['date'] - trend_data['date'].min()).dt.days.values
                    last_date = trend_data['date'].max()
                    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_days)
                    x_future = np.arange(x_historical[-1] + 1, x_historical[-1] + 1 + forecast_days)
                    
                    def get_projection(y_vals):
                        z = np.polyfit(x_historical, y_vals, 1)
                        p = np.poly1d(z)
                        return np.maximum(p(x_future), 0), z[0]
                    
                    fut_paper, slope_paper = get_projection(trend_data['total_paper'].values)
                    fut_gold, slope_gold = get_projection(trend_data['gold_paper'].values)
                    fut_silver, slope_silver = get_projection(trend_data['silver_paper'].values)
                    
                    st.markdown("##### 🚀 Charges Trajectory Analysis")
                    c1, c2, c3 = st.columns(3)
                    
                    def render_slope(col, title, slope_val):
                        direction = "📈 Growing" if slope_val > 0 else ("📉 Shrinking" if slope_val < 0 else "➡️ Flat")
                        color = "green" if slope_val > 0 else ("red" if slope_val < 0 else "gray")
                        col.markdown(f"**{title}:**")
                        col.markdown(f"<h5 style='color: {color}; margin-top: -10px;'>{direction} ({slope_val:,.1f} ₹/day)</h5>", unsafe_allow_html=True)
                    
                    render_slope(c1, "Total Paper Charges", slope_paper)
                    render_slope(c2, "Gold Paper Charges", slope_gold)
                    render_slope(c3, "Silver Paper Charges", slope_silver)
                    st.write("---")
                    
                    st.markdown(f"##### 🎯 Expected Collection (Next {forecast_months} Months)")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Est. Total Paper Charges", f"₹ {fut_paper.sum():,.0f}")
                    m2.metric("Est. Gold Paper Charges", f"₹ {fut_gold.sum():,.0f}")
                    m3.metric("Est. Silver Paper Charges", f"₹ {fut_silver.sum():,.0f}")
                    st.write("---")
                    
                    st.markdown("##### 📈 Charges Projection Visualizations")
                    hist_plot = pd.DataFrame({'Date': trend_data['date'], 'Value': trend_data['total_paper'].values, 'Type': 'Historical (Actual)'})
                    fut_plot = pd.DataFrame({'Date': future_dates, 'Value': fut_paper, 'Type': 'Projected (Mathematical)'})
                    combined_plot = pd.concat([hist_plot, fut_plot])
                    
                    fig_fut_pap = px.line(combined_plot, x='Date', y='Value', color='Type', title="Total Paper Charges Prediction",
                                          color_discrete_map={'Historical (Actual)': '#1f77b4', 'Projected (Mathematical)': '#FF8C00'})
                    fig_fut_pap.update_traces(line=dict(dash="dot"), selector=dict(name='Projected (Mathematical)'))
                    fig_fut_pap.update_layout(hovermode="x unified", yaxis_title="Amount (₹)")
                    st.plotly_chart(fig_fut_pap, use_container_width=True)

        if sub_page == "📑 All Summary (Everything)": st.write("---")

    # ==========================================
    # SECTION 2C: ACTIVE & OVERDUE (LIVE STATUS)
    # ==========================================
    if sub_page in ["⚠️ Active & Overdue", "📑 All Summary (Everything)"]:
        if sub_page == "📑 All Summary (Everything)": st.header("⚠️ Active & Overdue")
        else: st.subheader("Live Portfolio Health (Active vs Overdue)")
        
        if ao_data is not None and not ao_data.empty:
            
            # --- NEW: INDEPENDENT DATE FILTER FOR LIVE LOANS ---
            st.markdown("#### 📅 Filter Live Loans by Dispersal Date")
            ao_min_date = ao_data['loan_date'].min().date()
            ao_max_date = ao_data['loan_date'].max().date()
            
            ao_col1, ao_col2 = st.columns([1, 3])
            with ao_col1:
                ao_date_range = st.date_input(
                    "Select Dispersal Date Range:",
                    value=(ao_min_date, ao_max_date),
                    min_value=ao_min_date,
                    max_value=ao_max_date,
                    key="ao_date_picker" # Unique key prevents conflict with the top filter
                )
            
            if len(ao_date_range) == 2:
                ao_start, ao_end = ao_date_range
                f_ao = ao_data[(ao_data['loan_date'] >= pd.to_datetime(ao_start)) & (ao_data['loan_date'] <= pd.to_datetime(ao_end))]
            else:
                f_ao = ao_data.copy()
            
            st.write("---")
            # --------------------------------------------------

            if not f_ao.empty:
                act_df = f_ao[f_ao['state'] == 'Active']
                ovr_df = f_ao[f_ao['state'] == 'Overdue']
                
                t_act_amt = act_df['principal_amount'].sum()
                t_ovr_amt = ovr_df['principal_amount'].sum()
                overall_tot = t_act_amt + t_ovr_amt
                
                # --- NEW: Added Future Risk Forecast to the menu! ---
                ao_view = st.radio("Select View:", ["👑 Executive Summary", "💼 Principal Amounts", "📈 Live Calculated Interest", "📋 Data Table", "🔮 Future Risk Forecast"], horizontal=True)
                st.write("---")
                if ao_view == "👑 Executive Summary":
                    st.markdown("### 👑 Portfolio Health Executive Summary")
                    st.info("💡 **Overview:** A master view of your system's health, separating safe capital from high-risk overdue capital.")
                    
                    eao_col1, eao_col2 = st.columns(2)
                    with eao_col1:
                        # Health Gauge/Donut
                        health_df = pd.DataFrame({
                            "Status": ["Safe (Active)", "Risk (Overdue)"],
                            "Amount": [t_act_amt, t_ovr_amt]
                        })
                        fig_health_donut = px.pie(health_df, names="Status", values="Amount", hole=0.6, title="Portfolio Capital Health", color="Status", color_discrete_map={"Safe (Active)": "#2ca02c", "Risk (Overdue)": "#d62728"})
                        fig_health_donut.update_traces(textposition='inside', textinfo='percent+label')
                        st.plotly_chart(fig_health_donut, use_container_width=True)
                        
                    with eao_col2:
                        # Principal vs Uncollected Interest Bar
                        t_act_int = act_df['calculated_interest'].sum()
                        t_ovr_int = ovr_df['calculated_interest'].sum()
                        t_ovrall_int = t_act_int + t_ovr_int
                        
                        pv_int_df = pd.DataFrame({
                            "Metric": ["Total Principal Given", "Total Uncollected Interest"],
                            "Value": [overall_tot, t_ovrall_int]
                        })
                        fig_pv_int = px.bar(pv_int_df, x="Metric", y="Value", title="Capital vs Expected Return", color="Metric", color_discrete_map={"Total Principal Given": "#1f77b4", "Total Uncollected Interest": "#ff7f0e"}, text_auto='.2s')
                        st.plotly_chart(fig_pv_int, use_container_width=True)
                        
                    st.write("---")
                
                if ao_view == "💼 Principal Amounts":
                    st.markdown("### Outstanding Principal Amounts Top Metrics")
                    st.info("💡 Note: These metrics sum the Current Outstanding Principal (Present Amount) of your live loans. 'Overdue' is strictly defined as > 1 year.")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Total Active Principal", f"₹ {t_act_amt:,.0f}")
                        g_act = act_df[act_df['loan_type']=='Gold']['principal_amount'].sum()
                        s_act = act_df[act_df['loan_type']=='Silver']['principal_amount'].sum()
                        g_act_c = len(act_df[act_df['loan_type']=='Gold'])
                        s_act_c = len(act_df[act_df['loan_type']=='Silver'])
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_act:,.0f} ({g_act_c})<br>🥈 Silver: ₹{s_act:,.0f} ({s_act_c})</div>", unsafe_allow_html=True)
                    with c2:
                        st.metric("Total Overdue Principal", f"₹ {t_ovr_amt:,.0f}")
                        g_ovr = ovr_df[ovr_df['loan_type']=='Gold']['principal_amount'].sum()
                        s_ovr = ovr_df[ovr_df['loan_type']=='Silver']['principal_amount'].sum()
                        g_ovr_c = len(ovr_df[ovr_df['loan_type']=='Gold'])
                        s_ovr_c = len(ovr_df[ovr_df['loan_type']=='Silver'])
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_ovr:,.0f} ({g_ovr_c})<br>🥈 Silver: ₹{s_ovr:,.0f} ({s_ovr_c})</div>", unsafe_allow_html=True)
                    with c3:
                        st.metric("Overall Outstanding Principal", f"₹ {overall_tot:,.0f}")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>Total Live Loans: {len(f_ao)}</div>", unsafe_allow_html=True)
                    
                    st.write("---")
                    
                    grp_ao = f_ao.groupby(['loan_date', 'state'])['principal_amount'].sum().reset_index()
                    grp_ao = grp_ao.sort_values('loan_date')
                    
                    fig_ao = px.bar(grp_ao, x='loan_date', y='principal_amount', color='state', 
                                    title="Active vs Overdue Principal (Grouped by Loan Date)", barmode='stack',
                                    color_discrete_map={'Active': '#2ca02c', 'Overdue': '#d62728'})
                    fig_ao.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_ao, use_container_width=True)

                elif ao_view == "📈 Live Calculated Interest":
                    st.markdown("### Live Uncollected Interest Top Metrics")
                    st.info("💡 Note: Interest is dynamically calculated precisely like your Loan Close page (Up to Today's Date, applying Penalty Thresholds).")
                    
                    t_act_int = act_df['calculated_interest'].sum()
                    t_ovr_int = ovr_df['calculated_interest'].sum()
                    t_ovrall_int = t_act_int + t_ovr_int
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Active Interest Outstanding", f"₹ {t_act_int:,.0f}")
                        g_act_int = act_df[act_df['loan_type']=='Gold']['calculated_interest'].sum()
                        s_act_int = act_df[act_df['loan_type']=='Silver']['calculated_interest'].sum()
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold Int: ₹{g_act_int:,.0f}<br>🥈 Silver Int: ₹{s_act_int:,.0f}<br>Active Count: {len(act_df)}</div>", unsafe_allow_html=True)
                    with c2:
                        st.metric("Overdue Interest Outstanding", f"₹ {t_ovr_int:,.0f}")
                        g_ovr_int = ovr_df[ovr_df['loan_type']=='Gold']['calculated_interest'].sum()
                        s_ovr_int = ovr_df[ovr_df['loan_type']=='Silver']['calculated_interest'].sum()
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold Int: ₹{g_ovr_int:,.0f}<br>🥈 Silver Int: ₹{s_ovr_int:,.0f}<br>Overdue Count: {len(ovr_df)}</div>", unsafe_allow_html=True)
                    with c3:
                        st.metric("Total Uncollected Interest", f"₹ {t_ovrall_int:,.0f}")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>Total Live Loans: {len(f_ao)}</div>", unsafe_allow_html=True)
                        
                    st.write("---")

                    st.markdown("#### 📈 Uncollected Interest Graphs")
                    tab_a, tab_b = st.tabs(["📅 Timeline (By Loan Date)", "🕰️ Risk Exposure (By Loan Age)"])
                    
                    with tab_a:
                        grp_int = f_ao.groupby(['loan_date', 'state'])['calculated_interest'].sum().reset_index()
                        grp_int = grp_int.sort_values('loan_date')
                        fig_int = px.bar(grp_int, x='loan_date', y='calculated_interest', color='state', 
                                        title="Uncollected Interest (By Original Dispersal Date)", barmode='stack',
                                        color_discrete_map={'Active': '#2ca02c', 'Overdue': '#d62728'})
                        fig_int.update_layout(hovermode="x unified", xaxis_title="Loan Date", yaxis_title="Expected Interest (₹)")
                        st.plotly_chart(fig_int, use_container_width=True)
                        
                    with tab_b:
                        st.info("💡 Shows how much of your uncollected money is trapped in older, riskier loans vs fresh active loans.")
                        bins = [-1, 6, 12, 18, 24, 36, 1000]
                        labels = ['0-6 Months', '6-12 Months', '1-1.5 Years', '1.5-2 Years', '2-3 Years', '3+ Years']
                        f_ao['Age_Bucket'] = pd.cut(f_ao['total_month'], bins=bins, labels=labels)
                        age_int_df = f_ao.groupby(['Age_Bucket', 'loan_type'], observed=True)['calculated_interest'].sum().reset_index()
                        
                        fig_age = px.bar(age_int_df, x='Age_Bucket', y='calculated_interest', color='loan_type',
                                         title="Uncollected Interest by Loan Age (Gold vs Silver)", barmode='group',
                                         color_discrete_map={'Gold': '#FFD700', 'Silver': '#C0C0C0'})
                        fig_age.update_layout(xaxis_title="Age of Loan", yaxis_title="Uncollected Interest (₹)")
                        st.plotly_chart(fig_age, use_container_width=True)

                    st.write("---")
                    
                    disp_int = f_ao[['form_no', 'loan_date', 'loan_type', 'state', 'principal_amount', 'total_month', 'due_month', 'return_1', 'final_month', 'one_month', 'calculated_interest']].copy()
                    disp_int['loan_date'] = disp_int['loan_date'].dt.strftime('%d-%m-%Y')
                    disp_int['total_month'] = disp_int['total_month'].round(1)
                    disp_int['due_month'] = disp_int['due_month'].round(1)
                    disp_int['final_month'] = disp_int['final_month'].round(1)
                    disp_int['return_1'] = disp_int['return_1'].astype(int) 
                    
                    disp_int = disp_int.sort_values(by='calculated_interest', ascending=False)
                    disp_int = disp_int.rename(columns={
                        'form_no': 'Form No', 'loan_date': 'Loan Date', 'loan_type': 'Type', 
                        'state': 'Status', 'principal_amount': 'Present Amount (₹)', 
                        'total_month': 'Tot Mths', 'due_month': 'Due Mths', 
                        'return_1': 'Return 1', 'final_month': 'Final Mths',
                        'one_month': 'One Month (₹)', 'calculated_interest': 'Live Interest Due (₹)'
                    })
                    
                    st.markdown("##### 🥇 GOLD LOANS: LIVE INTEREST EXPECTATION")
                    gold_df = disp_int[disp_int['Type'] == 'Gold'].drop(columns=['Type'])
                    if not gold_df.empty: st.dataframe(gold_df, hide_index=True, use_container_width=True)
                    else: st.info("No Active/Overdue Gold loans found.")
                        
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    st.markdown("##### 🥈 SILVER LOANS: LIVE INTEREST EXPECTATION")
                    silver_df = disp_int[disp_int['Type'] == 'Silver'].drop(columns=['Type'])
                    if not silver_df.empty: st.dataframe(silver_df, hide_index=True, use_container_width=True)
                    else: st.info("No Active/Overdue Silver loans found.")

                elif ao_view == "📋 Data Table":
                    st.markdown("### 📊 Comprehensive Portfolio Data Summary")
                    st.info("This view combines Principal and Interest data to give you a top-down executive summary of your active and overdue loans.")

                    t_prin_g = f_ao[f_ao['loan_type']=='Gold']['principal_amount'].sum()
                    t_prin_s = f_ao[f_ao['loan_type']=='Silver']['principal_amount'].sum()
                    t_prin_tot = f_ao['principal_amount'].sum()

                    t_int_g = f_ao[f_ao['loan_type']=='Gold']['calculated_interest'].sum()
                    t_int_s = f_ao[f_ao['loan_type']=='Silver']['calculated_interest'].sum()
                    t_int_tot = f_ao['calculated_interest'].sum()

                    c_g = len(f_ao[f_ao['loan_type']=='Gold'])
                    c_s = len(f_ao[f_ao['loan_type']=='Silver'])
                    c_tot = len(f_ao)

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Total Outstanding Principal", f"₹ {t_prin_tot:,.0f}")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{t_prin_g:,.0f}<br>🥈 Silver: ₹{t_prin_s:,.0f}</div>", unsafe_allow_html=True)
                    with c2:
                        st.metric("Total Uncollected Interest", f"₹ {t_int_tot:,.0f}")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{t_int_g:,.0f}<br>🥈 Silver: ₹{t_int_s:,.0f}</div>", unsafe_allow_html=True)
                    with c3:
                        st.metric("Total Live Loans (Count)", f"{c_tot:,.0f} loans")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: {c_g:,.0f}<br>🥈 Silver: {c_s:,.0f}</div>", unsafe_allow_html=True)
                    st.write("---")

                    st.markdown("##### 🥧 PORTFOLIO COMPOSITION (PERCENTAGES)")
                    colA, colB = st.columns(2)
                    with colA:
                        state_df = f_ao.groupby('state').agg(Count=('id', 'count'), Principal=('principal_amount', 'sum'), Interest=('calculated_interest', 'sum')).reset_index()
                        state_df['Count %'] = (state_df['Count'] / c_tot * 100).round(1).astype(str) + '%' if c_tot > 0 else '0%'
                        state_df['Principal %'] = (state_df['Principal'] / t_prin_tot * 100).round(1).astype(str) + '%' if t_prin_tot > 0 else '0%'
                        state_df['Interest %'] = (state_df['Interest'] / t_int_tot * 100).round(1).astype(str) + '%' if t_int_tot > 0 else '0%'
                        state_df = state_df.rename(columns={'state': 'Status'})
                        st.dataframe(state_df, hide_index=True, use_container_width=True)
                    with colB:
                        type_df = f_ao.groupby('loan_type').agg(Count=('id', 'count'), Principal=('principal_amount', 'sum'), Interest=('calculated_interest', 'sum')).reset_index()
                        type_df['Count %'] = (type_df['Count'] / c_tot * 100).round(1).astype(str) + '%' if c_tot > 0 else '0%'
                        type_df['Principal %'] = (type_df['Principal'] / t_prin_tot * 100).round(1).astype(str) + '%' if t_prin_tot > 0 else '0%'
                        type_df['Interest %'] = (type_df['Interest'] / t_int_tot * 100).round(1).astype(str) + '%' if t_int_tot > 0 else '0%'
                        type_df = type_df.rename(columns={'loan_type': 'Loan Type'})
                        st.dataframe(type_df, hide_index=True, use_container_width=True)

                    st.write("---")

                    st.markdown("##### 📅 YEARLY BREAKDOWN (BY DISPERSAL YEAR)")
                    f_ao['Year'] = f_ao['loan_date'].dt.year
                    yr_df = f_ao.groupby('Year').agg(Loan_Count=('id', 'count'), Principal=('principal_amount', 'sum'), Expected_Interest=('calculated_interest', 'sum')).reset_index().sort_values('Year', ascending=False)
                    yr_df['Principal Share %'] = (yr_df['Principal'] / t_prin_tot * 100).round(2).astype(str) + '%' if t_prin_tot > 0 else '0%'
                    yr_df['Interest Share %'] = (yr_df['Expected_Interest'] / t_int_tot * 100).round(2).astype(str) + '%' if t_int_tot > 0 else '0%'
                    yr_df['Principal'] = yr_df['Principal'].apply(lambda x: f"₹ {x:,.0f}")
                    yr_df['Expected_Interest'] = yr_df['Expected_Interest'].apply(lambda x: f"₹ {x:,.0f}")
                    yr_df = yr_df.rename(columns={'Year': 'Dispersal Year', 'Loan_Count': 'Total Loans', 'Principal': 'Total Principal (₹)', 'Expected_Interest': 'Uncollected Interest (₹)'})
                    st.dataframe(yr_df, hide_index=True, use_container_width=True)
                    st.write("---")

                    st.markdown("##### ⚠️ LOAN AGING & RISK ANALYSIS")
                    st.info("💡 Categorizes your live loans by their exact age in months to highlight where your financial risk is accumulating.")
                    bins = [-1, 6, 12, 18, 24, 36, 1000]
                    labels = ['0-6 Months', '6-12 Months', '1-1.5 Years', '1.5-2 Years', '2-3 Years', '3+ Years']
                    f_ao['Age_Bucket'] = pd.cut(f_ao['total_month'], bins=bins, labels=labels)
                    age_df = f_ao.groupby('Age_Bucket', observed=True).agg(Count=('id', 'count'), Principal=('principal_amount', 'sum'), Interest=('calculated_interest', 'sum')).reset_index()
                    age_df = age_df[age_df['Count'] > 0]
                    age_df['Principal (₹)'] = age_df['Principal'].apply(lambda x: f"₹ {x:,.0f}")
                    age_df['Interest (₹)'] = age_df['Interest'].apply(lambda x: f"₹ {x:,.0f}")
                    age_df = age_df.rename(columns={'Age_Bucket': 'Loan Age Group', 'Count': 'Number of Loans'})
                    st.dataframe(age_df[['Loan Age Group', 'Number of Loans', 'Principal (₹)', 'Interest (₹)']], hide_index=True, use_container_width=True)

                # ========================================================
                # --- NEW DEEP ANALYSIS: FUTURE RISK FORECAST ---
                # ========================================================
                elif ao_view == "🔮 Future Risk Forecast":
                    st.markdown("### 🔮 Deep Risk & Collection Forecast")
                    st.info("💡 **How it works:** This mathematical engine projects your live loans into the future. It identifies which healthy loans will become 'Overdue', calculates exactly how much uncollected interest will balloon, and warns you about impending Penalty Triggers.")
                    
                    forecast_months = st.slider("Select Forecast Horizon (Months into the future):", min_value=1, max_value=12, value=3, key="ao_risk_horizon")
                    
                    # Core simulation setup
                    sim_df = f_ao.copy()
                    sim_df['Months_to_Overdue'] = 12 - sim_df['total_month']
                    sim_df['Months_to_Penalty'] = 18 - sim_df['total_month']
                    
                    # 1. THE DANGER ZONE (Active -> Overdue Transition)
                    st.markdown(f"#### 🚨 The 'Danger Zone' Pipeline (Next {forecast_months} Months)")
                    at_risk_df = sim_df[(sim_df['state'] == 'Active') & (sim_df['Months_to_Overdue'] <= forecast_months) & (sim_df['Months_to_Overdue'] > 0)]
                    
                    if not at_risk_df.empty:
                        r1, r2, r3 = st.columns(3)
                        r1.metric("Loans Becoming Overdue", f"{len(at_risk_df)} loans", delta="High Risk", delta_color="inverse")
                        r2.metric("Principal Entering Overdue", f"₹ {at_risk_df['principal_amount'].sum():,.0f}")
                        r3.metric("Current Uncollected Interest", f"₹ {at_risk_df['calculated_interest'].sum():,.0f}")
                        
                        risk_group = at_risk_df.groupby('loan_type').agg(Count=('id', 'count'), Principal=('principal_amount', 'sum')).reset_index()
                        risk_group['Principal'] = risk_group['Principal'].apply(lambda x: f"₹ {x:,.0f}")
                        st.dataframe(risk_group.rename(columns={'loan_type': 'Loan Type'}), hide_index=True, use_container_width=True)
                    else:
                        st.success(f"✅ Great news! No Active loans will cross the 1-year Overdue mark in the next {forecast_months} months.")
                    st.write("---")
                    
                    # 2. PENALTY TRIGGER WATCHLIST
                    st.markdown(f"#### ⚠️ The 'Penalty Trigger' Watchlist")
                    st.write("These specific loans will cross the **18-Month Threshold** during this forecast period, meaning their interest rate will permanently jump to your Penalty Rate.")
                    penalty_df = sim_df[(sim_df['Months_to_Penalty'] <= forecast_months) & (sim_df['Months_to_Penalty'] > 0)].copy()
                    
                    if not penalty_df.empty:
                        penalty_disp = penalty_df[['form_no', 'loan_type', 'principal_amount', 'total_month', 'Months_to_Penalty']].copy()
                        penalty_disp['total_month'] = penalty_disp['total_month'].round(1)
                        penalty_disp['Months_to_Penalty'] = penalty_disp['Months_to_Penalty'].round(1)
                        penalty_disp = penalty_disp.sort_values('Months_to_Penalty')
                        penalty_disp = penalty_disp.rename(columns={'form_no':'Form No', 'loan_type':'Type', 'principal_amount':'Principal (₹)', 'total_month':'Current Age (Months)', 'Months_to_Penalty': 'Months Until Penalty Jump'})
                        st.dataframe(penalty_disp, hide_index=True, use_container_width=True)
                    else:
                        st.success("✅ No loans will cross the 18-Month Penalty Threshold in this timeframe.")
                    st.write("---")

                    # 3. UNCOLLECTED INTEREST BALLOONING (Simulation Engine)
                    st.markdown("#### 🎈 Uncollected Interest Balloon Projection")
                    st.write("If no payments are made, this is exactly how your outstanding interest debt will grow as months pass and penalty rates trigger.")
                    
                    # Mathematical Interest Projection Engine
                    proj_records = []
                    g_n, g_p, s_n, s_p, thresh = 0.0175, 0.02, 0.03, 0.035, 18 # Global standard rates
                    
                    for m in range(0, forecast_months + 1):
                        temp_df = sim_df.copy()
                        temp_df['sim_tot_mth'] = temp_df['total_month'] + m
                        # Use precise final month calculation subtracting Advance and Dues
                        temp_df['sim_final_mth'] = (temp_df['sim_tot_mth'] - temp_df['return_1']) - temp_df['due_month']
                        temp_df['sim_final_mth'] = temp_df['sim_final_mth'].clip(lower=0)
                        
                        # Apply accurate dynamic interest rates
                        def get_rate(row):
                            if row['loan_type'] == 'Gold': return g_p if row['sim_tot_mth'] > thresh else g_n
                            else: return s_p if row['sim_tot_mth'] > thresh else s_n
                                
                        temp_df['sim_rate'] = temp_df.apply(get_rate, axis=1)
                        temp_df['sim_interest'] = np.ceil((temp_df['principal_amount'] * temp_df['sim_rate'] * temp_df['sim_final_mth']) / 10) * 10
                        
                        # Save the specific final target calculation for Priority List
                        if m == forecast_months: sim_df['Target_Future_Interest'] = temp_df['sim_interest']
                            
                        proj_records.append({
                            'Month_Num': m,
                            'Timeline': f"+{m} Months" if m > 0 else "Today (Current)",
                            'Total_Interest': temp_df['sim_interest'].sum(),
                            'Gold_Interest': temp_df[temp_df['loan_type']=='Gold']['sim_interest'].sum(),
                            'Silver_Interest': temp_df[temp_df['loan_type']=='Silver']['sim_interest'].sum()
                        })
                        
                    proj_df = pd.DataFrame(proj_records)
                    
                    # Visualize Ballooning
                    fig_balloon = px.area(proj_df, x='Timeline', y=['Gold_Interest', 'Silver_Interest'], 
                                          title=f"Interest Debt Ballooning (Next {forecast_months} Months)",
                                          color_discrete_map={'Gold_Interest': '#FFD700', 'Silver_Interest': '#C0C0C0'})
                    fig_balloon.update_layout(hovermode="x unified", xaxis_title="Timeline", yaxis_title="Ballooning Interest (₹)")
                    st.plotly_chart(fig_balloon, use_container_width=True)
                    
                    st.write("---")
                    
                    # 4. PRIORITY COLLECTION TARGETS
                    st.markdown("#### 🎯 Top 15 Priority Collection Targets")
                    st.info(f"💡 These specific loans will accumulate the **highest additional debt** over the next {forecast_months} months. Tell your collection team to prioritize calling these form numbers first!")
                    
                    sim_df['Debt_Growth'] = sim_df['Target_Future_Interest'] - sim_df['calculated_interest']
                    priority_df = sim_df.sort_values('Debt_Growth', ascending=False).head(15).copy()
                    
                    priority_disp = priority_df[['form_no', 'loan_type', 'state', 'principal_amount', 'total_month', 'calculated_interest', 'Target_Future_Interest', 'Debt_Growth']].copy()
                    priority_disp['total_month'] = priority_disp['total_month'].round(1)
                    
                    priority_disp = priority_disp.rename(columns={
                        'form_no':'Form No', 'loan_type':'Type', 'state':'Status', 'principal_amount':'Principal (₹)', 
                        'total_month':'Current Age', 'calculated_interest': 'Current Interest (₹)', 
                        'Target_Future_Interest': f'Future Int in {forecast_months}M (₹)', 'Debt_Growth': '🔥 Projected Debt Increase (₹)'
                    })
                    st.dataframe(priority_disp, hide_index=True, use_container_width=True)

            else:
                st.info("No active or overdue records found within the selected date range.")

        if sub_page == "📑 All Summary (Everything)": st.write("---")

    # ==========================================
    # SECTION 3: FUTURE ANALYSIS (FORECAST)
    # ==========================================
    if sub_page == "🔮 Future Analysis":
        st.subheader("Loan Growth & Volume Forecast")
        st.markdown("Use the slider below to set how many months into the future you want to predict. This uses mathematical trendlines based on your historical data.")
        
        forecast_months = st.slider("Forecast Period (Months):", min_value=1, max_value=12, value=6)
        forecast_days = forecast_months * 30 
        
        if len(filtered_data['date'].unique()) < 3: 
            st.warning("⚠️ Please select a date range with at least **3 distinct days** of data to generate a mathematically accurate trend projection.")
        else:
            trend_data = filtered_data.groupby('date')[['total_loan_amount', 'total_count']].sum().reset_index()
            x_historical = (trend_data['date'] - trend_data['date'].min()).dt.days.values
            
            y_amount = trend_data['total_loan_amount'].values
            z_amount = np.polyfit(x_historical, y_amount, 1)
            p_amount = np.poly1d(z_amount)
            
            y_count = trend_data['total_count'].values
            z_count = np.polyfit(x_historical, y_count, 1)
            p_count = np.poly1d(z_count)
            
            last_date = trend_data['date'].max()
            future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_days)
            x_future = np.arange(x_historical[-1] + 1, x_historical[-1] + 1 + forecast_days)
            
            y_future_amount = np.maximum(p_amount(x_future), 0)
            y_future_count = np.maximum(p_count(x_future), 0)
            
            st.markdown(f"### 📈 Projected Summary for the next {forecast_months} Months")
            
            total_projected_amount = y_future_amount.sum()
            avg_daily_projected_amount = y_future_amount.mean()
            total_projected_count = y_future_count.sum()
            avg_daily_projected_count = y_future_count.mean()
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Est. Total Dispersal", f"₹ {total_projected_amount:,.0f}")
            c2.metric("Est. Daily Avg Amount", f"₹ {avg_daily_projected_amount:,.0f}")
            c3.metric("Est. Total Loan Count", f"{total_projected_count:,.0f} loans")
            c4.metric("Est. Daily Avg Count", f"{avg_daily_projected_count:,.1f} / day")
            st.write("---")
            
            hist_plot_amt = pd.DataFrame({'Date': trend_data['date'], 'Value': y_amount, 'Type': 'Historical Data'})
            future_plot_amt = pd.DataFrame({'Date': future_dates, 'Value': y_future_amount, 'Type': f'Projected ({forecast_months} Months)'})
            combined_forecast_amt = pd.concat([hist_plot_amt, future_plot_amt])
            
            fig_forecast_amt = px.line(combined_forecast_amt, x='Date', y='Value', color='Type', 
                                   title="Total Amount Projection vs Historical Data",
                                   color_discrete_map={'Historical Data': '#1f77b4', f'Projected ({forecast_months} Months)': '#FF8C00'})
            fig_forecast_amt.update_traces(line=dict(dash="dot"), selector=dict(name=f'Projected ({forecast_months} Months)'))
            fig_forecast_amt.update_traces(line=dict(width=3))
            fig_forecast_amt.update_layout(hovermode="x unified", yaxis_title="Loan Amount (₹)")
            st.plotly_chart(fig_forecast_amt, use_container_width=True)

            hist_plot_count = pd.DataFrame({'Date': trend_data['date'], 'Value': y_count, 'Type': 'Historical Data'})
            future_plot_count = pd.DataFrame({'Date': future_dates, 'Value': y_future_count, 'Type': f'Projected ({forecast_months} Months)'})
            combined_forecast_count = pd.concat([hist_plot_count, future_plot_count])

            fig_forecast_count = px.line(combined_forecast_count, x='Date', y='Value', color='Type', 
                                   title="Total Loan Count Projection vs Historical Data",
                                   color_discrete_map={'Historical Data': '#2ca02c', f'Projected ({forecast_months} Months)': '#d62728'})
            fig_forecast_count.update_traces(line=dict(dash="dot"), selector=dict(name=f'Projected ({forecast_months} Months)'))
            fig_forecast_count.update_traces(line=dict(width=3))
            fig_forecast_count.update_layout(hovermode="x unified", yaxis_title="Number of Loans")
            st.plotly_chart(fig_forecast_count, use_container_width=True)

    # ==========================================
    # SECTION 4: OUTER LOAN ANALYSIS (CONSOLIDATED)
    # ==========================================
    if sub_page in ["🏢 Outer Loan Analysis", "📑 All Summary (Everything)"]:
        if sub_page == "📑 All Summary (Everything)": st.header("🏢 Outer Loan Analysis")
        else: st.subheader("Outer Loan Analysis & Profit Tracking")

        def format_currency(val):
            if pd.isna(val): return "₹ 0.00"
            if val < 0: return f"- ₹ {abs(val):,.2f}"
            return f"₹ {val:,.2f}"
            
        def metric_sub(g_amt, s_amt, g_cnt, s_cnt):
            return f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_amt:,.0f} (Count: {g_cnt})<br>🥈 Silver: ₹{s_amt:,.0f} (Count: {s_cnt})</div>"

        # --- 1. COLLECT ALL DATES TO SET MASTER FILTER MIN/MAX ---
        valid_dates = []
        if outer_data is not None and not outer_data.empty: valid_dates.extend(outer_data['date'].tolist())
        if outer_closed_data is not None and not outer_closed_data.empty: valid_dates.extend(outer_closed_data['date'].tolist())
        
        if not valid_dates:
            st.info("⚠️ No outer loan data available in the system yet.")
        else:
            # --- 2. MASTER DATE FILTER ---
            st.markdown("#### 📅 Master Date Filter (Applies to all Outer Analysis)")
            st.info("💡 **What this does:** Select a date range here, and ALL the outer loan graphs, profits, and tables below will instantly update to match this exact period.")
            
            # --- 2. MASTER DATE FILTER ---
            import datetime
            db_master_min = pd.Series(valid_dates).min().date()
            db_master_max = pd.Series(valid_dates).max().date()
            
            today = datetime.date.today()
            current_year_start = datetime.date(today.year, 1, 1)
            
            out_allowed_min = min(db_master_min, current_year_start)
            out_allowed_max = max(db_master_max, today)
            out_default_start = max(db_master_min, current_year_start)
            out_default_end = min(db_master_max, today)
            
            m_col1, _ = st.columns([1, 3])
            with m_col1: 
                o_range = st.date_input(
                    "Select Master Date Range:", 
                    value=(out_default_start, out_default_end), 
                    min_value=out_allowed_min, 
                    max_value=out_allowed_max, 
                    key=f"master_outer_filter_{sub_page}"
                )
            
            st.write("---")
            
            if len(o_range) == 2:
                # --- 3. FILTER ALL DATAFRAMES SAFELY ---
                
                # Active Outer Data
                if outer_data is not None and not outer_data.empty:
                    f_outer = outer_data[(outer_data['date'] >= pd.to_datetime(o_range[0])) & (outer_data['date'] <= pd.to_datetime(o_range[1]))].copy()
                    f_outer['pres'] = pd.to_numeric(f_outer['present_amount'], errors='coerce').fillna(0)
                    f_outer['tot'] = pd.to_numeric(f_outer['total_given_amount'], errors='coerce').fillna(0)
                    f_outer['core_amount'] = np.where(f_outer['pres'] > 0, f_outer['pres'], f_outer['tot'])
                    f_outer['outer_amount'] = pd.to_numeric(f_outer['amount'], errors='coerce').fillna(0)
                    
                    f_outer['shop_int'] = pd.to_numeric(f_outer['shop_total_interest'], errors='coerce').fillna(0)
                    f_outer['outer_int'] = pd.to_numeric(f_outer['outer_expected_interest'], errors='coerce').fillna(0)
                    f_outer['profit'] = f_outer['shop_int'] - f_outer['outer_int']
                    f_outer['profit_pct'] = np.where(f_outer['shop_int'] > 0, (f_outer['profit'] / f_outer['shop_int']) * 100, 0)
                    
                    f_outer['paper_amount'] = pd.to_numeric(f_outer['paper_amount'], errors='coerce').fillna(0)
                    f_outer['live_doc_charge'] = pd.to_numeric(f_outer['live_doc_charge'], errors='coerce').fillna(0)
                    f_outer['op_margin'] = f_outer['paper_amount'] - f_outer['live_doc_charge']
                else: f_outer = pd.DataFrame()

                # Closed Outer Data
                if outer_closed_data is not None and not outer_closed_data.empty:
                    f_cl = outer_closed_data[(outer_closed_data['date'] >= pd.to_datetime(o_range[0])) & (outer_closed_data['date'] <= pd.to_datetime(o_range[1]))].copy()
                    f_cl['pres'] = pd.to_numeric(f_cl['present_amount'], errors='coerce').fillna(0)
                    f_cl['tot'] = pd.to_numeric(f_cl['total_given_amount'], errors='coerce').fillna(0)
                    f_cl['core_amount'] = np.where(f_cl['pres'] > 0, f_cl['pres'], f_cl['tot'])
                    f_cl['outer_amount'] = pd.to_numeric(f_cl['outer_amount'], errors='coerce').fillna(0)
                    
                    f_cl['shop_loan_int'] = pd.to_numeric(f_cl['shop_total_interest'], errors='coerce').fillna(0)
                    f_cl['outer_loan_int'] = pd.to_numeric(f_cl['outer_interest'], errors='coerce').fillna(0)
                    f_cl['profit_amount'] = f_cl['shop_loan_int'] - f_cl['outer_loan_int']
                    f_cl['profit_pct'] = np.where(f_cl['shop_loan_int'] > 0, (f_cl['profit_amount'] / f_cl['shop_loan_int']) * 100, 0)
                    
                    f_cl['paper_amount'] = pd.to_numeric(f_cl['paper_amount'], errors='coerce').fillna(0)
                    f_cl['doc_charge'] = pd.to_numeric(f_cl['doc_charge'], errors='coerce').fillna(0)
                    f_cl['op_margin'] = f_cl['paper_amount'] - f_cl['doc_charge']
                else: f_cl = pd.DataFrame()

                
                # --- 4. TOGGLE MENU ---
                outer_view = st.radio("Select Analysis Module:", [
                    "👑 Executive Summary (God View)", 
                    "🟢 Principal & Exposure Analysis", 
                    "🔵 Profitability Analysis (Live & Closed)", 
                    "📄 Operational Costs (Shop vs Outer)"
                ], horizontal=True)
                st.write("---")


                # ==========================================
                # VIEW 1: EXECUTIVE SUMMARY
                # ==========================================
                if outer_view == "👑 Executive Summary (God View)":
                    st.markdown("### 👑 Outer Loan Executive Summary")
                    st.info("💡 **What this is:** A complete, top-down view of your entire Outer Loan strategy. It combines Capital Leverage, Realized Profits, Uncollected Pipeline, and Operational Health in one place.")
                    
                    # Pre-calculate overall metrics
                    o_g = f_outer[f_outer['loan_type']=='Gold'] if not f_outer.empty else pd.DataFrame()
                    o_s = f_outer[f_outer['loan_type']=='Silver'] if not f_outer.empty else pd.DataFrame()
                    c_g = f_cl[f_cl['loan_type']=='Gold'] if not f_cl.empty else pd.DataFrame()
                    c_s = f_cl[f_cl['loan_type']=='Silver'] if not f_cl.empty else pd.DataFrame()

                    col_p, col_pr, col_f, col_o = st.columns(4)
                    
                    with col_p:
                        st.markdown("#### 🔴 Realized Profit")
                        t_cl_p = f_cl['profit_amount'].sum() if not f_cl.empty else 0
                        g_cl_p = c_g['profit_amount'].sum() if not c_g.empty else 0
                        s_cl_p = c_s['profit_amount'].sum() if not c_s.empty else 0
                        st.metric("Total Banked Profit", format_currency(t_cl_p))
                        st.markdown(metric_sub(g_cl_p, s_cl_p, len(c_g), len(c_s)), unsafe_allow_html=True)
                        
                    with col_pr:
                        st.markdown("#### 🔵 Live Est. Profit")
                        t_li_p = f_outer['profit'].sum() if not f_outer.empty else 0
                        g_li_p = o_g['profit'].sum() if not o_g.empty else 0
                        s_li_p = o_s['profit'].sum() if not o_s.empty else 0
                        st.metric("Uncollected Live Profit", format_currency(t_li_p))
                        st.markdown(metric_sub(g_li_p, s_li_p, len(o_g), len(o_s)), unsafe_allow_html=True)
                        
                    with col_f:
                        st.markdown("#### ⚖️ Leveraged Capital")
                        t_act_o = f_outer['outer_amount'].sum() if not f_outer.empty else 0
                        g_act_o = o_g['outer_amount'].sum() if not o_g.empty else 0
                        s_act_o = o_s['outer_amount'].sum() if not o_s.empty else 0
                        st.metric("Live Outer Debt", format_currency(t_act_o))
                        st.markdown(metric_sub(g_act_o, s_act_o, len(o_g), len(o_s)), unsafe_allow_html=True)
                        
                    with col_o:
                        st.markdown("#### 📄 Op Margin (Closed)")
                        t_cl_op = f_cl['op_margin'].sum() if not f_cl.empty else 0
                        g_cl_op = c_g['op_margin'].sum() if not c_g.empty else 0
                        s_cl_op = c_s['op_margin'].sum() if not c_s.empty else 0
                        st.metric("Paper vs Doc Net Margin", format_currency(t_cl_op))
                        st.markdown(metric_sub(g_cl_op, s_cl_op, len(c_g), len(c_s)), unsafe_allow_html=True)
                        
                    st.write("---")
                    
                    st.markdown("#### 📊 Master Analytics Dashboard")
                    r1c1, r1c2 = st.columns(2)
                    r2c1, r2c2 = st.columns(2)
                    
                    with r1c1:
                        st.info("💡 **Capital Leverage Ratio:** How much is your money vs Outer Shop's money?")
                        t_core = f_outer['core_amount'].sum() if not f_outer.empty else 0
                        df_pie1 = pd.DataFrame({"Source": ["Shop Core Value", "Outer Leverage"], "Amount": [t_core, t_act_o]})
                        fig_pie1 = px.pie(df_pie1, names="Source", values="Amount", hole=0.5, color="Source", color_discrete_map={"Shop Core Value": "#1f77b4", "Outer Leverage": "#ff7f0e"})
                        fig_pie1.update_layout(margin=dict(t=30, b=0, l=0, r=0)); st.plotly_chart(fig_pie1, use_container_width=True)
                        
                    with r1c2:
                        st.info("💡 **Profit Status:** Cash already banked vs Cash waiting to be collected.")
                        df_bar1 = pd.DataFrame({"Status": ["Closed (Realized)", "Active (Uncollected)"], "Profit": [t_cl_p, t_li_p]})
                        fig_bar1 = px.bar(df_bar1, x="Status", y="Profit", color="Status", color_discrete_map={"Closed (Realized)": "#2ca02c", "Active (Uncollected)": "#FF8C00"}, text_auto='.2s')
                        fig_bar1.add_hline(y=0, line_color="black"); fig_bar1.update_layout(margin=dict(t=30, b=0, l=0, r=0)); st.plotly_chart(fig_bar1, use_container_width=True)
                        
                    with r2c1:
                        st.info("💡 **Active Outer Capital Distribution:** Where is the leveraged capital sitting?")
                        if not f_outer.empty:
                            df_shop = f_outer.groupby(['shop', 'loan_type'])['outer_amount'].sum().reset_index()
                            fig_shop = px.bar(df_shop, x='shop', y='outer_amount', color='loan_type', barmode='stack', color_discrete_map={'Gold':'#FFD700', 'Silver':'#C0C0C0'})
                            fig_shop.update_layout(margin=dict(t=30, b=0, l=0, r=0)); st.plotly_chart(fig_shop, use_container_width=True)
                        else: st.write("No active capital data.")
                        
                    with r2c2:
                        st.info("💡 **Historical Operational Health:** Are Document Charges eating your Paper Charge income?")
                        if not f_cl.empty:
                            df_op = f_cl.groupby('date')[['paper_amount', 'doc_charge']].sum().reset_index()
                            fig_op = px.area(df_op, x='date', y=['paper_amount', 'doc_charge'], color_discrete_map={'paper_amount':'#2ca02c', 'doc_charge':'#d62728'})
                            fig_op.update_layout(margin=dict(t=30, b=0, l=0, r=0), legend_title="Income vs Expense"); st.plotly_chart(fig_op, use_container_width=True)
                        else: st.write("No closed operational data.")


                # ==========================================
                # VIEW 2: PRINCIPAL & EXPOSURE
                # ==========================================
                elif outer_view == "🟢 Principal & Exposure Analysis":
                    st.markdown("### 🟢 Active Outer Principal & Exposure")
                    st.info("💡 **What this is:** Deep analysis of the raw capital currently sitting in Outer Shops.")
                    
                    if not f_outer.empty:
                        o_g = f_outer[f_outer['loan_type']=='Gold']
                        o_s = f_outer[f_outer['loan_type']=='Silver']
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Total Leveraged Principal", format_currency(f_outer['outer_amount'].sum()))
                        m1.markdown(metric_sub(o_g['outer_amount'].sum(), o_s['outer_amount'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                        
                        m2.metric("Total Shop Core Principal", format_currency(f_outer['core_amount'].sum()))
                        m2.markdown(metric_sub(o_g['core_amount'].sum(), o_s['core_amount'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                        
                        m3.metric("Overall Leverage Ratio", f"{(f_outer['outer_amount'].sum() / f_outer['core_amount'].sum() * 100) if f_outer['core_amount'].sum() > 0 else 0:.1f}%")
                        st.write("---")

                        ptab_g, ptab_s, ptab_d, ptab_f = st.tabs(["📊 Exposure Trends", "🏬 Shop Comparison", "📋 Principal Data Table", "🔮 Future Exposure"])
                        
                        with ptab_g:
                            st.markdown("#### Shop Value vs Outer Leverage Trend")
                            st.info("💡 **What this shows:** Tracks the timeline of your capital exposure.")
                            d_prin = f_outer.groupby('date')[['core_amount', 'outer_amount']].sum().reset_index()
                            fig_exp = px.line(d_prin, x='date', y=['core_amount', 'outer_amount'], markers=True, color_discrete_map={'core_amount':'#1f77b4', 'outer_amount':'#ff7f0e'})
                            fig_exp.update_layout(hovermode="x unified", yaxis_title="Principal (₹)", legend_title="Capital Type"); st.plotly_chart(fig_exp, use_container_width=True)
                            
                        with ptab_s:
                            st.markdown("#### Capital Concentration by Outer Shop")
                            fig_shop = px.bar(f_outer.groupby(['shop', 'loan_type'])['outer_amount'].sum().reset_index(), x='shop', y='outer_amount', color='loan_type', barmode='group', color_discrete_map={'Gold':'#FFD700', 'Silver':'#C0C0C0'})
                            fig_shop.update_layout(xaxis_title="Outer Shop Name", yaxis_title="Total Capital Held (₹)"); st.plotly_chart(fig_shop, use_container_width=True)

                        with ptab_d:
                            st.markdown("##### 💰 GRAND TOTALS & AVERAGES")
                            avg_df = pd.DataFrame({
                                "Metric": ["Grand Total", "Daily Average"],
                                "Shop Core Principal": [format_currency(f_outer['core_amount'].sum()), format_currency(f_outer['core_amount'].mean())],
                                "Outer Leveraged Principal": [format_currency(f_outer['outer_amount'].sum()), format_currency(f_outer['outer_amount'].mean())],
                            })
                            st.dataframe(avg_df, hide_index=True, use_container_width=True)
                            st.markdown("<br>", unsafe_allow_html=True)
                            
                            st.markdown("##### 📊 MONTHLY EXPOSURE TRENDS")
                            m_pr = f_outer.copy(); m_pr['Month-Year'] = m_pr['date'].dt.to_period('M')
                            m_tr_pr = m_pr.groupby('Month-Year').agg(Core=('core_amount','sum'), Outer=('outer_amount','sum')).reset_index()
                            m_tr_pr['Leverage Ratio %'] = np.where(m_tr_pr['Core']>0, (m_tr_pr['Outer']/m_tr_pr['Core']*100), 0).round(2).astype(str) + '%'
                            for c in ['Core', 'Outer']: m_tr_pr[c] = m_tr_pr[c].apply(format_currency)
                            m_tr_pr['Month-Year'] = m_tr_pr['Month-Year'].dt.strftime('%b %Y')
                            st.dataframe(m_tr_pr.rename(columns={'Core': 'Total Shop Amt', 'Outer': 'Total Outer Amt'}), hide_index=True, use_container_width=True)
                            st.markdown("<br>", unsafe_allow_html=True)

                            st.markdown("##### 📋 ACTIVE OUTER PRINCIPAL LEDGER")
                            d_disp = f_outer[['date', 'shop', 'loan_type', 'form_no', 'core_amount', 'outer_amount']].copy()
                            d_disp['date'] = d_disp['date'].dt.strftime('%d-%m-%Y')
                            d_disp['Risk Ratio %'] = (d_disp['outer_amount'] / d_disp['core_amount'] * 100).fillna(0).round(2).astype(str) + '%'
                            for c in ['core_amount', 'outer_amount']: d_disp[c] = d_disp[c].apply(format_currency)
                            st.dataframe(d_disp.rename(columns={'date':'Outer Date', 'shop':'Shop', 'loan_type':'Type', 'form_no':'Loan No', 'core_amount':'Shop Amt', 'outer_amount':'Outer Amt'}), hide_index=True, use_container_width=True)

                        with ptab_f:
                            st.subheader("🔮 Future Exposure Modeling")
                            st.info("💡 **What this does:** Mathematically predicts your future capital dependency. If the red 'Leverage' line crosses above the blue 'Shop' line, you are risking more external money than the loan is worth.")
                            if len(f_outer['date'].unique()) < 5: st.warning("⚠️ Need 5 days of data.")
                            else:
                                f_m = st.slider("Horizon (Months):", 1, 12, 3, key=f"pr_f_{sub_page}")
                                t_d = f_outer.groupby('date')[['core_amount', 'outer_amount']].sum().reset_index()
                                x_h = (t_d['date'] - t_d['date'].min()).dt.days.values
                                f_days = f_m * 30
                                x_f = np.arange(x_h[-1] + 1, x_h[-1] + 1 + f_days)
                                def proj(y): return np.maximum(np.poly1d(np.polyfit(x_h, y, 1))(x_f), 0)
                                f_c = proj(t_d['core_amount'].values); f_o = proj(t_d['outer_amount'].values)
                                
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Est. Future Shop Capital", format_currency(f_c.sum()))
                                c2.metric("Est. Future Outer Leverage", format_currency(f_o.sum()))
                                c3.metric("Est. Average Leverage Ratio", f"{(f_o.sum() / f_c.sum() * 100) if f_c.sum() > 0 else 0:.1f}%")
                                st.write("---")
                                
                                cd = pd.concat([pd.DataFrame({'D': t_d['date'], 'V': t_d['outer_amount'].values, 'T': 'Historical Leverage'}), pd.DataFrame({'D': pd.date_range(t_d['date'].max()+pd.Timedelta(days=1), periods=f_days), 'V': f_o, 'T': 'Projected Leverage'})])
                                fig_lc = px.line(cd, x='D', y='V', color='T', title="Outer Leverage Trajectory", color_discrete_map={'Historical Leverage':'#ff7f0e', 'Projected Leverage':'#d62728'})
                                fig_lc.update_traces(line=dict(dash="dot"), selector=dict(name='Projected Leverage')); st.plotly_chart(fig_lc, use_container_width=True)
                    else: st.info("No Active Principal data for this date range.")


                # ==========================================
                # VIEW 3: PROFITABILITY (LIVE & CLOSED)
                # ==========================================
                elif outer_view == "🔵 Profitability Analysis (Live & Closed)":
                    st.markdown("### 🔵 Outer Loan Profitability Analysis")
                    st.info("💡 **What this is:** Analyzes the exact financial gap between the Interest you Collect from Customers vs the Interest you Pay to Outer Shops.")
                    
                    otab_cl, otab_act, otab_data, otab_fut = st.tabs(["🔴 Historical (Closed)", "🔵 Live (Active)", "📋 Comprehensive Profit Table", "🔮 Future Profit Predictions"])
                    
                    # --- CLOSED PROFIT ---
                    with otab_cl:
                        st.markdown("#### 🔴 Realized Profit (Closed Loans)")
                        st.info("💡 **What this shows:** Hard, finalized data for loans that have successfully closed. This is cash in the bank.")
                        if not f_cl.empty:
                            c_g = f_cl[f_cl['loan_type']=='Gold']
                            c_s = f_cl[f_cl['loan_type']=='Silver']
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Total Shop Interest Collected", format_currency(f_cl['shop_loan_int'].sum()))
                            c1.markdown(metric_sub(c_g['shop_loan_int'].sum(), c_s['shop_loan_int'].sum(), len(c_g), len(c_s)), unsafe_allow_html=True)
                            
                            c2.metric("Total Outer Interest Paid", format_currency(f_cl['outer_loan_int'].sum()))
                            c2.markdown(metric_sub(c_g['outer_loan_int'].sum(), c_s['outer_loan_int'].sum(), len(c_g), len(c_s)), unsafe_allow_html=True)
                            
                            c3.metric("Total Net Profit Banked", format_currency(f_cl['profit_amount'].sum()))
                            c3.markdown(metric_sub(c_g['profit_amount'].sum(), c_s['profit_amount'].sum(), len(c_g), len(c_s)), unsafe_allow_html=True)
                            
                            d_cl = f_cl.groupby('date')[['shop_loan_int', 'outer_loan_int', 'profit_amount']].sum().reset_index()
                            fig_ic = px.line(d_cl, x='date', y=['shop_loan_int', 'outer_loan_int'], markers=True, color_discrete_map={'shop_loan_int':'#2ca02c', 'outer_loan_int':'#d62728'}, title="Shop Collected vs Outer Paid")
                            fig_ic.update_layout(hovermode="x unified", yaxis_title="Interest (₹)"); st.plotly_chart(fig_ic, use_container_width=True)
                        else: st.info("No closed loans found in this date range.")

                    # --- LIVE PROFIT ---
                    with otab_act:
                        st.markdown("#### 🔵 Uncollected Profit (Active Loans)")
                        st.info("💡 **What this shows:** A live calculation answering the question: 'If we closed every single active outer loan *today*, how much profit would we make?'")
                        if not f_outer.empty:
                            o_g = f_outer[f_outer['loan_type']=='Gold']
                            o_s = f_outer[f_outer['loan_type']=='Silver']
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Live Shop Int to Collect", format_currency(f_outer['shop_int'].sum()))
                            c1.markdown(metric_sub(o_g['shop_int'].sum(), o_s['shop_int'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                            
                            c2.metric("Live Outer Int to Pay", format_currency(f_outer['outer_int'].sum()))
                            c2.markdown(metric_sub(o_g['outer_int'].sum(), o_s['outer_int'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                            
                            c3.metric("Live Uncollected Net Profit", format_currency(f_outer['profit'].sum()))
                            c3.markdown(metric_sub(o_g['profit'].sum(), o_s['profit'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                            
                            d_act_grp = f_outer.groupby('date')[['shop_int', 'outer_int']].sum().reset_index()
                            fig_li = px.bar(d_act_grp.melt(id_vars='date'), x='date', y='value', color='variable', barmode='group', title="Expected Live Interest Accumulation", color_discrete_map={'shop_int':'#2ca02c', 'outer_int':'#d62728'})
                            st.plotly_chart(fig_li, use_container_width=True)
                        else: st.info("No active loans found in this date range.")

                    # --- COMPREHENSIVE DATA TABLE ---
                    with otab_data:
                        st.markdown("##### 💰 GRAND TOTALS (CLOSED PROFIT)")
                        tot_shop_int = f_cl['shop_loan_int'].sum() if not f_cl.empty else 0
                        tot_outer_int = f_cl['outer_loan_int'].sum() if not f_cl.empty else 0
                        tot_profit = f_cl['profit_amount'].sum() if not f_cl.empty else 0
                        
                        tot_summ = pd.DataFrame({"Metric": ["Closed Totals"], "Total Shop Int Collected": [format_currency(tot_shop_int)], "Total Outer Int Paid": [format_currency(tot_outer_int)], "Net Realized Profit": [format_currency(tot_profit)], "Overall Margin %": [f"{(tot_profit/tot_shop_int*100) if tot_shop_int>0 else 0:.2f}%"]})
                        st.dataframe(tot_summ, hide_index=True, use_container_width=True)
                        st.markdown("<br>", unsafe_allow_html=True)

                        if not f_cl.empty:
                            st.markdown("##### 📊 MONTHLY PROFIT TRENDS (CLOSED LOANS)")
                            m_d = f_cl.copy(); m_d['Month-Year'] = m_d['date'].dt.to_period('M')
                            m_tr = m_d.groupby('Month-Year').agg(S=('shop_loan_int','sum'), O=('outer_loan_int','sum'), P=('profit_amount','sum')).reset_index()
                            m_tr['Margin %'] = np.where(m_tr['S']>0, (m_tr['P']/m_tr['S']*100), 0)
                            m_tr['Margin %'] = m_tr['Margin %'].round(2).astype(str) + '%'
                            for c in ['S','O','P']: m_tr[c] = m_tr[c].apply(format_currency)
                            m_tr['Month-Year'] = m_tr['Month-Year'].dt.strftime('%b %Y')
                            st.dataframe(m_tr.rename(columns={'S':'Shop Int', 'O':'Outer Int', 'P':'Net Profit'}), hide_index=True, use_container_width=True)
                            st.markdown("<br>", unsafe_allow_html=True)

                            st.markdown("##### 📅 DAILY CLOSED RECORD (RAW DATA)")
                            d_cl_t = f_cl[['date', 'loan_type', 'form_no', 'shop', 'shop_loan_int', 'outer_loan_int', 'profit_amount', 'profit_pct']].copy()
                            d_cl_t['date'] = d_cl_t['date'].dt.strftime('%d-%m-%Y')
                            d_cl_t['profit_pct'] = d_cl_t['profit_pct'].round(2).astype(str) + '%'
                            for c in ['shop_loan_int', 'outer_loan_int', 'profit_amount']: d_cl_t[c] = d_cl_t[c].apply(format_currency)
                            d_cl_t = d_cl_t.rename(columns={'date':'Date', 'loan_type':'Type', 'form_no':'Loan No', 'shop':'Shop', 'shop_loan_int':'Shop Int', 'outer_loan_int':'Outer Int', 'profit_amount':'Profit', 'profit_pct':'Margin %'})
                            st.dataframe(d_cl_t, hide_index=True, use_container_width=True)

                    # --- FUTURE PROFIT ---
                    with otab_fut:
                        st.subheader("🔮 Mathematical Profit Trajectory")
                        st.info("💡 **What this does:** Uses a stable Cumulative Average Model to perfectly scale predictions. Adjusting the slider mathematically multiplies your daily collection average.")
                        if not f_cl.empty and len(f_cl['date'].unique()) >= 3:
                            f_m = st.slider("Horizon (Months):", 1, 12, 3, key=f"op_f_{sub_page}")
                            f_days = f_m * 30
                            
                            unique_days = len(f_cl['date'].unique())
                            t_s_int = f_cl['shop_loan_int'].sum()
                            t_o_int = f_cl['outer_loan_int'].sum()
                            t_p_int = f_cl['profit_amount'].sum()
                            
                            avg_s = t_s_int / unique_days
                            avg_o = t_o_int / unique_days
                            avg_p = t_p_int / unique_days
                            
                            est_s = avg_s * f_days
                            est_o = avg_o * f_days
                            est_p = avg_p * f_days
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric(f"Est. Shop Int (Next {f_m}M)", format_currency(est_s))
                            c2.metric(f"Est. Outer Int (Next {f_m}M)", format_currency(est_o))
                            c3.metric(f"Est. Net Profit (Next {f_m}M)", format_currency(est_p))
                            st.write("---")
                            
                            # Build Cumulative Chart
                            t_d_cum = f_cl.groupby('date')['profit_amount'].sum().cumsum().reset_index()
                            fut_dates = pd.date_range(start=t_d_cum['date'].max() + pd.Timedelta(days=1), periods=f_days)
                            fut_vals = np.linspace(avg_p, est_p, f_days)
                            
                            cd = pd.concat([
                                pd.DataFrame({'D': t_d_cum['date'], 'V': t_d_cum['profit_amount'], 'T': 'Historical Cumulative'}), 
                                pd.DataFrame({'D': fut_dates, 'V': t_d_cum['profit_amount'].iloc[-1] + fut_vals, 'T': 'Projected Cumulative'})
                            ])
                            f_p_c = px.line(cd, x='D', y='V', color='T', title="Cumulative Profit Prediction Trajectory", color_discrete_map={'Historical Cumulative':'#2ca02c', 'Projected Cumulative':'#FF8C00'})
                            f_p_c.update_traces(line=dict(dash="dot"), selector=dict(name='Projected Cumulative'))
                            f_p_c.add_hline(y=0, line_color="black"); st.plotly_chart(f_p_c, use_container_width=True)
                        else: st.warning("⚠️ Need at least 3 distinct days of 'Closed' loan data to generate an accurate profit trendline.")

                # ==========================================
                # VIEW 4: OPERATIONAL COSTS (PAPER VS DOC)
                # ==========================================
                elif outer_view == "📄 Operational Costs (Shop vs Outer)":
                    st.markdown("### 📄 Operational Costs: Shop Paper vs Outer Doc")
                    st.info("💡 **What this is:** A direct comparison between the 'Paper Charges' you collect from your Customers (Income) versus the 'Document Charges' you pay to the Outer Shops (Expense).")
                    
                    op_tab_cl, op_tab_act, op_tab_data, op_tab_fut = st.tabs(["🔴 Realized Costs (Closed Loans)", "🔵 Live Estimated Costs (Active Loans)", "📋 Operational Data Table", "🔮 Future Analysis"])
                    
                    with op_tab_cl:
                        st.markdown("#### 🔴 Realized Operational Margin (Closed Outer Loans)")
                        st.info("💡 **What this shows:** Exact historical data pulled from the database for loans that have successfully finished their cycle.")
                        
                        if not f_cl.empty:
                            c_g = f_cl[f_cl['loan_type']=='Gold']
                            c_s = f_cl[f_cl['loan_type']=='Silver']
                            
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Shop Paper Charges Collected", format_currency(f_cl['paper_amount'].sum()), "Income from Customer")
                            m1.markdown(metric_sub(c_g['paper_amount'].sum(), c_s['paper_amount'].sum(), len(c_g), len(c_s)), unsafe_allow_html=True)
                            
                            m2.metric("Outer Doc Charges Paid", format_currency(f_cl['doc_charge'].sum()), "Expense Paid to Outer Shop", delta_color="inverse")
                            m2.markdown(metric_sub(c_g['doc_charge'].sum(), c_s['doc_charge'].sum(), len(c_g), len(c_s)), unsafe_allow_html=True)
                            
                            m3.metric("Net Operational Margin", format_currency(f_cl['op_margin'].sum()), "Overall Profit / Loss")
                            m3.markdown(metric_sub(c_g['op_margin'].sum(), c_s['op_margin'].sum(), len(c_g), len(c_s)), unsafe_allow_html=True)
                            
                            st.write("---")
                            d_op = f_cl.groupby('date')[['paper_amount', 'doc_charge']].sum().reset_index()
                            fig_op = px.area(d_op, x='date', y=['paper_amount', 'doc_charge'], color_discrete_map={'paper_amount':'#2ca02c', 'doc_charge':'#d62728'}, title="Daily Realized Income vs Expense")
                            fig_op.update_layout(hovermode="x unified", yaxis_title="Amount (₹)", legend_title="Charge Type"); st.plotly_chart(fig_op, use_container_width=True)
                        else: st.info("No closed operational data found in this range.")

                    with op_tab_act:
                        st.markdown("#### 🔵 Live Estimated Operational Margin (Active Outer Loans)")
                        st.info("💡 **What this shows:** Analyzes your active loans. If you closed them today, this is the estimated Doc Charge you will be forced to pay based on current shop rates.")
                        
                        if not f_outer.empty:
                            o_g = f_outer[f_outer['loan_type']=='Gold']
                            o_s = f_outer[f_outer['loan_type']=='Silver']
                            
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Shop Paper Charges Collected", format_currency(f_outer['paper_amount'].sum()), "Already banked from Customer")
                            m1.markdown(metric_sub(o_g['paper_amount'].sum(), o_s['paper_amount'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                            
                            m2.metric("Est. Outer Doc to Pay", format_currency(f_outer['live_doc_charge'].sum()), "Future Expense", delta_color="inverse")
                            m2.markdown(metric_sub(o_g['live_doc_charge'].sum(), o_s['live_doc_charge'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                            
                            m3.metric("Est. Net Operational Margin", format_currency(f_outer['op_margin'].sum()), "Predicted Profit")
                            m3.markdown(metric_sub(o_g['op_margin'].sum(), o_s['op_margin'].sum(), len(o_g), len(o_s)), unsafe_allow_html=True)
                            
                            st.write("---")
                            d_act_grp = f_outer.groupby('date')[['paper_amount', 'live_doc_charge']].sum().reset_index()
                            fig_li_op = px.bar(d_act_grp.melt(id_vars='date'), x='date', y='value', color='variable', barmode='group', title="Expected Live Operational Costs", color_discrete_map={'paper_amount':'#2ca02c', 'live_doc_charge':'#d62728'})
                            st.plotly_chart(fig_li_op, use_container_width=True)
                        else: st.info("No active operational data found in this range.")

                    with op_tab_data:
                        st.markdown("##### 💰 GRAND TOTALS (OPERATIONAL COSTS)")
                        t_pap = f_cl['paper_amount'].sum() if not f_cl.empty else 0
                        t_doc = f_cl['doc_charge'].sum() if not f_cl.empty else 0
                        t_net = f_cl['op_margin'].sum() if not f_cl.empty else 0
                        
                        op_summ = pd.DataFrame({"Metric": ["Closed Totals"], "Total Paper Income": [format_currency(t_pap)], "Total Doc Expense": [format_currency(t_doc)], "Net Operational Profit": [format_currency(t_net)]})
                        st.dataframe(op_summ, hide_index=True, use_container_width=True)
                        st.markdown("<br>", unsafe_allow_html=True)

                        if not f_cl.empty:
                            st.markdown("##### 📊 MONTHLY OPERATIONAL TRENDS (CLOSED)")
                            m_d = f_cl.copy(); m_d['Month-Year'] = m_d['date'].dt.to_period('M')
                            m_tr = m_d.groupby('Month-Year').agg(Paper=('paper_amount','sum'), Doc=('doc_charge','sum'), Net=('op_margin','sum')).reset_index()
                            for c in ['Paper','Doc','Net']: m_tr[c] = m_tr[c].apply(format_currency)
                            m_tr['Month-Year'] = m_tr['Month-Year'].dt.strftime('%b %Y')
                            st.dataframe(m_tr.rename(columns={'Paper':'Paper Income', 'Doc':'Doc Expense', 'Net':'Net Op Margin'}), hide_index=True, use_container_width=True)
                            st.markdown("<br>", unsafe_allow_html=True)

                            st.markdown("##### 📋 CLOSED OPERATIONAL LEDGER (RAW DATA)")
                            d_cl_op = f_cl[['date', 'loan_type', 'form_no', 'shop', 'paper_amount', 'doc_charge', 'op_margin']].copy()
                            d_cl_op['date'] = d_cl_op['date'].dt.strftime('%d-%m-%Y')
                            for c in ['paper_amount', 'doc_charge', 'op_margin']: d_cl_op[c] = d_cl_op[c].apply(format_currency)
                            st.dataframe(d_cl_op.rename(columns={'date':'Close Date', 'loan_type':'Type', 'form_no':'Loan No', 'shop':'Outer Shop', 'paper_amount':'Shop Paper Inc (₹)', 'doc_charge':'Outer Doc Exp (₹)', 'op_margin':'Net Gain'}), hide_index=True, use_container_width=True)

                    with op_tab_fut:
                        st.subheader("🔮 Mathematical Future Projections (Operational Health)")
                        st.info("💡 **What this does:** Analyzes your historical Paper vs Doc ratio and mathematically predicts your future Operational margins.")
                        if not f_cl.empty and len(f_cl['date'].unique()) >= 5:
                            f_m = st.slider("Horizon (Months):", 1, 12, 3, key=f"opc_f_{sub_page}")
                            t_d = f_cl.groupby('date')[['paper_amount', 'doc_charge', 'op_margin']].sum().reset_index()
                            x_h = (t_d['date'] - t_d['date'].min()).dt.days.values
                            f_days = f_m * 30
                            x_f = np.arange(x_h[-1] + 1, x_h[-1] + 1 + f_days)
                            
                            def proj(y, allow_neg=False): 
                                p = np.poly1d(np.polyfit(x_h, y, 1))
                                return p(x_f) if allow_neg else np.maximum(p(x_f), 0)

                            f_pap = proj(t_d['paper_amount'].values)
                            f_doc = proj(t_d['doc_charge'].values)
                            f_net = proj(t_d['op_margin'].values, allow_neg=True)
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric(f"Est. Paper Income (Next {f_m}M)", format_currency(f_pap.sum()))
                            c2.metric(f"Est. Doc Expense (Next {f_m}M)", format_currency(f_doc.sum()))
                            c3.metric(f"Est. Net Op Margin (Next {f_m}M)", format_currency(f_net.sum()))
                            st.write("---")
                            
                            cd = pd.concat([pd.DataFrame({'D': t_d['date'], 'V': t_d['op_margin'].values, 'T': 'Historical Op Margin'}), pd.DataFrame({'D': pd.date_range(t_d['date'].max()+pd.Timedelta(days=1), periods=f_days), 'V': f_net, 'T': 'Projected Op Margin'})])
                            f_p_c = px.line(cd, x='D', y='V', color='T', title="Operational Cost Trajectory Analysis", color_discrete_map={'Historical Op Margin':'#2ca02c', 'Projected Op Margin':'#FF8C00'})
                            f_p_c.update_traces(line=dict(dash="dot"), selector=dict(name='Projected Op Margin')); f_p_c.add_hline(y=0, line_color="black", annotation_text="0 Profit Line")
                            st.plotly_chart(f_p_c, use_container_width=True)
                        else: st.warning("⚠️ Need at least 5 distinct days of 'Closed' operational data.")

        if sub_page == "📑 All Summary (Everything)": st.write("---")

    # ==========================================
    # SECTION: SHOP VS OUTER AMOUNT (10-POINT DEEP ANALYSIS)
    # ==========================================
    if sub_page in ["⚖️ Shop vs Outer (Live)", "📑 All Summary (Everything)"]:
        if sub_page == "📑 All Summary (Everything)": st.header("⚖️ Shop vs Outer (Live)")
        else: st.subheader("⚖️ Shop vs Outer Capital (Active & Overdue)")
        
        st.info("💡 **Overview:** This module provides a 10-point deep dive into your capital leverage, risk exposure, and interest drain for your live portfolio.")

        if ao_data is not None and not ao_data.empty:
            
            # --- 1. INDEPENDENT DATE FILTER ---
            st.markdown("#### 📅 1. Filter Live Exposure by Dispersal Date")
            st.write("Isolate your risk by viewing only loans dispersed within a specific timeframe.")
            
            so_min_date = ao_data['loan_date'].min().date()
            so_max_date = ao_data['loan_date'].max().date()
            
            so_col1, so_col2 = st.columns([1, 3])
            with so_col1:
                so_date_range = st.date_input(
                    "Select Dispersal Date Range:",
                    value=(so_min_date, so_max_date),
                    min_value=so_min_date,
                    max_value=so_max_date,
                    key="so_date_picker_advanced"
                )
            
            if len(so_date_range) == 2:
                so_start, so_end = so_date_range
                f_ao = ao_data[(ao_data['loan_date'] >= pd.to_datetime(so_start)) & (ao_data['loan_date'] <= pd.to_datetime(so_end))].copy()
            else:
                f_ao = ao_data.copy()
                
            st.write("---")

            if not f_ao.empty:
                # --- DATA MAPPING ---
                # Map outer principal amounts ONLY for Active Outer Loans
                if outer_data is not None and not outer_data.empty:
                    # Filter to ensure we only look at Active Outer Status
                    active_outers = outer_data[outer_data['outer_loan_status'].str.lower() == 'active'] if 'outer_loan_status' in outer_data.columns else outer_data
                    
                    outer_map = active_outers.groupby('form_no')['amount'].sum().to_dict()
                    outer_int_map = active_outers.groupby('form_no')['outer_expected_interest'].sum().to_dict()
                    
                    f_ao['outer_amt'] = f_ao['form_no'].map(outer_map).fillna(0)
                    f_ao['outer_expected_int'] = f_ao['form_no'].map(outer_int_map).fillna(0)
                else:
                    f_ao['outer_amt'] = 0
                    f_ao['outer_expected_int'] = 0

                # Calculate Shop Amount (Principal - Outer)
                f_ao['shop_amt'] = f_ao['principal_amount'] - f_ao['outer_amt']
                f_ao['shop_amt'] = f_ao['shop_amt'].clip(lower=0) 

                t_prin = f_ao['principal_amount'].sum()
                t_shop = f_ao['shop_amt'].sum()
                t_out = f_ao['outer_amt'].sum()

                # Create Tabs for the remaining 9 Analyses
                tab_split, tab_risk, tab_margin, tab_trend, tab_ledger = st.tabs([
                    "🥧 Capital Split & Leverage", 
                    "🚨 Risk & Aging Exposure", 
                    "💸 Interest Margin Drain", 
                    "📈 Leverage Timeline", 
                    "📋 Actionable Ledger"
                ])

                with tab_split:
                    st.markdown("### 🥧 Capital Split & Leverage Metrics")
                    
                    # --- 2. Global Capital Split ---
                    st.markdown("#### 2. Global Capital Split")
                    st.write("Provides a macro-level view of how much of your working capital actually belongs to you.")
                    
                    # Calculate Gold vs Silver splits for the metrics
                    g_df = f_ao[f_ao['loan_type'] == 'Gold']
                    s_df = f_ao[f_ao['loan_type'] == 'Silver']

                    # --- EXPLICIT OUTER ACTIVE COUNTS ---
                    total_active_outer_count = len(f_ao[f_ao['outer_amt'] > 0])
                    gold_outer_count = len(g_df[g_df['outer_amt'] > 0])
                    silver_outer_count = len(s_df[s_df['outer_amt'] > 0])

                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.metric("Total Live Principal", f"₹ {t_prin:,.0f}")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_df['principal_amount'].sum():,.0f}<br>🥈 Silver: ₹{s_df['principal_amount'].sum():,.0f}</div>", unsafe_allow_html=True)
                        
                    with c2:
                        st.metric("Total Shop Capital", f"₹ {t_shop:,.0f}")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_df['shop_amt'].sum():,.0f}<br>🥈 Silver: ₹{s_df['shop_amt'].sum():,.0f}</div>", unsafe_allow_html=True)
                        
                    with c3:
                        st.metric("Total Active Outer Capital", f"₹ {t_out:,.0f}")
                        # Displaying the total count of loans present in the outer active status here
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_df['outer_amt'].sum():,.0f} (Count: {gold_outer_count})<br>🥈 Silver: ₹{s_df['outer_amt'].sum():,.0f} (Count: {silver_outer_count})<br><b>🔢 Total Active Outer Loans: {total_active_outer_count}</b></div>", unsafe_allow_html=True)
                        
                    with c4:
                        st.metric("System Leverage Ratio", f"{(t_out/t_prin*100) if t_prin > 0 else 0:.1f}%")
                        st.markdown(f"<div style='font-size: 0.85em; color: gray;'>Ratio of Outer vs Total Principal</div>", unsafe_allow_html=True)
                    
                    pie_df = pd.DataFrame({
                        "Capital Source": ["🏢 Shop Capital", "🤝 Outer Capital"],
                        "Amount": [t_shop, t_out]
                    })
                    fig_pie = px.pie(pie_df, names="Capital Source", values="Amount", hole=0.5, color="Capital Source", color_discrete_map={"🏢 Shop Capital": "#1f77b4", "🤝 Outer Capital": "#ff7f0e"})
                    st.plotly_chart(fig_pie, use_container_width=True)
                    st.write("---")

                    # --- 3. Metal Leverage ---
                    st.markdown("#### 3. Leverage by Metal Type")
                    st.write("Compares if you are heavily leveraging your Gold portfolio versus your Silver portfolio.")
                    gs_df = f_ao.groupby('loan_type')[['shop_amt', 'outer_amt']].sum().reset_index()
                    gs_melt = gs_df.melt(id_vars="loan_type", var_name="Source", value_name="Amount")
                    gs_melt['Source'] = gs_melt['Source'].map({'shop_amt': 'Shop Capital', 'outer_amt': 'Outer Capital'})
                    fig_bar = px.bar(gs_melt, x="loan_type", y="Amount", color="Source", barmode="group", color_discrete_map={"Shop Capital": "#1f77b4", "Outer Capital": "#ff7f0e"})
                    st.plotly_chart(fig_bar, use_container_width=True)
                    st.write("---")
                    
                    # --- 4. Shop Independence Score ---
                    st.markdown("#### 4. Shop Independence Score")
                    st.write("Shows the percentage of individual loans that are entirely funded by the shop without any outside help.")
                    independent_loans = len(f_ao[f_ao['outer_amt'] == 0])
                    leveraged_loans = len(f_ao[f_ao['outer_amt'] > 0])
                    total_loans = len(f_ao)
                    
                    ind_col1, ind_col2 = st.columns([1, 2])
                    with ind_col1:
                        st.metric("100% Independent Loans", f"{independent_loans} Loans")
                        st.metric("Leveraged Loans", f"{leveraged_loans} Loans")
                        st.metric("Independence Score", f"{(independent_loans/total_loans*100) if total_loans > 0 else 0:.1f}%")
                    with ind_col2:
                        ind_df = pd.DataFrame({"Status": ["Independent (Safe)", "Leveraged (Attached Debt)"], "Count": [independent_loans, leveraged_loans]})
                        fig_ind = px.pie(ind_df, names="Status", values="Count", hole=0.4, color="Status", color_discrete_map={"Independent (Safe)": "#2ca02c", "Leveraged (Attached Debt)": "#d62728"})
                        st.plotly_chart(fig_ind, use_container_width=True)

                with tab_risk:
                    st.markdown("### 🚨 Risk & Aging Exposure")
                    
                    # --- 5. Active vs Overdue Risk Exposure ---
                    st.markdown("#### 5. Active vs Overdue Exposure")
                    st.write("Highlights exactly how much of your borrowed outer money is rotting in overdue accounts. Overdue outer debt is highly toxic as you must pay interest on money the customer might never return.")
                    
                    ao_split = f_ao.groupby('state')[['shop_amt', 'outer_amt']].sum().reset_index()
                    ao_melt = ao_split.melt(id_vars="state", var_name="Source", value_name="Amount")
                    ao_melt['Source'] = ao_melt['Source'].map({'shop_amt': 'Shop Capital', 'outer_amt': 'Outer Capital'})
                    
                    fig_ao_risk = px.bar(ao_melt, x="state", y="Amount", color="Source", barmode="group", color_discrete_map={"Shop Capital": "#2ca02c", "Outer Capital": "#d62728"})
                    st.plotly_chart(fig_ao_risk, use_container_width=True)
                    st.write("---")

                    # --- 6. Aging Outer Debt (Risk Buckets) ---
                    st.markdown("#### 6. Aging Outer Debt")
                    st.write("Groups your outer exposure by the age of the loan. Focus on clearing outer loans in the higher month brackets before penalty rates apply.")
                    
                    bins = [-1, 6, 12, 18, 24, 36, 1000]
                    labels = ['0-6 Months', '6-12 Months', '1-1.5 Years', '1.5-2 Years', '2-3 Years', '3+ Years']
                    f_ao['Age_Bucket'] = pd.cut(f_ao['total_month'], bins=bins, labels=labels)
                    
                    age_outer_df = f_ao.groupby('Age_Bucket', observed=True)['outer_amt'].sum().reset_index()
                    fig_age_outer = px.bar(age_outer_df, x='Age_Bucket', y='outer_amt', title="Outer Debt Distributed by Loan Age", color_discrete_sequence=['#ff7f0e'])
                    fig_age_outer.update_layout(xaxis_title="Age of Loan", yaxis_title="Outer Debt Amount (₹)")
                    st.plotly_chart(fig_age_outer, use_container_width=True)
                    st.write("---")

                    # --- 7. Whale Concentration Risk ---
                    st.markdown("#### 7. Whale Concentration Risk")
                    st.write("Identifies if your outer debt is safely spread out, or dangerously concentrated in a few massive VIP loans.")
                    
                    leveraged_only = f_ao[f_ao['outer_amt'] > 0].sort_values('outer_amt', ascending=False)
                    if not leveraged_only.empty:
                        top_10_count = max(1, int(len(leveraged_only) * 0.10))
                        whale_outer_debt = leveraged_only.head(top_10_count)['outer_amt'].sum()
                        whale_pct = (whale_outer_debt / t_out * 100) if t_out > 0 else 0
                        
                        w1, w2, w3 = st.columns(3)
                        w1.metric("Top 10% Outer Debt", f"₹ {whale_outer_debt:,.0f}")
                        w2.metric("Remaining 90% Outer Debt", f"₹ {t_out - whale_outer_debt:,.0f}")
                        w3.metric("Whale Concentration Risk", f"{whale_pct:.1f}%")
                    else:
                        st.info("No outer debt found to calculate concentration.")

                with tab_margin:
                    st.markdown("### 💸 Interest Margin Drain")
                    
                    # --- 8. Interest Margin Drain ---
                    st.markdown("#### 8. Live Interest Arbitrage & Drain")
                    st.write("Calculates the expected interest you will collect from the customer versus the interest you owe to the outer shop, revealing your true live profit margin.")
                    
                    t_expected_cust_int = f_ao['calculated_interest'].sum()
                    t_expected_out_int = f_ao['outer_expected_int'].sum()
                    t_live_net_profit = t_expected_cust_int - t_expected_out_int
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Expected Customer Interest", f"₹ {t_expected_cust_int:,.0f}")
                    m2.metric("Owed Outer Interest", f"₹ {t_expected_out_int:,.0f}", delta="Drain", delta_color="inverse")
                    m3.metric("True Live Net Profit", f"₹ {t_live_net_profit:,.0f}")
                    
                    drain_df = pd.DataFrame({
                        "Interest Type": ["Expected Customer Interest", "Owed Outer Interest"],
                        "Amount": [t_expected_cust_int, t_expected_out_int]
                    })
                    fig_drain = px.bar(drain_df, x="Interest Type", y="Amount", color="Interest Type", color_discrete_map={"Expected Customer Interest": "#2ca02c", "Owed Outer Interest": "#d62728"})
                    st.plotly_chart(fig_drain, use_container_width=True)
                    
                    # --- 9. Average Leverage Ticket Size ---
                    st.markdown("#### 9. Average Leverage Ticket Size")
                    st.write("Breaks down the average financial size of an independent loan versus a leveraged loan.")
                    
                    avg_ind = f_ao[f_ao['outer_amt'] == 0]['principal_amount'].mean()
                    avg_lev = f_ao[f_ao['outer_amt'] > 0]['principal_amount'].mean()
                    
                    a1, a2 = st.columns(2)
                    a1.metric("Avg Size (Independent Loan)", f"₹ {avg_ind:,.0f}" if pd.notna(avg_ind) else "₹ 0")
                    a2.metric("Avg Size (Leveraged Loan)", f"₹ {avg_lev:,.0f}" if pd.notna(avg_lev) else "₹ 0")

                with tab_trend:
                    st.markdown("### 📈 Dispersal Leverage Timeline")
                    
                    # --- 10. Leverage Timeline ---
                    st.markdown("#### 10. Historical Leverage Trajectory")
                    st.write("A timeline showing exactly when you relied on outer capital versus your own shop capital based on the dispersal date.")
                    
                    time_df = f_ao.groupby('loan_date')[['shop_amt', 'outer_amt']].sum().reset_index()
                    fig_time = px.area(time_df, x="loan_date", y=["shop_amt", "outer_amt"], title="Dispersal Volume Over Time", color_discrete_map={"shop_amt": "#1f77b4", "outer_amt": "#ff7f0e"})
                    fig_time.update_layout(hovermode="x unified", xaxis_title="Loan Dispersal Date", yaxis_title="Amount (₹)")
                    st.plotly_chart(fig_time, use_container_width=True)

                with tab_ledger:
                    st.markdown("### 📋 Actionable Priority Ledger")
                    st.write("Raw data table sorted by **Outer Amount (Descending)**. Hand this to your team to prioritize clearing the largest external debts first.")
                    
                    disp_df = f_ao[['form_no', 'loan_date', 'loan_type', 'state', 'total_month', 'principal_amount', 'shop_amt', 'outer_amt', 'calculated_interest', 'outer_expected_int']].copy()
                    disp_df['loan_date'] = disp_df['loan_date'].dt.strftime('%d-%m-%Y')
                    disp_df['total_month'] = disp_df['total_month'].round(1)
                    
                    # Calculate true profit for the ledger
                    disp_df['net_profit'] = disp_df['calculated_interest'] - disp_df['outer_expected_int']
                    
                    # Sort by highest outer exposure first
                    disp_df = disp_df.sort_values(by='outer_amt', ascending=False)
                    
                    disp_df = disp_df.rename(columns={
                        'form_no': 'Form No', 'loan_date': 'Date', 'loan_type': 'Type', 'state': 'Status', 'total_month': 'Age (Mths)',
                        'principal_amount': 'Total Principal (₹)', 'shop_amt': 'Shop Amount (₹)', 'outer_amt': 'Outer Amount (₹)',
                        'calculated_interest': 'Cust. Int (₹)', 'outer_expected_int': 'Outer Int (₹)', 'net_profit': 'Net Margin (₹)'
                    })
                    st.dataframe(disp_df, hide_index=True, use_container_width=True)
            else:
                st.warning("No Active or Overdue loan data found within the selected dispersal date range.")
        else:
            st.warning("No Active or Overdue loan data available for analysis in the database.")

    # ==========================================
    # SECTION 5: FINAL EXECUTIVE REPORT (MASTER DASHBOARD)
    # ==========================================
    if sub_page == "🏆 Final Executive Report":
        st.header("🏆 Master Final Executive Report")
        st.info("💡 **What this is:** This is your ultimate business scorecard. It takes every single transaction (Money Out, Interest In, Outer Profits, Expenses, and Loan Counts) and mathematically combines them into one final, easy-to-read Profit & Loss (P&L) dashboard.")
        
        def format_currency(val):
            if pd.isna(val): return "₹ 0.00"
            if val < 0: return f"- ₹ {abs(val):,.2f}"
            return f"₹ {val:,.2f}"
            
        def breakdown_text(text):
            return f"<div style='font-size: 0.85em; color: gray; margin-top: -10px; margin-bottom: 15px;'>{text}</div>"

        # ------------------------------------------------
        # 1. MASTER DATA AGGREGATION
        # ------------------------------------------------
        # A. Growth, Interest & Counts (From filtered_data based on selected dates)
        t_disp = filtered_data['total_loan_amount'].sum() if not filtered_data.empty else 0
        t_disp_g = filtered_data['gold_amount'].sum() if not filtered_data.empty else 0
        t_disp_s = filtered_data['silver_amount'].sum() if not filtered_data.empty else 0
        
        c_disp = filtered_data['total_count'].sum() if not filtered_data.empty else 0
        c_disp_g = filtered_data['gold_count'].sum() if not filtered_data.empty else 0
        c_disp_s = filtered_data['silver_count'].sum() if not filtered_data.empty else 0
        
        t_interest = filtered_data['total_overall_interest'].sum() if not filtered_data.empty else 0
        t_paper = filtered_data['total_paper'].sum() if not filtered_data.empty else 0

        # B. Portfolio Risk (LIVE SNAPSHOT - Bypasses Date Filter to show TRUE ENTIRE risk)
        f_ao = pd.DataFrame()
        t_act_prin = 0; t_ovr_prin = 0; c_act = 0; c_ovr = 0
        if ao_data is not None and not ao_data.empty:
            f_ao = ao_data.copy() 
            t_act_prin = f_ao[f_ao['state'] == 'Active']['principal_amount'].sum()
            c_act = len(f_ao[f_ao['state'] == 'Active'])
            t_ovr_prin = f_ao[f_ao['state'] == 'Overdue']['principal_amount'].sum()
            c_ovr = len(f_ao[f_ao['state'] == 'Overdue'])

        # C. Outer Strategy (From outer_data based on selected dates)
        f_out_act = pd.DataFrame(); f_out_cl = pd.DataFrame()
        t_out_lev = 0; t_out_core = 0; lev_ratio = 0; global_lev_ratio = 0
        t_out_prof = 0; t_doc = 0; c_out_act = 0; c_out_cl = 0
        
        if outer_data is not None and not outer_data.empty:
            f_out_act = outer_data[(outer_data['date'] >= pd.to_datetime(start_date)) & (outer_data['date'] <= pd.to_datetime(end_date))].copy()
            if not f_out_act.empty:
                f_out_act['pres'] = pd.to_numeric(f_out_act['present_amount'], errors='coerce').fillna(0)
                f_out_act['tot'] = pd.to_numeric(f_out_act['total_given_amount'], errors='coerce').fillna(0)
                f_out_act['core_amount'] = np.where(f_out_act['pres'] > 0, f_out_act['pres'], f_out_act['tot'])
                f_out_act['outer_amount'] = pd.to_numeric(f_out_act['amount'], errors='coerce').fillna(0)
                
                t_out_lev = f_out_act['outer_amount'].sum()
                t_out_core = f_out_act['core_amount'].sum()
                c_out_act = len(f_out_act)
                
                lev_ratio = (t_out_lev / t_out_core * 100) if t_out_core > 0 else 0
                global_lev_ratio = (t_out_lev / t_disp * 100) if t_disp > 0 else 0

        if outer_closed_data is not None and not outer_closed_data.empty:
            f_out_cl = outer_closed_data[(outer_closed_data['date'] >= pd.to_datetime(start_date)) & (outer_closed_data['date'] <= pd.to_datetime(end_date))].copy()
            if not f_out_cl.empty:
                f_out_cl['shop_int'] = pd.to_numeric(f_out_cl['shop_total_interest'], errors='coerce').fillna(0)
                f_out_cl['outer_int'] = pd.to_numeric(f_out_cl['outer_interest'], errors='coerce').fillna(0)
                f_out_cl['profit_amount'] = f_out_cl['shop_int'] - f_out_cl['outer_int']
                f_out_cl['doc_charge'] = pd.to_numeric(f_out_cl['doc_charge'], errors='coerce').fillna(0)
                
                t_out_prof = f_out_cl['profit_amount'].sum()
                t_doc = f_out_cl['doc_charge'].sum()
                c_out_cl = len(f_out_cl)

        # D. Ultimate Net Revenue Calcs (Op Margin Removed for Clarity)
        t_total_revenue = t_interest + t_out_prof + t_paper - t_doc
        
        # --- NEW: CALCULATE SHOP AMOUNT ---
        shop_amount = t_disp - t_out_lev

        # ------------------------------------------------
        # 2. MASTER KPI ROW (FINANCIALS)
        # ------------------------------------------------
        st.markdown("### 👑 1. Global Financial Status")
        k1, k2, k3, k4 = st.columns(4)
        
        with k1:
            st.metric("Total Money Lent Out", format_currency(t_disp))
            # --- NEW ADDITION: Breakdown of Shop Amount and Outer Loan below the main metric ---
            st.markdown(breakdown_text(f"🏢 Shop Amount: ₹{shop_amount:,.0f}<br>🤝 Outer Loan: ₹{t_out_lev:,.0f}<br>🥇 Gold: ₹{t_disp_g:,.0f} | 🥈 Silver: ₹{t_disp_s:,.0f}"), unsafe_allow_html=True)
            
        with k2:
            st.metric("Total Final Net Revenue", format_currency(t_total_revenue))
            st.markdown(breakdown_text(f"+ Cust. Int: ₹{t_interest:,.0f}<br>+ Outer Profit: ₹{t_out_prof:,.0f}<br>+ Paper Fees: ₹{t_paper:,.0f}<br>- Outer Doc Fees: ₹{t_doc:,.0f}"), unsafe_allow_html=True)
            
        with k3:
            st.metric("Global Capital Leverage", f"{global_lev_ratio:.1f}%")
            st.markdown(breakdown_text(f"Outer Debt vs Total Money Lent Out<br>*(₹{t_out_lev:,.0f} / ₹{t_disp:,.0f})*"), unsafe_allow_html=True)
            
        with k4:
            st.metric("Money Stuck at Risk", format_currency(t_ovr_prin))
            st.markdown(breakdown_text(f"Overdue (>1 Yr): {c_ovr} loans<br>Safe Active: {c_act} loans<br>*(Snapshot of ENTIRE portfolio)*"), unsafe_allow_html=True)
            
        st.write("---")

        # ------------------------------------------------
        # 3. MASTER KPI ROW (LOAN VOLUME & COUNTS)
        # ------------------------------------------------
        st.markdown("### 📊 2. Loan Volume & Operational Operations")
        v1, v2, v3, v4 = st.columns(4)
        
        with v1:
            st.metric("Total Loans Dispersed", f"{int(c_disp)} Loans")
            st.markdown(breakdown_text(f"🥇 Gold: {int(c_disp_g)} | 🥈 Silver: {int(c_disp_s)}"), unsafe_allow_html=True)
            
        with v2:
            st.metric("Live Active Shop Loans", f"{c_act} Loans")
            st.markdown(breakdown_text("Healthy loans currently paying interest to the shop."), unsafe_allow_html=True)
            
        with v3:
            st.metric("Active Outer Loans", f"{c_out_act} Loans")
            st.markdown(breakdown_text("Loans currently pledged to an external outer shop."), unsafe_allow_html=True)
            
        with v4:
            st.metric("Successfully Closed Outer", f"{c_out_cl} Loans")
            st.markdown(breakdown_text("Finished outer cycles where profit has been banked."), unsafe_allow_html=True)
            
        st.write("---")


        # ------------------------------------------------
        # 4. REVENUE COMPOSITION & LEVERAGE
        # ------------------------------------------------
        st.markdown("### 📈 3. Revenue Breakdown & Leverage Exposure")
        st.info("💡 **How to read this:** The Pie chart shows EXACTLY where your gross business income comes from. The Bar chart compares the core value of loans sitting outside vs how much money you borrowed against them.")
        
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            rev_df = pd.DataFrame({
                "Income Source": ["Direct Customer Interest", "External Outer Profit", "Paper Fee Income"],
                "Amount": [t_interest, t_out_prof, t_paper] 
            })
            if rev_df['Amount'].sum() > 0:
                fig_rev_pie = px.pie(rev_df, names="Income Source", values="Amount", hole=0.4, title="Where is the Income coming from?", color="Income Source", color_discrete_map={"Direct Customer Interest": "#2ca02c", "External Outer Profit": "#FF8C00", "Paper Fee Income": "#1f77b4"})
                fig_rev_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_rev_pie, use_container_width=True)
            else:
                st.warning("No positive revenue generated in this date range.")

        with r_col2:
            if not f_out_act.empty:
                st.markdown(f"<div style='text-align: center; font-weight: bold; margin-bottom: 10px;'>Active Outer Ratio ({lev_ratio:.1f}%)</div>", unsafe_allow_html=True)
                lev_df = pd.DataFrame({
                    "Capital Type": ["Actual Shop Loan Value", "Borrowed Outer Debt"],
                    "Amount": [t_out_core, t_out_lev]
                })
                fig_lev = px.bar(lev_df, x="Capital Type", y="Amount", color="Capital Type", color_discrete_map={"Actual Shop Loan Value": "#1f77b4", "Borrowed Outer Debt": "#d62728"}, text_auto='.2s')
                fig_lev.update_layout(showlegend=False, xaxis_title="", yaxis_title="Capital Amount (₹)")
                st.plotly_chart(fig_lev, use_container_width=True)
            else:
                st.warning("No active outer loan data available for Leverage Ratio chart.")


        # ------------------------------------------------
        # 5. PORTFOLIO HEALTH (CLEAR RISK EXPLANATION)
        # ------------------------------------------------
        st.write("---")
        st.markdown("### ⚠️ 4. Default Risk Analysis (Safe vs Stuck Money)")
        st.info("💡 **How to read this:** This analyzes all your LIVE loans across the entire system. 'Safe Capital' are loans under 1 year old. 'Stuck Capital (Risk)' are Overdue loans older than 1 year. If the Red slice gets too big, your money is getting trapped.")
        
        h_col1, h_col2 = st.columns(2)
        with h_col1:
            health_df = pd.DataFrame({
                "Status": ["Safe Capital (Active)", "Stuck Capital (Overdue Risk)"],
                "Amount": [t_act_prin, t_ovr_prin]
            })
            if health_df['Amount'].sum() > 0:
                fig_health = px.pie(health_df, names="Status", values="Amount", title="Live Principal Health Distribution", color="Status", color_discrete_map={"Safe Capital (Active)": "#2ca02c", "Stuck Capital (Overdue Risk)": "#d62728"})
                st.plotly_chart(fig_health, use_container_width=True)
            else: st.write("No Active/Overdue data available.")
            
        with h_col2:
            if not f_ao.empty:
                t_act_int = f_ao[f_ao['state'] == 'Active']['calculated_interest'].sum()
                t_ovr_int = f_ao[f_ao['state'] == 'Overdue']['calculated_interest'].sum()
                
                risk_df = pd.DataFrame({
                    "Loan Status": ["Active (Safe)", "Active (Safe)", "Overdue (Stuck)", "Overdue (Stuck)"],
                    "Value Type": ["Principal Given", "Expected Interest", "Principal Given", "Expected Interest"],
                    "Amount": [t_act_prin, t_act_int, t_ovr_prin, t_ovr_int]
                })
                fig_risk = px.bar(risk_df, x='Loan Status', y='Amount', color='Value Type', barmode='group', title="Capital vs Uncollected Interest by Status", color_discrete_map={'Principal Given': '#1f77b4', 'Expected Interest': '#FF8C00'})
                fig_risk.update_layout(hovermode="x unified", xaxis_title="Loan Status", yaxis_title="Amount (₹)")
                st.plotly_chart(fig_risk, use_container_width=True)


        # ------------------------------------------------
        # 6. THE ULTIMATE MONTHLY P&L LEDGER
        # ------------------------------------------------
        st.write("---")
        st.markdown("### 📋 5. Ultimate Monthly Profit & Loss (P&L) Ledger")
        st.success("📖 **How to read this table:** This is your final accounting ledger grouped month by month. \n\n* **[OUT]** means money leaving your shop.\n* **[IN]** means money entering your shop (Customer interest, paper charges, or net outer profit).\n* **Growth %** tells you if your Final Net Revenue is growing or shrinking compared to the previous month.")
        
        if not filtered_data.empty:
            # 1. Base monthly aggregation (Core Income)
            filtered_data['Month-Year'] = filtered_data['date'].dt.to_period('M')
            m_main = filtered_data.groupby('Month-Year').agg(
                Dispersal=('total_loan_amount', 'sum'),
                Interest=('total_overall_interest', 'sum'),
                Paper_Inc=('total_paper', 'sum')
            ).reset_index()
            
            # 2. Add Outer Profit & Doc Expense (from Closed Outer Loans)
            if not f_out_cl.empty:
                f_out_cl['Month-Year'] = f_out_cl['date'].dt.to_period('M')
                m_out = f_out_cl.groupby('Month-Year').agg(
                    Outer_Profit=('profit_amount', 'sum'),
                    Doc_Exp=('doc_charge', 'sum')
                ).reset_index()
                m_master = pd.merge(m_main, m_out, on='Month-Year', how='left').fillna(0)
            else:
                m_master = m_main.copy()
                m_master['Outer_Profit'] = 0
                m_master['Doc_Exp'] = 0
                
            # 3. Calculate Final Net Formulas
            m_master['Total_Revenue'] = m_master['Interest'] + m_master['Outer_Profit'] + m_master['Paper_Inc'] - m_master['Doc_Exp']
            
            # 4. Calculate Month-over-Month Growth Rate %
            m_master['Revenue Growth %'] = m_master['Total_Revenue'].pct_change() * 100
            m_master['Revenue Growth %'] = m_master['Revenue Growth %'].fillna(0).round(2).astype(str) + '%'
            
            # Format cleanly
            m_master['Month-Year'] = m_master['Month-Year'].dt.strftime('%b %Y')
            for col in ['Dispersal', 'Interest', 'Paper_Inc', 'Doc_Exp', 'Outer_Profit', 'Total_Revenue']:
                m_master[col] = m_master[col].apply(format_currency)
                
            m_master = m_master.rename(columns={
                'Month-Year': 'Timeline',
                'Dispersal': 'Dispersal [OUT]',
                'Interest': 'Cust. Interest [IN]',
                'Paper_Inc': 'Paper Charge [IN]',
                'Doc_Exp': 'Outer Doc Fee [OUT]',
                'Outer_Profit': 'Net Outer Profit [IN]',
                'Total_Revenue': 'FINAL NET REVENUE [=]'
            })
            
            # Reorder columns for logical reading
            m_master = m_master[['Timeline', 'Dispersal [OUT]', 'Cust. Interest [IN]', 'Paper Charge [IN]', 'Outer Doc Fee [OUT]', 'Net Outer Profit [IN]', 'FINAL NET REVENUE [=]', 'Revenue Growth %']]
            
            st.dataframe(m_master, hide_index=True, use_container_width=True)
            
            # Master P&L Download Option
            csv = m_master.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Master P&L Report as CSV",
                data=csv,
                file_name=f'master_business_report_{start_date}_to_{end_date}.csv',
                mime='text/csv',
            )
        else:
            st.warning("No data available to generate Master Ledger.")

        if sub_page == "📑 All Summary (Everything)": st.write("---")