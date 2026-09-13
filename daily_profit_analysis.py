import streamlit as st
import pandas as pd
import sqlite3
import datetime
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- CONSTANTS FROM TKINTER LOGIC ---
PREFIXES = [
    "Capital: Gpay Capital : ", "Capital: Gpay Capital :", 
    "Gpay Capital : ", "Gpay Capital :",                   
    "CASH CAPITAL: ", "CASH CAPITAL:",                     
    "Capital Amount : ", "Capital Amount :",               
    "CAPITAL: ", "CAPITAL:",                               
    "Capital: "                                            
]

EXCLUDED_KEYS = [
    "CAPITAL AMOUNT:", "CAPITAL AMOUNT", 
    "GPAY CAPITAL ADDED:", "GPAY CAPITAL ADDED",
    "Capital", "GPay Capital", "Opening Capital",
    "ADJUSTMENT", "REVERSAL"
]

def format_currency(val):
    if pd.isna(val): return "₹ 0.00"
    if val < 0: return f"- ₹ {abs(val):,.2f}"
    return f"₹ {val:,.2f}"

def render_insight(status, title, insight, action):
    if status == "GOOD":
        st.success(f"✅ **{title}**\n\n**Insight:** {insight}\n\n**Action:** {action}")
    elif status == "AVG":
        st.warning(f"⚠️ **{title}**\n\n**Insight:** {insight}\n\n**Action:** {action}")
    else:
        st.error(f"🚨 **{title}**\n\n**Insight:** {insight}\n\n**Action:** {action}")

def fetch_daily_profit_data(start_date, end_date):
    """
    Translates the strict hierarchical matching logic from Tkinter 
    into a structured Pandas DataFrame for Streamlit.
    """
    conn = sqlite3.connect('users.db')
    
    # 1. Load Hierarchy (Mains and Subs)
    hierarchy = {'Cash': {'mains': {}}, 'GPay': {'mains': {}}}
    try:
        for t_key in ['Cash', 'GPay']:
            rows = conn.execute("SELECT description FROM transaction_descriptions WHERE type=? ORDER BY description", (t_key,)).fetchall()
            for r in rows:
                m_cat = r[0].strip()
                if m_cat not in EXCLUDED_KEYS:
                    hierarchy[t_key]['mains'][m_cat] = {'subs': []}
            
            rows = conn.execute("SELECT parent_description, sub_description FROM transaction_sub_descriptions WHERE type=? ORDER BY sub_description", (t_key,)).fetchall()
            for p, s in rows:
                p_cat = p.strip(); s_cat = s.strip()
                if p_cat in hierarchy[t_key]['mains']:
                    hierarchy[t_key]['mains'][p_cat]['subs'].append(s_cat)
    except Exception:
        pass

    records = []
    trend_daily = {}

    # 2. Process Transactions matching the Tkinter prefix-stripping logic
    def process_transactions(t_root, query):
        rows = conn.execute(query).fetchall()
        for r in rows:
            d_str, raw_desc, t_type, amt = r
            try:
                dt = datetime.datetime.strptime(d_str, "%d/%m/%Y").date()
                if not (start_date <= dt <= end_date): continue

                # Clean Description
                c_desc = raw_desc.strip()
                for pfx in PREFIXES:
                    if c_desc.lower().startswith(pfx.lower()):
                        c_desc = c_desc[len(pfx):].strip()
                        break
                
                if not c_desc: continue

                # Split Main vs Sub
                if " - " in c_desc:
                    main_c, sub_c = c_desc.split(" - ", 1)
                else:
                    main_c, sub_c = c_desc, "-"
                    
                main_c = main_c.strip()
                sub_c = sub_c.strip()

                # STRICT MATCHING: Only process if it belongs to our Expense/Income hierarchy
                if main_c in hierarchy[t_root]['mains']:
                    is_credit = t_type in ['Credit', 'Incoming']
                    credit = amt if is_credit else 0.0
                    debit = amt if not is_credit else 0.0

                    records.append({
                        'Date': dt,
                        'Day_of_Week': dt.strftime('%A'),
                        'Account': t_root,
                        'Main Category': main_c,
                        'Sub Category': sub_c,
                        'Credit': credit,
                        'Debit': debit
                    })

                    # Aggregate Daily Trends
                    if dt not in trend_daily:
                        trend_daily[dt] = {'Credit': 0.0, 'Debit': 0.0}
                    trend_daily[dt]['Credit'] += credit
                    trend_daily[dt]['Debit'] += debit

            except Exception:
                continue

    process_transactions('Cash', "SELECT transaction_date, description, transaction_type, amount FROM capital_transactions")
    process_transactions('GPay', "SELECT transaction_date, description, transaction_type, amount FROM GpayAccount")
    
    conn.close()
    
    df_records = pd.DataFrame(records)
    if not df_records.empty:
        df_records = df_records.sort_values(by=['Date', 'Account', 'Main Category'])
        
    df_trend = pd.DataFrame.from_dict(trend_daily, orient='index')
    if not df_trend.empty:
        df_trend.index.name = 'Date'
        df_trend = df_trend.sort_index()
        df_trend['Net Profit'] = df_trend['Credit'] - df_trend['Debit']
        
        # FIX: Explicitly convert the index to a DatetimeIndex first
        df_trend.index = pd.to_datetime(df_trend.index)
        df_trend['Day_of_Week'] = df_trend.index.strftime('%A')
        
        df_trend = df_trend.reset_index()
        # Convert Date back to standard date object for clean graphs
        df_trend['Date'] = df_trend['Date'].dt.date
        
    return df_records, df_trend

def render():
    st.title("💸 Daily Operational Profit & Expenses")
    st.info("💡 **Deep Analysis Mode:** This dashboard provides a highly detailed breakdown of your day-to-day operational income (Credits) and expenses (Debits), filtering out loan dispersals to reveal your true shop running costs.")

    # --- DATE FILTER ---
    today = datetime.date.today()
    default_start = datetime.date(today.year, today.month, 1)
    
    col_d1, _ = st.columns([1, 2])
    with col_d1:
        date_range = st.date_input("📅 Select Analysis Window:", value=(default_start, today), max_value=today)

    if len(date_range) != 2: return 
    sd, ed = date_range

    st.write("---")

    # --- FETCH DATA ---
    df_records, df_trend = fetch_daily_profit_data(sd, ed)

    if df_records.empty:
        st.warning("No operational income or expense data found for the selected date range.")
        return

    # --- CALCULATE KPIs ---
    total_credit = df_records['Credit'].sum()
    total_debit = df_records['Debit'].sum()
    net_profit = total_credit - total_debit
    
    # Advanced KPIs
    days_in_period = (ed - sd).days + 1
    avg_daily_income = total_credit / days_in_period if days_in_period > 0 else 0
    avg_daily_expense = total_debit / days_in_period if days_in_period > 0 else 0
    
    profit_margin = (net_profit / total_credit * 100) if total_credit > 0 else 0

    # --- TOP KPI METRICS ---
    st.markdown("### 👑 Executive Summary")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Operational Income (+)", format_currency(total_credit))
    k2.metric("Total Operational Expense (-)", format_currency(total_debit))
    
    profit_status = "normal" if net_profit >= 0 else "inverse"
    k3.metric("Net Operational Profit", format_currency(net_profit), delta="Net Balance", delta_color=profit_status)
    k4.metric("Operating Profit Margin", f"{profit_margin:.1f}%", delta="Efficiency", delta_color="normal" if profit_margin > 0 else "inverse")

    st.write("---")

    # --- ADVANCED TABS ---
    tab_exec, tab_trends, tab_breakdown, tab_ledger = st.tabs([
        "💡 Actionable Insights", 
        "📈 Trends & Day-of-Week", 
        "💰 Income vs Expense Breakdown", 
        "📋 Full Transaction Ledger"
    ])

    # ==========================================
    # TAB 1: ACTIONABLE INSIGHTS (AI-STYLE)
    # ==========================================
    with tab_exec:
        st.markdown("### 🧠 Automated Shop Health Analysis")
        
        c_ex1, c_ex2 = st.columns(2)
        
        with c_ex1:
            # Insight 1: Profit Margin Health
            if profit_margin >= 40:
                render_insight("GOOD", "High Operating Efficiency", f"Your operating profit margin is {profit_margin:.1f}%. You are keeping a vast majority of the money you make.", "Maintain current expense limits. Your shop is running lean and highly profitable.")
            elif 0 <= profit_margin < 40:
                render_insight("AVG", "Moderate Expense Bleed", f"Your profit margin is {profit_margin:.1f}%. Expenses are taking a significant chunk of your daily income.", "Review your top expenses in the 'Breakdown' tab to see where you can cut costs this week.")
            else:
                render_insight("BAD", "Severe Cash Bleed", f"Your margin is {profit_margin:.1f}%. You are spending more to run the shop than you are making in daily income.", "Immediate Action Required: Freeze non-essential shop expenses instantly until income recovers.")

            # Insight 2: Daily Averages
            st.markdown(f"**📊 Daily Run Rate:** You average **{format_currency(avg_daily_income)}** in income per day, while spending **{format_currency(avg_daily_expense)}** per day.")

        with c_ex2:
            # Insight 3: Top Expense Danger
            df_expenses = df_records[df_records['Debit'] > 0]
            if not df_expenses.empty:
                top_expense = df_expenses.groupby('Main Category')['Debit'].sum().reset_index().sort_values('Debit', ascending=False).iloc[0]
                expense_pct = (top_expense['Debit'] / total_debit * 100) if total_debit > 0 else 0
                
                if expense_pct >= 50:
                    render_insight("BAD", "High Expense Concentration", f"'{top_expense['Main Category']}' accounts for {expense_pct:.1f}% of all your shop expenses ({format_currency(top_expense['Debit'])}).", "Target this specific category for immediate cost-reduction.")
                else:
                    render_insight("GOOD", "Balanced Expenses", f"Your highest expense is '{top_expense['Main Category']}' at {expense_pct:.1f}%. Your costs are safely distributed.", "Continue monitoring daily limits.")

    # ==========================================
    # TAB 2: TRENDS & DAY OF WEEK
    # ==========================================
    with tab_trends:
        st.markdown("### 📈 Cash Flow Timeline")
        
        # 1. Overlay Bar Chart (Income vs Expense Daily)
        fig_overlay = go.Figure()
        fig_overlay.add_trace(go.Bar(x=df_trend['Date'], y=df_trend['Credit'], name='Daily Income (+)', marker_color='#2ca02c'))
        fig_overlay.add_trace(go.Bar(x=df_trend['Date'], y=-df_trend['Debit'], name='Daily Expense (-)', marker_color='#d62728'))
        fig_overlay.add_trace(go.Scatter(x=df_trend['Date'], y=df_trend['Net Profit'], name='Net Profit Trend', mode='lines+markers', line=dict(color='black', width=2)))
        
        fig_overlay.update_layout(title="Daily Cash Flow Analysis (In vs Out)", barmode='relative', hovermode='x unified')
        st.plotly_chart(fig_overlay, use_container_width=True)
        
        st.write("---")
        
        # 2. Day of Week Analysis
        st.markdown("### 📅 Day of the Week Efficiency")
        st.info("Find out which days of the week generate the most miscellaneous income versus the highest operating costs.")
        
        dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        df_trend['Day_of_Week'] = pd.Categorical(df_trend['Day_of_Week'], categories=dow_order, ordered=True)
        dow_summary = df_trend.groupby('Day_of_Week')[['Credit', 'Debit', 'Net Profit']].mean().reset_index()
        
        fig_dow = px.bar(
            dow_summary, 
            x='Day_of_Week', 
            y=['Credit', 'Debit'], 
            barmode='group',
            title="Average Income & Expense by Day of Week",
            color_discrete_map={'Credit': '#2ca02c', 'Debit': '#d62728'},
            labels={'value': 'Average Amount (₹)', 'variable': 'Transaction Type'}
        )
        st.plotly_chart(fig_dow, use_container_width=True)

    # ==========================================
    # TAB 3: INCOME VS EXPENSE BREAKDOWN
    # ==========================================
    with tab_breakdown:
        c_brk1, c_brk2 = st.columns(2)
        
        with c_brk1:
            st.markdown("#### 💰 Where is the money coming from?")
            df_income = df_records[df_records['Credit'] > 0]
            if not df_income.empty:
                inc_summary = df_income.groupby('Main Category')['Credit'].sum().reset_index().sort_values('Credit', ascending=False)
                fig_inc_pie = px.pie(
                    inc_summary, 
                    names='Main Category', 
                    values='Credit', 
                    hole=0.4,
                    title="Operating Income Sources",
                    color_discrete_sequence=px.colors.sequential.Greens_r
                )
                fig_inc_pie.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_inc_pie, use_container_width=True)
                
                st.markdown("**Top 5 Income Categories:**")
                inc_disp = inc_summary.head(5).copy()
                inc_disp['Credit'] = inc_disp['Credit'].apply(format_currency)
                st.dataframe(inc_disp, hide_index=True, use_container_width=True)
            else:
                st.info("No miscellaneous income recorded in this period.")

        with c_brk2:
            st.markdown("#### 💸 Where is the money going?")
            df_expenses = df_records[df_records['Debit'] > 0]
            if not df_expenses.empty:
                exp_summary = df_expenses.groupby('Main Category')['Debit'].sum().reset_index().sort_values('Debit', ascending=False)
                fig_exp_pie = px.pie(
                    exp_summary, 
                    names='Main Category', 
                    values='Debit', 
                    hole=0.4,
                    title="Operating Expense Sources",
                    color_discrete_sequence=px.colors.sequential.Reds_r
                )
                fig_exp_pie.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_exp_pie, use_container_width=True)

                st.markdown("**Top 5 Expense Categories:**")
                exp_disp = exp_summary.head(5).copy()
                exp_disp['Debit'] = exp_disp['Debit'].apply(format_currency)
                st.dataframe(exp_disp, hide_index=True, use_container_width=True)
            else:
                st.info("No expenses recorded in this period.")

    # ==========================================
    # TAB 4: HIERARCHICAL LEDGER
    # ==========================================
    with tab_ledger:
        st.markdown("### 📋 Categorized Transaction Ledger")
        st.write("Grouped by Account Type (Cash/GPay) ➔ Main Category ➔ Sub Category")

        # Group data exactly like the Tkinter Treeview hierarchy
        summary_table = df_records.groupby(['Account', 'Main Category', 'Sub Category']).agg(
            Total_Credit=('Credit', 'sum'),
            Total_Debit=('Debit', 'sum')
        ).reset_index()

        # Add Net Column
        summary_table['Net Amount'] = summary_table['Total_Credit'] - summary_table['Total_Debit']

        # Format currencies for display
        display_df = summary_table.copy()
        for col in ['Total_Credit', 'Total_Debit', 'Net Amount']:
            display_df[col] = display_df[col].apply(format_currency)

        # Sort logically
        display_df = display_df.sort_values(by=['Account', 'Main Category', 'Sub Category'])
        
        st.dataframe(display_df, hide_index=True, use_container_width=True)