import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import json
from functools import reduce
import datetime
import streamlit.components.v1 as components

def fetch_raw_data_master():
    """Fetches customer, location, and item data from all portfolios, plus outer shop status."""
    conn = sqlite3.connect('users.db')
    
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

def fetch_final_tally():
    """Fetches Final Tally records."""
    conn = sqlite3.connect('users.db')
    try:
        df = pd.read_sql_query("SELECT * FROM FinalTally", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def render(n_data, n_ao, n_outer, n_out_cl, b_data, b_ao, b_outer, b_out_cl, box_data, box_ao, box_outer, box_out_cl):
    st.title("🌍 ULTIMATE MASTER DASHBOARD (20-POINT ANALYSIS)")
    st.info("💡 **Welcome to the Master Intelligence Hub.** This dashboard analyzes your entire business. **How to read:** Look at the Action Plan on the left. To see the exact numbers behind any graph, click the **'📋 Detailed Data Table'** tab next to it!")

    def format_currency(val):
        if pd.isna(val): return "₹ 0"
        if val < 0: return f"- ₹ {abs(val):,.0f}"
        return f"₹ {val:,.0f}"

    def render_detailed_block(title, metric_label, metric_val, status, status_reason, action_desc, math_desc, meaning_desc, fig, df_table):
        st.markdown(f"### {title}")
        
        c_text, c_visual = st.columns([1.2, 2])
        
        with c_text:
            st.metric(label=metric_label, value=metric_val)
            
            if status == "GOOD": st.success(f"✅ **EXCELLENT:** {status_reason}")
            elif status == "AVG": st.warning(f"⚠️ **MONITOR:** {status_reason}")
            elif status == "BAD": st.error(f"🚨 **HIGH RISK:** {status_reason}")
            elif status == "INFO": st.info(f"ℹ️ **INFO:** {status_reason}")
            
            st.markdown("**🚀 Action Plan:**")
            st.info(action_desc)
            
            with st.expander("📖 Understand this Metric (Math & Logic)"):
                st.markdown(f"**🧮 The Math:** {math_desc}")
                st.markdown(f"**💡 The Meaning:** {meaning_desc}")
                
        with c_visual:
            tab_chart, tab_data = st.tabs(["📊 Visual Graph", "📋 Detailed Data Table"])
            with tab_chart:
                st.plotly_chart(fig, use_container_width=True)
            with tab_data:
                st.dataframe(df_table, hide_index=True, use_container_width=True)
                
        st.write("---")

    # --- 1. MASTER DATE FILTER ---
    all_dates = []
    for d in [n_data, b_data, box_data]:
        if not d.empty: all_dates.extend(d['date'].tolist())
    
    if not all_dates:
        st.warning("No data found in the system.")
        return
        
    db_min, db_max = pd.Series(all_dates).min().date(), pd.Series(all_dates).max().date()
    today = datetime.date.today()
    current_year_start = datetime.date(today.year, 1, 1)
    
    allowed_min = min(db_min, current_year_start)
    allowed_max = max(db_max, today)
    default_start = max(db_min, current_year_start)
    
    col1, _ = st.columns([1, 3])
    with col1:
        date_range = st.date_input("📅 Select Master Date Range:", value=(default_start, min(db_max, today)), min_value=allowed_min, max_value=allowed_max)

    if len(date_range) != 2: return 
    sd, ed = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

    # --- 2. RAW DATA FETCH & CLEANUP ---
    raw_data, active_outer = fetch_raw_data_master()
    if not raw_data.empty:
        raw_data['date_parsed'] = pd.to_datetime(raw_data['loan_date'], format='%d/%m/%Y', errors='coerce')
        for col in ['address', 'post', 'district', 'pincode']:
            raw_data[col] = raw_data[col].astype(str).str.strip().str.title()
            raw_data[col] = raw_data[col].replace(['', 'Nan', 'None'], 'Unknown')
        raw_data['Storage'] = np.where(raw_data['form_no'].isin(active_outer), 'Outer Shop', 'In Shop')
        filtered_raw = raw_data[(raw_data['date_parsed'] >= sd) & (raw_data['date_parsed'] <= ed)].copy()
    else:
        filtered_raw = pd.DataFrame()

    tally_data = fetch_final_tally()
    if not tally_data.empty:
        tally_data['tally_date_parsed'] = pd.to_datetime(tally_data['tally_date'], format='%d/%m/%Y', errors='coerce')
        tally_filt = tally_data[(tally_data['tally_date_parsed'] >= sd) & (tally_data['tally_date_parsed'] <= ed)].copy()
    else:
        tally_filt = pd.DataFrame()

    # --- 3. AGGREGATION & CLEANUP ---
    def f_data(df): return df[(df['date'] >= sd) & (df['date'] <= ed)].copy() if not df.empty else pd.DataFrame()
    n_filt, b_filt, box_filt = f_data(n_data), f_data(b_data), f_data(box_data)

    def prep_ao(df, name):
        if df.empty: return pd.DataFrame()
        d = df.copy()
        d['Portfolio'] = name
        return d
    comb_ao = pd.concat([prep_ao(n_ao, 'Normal'), prep_ao(b_ao, 'Big'), prep_ao(box_ao, 'Box')], ignore_index=True)

    def clean_outer_active(df, name):
        if df is None or df.empty: return pd.DataFrame()
        d = df[(df['date'] >= sd) & (df['date'] <= ed)].copy()
        if d.empty: return pd.DataFrame()
        d['pres'] = pd.to_numeric(d['present_amount'], errors='coerce').fillna(0)
        d['tot'] = pd.to_numeric(d['total_given_amount'], errors='coerce').fillna(0)
        d['core_amount'] = np.where(d['pres'] > 0, d['pres'], d['tot'])
        d['outer_amount'] = pd.to_numeric(d['amount'], errors='coerce').fillna(0)
        d['Portfolio'] = name
        return d

    def clean_outer_closed(df, name):
        if df is None or df.empty: return pd.DataFrame()
        d = df[(df['date'] >= sd) & (df['date'] <= ed)].copy()
        if d.empty: return pd.DataFrame()
        d['shop_loan_int'] = pd.to_numeric(d.get('shop_total_interest', 0), errors='coerce').fillna(0)
        d['outer_loan_int'] = pd.to_numeric(d.get('outer_interest', 0), errors='coerce').fillna(0)
        d['profit_amount'] = d['shop_loan_int'] - d['outer_loan_int']
        d['doc_charge'] = pd.to_numeric(d.get('doc_charge', 0), errors='coerce').fillna(0)
        d['paper_amount'] = pd.to_numeric(d.get('paper_amount', 0), errors='coerce').fillna(0)
        d['Portfolio'] = name
        return d

    comb_out_act = pd.concat([clean_outer_active(n_outer, "Normal"), clean_outer_active(b_outer, "Big"), clean_outer_active(box_outer, "Box")], ignore_index=True)
    comb_out_cl = pd.concat([clean_outer_closed(n_out_cl, "Normal"), clean_outer_closed(b_out_cl, "Big"), clean_outer_closed(box_out_cl, "Box")], ignore_index=True)

    # COMBINED TIMELINE
    def prefix_cols(df, suffix):
        if df.empty: return df
        d = df.copy()
        d.columns = [c if c == 'date' else f"{c}_{suffix}" for c in d.columns]
        return d

    dfs_to_merge = []
    if not n_filt.empty: dfs_to_merge.append(prefix_cols(n_filt, 'norm'))
    if not b_filt.empty: dfs_to_merge.append(prefix_cols(b_filt, 'big'))
    if not box_filt.empty: dfs_to_merge.append(prefix_cols(box_filt, 'box'))

    if dfs_to_merge:
        merged_daily = reduce(lambda l, r: pd.merge(l, r, on='date', how='outer'), dfs_to_merge).fillna(0)
        merged_daily = merged_daily.sort_values('date')
    else:
        st.warning("No data in selected date range.")
        return

    # ==========================================
    # GLOBAL MASTER MATH (Used across all tabs)
    # ==========================================
    for p in ['norm', 'big', 'box']:
        for base in ['total_loan_amount', 'total_overall_interest', 'total_paper', 'total_count', 'gold_amount', 'silver_amount']:
            col = f"{base}_{p}"
            if col not in merged_daily.columns: merged_daily[col] = 0.0

    merged_daily['Grand_Dispersed'] = merged_daily['total_loan_amount_norm'] + merged_daily['total_loan_amount_big'] + merged_daily['total_loan_amount_box']
    merged_daily['Grand_Interest'] = merged_daily['total_overall_interest_norm'] + merged_daily['total_overall_interest_big'] + merged_daily['total_overall_interest_box']
    merged_daily['Grand_Paper'] = merged_daily['total_paper_norm'] + merged_daily['total_paper_big'] + merged_daily['total_paper_box']
    merged_daily['Grand_Count'] = merged_daily['total_count_norm'] + merged_daily['total_count_big'] + merged_daily['total_count_box']

    t_disp = merged_daily['Grand_Dispersed'].sum()
    t_int = merged_daily['Grand_Interest'].sum()
    t_paper = merged_daily['Grand_Paper'].sum()
    t_out_prof = comb_out_cl['profit_amount'].sum() if not comb_out_cl.empty else 0
    t_doc = comb_out_cl['doc_charge'].sum() if not comb_out_cl.empty else 0
    t_net_rev = t_int + t_out_prof + t_paper - t_doc

    t_core_o = comb_out_act['core_amount'].sum() if not comb_out_act.empty else 0
    t_lev_o = comb_out_act['outer_amount'].sum() if not comb_out_act.empty else 0

    merged_daily['Daily_Net'] = merged_daily['Grand_Interest'] + merged_daily['Grand_Paper']
    if not comb_out_cl.empty:
        out_d = comb_out_cl.groupby('date')[['profit_amount', 'doc_charge']].sum().reset_index()
        merged_daily = pd.merge(merged_daily, out_d, on='date', how='left').fillna(0)
        merged_daily['Daily_Net'] = merged_daily['Daily_Net'] + merged_daily['profit_amount'] - merged_daily['doc_charge']
    merged_daily['Cum_Net'] = merged_daily['Daily_Net'].cumsum()

    if not comb_ao.empty:
        t_act_p = comb_ao[comb_ao['state'] == 'Active']['principal_amount'].sum()
        t_ovr_p = comb_ao[comb_ao['state'] == 'Overdue']['principal_amount'].sum()
        tox_ratio = (t_ovr_p / (t_act_p + t_ovr_p) * 100) if (t_act_p + t_ovr_p) > 0 else 0
    else:
        t_act_p, t_ovr_p, tox_ratio = 0, 0, 0

    lev_ratio = (t_lev_o / t_disp * 100) if t_disp > 0 else 0

    st.write("---")

    # --- TABS WITH NEW MODULES INCLUDED ---
    t_rev, t_cap, t_shop_outer, t_risk, t_ops, t_loc, t_inv, t_tally, t_ledger, t_summary = st.tabs([
        "💰 1-5: Revenue & Profit", 
        "🏢 6-10: Capital & Leverage", 
        "⚖️ Master Shop vs Outer",
        "🚨 11-15: Risk & Toxicity", 
        "📦 16-20: Portfolio Operations",
        "📍 Territory & Location",
        "⚖️ Inventory & Weight Intelligence",
        "📊 Final Tally Analysis",
        "📋 Ultimate Master P&L",
        "🏆 Final Growth Report & Print"
    ])

    # ==========================================
    # TAB 1: REVENUE & PROFIT SCIENCE (1-5)
    # ==========================================
    with t_rev:
        # A1: Yield
        yield_pct = (t_net_rev / t_disp * 100) if t_disp > 0 else 0
        if yield_pct >= 2.5: stat, msg, act = "GOOD", "Your money is returning excellent pure profit.", "Maintain your current interest rates."
        elif yield_pct >= 1.5: stat, msg, act = "AVG", "Profits are acceptable, but efficiency is slipping.", "Check if you are giving away too much profit to outside financiers."
        else: stat, msg, act = "BAD", "You are risking massive amounts of cash for pennies.", "Immediate Action: Raise your shop interest rates or stop taking outside loans with high fees."
        
        fig1 = px.bar(x=["Total Dispersed", "Net Revenue"], y=[t_disp, t_net_rev], color=["Total Dispersed", "Net Revenue"], color_discrete_map={"Total Dispersed": "#1f77b4", "Net Revenue": "#2ca02c"}, text_auto='.2s')
        fig1.update_layout(showlegend=False, yaxis_title="Amount (₹)")
        
        df_t1 = pd.DataFrame({"Metric": ["Total Dispersed (Money Out)", "Net Revenue (Pure Profit)"], "Amount": [format_currency(t_disp), format_currency(t_net_rev)]})
        
        render_detailed_block("Analysis 1: Global Yield on Capital (ROI)", "Total Yield %", f"{yield_pct:.2f}%", stat, msg, act,
            "(Total Net Revenue ÷ Total Money Lent Out) × 100",
            "This measures how hard your money works. High volume does not mean high profit if your yield is low.", fig1, df_t1)

        # A2: Rev Dominance
        int_share = (t_int/(t_net_rev+t_doc)*100) if t_net_rev > 0 else 0
        if int_share >= 50: stat, msg, act = "GOOD", "Customer interest safely dominates your income.", "Keep prioritizing direct customer loans."
        elif int_share >= 30: stat, msg, act = "AVG", "You are becoming reliant on outer financiers.", "Ensure outer financiers don't raise their rates, it would destroy your profit."
        else: stat, msg, act = "BAD", "Outside profit dominates your income.", "You are acting like a broker. Focus on growing your own loan book."

        df_pie = pd.DataFrame({"Source": ["Customer Interest", "Outer Profit", "Paper Fees"], "Value": [t_int, t_out_prof, t_paper]})
        fig2 = px.pie(df_pie, names="Source", values="Value", hole=0.5, color="Source", color_discrete_map={"Customer Interest": "#2ca02c", "Outer Profit": "#FFD700", "Paper Fees": "#1f77b4"})
        
        df_t2 = df_pie.copy()
        df_t2['Value'] = df_t2['Value'].apply(format_currency)
        df_t2.columns = ["Income Source", "Amount Generated"]
        
        render_detailed_block("Analysis 2: Revenue Stream Dominance", "Customer Int. Share", f"{int_share:.1f}%", stat, msg, act,
            "Comparing sums of (Customer Int vs. Outer Profit vs. Paper Fees).",
            "A safe loan business should survive mostly on Customer Interest. Over-reliance on Outer Profit is dangerous.", fig2, df_t2)

        # A3: Arbitrage
        tot_shop_int_closed = comb_out_cl['shop_loan_int'].sum() if not comb_out_cl.empty else 0
        tot_outer_int_closed = comb_out_cl['outer_loan_int'].sum() if not comb_out_cl.empty else 0
        arb_margin = (t_out_prof / tot_shop_int_closed * 100) if tot_shop_int_closed > 0 else 0
        
        if arb_margin >= 30: stat, msg, act = "GOOD", "Excellent spread. You keep a large chunk of interest.", "Continue pledging items to this outside financier."
        elif arb_margin >= 15: stat, msg, act = "AVG", "Moderate spread. The outer shop takes a large cut.", "Try to negotiate a cheaper interest rate outside."
        else: stat, msg, act = "BAD", "You are keeping almost none of the collected interest.", "Stop pledging these items. The risk is not worth the tiny profit."

        fig3 = go.Figure(go.Waterfall(name="20", orientation="v", measure=["relative", "relative", "total"], x=["Shop Int Received", "Outer Int Paid", "Net Outer Profit"], textposition="outside", y=[tot_shop_int_closed, -tot_outer_int_closed, t_out_prof], connector={"line":{"color":"rgb(63, 63, 63)"}}))
        fig3.update_layout(waterfallgap=0.3)
        
        df_t3 = pd.DataFrame({"Transaction Stage": ["Total Customer Interest Received", "Minus: Outer Interest Paid", "Equals: Net Outer Profit in Pocket"], "Amount": [format_currency(tot_shop_int_closed), format_currency(-tot_outer_int_closed), format_currency(t_out_prof)]})
        
        render_detailed_block("Analysis 3: Outer Arbitrage Efficiency", "Arbitrage Margin", f"{arb_margin:.1f}%", stat, msg, act,
            "(Net Outer Profit ÷ Total Interest Collected from Customer) × 100",
            "When you pledge an item outside, you collect interest and pay the outer shop. This shows what % of that money stays in your pocket.", fig3, df_t3)

        # A4: Friction
        friction_pct = (t_doc / t_out_prof * 100) if t_out_prof > 0 else 0
        if friction_pct <= 5: stat, msg, act = "GOOD", "Doc fees are a tiny fraction of your profit.", "Your parceling strategy is highly efficient."
        elif friction_pct <= 15: stat, msg, act = "AVG", "Doc fees are starting to eat into profits.", "Combine more items into a single pledge to save on flat document fees."
        else: stat, msg, act = "BAD", "You are bleeding money to paperwork fees.", "Stop pledging small 5k-10k items individually. Combine them into big parcels."

        fig4 = px.bar(x=["Gross Outer Profit", "Doc Fees Paid"], y=[t_out_prof+t_doc, t_doc], color=["Gross", "Fee"], color_discrete_map={"Gross": "#FFD700", "Fee": "#d62728"})
        fig4.update_layout(showlegend=False, yaxis_title="Amount (₹)")
        
        df_t4 = pd.DataFrame({"Metric": ["Gross Profit", "Doc Fees Paid (Expense)"], "Amount": [format_currency(t_out_prof+t_doc), format_currency(t_doc)]})
        
        render_detailed_block("Analysis 4: Outer Friction (Doc Cost Leakage)", "Doc Fee Leakage", f"{friction_pct:.1f}%", stat, msg, act,
            "(Total Doc Fees Paid ÷ Gross Outer Profit Generated) × 100",
            "This compares the pure profit you generated against the 'friction' cost of doing the paperwork. High friction kills profit.", fig4, df_t4)

        # A5: Trajectory
        if merged_daily['Daily_Net'].sum() > 0: stat, msg, act = "GOOD", "Overall business wealth is growing upwards.", "Investigate any small downward dips on the graph to prevent future profit leaks."
        else: stat, msg, act = "BAD", "Business is operating at a net loss for this period.", "You are paying more in Doc Fees/Outside Interest than you are making. Freeze pledging."

        fig5 = px.area(merged_daily, x='date', y='Cum_Net', color_discrete_sequence=['#2ca02c'])
        fig5.update_layout(yaxis_title="Total Wealth (₹)")
        
        df_t5 = merged_daily[['date', 'Daily_Net', 'Cum_Net']].copy()
        df_t5['date'] = df_t5['date'].dt.strftime('%d %b %Y')
        df_t5['Daily Pure Profit'] = df_t5['Daily_Net'].apply(format_currency)
        df_t5['Cumulative Banked Wealth'] = df_t5['Cum_Net'].apply(format_currency)
        df_t5 = df_t5[['date', 'Daily Pure Profit', 'Cumulative Banked Wealth']]
        
        render_detailed_block("Analysis 5: Net Revenue Growth Trajectory", "Final Accumulated", format_currency(t_net_rev), stat, msg, act,
            "Cumulative Sum of (Daily Interest + Daily Outer Profit + Daily Paper Fees - Daily Doc Fees).",
            "Tracks the pure bottom-line wealth accumulation of your business over time.", fig5, df_t5)

    # ==========================================
    # TAB 2: CAPITAL & LEVERAGE DYNAMICS (6-10)
    # ==========================================
    with t_cap:
        # A6: Leverage
        if lev_ratio <= 40: stat, msg, act = "GOOD", "Safe. You are mostly using your own money.", "You have safe room to borrow more if customer demand spikes."
        elif lev_ratio <= 75: stat, msg, act = "AVG", "Moderate risk. Relying heavily on borrowed money.", "Do not let this cross 75%. Start using customer interest to clear outer debts."
        else: stat, msg, act = "BAD", "DANGER. Your shop is running entirely on debt.", "If outer financiers recall their money, you collapse. Unpledge items immediately."

        fig6 = go.Figure(go.Indicator(mode="gauge+number", value=lev_ratio, title={'text': "Leverage %"}, gauge={'axis': {'range': [None, 100]}, 'bar': {'color': "darkred"}, 'steps': [{'range': [0, 40], 'color': "lightgreen"}, {'range': [40, 75], 'color': "gold"}, {'range': [75, 100], 'color': "salmon"}]}))
        
        df_t6 = pd.DataFrame({"Capital Origin": ["Pure Shop Money (Safe)", "Borrowed Outer Debt (Risk)"], "Amount": [format_currency(t_disp - t_lev_o), format_currency(t_lev_o)]})
        
        render_detailed_block("Analysis 6: Global Capital Leverage Ratio", "Debt to Capital", f"{lev_ratio:.1f}%", stat, msg, act,
            "(Total Active Outer Debt ÷ Total Historical Money Lent Out) × 100",
            "Measures how much of your business is currently funded by external borrowing. 0% is best.", fig6, df_t6)

        # A7: Lev Dist
        if not comb_out_act.empty:
            lev_dist = comb_out_act.groupby('Portfolio')['outer_amount'].sum().reset_index()
            biggest_lev = lev_dist.loc[lev_dist['outer_amount'].idxmax()]['Portfolio'] if not lev_dist.empty else "None"
            if biggest_lev == 'Normal': stat, msg, act = "GOOD", "Debt safely spread across small normal items.", "This is the safest way to pledge."
            else: stat, msg, act = "AVG", f"Debt heavily tied to {biggest_lev} VIP loans.", f"Pledging massive {biggest_lev} items is risky. If the VIP defaults, you owe a huge sum."
            
            fig7 = px.pie(lev_dist, names='Portfolio', values='outer_amount', hole=0.4, color='Portfolio', color_discrete_map={'Normal': '#1f77b4', 'Big': '#ff7f0e', 'Box': '#9467bd'})
            
            df_t7 = lev_dist.copy()
            df_t7['outer_amount'] = df_t7['outer_amount'].apply(format_currency)
            df_t7.columns = ["Portfolio", "Active Outer Debt"]
            
            render_detailed_block("Analysis 7: Leverage Distribution by Portfolio", "Heaviest Debt", biggest_lev, stat, msg, act,
                "Sum of active outer debt grouped by category.",
                "Shows exactly which portfolio is responsible for your external debt.", fig7, df_t7)
        else: st.warning("No active outer debt for Analysis 7.")

        # A8: Dispersal
        avg_disp = merged_daily['Grand_Dispersed'].mean() if not merged_daily.empty else 0
        stat, msg, act = "INFO", "Baseline tracking of daily cash outflow.", f"Keep at least ₹ {avg_disp*3:,.0f} (3x Average) in your safe at all times to avoid turning customers away."
        
        fig8 = px.line(merged_daily, x='date', y='Grand_Dispersed', markers=True, color_discrete_sequence=['#1f77b4'])
        fig8.add_hline(y=avg_disp, line_dash="dash", line_color="red", annotation_text="Average Daily Outflow")
        
        df_t8 = merged_daily[['date', 'Grand_Dispersed']].copy()
        df_t8['date'] = df_t8['date'].dt.strftime('%d %b %Y')
        df_t8['Money Given Out'] = df_t8['Grand_Dispersed'].apply(format_currency)
        df_t8 = df_t8[['date', 'Money Given Out']]
        
        render_detailed_block("Analysis 8: Daily Dispersal Velocity (Cash Outflow)", "Avg Daily Outflow", format_currency(avg_disp), stat, msg, act,
            "Sum of all money lent out divided by the number of days.",
            "Dictates your daily cash-drawer requirements.", fig8, df_t8)

        # A9: Ticket Size
        n_tkt = (merged_daily['total_loan_amount_norm'].sum() / merged_daily['total_count_norm'].sum()) if merged_daily['total_count_norm'].sum() > 0 else 0
        b_tkt = (merged_daily['total_loan_amount_big'].sum() / merged_daily['total_count_big'].sum()) if merged_daily['total_count_big'].sum() > 0 else 0
        bx_tkt = (merged_daily['total_loan_amount_box'].sum() / merged_daily['total_count_box'].sum()) if merged_daily['total_count_box'].sum() > 0 else 0
        
        if b_tkt > (n_tkt * 1.5): stat, msg, act = "GOOD", "Clear distinction between Normal and Big sizes.", "Your software tiers are being used correctly."
        else: stat, msg, act = "AVG", "Normal and Big loans are mathematically similar.", "Staff might be entering small loans into the 'Big' category. Audit data entry."

        fig9 = px.bar(x=['Normal', 'Big', 'Box'], y=[n_tkt, b_tkt, bx_tkt], color=['Normal', 'Big', 'Box'], color_discrete_map={'Normal': '#1f77b4', 'Big': '#ff7f0e', 'Box': '#9467bd'}, text_auto='.2s')
        fig9.update_layout(showlegend=False, yaxis_title="Avg Loan Size (₹)")
        
        df_t9 = pd.DataFrame({"Portfolio": ["Normal", "Big", "Box"], "Average Size per Loan": [format_currency(n_tkt), format_currency(b_tkt), format_currency(bx_tkt)]})
        
        render_detailed_block("Analysis 9: Ticket Size Disparity", "Big Loan Avg Size", format_currency(b_tkt), stat, msg, act,
            "Total Dispersed in Portfolio ÷ Total Number of Loans.",
            "Proves if your 'Big' and 'Box' portfolios are actually behaving like VIP products.", fig9, df_t9)

        # A10: Seasonality
        merged_daily['Month'] = merged_daily['date'].dt.month_name()
        months_order = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        merged_daily['Month'] = pd.Categorical(merged_daily['Month'], categories=months_order, ordered=True)
        seas_df = merged_daily.groupby('Month')['Grand_Dispersed'].sum().reset_index()
        peak_month = seas_df.loc[seas_df['Grand_Dispersed'].idxmax()]['Month'] if not seas_df.empty and seas_df['Grand_Dispersed'].max() > 0 else "None"
        
        stat, msg, act = "INFO", f"Your highest cash drain is usually {peak_month}.", f"Exactly 30 days before {peak_month} begins, arrange backup capital."

        fig10 = px.bar(seas_df, x='Month', y='Grand_Dispersed', color='Grand_Dispersed', color_continuous_scale="Blues")
        
        df_t10 = seas_df.copy()
        df_t10['Total Demand'] = df_t10['Grand_Dispersed'].apply(format_currency)
        df_t10 = df_t10[['Month', 'Total Demand']]
        
        render_detailed_block("Analysis 10: Cashflow Seasonality (Outflow Heatmap)", "Peak Outflow Month", str(peak_month), stat, msg, act,
            "Sum of all dispersals aggregated by Month.",
            "Identifies your 'Cash Crunch' months. Shows when demand spikes.", fig10, df_t10)

    # ==========================================
    # TAB 3: MASTER SHOP VS OUTER 
    # ==========================================
    with t_shop_outer:
        st.markdown("### ⚖️ Master Shop vs Outer Capital (Active & Overdue)")
        st.info("💡 **Overview:** Global breakdown of your Live Capital by Metal (Gold vs Silver) and Source (Shop vs Outer).")

        if not comb_ao.empty:
            f_ao = comb_ao.copy()
            
            if not comb_out_act.empty and 'form_no' in comb_out_act.columns and 'form_no' in f_ao.columns:
                outer_map = comb_out_act.groupby('form_no')['outer_amount'].sum().to_dict()
                f_ao['outer_amt'] = f_ao['form_no'].map(outer_map).fillna(0)
            else:
                f_ao['outer_amt'] = 0
                
            f_ao['shop_amt'] = (f_ao['principal_amount'] - f_ao['outer_amt']).clip(lower=0)
            
            t_prin = f_ao['principal_amount'].sum()
            t_shop = f_ao['shop_amt'].sum()
            t_out = f_ao['outer_amt'].sum()
            
            if 'loan_type' in f_ao.columns:
                g_df = f_ao[f_ao['loan_type'] == 'Gold']
                s_df = f_ao[f_ao['loan_type'] == 'Silver']
            else:
                g_df = pd.DataFrame({'principal_amount': [], 'shop_amt': [], 'outer_amt': []})
                s_df = pd.DataFrame({'principal_amount': [], 'shop_amt': [], 'outer_amt': []})
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Total Live Principal", format_currency(t_prin))
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_df['principal_amount'].sum():,.0f}<br>🥈 Silver: ₹{s_df['principal_amount'].sum():,.0f}</div>", unsafe_allow_html=True)
            with c2:
                st.metric("Total Shop Capital", format_currency(t_shop))
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_df['shop_amt'].sum():,.0f}<br>🥈 Silver: ₹{s_df['shop_amt'].sum():,.0f}</div>", unsafe_allow_html=True)
            with c3:
                st.metric("Total Outer Capital", format_currency(t_out))
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>🥇 Gold: ₹{g_df['outer_amt'].sum():,.0f}<br>🥈 Silver: ₹{s_df['outer_amt'].sum():,.0f}</div>", unsafe_allow_html=True)
            with c4:
                st.metric("System Leverage Ratio", f"{(t_out/t_prin*100) if t_prin > 0 else 0:.1f}%")
                st.markdown(f"<div style='font-size: 0.85em; color: gray;'>Ratio of Outer vs Total Principal</div>", unsafe_allow_html=True)

            st.write("---")
            
            st.markdown("#### 🔋 Live Leverage & Portfolio Ownership")
            g_col1, g_col2 = st.columns(2)
            
            with g_col1:
                lev_val = (t_out / t_prin * 100) if t_prin > 0 else 0
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=lev_val,
                    title={'text': "Global Leverage Risk Meter (%)"},
                    gauge={
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "darkred"},
                        'steps': [
                            {'range': [0, 40], 'color': "lightgreen"},  
                            {'range': [40, 75], 'color': "gold"},         
                            {'range': [75, 100], 'color': "salmon"}       
                        ]
                    }
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)
                st.info("💡 **How to read:** Green is safe (you are mostly using your own money). Yellow is a warning. Red means you are heavily over-leveraged on borrowed money.")

            with g_col2:
                pie_df = pd.DataFrame({
                    "Money Source": ["🏢 Your Pure Shop Money", "🤝 Borrowed Outer Money"],
                    "Amount": [t_shop, t_out]
                })
                fig_easy_pie = px.pie(
                    pie_df, 
                    names="Money Source", 
                    values="Amount", 
                    hole=0.55, 
                    title="Who really owns the money in the market right now?",
                    color="Money Source", 
                    color_discrete_map={"🏢 Your Pure Shop Money": "#2ca02c", "🤝 Borrowed Outer Money": "#d62728"}
                )
                fig_easy_pie.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
                st.plotly_chart(fig_easy_pie, use_container_width=True)
                st.success("💡 **Simple Breakdown:** Ignoring all complex math, this simply shows what chunk of the live market belongs to you versus outsiders.")
                
            st.write("---")

            if 'loan_type' in f_ao.columns:
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    gs_df = f_ao.groupby('loan_type')[['shop_amt', 'outer_amt']].sum().reset_index()
                    gs_melt = gs_df.melt(id_vars="loan_type", var_name="Source", value_name="Amount")
                    gs_melt['Source'] = gs_melt['Source'].map({'shop_amt': 'Shop Capital', 'outer_amt': 'Outer Capital'})
                    fig_bar = px.bar(gs_melt, x="loan_type", y="Amount", color="Source", barmode="group", title="Capital Split by Metal (Global)", color_discrete_map={"Shop Capital": "#1f77b4", "Outer Capital": "#ff7f0e"})
                    st.plotly_chart(fig_bar, use_container_width=True)
                    
                with col_chart2:
                    ao_split = f_ao.groupby('state')[['shop_amt', 'outer_amt']].sum().reset_index()
                    ao_melt = ao_split.melt(id_vars="state", var_name="Source", value_name="Amount")
                    ao_melt['Source'] = ao_melt['Source'].map({'shop_amt': 'Shop Capital', 'outer_amt': 'Outer Capital'})
                    fig_ao_risk = px.bar(ao_melt, x="state", y="Amount", color="Source", barmode="group", title="Active vs Overdue Global Exposure", color_discrete_map={"Shop Capital": "#2ca02c", "Outer Capital": "#d62728"})
                    st.plotly_chart(fig_ao_risk, use_container_width=True)
                
            st.markdown("#### 📋 Global Actionable Priority Ledger (Highest Outer Debt)")
            disp_cols = ['form_no', 'loan_date', 'loan_type', 'Portfolio', 'state', 'principal_amount', 'shop_amt', 'outer_amt']
            avail_cols = [c for c in disp_cols if c in f_ao.columns]
            disp_df = f_ao[avail_cols].copy()
            
            if not disp_df.empty:
                disp_df['loan_date'] = disp_df['loan_date'].dt.strftime('%d-%m-%Y')
                disp_df = disp_df.sort_values(by='outer_amt', ascending=False).head(100)
                disp_df = disp_df.rename(columns={
                    'form_no': 'Form No', 'loan_date': 'Date', 'loan_type': 'Metal', 'state': 'Status',
                    'principal_amount': 'Total Principal (₹)', 'shop_amt': 'Shop Amount (₹)', 'outer_amt': 'Outer Amount (₹)'
                })
                st.dataframe(disp_df, hide_index=True, use_container_width=True)
        else:
            st.warning("No live data available for Shop vs Outer analysis.")

    # ==========================================
    # TAB 4: RISK & TOXICITY METRICS (11-15)
    # ==========================================
    with t_risk:
        if not comb_ao.empty:
            # A11: Toxic Ratio
            if tox_ratio <= 10: stat, msg, act = "GOOD", "Very little dead money.", "Your collection team is doing a great job."
            elif tox_ratio <= 25: stat, msg, act = "AVG", "Dead money is building up.", "Call customers whose items are over 10 months old to warn them."
            else: stat, msg, act = "BAD", "Over a quarter of your money is rotting.", "Emergency! Halt new loans. Focus on auctioning old items to recover cash."

            fig11 = px.pie(names=['Safe (Active)', 'Toxic (Overdue > 1Yr)'], values=[t_act_p, t_ovr_p], hole=0.6, color_discrete_sequence=['#2ca02c', '#d62728'])
            
            df_t11 = pd.DataFrame({"Status": ["Safe Active Capital", "Toxic Overdue Capital"], "Amount": [format_currency(t_act_p), format_currency(t_ovr_p)]})
            
            render_detailed_block("Analysis 11: Global Toxic Debt Ratio", "Toxic Debt %", f"{tox_ratio:.1f}%", stat, msg, act,
                "(Total Overdue Principal ÷ Total Active + Overdue Principal) × 100",
                "The most critical risk metric in the system. 'Toxic Debt' is money stuck past your penalty threshold.", fig11, df_t11)

            # A12: Toxic Dist
            tox_dist = comb_ao[comb_ao['state'] == 'Overdue'].groupby('Portfolio')['principal_amount'].sum().reset_index()
            worst_port = tox_dist.loc[tox_dist['principal_amount'].idxmax()]['Portfolio'] if not tox_dist.empty else "None"
            stat, msg, act = "INFO", f"Rot is concentrated in {worst_port}.", f"Focus all debt collection phone calls exclusively on {worst_port} customers today."

            fig12 = px.bar(tox_dist, x='Portfolio', y='principal_amount', color='Portfolio', color_discrete_map={'Normal': '#1f77b4', 'Big': '#ff7f0e', 'Box': '#9467bd'})
            fig12.update_layout(yaxis_title="Overdue Capital (₹)")
            
            df_t12 = tox_dist.copy()
            df_t12['principal_amount'] = df_t12['principal_amount'].apply(format_currency)
            df_t12.columns = ["Portfolio", "Total Dead Money"]
            
            render_detailed_block("Analysis 12: Toxic Debt Distribution by Portfolio", "Highest Risk Tier", worst_port, stat, msg, act,
                "Sum of Overdue Principal grouped by Portfolio.",
                "Shows exactly where the rot is. Overdue Big loans mean a few rich clients hold your money hostage.", fig12, df_t12)

            # A13: Uncoll Int
            t_act_int = comb_ao[comb_ao['state'] == 'Active']['calculated_interest'].sum()
            t_ovr_int = comb_ao[comb_ao['state'] == 'Overdue']['calculated_interest'].sum()
            if t_act_int >= t_ovr_int: stat, msg, act = "GOOD", "Most of your expected interest is safe.", "Keep monitoring to ensure the orange bar stays small."
            else: stat, msg, act = "BAD", "Most expected interest is a phantom mirage.", "Do not treat overdue interest as real money. You may have to waive it."

            fig13 = px.bar(x=['Safe Expected Int', 'At-Risk Expected Int'], y=[t_act_int, t_ovr_int], color=['Safe Expected Int', 'At-Risk Expected Int'], color_discrete_sequence=['#2ca02c', '#ff7f0e'])
            fig13.update_layout(showlegend=False, yaxis_title="Uncollected Interest (₹)")
            
            df_t13 = pd.DataFrame({"Interest Type": ["Healthy Expected", "Dangerous Overdue (Phantom)"], "Amount": [format_currency(t_act_int), format_currency(t_ovr_int)]})
            
            render_detailed_block("Analysis 13: Uncollected Interest Liability", "At-Risk Interest", format_currency(t_ovr_int), stat, msg, act,
                "Sum of generated interest on Active vs Overdue loans.",
                "Overdue interest looks great on paper, but if the customer never returns, you take a pure loss.", fig13, df_t13)

            # A14: Metal Exp
            metal_dist = comb_ao.groupby('loan_type')['principal_amount'].sum().reset_index()
            g_exp = metal_dist[metal_dist['loan_type'] == 'Gold']['principal_amount'].sum() if 'Gold' in metal_dist['loan_type'].values else 0
            g_pct = (g_exp / (t_act_p + t_ovr_p) * 100) if (t_act_p + t_ovr_p) > 0 else 0
            if g_pct >= 70: stat, msg, act = "GOOD", "Your safe is backed by stable Gold.", "Gold holds value. You are well protected."
            else: stat, msg, act = "AVG", "High Silver exposure. Silver fluctuates wildly.", "Reduce Loan-to-Value (LTV) limits on new silver pledges to protect against price drops."

            fig14 = px.pie(metal_dist, names='loan_type', values='principal_amount', hole=0.5, color='loan_type', color_discrete_map={'Gold': '#FFD700', 'Silver': '#C0C0C0'})
            
            df_t14 = metal_dist.copy()
            df_t14['principal_amount'] = df_t14['principal_amount'].apply(format_currency)
            df_t14.columns = ["Collateral Type", "Capital Secured"]
            
            render_detailed_block("Analysis 14: Capital Metal Exposure", "Gold Exposure %", f"{g_pct:.1f}%", stat, msg, act,
                "(Total Principal Secured by Gold ÷ Total Active Principal) × 100",
                "Shows what physical metal is securing your live capital.", fig14, df_t14)

            # A15: Flight Risk
            c_act = len(comb_ao[comb_ao['state'] == 'Active'])
            c_ovr = len(comb_ao[comb_ao['state'] == 'Overdue'])
            if c_ovr < (c_act * 0.2): stat, msg, act = "GOOD", "High customer retention.", "Customers are returning for their items."
            elif c_ovr < (c_act * 0.5): stat, msg, act = "AVG", "Customers are going missing.", "Send a WhatsApp broadcast offering a minor discount if they renew today."
            else: stat, msg, act = "BAD", "Mass customer exodus.", "Competitors are stealing your customers. Call them personally."

            fig15 = px.bar(x=['Active Pledges', 'Overdue Pledges'], y=[c_act, c_ovr], color=['Active Pledges', 'Overdue Pledges'], color_discrete_sequence=['#1f77b4', '#d62728'], text_auto=True)
            fig15.update_layout(showlegend=False, yaxis_title="Number of Loans")
            
            df_t15 = pd.DataFrame({"Status": ["Live Customers", "Missing Customers (Overdue)"], "Count": [c_act, c_ovr]})
            
            render_detailed_block("Analysis 15: Flight Risk Warning (Count Density)", "Missing Pledges", str(c_ovr), stat, msg, act,
                "Total Count of Active Loans vs Total Count of Overdue Loans.",
                "A high count of overdue loans means a mass exodus of customers who are silently defaulting.", fig15, df_t15)
        else: st.warning("No Active/Overdue snapshot data available for Risk Analysis.")

    # ==========================================
    # TAB 5: PORTFOLIO & OPERATIONS (16-20)
    # ==========================================
    with t_ops:
        # A16: Vol Dominance
        vol_df = pd.DataFrame({"Portfolio": ["Normal", "Big", "Box"], "Volume": [merged_daily['total_loan_amount_norm'].sum(), merged_daily['total_loan_amount_big'].sum(), merged_daily['total_loan_amount_box'].sum()]})
        biggest_vol = vol_df.loc[vol_df['Volume'].idxmax()]['Portfolio'] if not vol_df.empty else "None"
        stat, msg, act = "INFO", f"{biggest_vol} drives your cash flow.", f"Since {biggest_vol} moves the most money, ensure physical shop security matches this risk."

        fig16 = px.pie(vol_df, names="Portfolio", values="Volume", hole=0.4, color="Portfolio", color_discrete_map={'Normal': '#1f77b4', 'Big': '#ff7f0e', 'Box': '#9467bd'})
        
        df_t16 = vol_df.copy()
        df_t16['Volume'] = df_t16['Volume'].apply(format_currency)
        df_t16.columns = ["Portfolio", "Money Moved"]
        
        render_detailed_block("Analysis 16: System Volume Dominance", "Total Processed", format_currency(vol_df['Volume'].sum()), stat, msg, act,
            "Total Dispersal grouped by Portfolio.",
            "Shows exactly which portfolio is moving the most physical cash out the door.", fig16, df_t16)

        # A17: ROI Yield
        y_n = (merged_daily['total_overall_interest_norm'].sum() / merged_daily['total_loan_amount_norm'].sum() * 100) if merged_daily['total_loan_amount_norm'].sum() > 0 else 0
        y_b = (merged_daily['total_overall_interest_big'].sum() / merged_daily['total_loan_amount_big'].sum() * 100) if merged_daily['total_loan_amount_big'].sum() > 0 else 0
        y_bx = (merged_daily['total_overall_interest_box'].sum() / merged_daily['total_loan_amount_box'].sum() * 100) if merged_daily['total_loan_amount_box'].sum() > 0 else 0
        
        if y_n >= y_b: stat, msg, act = "GOOD", "Normal loans properly yield the highest %.", "Small loans carry higher risk and should mathematically pay higher %."
        else: stat, msg, act = "AVG", "Big loans yield higher % than Normal.", "You are overcharging VIPs or undercharging small customers. Adjust rates."

        fig17 = px.bar(x=['Normal', 'Big', 'Box'], y=[y_n, y_b, y_bx], color=['Normal', 'Big', 'Box'], color_discrete_map={'Normal': '#1f77b4', 'Big': '#ff7f0e', 'Box': '#9467bd'}, text_auto='.2s')
        fig17.update_layout(showlegend=False, yaxis_title="Interest ROI %")
        
        df_t17 = pd.DataFrame({"Portfolio": ["Normal", "Big", "Box"], "Return on Investment (%)": [f"{y_n:.2f}%", f"{y_b:.2f}%", f"{y_bx:.2f}%"]})
        
        render_detailed_block("Analysis 17: Pure ROI Yield by Portfolio", "Normal ROI %", f"{y_n:.1f}%", stat, msg, act,
            "(Total Interest Collected ÷ Total Dispersed) × 100 for each portfolio.",
            "Calculates the exact Return on Investment percentage for each specific portfolio independently.", fig17, df_t17)

        # A18: Outer Strat
        if not comb_out_cl.empty:
            out_prof_dist = comb_out_cl.groupby('Portfolio')['profit_amount'].sum().reset_index()
            out_prof_dist['profit_amount'] = out_prof_dist['profit_amount'].clip(lower=0)
            best_out = out_prof_dist.loc[out_prof_dist['profit_amount'].idxmax()]['Portfolio'] if not out_prof_dist.empty else "None"
            stat, msg, act = "INFO", f"{best_out} generates the most arbitrage profit.", f"Double down on pledging {best_out} items outside. Stop pledging unprofitable portfolios."

            fig18 = px.pie(out_prof_dist, names='Portfolio', values='profit_amount', color='Portfolio', color_discrete_map={'Normal': '#1f77b4', 'Big': '#ff7f0e', 'Box': '#9467bd'})
            
            df_t18 = out_prof_dist.copy()
            df_t18['profit_amount'] = df_t18['profit_amount'].apply(format_currency)
            df_t18.columns = ["Portfolio", "Net Profit from Outside Pledging"]
            
            render_detailed_block("Analysis 18: Outer Profit Generation Strategy", "Top Outer Earner", best_out, stat, msg, act,
                "Sum of Net Outer Profit grouped by Portfolio.",
                "Visualizes which tier of loans is successfully generating the most profit through external re-pledging.", fig18, df_t18)
        else: st.warning("No closed outer loans for Analysis 18.")

        # A19: Weekday
        merged_daily['Day'] = merged_daily['date'].dt.day_name()
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        merged_daily['Day'] = pd.Categorical(merged_daily['Day'], categories=days_order, ordered=True)
        heat_df = merged_daily.groupby('Day')['Grand_Dispersed'].sum().reset_index()
        busiest_day = heat_df.loc[heat_df['Grand_Dispersed'].idxmax()]['Day'] if not heat_df.empty and heat_df['Grand_Dispersed'].max() > 0 else "None"
        stat, msg, act = "INFO", f"{busiest_day} is your highest volume day.", f"Never schedule staff time-off on {busiest_day}. Withdraw extra bank cash the day before."

        fig19 = px.bar(heat_df, x='Day', y='Grand_Dispersed', color='Grand_Dispersed', color_continuous_scale="Purples")
        
        df_t19 = heat_df.copy()
        df_t19['Grand_Dispersed'] = df_t19['Grand_Dispersed'].apply(format_currency)
        df_t19.columns = ["Day of the Week", "Total Business Volume"]
        
        render_detailed_block("Analysis 19: Weekday Operational Intensity Heatmap", "Busiest Day", str(busiest_day), stat, msg, act,
            "Sum of all dispersals aggregated by the Day of the Week.",
            "Aggregates historical data to definitively prove which day requires the most cash and manpower.", fig19, df_t19)

        # A20: Volatility
        merged_daily['Volatility'] = merged_daily['Grand_Dispersed'].pct_change().fillna(0) * 100
        max_spike = merged_daily['Volatility'].max() if not merged_daily.empty else 0
        if max_spike < 150: stat, msg, act = "GOOD", "Smooth and predictable business operations.", "Cash flow is easy to manage right now."
        elif max_spike < 300: stat, msg, act = "AVG", "Moderate daily spikes in walk-ins.", "Keep extra reserve cash on hand for sudden VIP visits."
        else: stat, msg, act = "BAD", "Highly erratic walk-in volume.", "Your business is relying on random massive hits. Run daily marketing to stabilize traffic."

        fig20 = px.line(merged_daily, x='date', y='Volatility', markers=True, color_discrete_sequence=['#ff7f0e'])
        fig20.add_hline(y=0, line_color="black")
        fig20.update_layout(yaxis_title="Change vs Previous Day (%)")
        
        df_t20 = merged_daily[['date', 'Volatility']].copy()
        df_t20['date'] = df_t20['date'].dt.strftime('%d %b %Y')
        df_t20['Percentage Change'] = df_t20['Volatility'].apply(lambda x: f"{x:.1f}%")
        df_t20 = df_t20[['date', 'Percentage Change']]
        
        render_detailed_block("Analysis 20: Dispersal Growth Volatility", "Max Daily Spike", f"{max_spike:.0f}%", stat, msg, act,
            "Percentage Change in Dispersals between Day(X) and Day(X-1).",
            "Measures stability. Extreme spikes mean your business is highly unpredictable.", fig20, df_t20)

    # =====================================================================
    # TAB 6: TERRITORY & LOCATION
    # =====================================================================
    with t_loc:
        if filtered_raw.empty:
            st.warning("No location data for this period.")
        else:
            loc_df = filtered_raw.groupby(['post', 'address', 'district', 'pincode']).agg(
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
    # TAB 7: INVENTORY & WEIGHT INTELLIGENCE
    # =====================================================================
    with t_inv:
        st.markdown("### ⚖️ Inventory & Weight Intelligence")
        item_records = []
        for _, row in filtered_raw.iterrows():
            if pd.notna(row['items']) and str(row['items']).strip() != "":
                try:
                    items_json = json.loads(row['items'])
                    for itm in items_json:
                        w = float(itm.get('weight', 0))
                        item_records.append({
                            'Item_Name': str(itm.get('name', '')).strip().title(),
                            'Weight_g': w,
                            'Qty': int(itm.get('qty', 1)),
                            'Metal': row['item_category'],
                            'Portfolio': row['portfolio'],
                            'Storage': row['Storage'],
                            'Status': row['status']
                        })
                except Exception: 
                    pass
                    
        items_df = pd.DataFrame(item_records)
        
        if items_df.empty:
            st.warning("No item weight data found.")
        else:
            live_items = items_df[items_df['Status'].str.lower().isin(['active', 'overdue'])]
            
            t_gold = live_items[live_items['Metal'] == 'Gold']['Weight_g'].sum()
            t_silver = live_items[live_items['Metal'] == 'Silver']['Weight_g'].sum()
            
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Total Gold Weight", f"{t_gold:,.2f} g")
            i2.metric("Total Silver Weight", f"{t_silver:,.2f} g")
            i3.metric("Items In Shop", live_items[live_items['Storage']=='In Shop']['Qty'].sum())
            i4.metric("Items In Outer Shop", live_items[live_items['Storage']=='Outer Shop']['Qty'].sum())
            
            inv_summary = live_items.groupby(['Metal', 'Portfolio', 'Storage', 'Item_Name']).agg(
                Total_Weight=('Weight_g', 'sum'),
                Mean_Weight=('Weight_g', 'mean'),
                Total_Qty=('Qty', 'sum')
            ).reset_index().sort_values('Total_Weight', ascending=False)
            
            inv_summary['Total_Weight'] = inv_summary['Total_Weight'].round(3)
            inv_summary['Mean_Weight'] = inv_summary['Mean_Weight'].round(3)

            st.write("---")
            st.success("✅ **Inventory Insight:** The breakdown below categorizes your live assets precisely by Metal ➡️ Loan Type ➡️ Storage Location. Use the 'Mean Weight' to easily identify standard ticket sizes for specific collateral.")
            
            c1, c2 = st.columns(2)
            with c1:
                fig_sun = px.sunburst(
                    inv_summary, 
                    path=['Metal', 'Portfolio', 'Storage'], 
                    values='Total_Weight', 
                    title="Weight Distribution Hierarchy",
                    color='Metal',
                    color_discrete_map={"Gold": "#FFD700", "Silver": "#C0C0C0"}
                )
                st.plotly_chart(fig_sun, use_container_width=True)
            with c2:
                risk_df = live_items.groupby(['Metal', 'Storage'])['Weight_g'].sum().reset_index()
                fig_bar = px.bar(
                    risk_df, 
                    x="Metal", 
                    y="Weight_g", 
                    color="Storage", 
                    barmode="group", 
                    title="Physical Risk (In Shop vs Outer)",
                    color_discrete_map={"In Shop": "#2ca02c", "Outer Shop": "#d62728"}
                )
                st.plotly_chart(fig_bar, use_container_width=True)
                
            st.markdown("#### 🪙 GOLD INVENTORY")
            st.dataframe(inv_summary[inv_summary['Metal'] == 'Gold'].drop(columns=['Metal']), hide_index=True, use_container_width=True)
            st.markdown("#### 🥈 SILVER INVENTORY")
            st.dataframe(inv_summary[inv_summary['Metal'] == 'Silver'].drop(columns=['Metal']), hide_index=True, use_container_width=True)

    # =====================================================================
    # TAB 8: FINAL TALLY ANALYSIS
    # =====================================================================
    with t_tally:
        st.markdown("### 📊 Final Tally Analysis")
        if tally_filt.empty:
            st.warning("No Final Tally data available for this period.")
        else:
            tally_filt['Discrepancy'] = tally_filt['final_tally_amount'] - tally_filt['capital_by_owner']
            avg_sys = tally_filt['capital_by_system'].mean()
            avg_own = tally_filt['capital_by_owner'].mean()
            total_sales = tally_filt['total_sales'].sum()
            
            t1, t2, t3 = st.columns(3)
            t1.metric("Avg System Capital", format_currency(avg_sys))
            t2.metric("Avg Owner Capital", format_currency(avg_own))
            t3.metric("Total Sales Count", f"{total_sales:,.0f}")
            
            st.write("---")
            if tally_filt['Discrepancy'].sum() < 0:
                st.warning(f"⚠️ **Tally Insight:** You have a cumulative shortage of {format_currency(tally_filt['Discrepancy'].sum())} over this period. Monitor daily tallies closely.")
            else:
                st.success(f"✅ **Tally Insight:** Your tallies are balancing well. Net discrepancy is {format_currency(tally_filt['Discrepancy'].sum())}.")
            
            c1, c2 = st.columns(2)
            with c1:
                fig_tally = px.line(
                    tally_filt, 
                    x='tally_date_parsed', 
                    y=['capital_by_system', 'capital_by_owner'], 
                    title="System vs Owner Capital Over Time", 
                    markers=True,
                    color_discrete_map={'capital_by_system': '#1f77b4', 'capital_by_owner': '#2ca02c'}
                )
                st.plotly_chart(fig_tally, use_container_width=True)
            with c2:
                fig_vol = px.bar(
                    tally_filt, 
                    x='tally_date_parsed', 
                    y=['total_new_loan', 'total_closed_loan'], 
                    title="Daily Loan Volume (New vs Closed)", 
                    barmode='group',
                    color_discrete_map={'total_new_loan': '#1f77b4', 'total_closed_loan': '#d62728'}
                )
                st.plotly_chart(fig_vol, use_container_width=True)
                
            st.markdown("#### 📋 Final Tally Ledger")
            disp_cols = ['tally_date', 'total_new_loan', 'total_closed_loan', 'total_outer_loan', 'capital_by_system', 'capital_by_owner', 'final_tally_amount', 'Discrepancy']
            # FIX: Sort the entire dataframe FIRST, then slice the display columns
            st.dataframe(tally_filt.sort_values('tally_date_parsed', ascending=False)[disp_cols], hide_index=True, use_container_width=True)


    # ==========================================
    # FINAL LEDGER
    # ==========================================
    with t_ledger:
        st.markdown("### 🏢 Ultimate Master Profit & Loss (P&L) Ledger")
        st.success("📖 **How to read this:** This perfectly consolidates Normal, Big, Box Dispersals, and all Outer activity month by month. It is your ultimate accounting truth.")
        
        merged_daily['Month-Year'] = merged_daily['date'].dt.to_period('M')
        m_master = merged_daily.groupby('Month-Year').agg(
            Norm_Disp=('total_loan_amount_norm', 'sum'), Big_Disp=('total_loan_amount_big', 'sum'), Box_Disp=('total_loan_amount_box', 'sum'),
            Norm_Int=('total_overall_interest_norm', 'sum'), Big_Int=('total_overall_interest_big', 'sum'), Box_Int=('total_overall_interest_box', 'sum'),
            Norm_Paper=('total_paper_norm', 'sum'), Big_Paper=('total_paper_big', 'sum'), Box_Paper=('total_paper_box', 'sum')
        ).reset_index()
        
        m_master['Grand_Total_Dispersed'] = m_master['Norm_Disp'] + m_master['Big_Disp'] + m_master['Box_Disp']
        m_master['Grand_Total_Interest'] = m_master['Norm_Int'] + m_master['Big_Int'] + m_master['Box_Int']
        m_master['Grand_Total_Paper'] = m_master['Grand_Total_Paper'] = m_master['Norm_Paper'] + m_master['Big_Paper'] + m_master['Box_Paper']

        if not comb_out_cl.empty:
            comb_out_cl['Month-Year'] = comb_out_cl['date'].dt.to_period('M')
            m_out = comb_out_cl.groupby('Month-Year').agg(Total_Outer_Profit=('profit_amount', 'sum'), Total_Doc_Exp=('doc_charge', 'sum')).reset_index()
            m_master = pd.merge(m_master, m_out, on='Month-Year', how='left').fillna(0)
        else:
            m_master['Total_Outer_Profit'], m_master['Total_Doc_Exp'] = 0, 0
        
        m_master['FINAL_NET_REVENUE'] = m_master['Grand_Total_Interest'] + m_master['Total_Outer_Profit'] + m_master['Grand_Total_Paper'] - m_master['Total_Doc_Exp']
        m_master['Revenue Growth %'] = (m_master['FINAL_NET_REVENUE'].pct_change() * 100).fillna(0).round(2).astype(str) + '%'

        disp_master = m_master[['Month-Year', 'Grand_Total_Dispersed', 'Grand_Total_Interest', 'Total_Outer_Profit', 'Grand_Total_Paper', 'Total_Doc_Exp', 'FINAL_NET_REVENUE', 'Revenue Growth %']].copy()
        disp_master['Month-Year'] = disp_master['Month-Year'].dt.strftime('%b %Y')
            
        for col in ['Grand_Total_Dispersed', 'Grand_Total_Interest', 'Total_Outer_Profit', 'Grand_Total_Paper', 'Total_Doc_Exp', 'FINAL_NET_REVENUE']:
            disp_master[col] = disp_master[col].apply(format_currency)
            
        disp_master = disp_master.rename(columns={
            'Month-Year': 'Timeline', 'Grand_Total_Dispersed': 'Total Dispersal [OUT]', 'Grand_Total_Interest': 'Total Interest [IN]',
            'Total_Outer_Profit': 'Total Outer Profit [IN]', 'Grand_Total_Paper': 'Total Paper Fees [IN]',
            'Total_Doc_Exp': 'Total Doc Fees [OUT]', 'FINAL_NET_REVENUE': '🔥 FINAL NET REVENUE [=]'
        })
        
        st.dataframe(disp_master, hide_index=True, use_container_width=True)
        st.download_button(label="📥 Download Ultimate P&L Report as CSV", data=disp_master.to_csv(index=False).encode('utf-8'), file_name='ultimate_master_business_report.csv', mime='text/csv')

    # ==========================================
    # FINAL GROWTH REPORT & PRINT
    # ==========================================
    with t_summary:
        st.markdown("<h2 style='text-align: center; color: #1f77b4;'>🏆 Final Executive Growth Report</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-size: 18px;'>This report calculates the momentum of your business by splitting your selected date range in half and comparing the results.</p>", unsafe_allow_html=True)
        st.write("---")

        # --- 1. Business Momentum (Growth Calculation) ---
        days_total = (ed - sd).days + 1
        if days_total >= 4: 
            mid_point = sd + datetime.timedelta(days=days_total // 2)
            p1_df = merged_daily[merged_daily['date'] < pd.to_datetime(mid_point)]
            p2_df = merged_daily[merged_daily['date'] >= pd.to_datetime(mid_point)]

            p1_rev = p1_df['Daily_Net'].sum()
            p2_rev = p2_df['Daily_Net'].sum()
            growth_pct = ((p2_rev - p1_rev) / abs(p1_rev) * 100) if p1_rev != 0 else 0
        else:
            p1_rev, p2_rev, growth_pct = 0, 0, 0
            st.warning("Please select a date range of at least 4 days to calculate growth momentum.")

        c_g1, c_g2, c_g3 = st.columns(3)
        c_g1.metric("1st Half Profit", format_currency(p1_rev))
        c_g2.metric("2nd Half Profit", format_currency(p2_rev))
        c_g3.metric("📈 Profit Growth Momentum", f"{growth_pct:+.1f}%", delta=f"{growth_pct:+.1f}%")

        # --- 2. The Big 3 Health Scorecard ---
        st.markdown("### 🏥 The 'Big 3' Health Scorecard")
        sc1, sc2, sc3 = st.columns(3)
        
        with sc1:
            if t_net_rev > 0: st.success(f"💰 **Highly Profitable**\n\nGenerated {format_currency(t_net_rev)}")
            else: st.error(f"⚠️ **Operating at a Loss**\n\nLost {format_currency(t_net_rev)}")
            
        with sc2:
            if lev_ratio < 40: st.success(f"🛡️ **Safe Debt Levels**\n\nOnly {lev_ratio:.1f}% Leverage")
            else: st.error(f"🚨 **Dangerous Debt**\n\nHigh Leverage at {lev_ratio:.1f}%")
            
        with sc3:
            if tox_ratio < 15: st.success(f"💎 **Healthy Assets**\n\nLow Toxic Debt ({tox_ratio:.1f}%)")
            else: st.error(f"☠️ **Toxic Assets**\n\nHigh Toxic Debt ({tox_ratio:.1f}%)")

        st.write("---")

        # --- 3. THE ULTIMATE VERDICT ---
        st.markdown("### ⚖️ The Ultimate Shop Verdict")
        
        if growth_pct >= 5 and tox_ratio < 15 and lev_ratio < 50:
            verdict = "🌟 **EXCELLENT: Your business is Growing Safely!** Revenue is increasing, your debt is under control, and you have very little dead money in the market. Keep doing exactly what you are doing!"
            st.success(verdict)
        elif growth_pct >= 5 and (tox_ratio >= 15 or lev_ratio >= 50):
            verdict = "⚠️ **GROWING BUT RISKY:** Your revenue is going up, which is great! However, your underlying risk (either high outside debt or high uncollected toxic loans) is dangerous. Focus entirely on collecting old debts this month instead of giving out new loans."
            st.warning(verdict)
        elif growth_pct < -5:
            verdict = "🚨 **DECLINING:** Your revenue dropped in the second half of this period. Check the 'Operations' tab to see if your cash flow is erratic, or check if Outer Shop Document fees are eating all your profit."
            st.error(verdict)
        else:
            verdict = "⚖️ **STABLE:** Your business is maintaining its current level. It is neither growing rapidly nor shrinking. Look at cross-selling (like taking in more Silver or Box loans) to spark new growth."
            st.info(verdict)

        # --- 4. PRINT BUTTON ---
        st.write("---")
        components.html(
            """
            <div style="text-align: center; margin-top: 20px;">
                <button onclick="window.print()" style="padding: 12px 24px; font-size: 18px; font-weight: bold; background-color: #007BFF; color: white; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0px 4px 6px rgba(0,0,0,0.1);">
                    🖨️ Print Final Executive Report
                </button>
                <p style="font-family: sans-serif; font-size: 12px; color: gray; margin-top: 10px;">(Clicking this will open your browser's Print/Save as PDF menu)</p>
            </div>
            """, height=100
        )