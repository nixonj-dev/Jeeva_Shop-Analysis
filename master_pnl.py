import streamlit as st
import pandas as pd
import sqlite3
import datetime
import plotly.express as px

# --- CONSTANTS FOR OPERATIONAL TRANSACTIONS ---
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

def fetch_daily_credits_and_debits():
    """
    Fetches daily operational credits (income) and debits (expenses) 
    directly from capital_transactions and GpayAccount matching 
    the exact classification logic in daily_profit_analysis.py.
    """
    conn = sqlite3.connect('users.db')
    
    # 1. Build Category Hierarchy
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

    daily_totals = {}

    # 2. Process Transactions from capital_transactions and GpayAccount
    def process_transactions(t_root, query):
        try:
            rows = conn.execute(query).fetchall()
            for r in rows:
                d_str, raw_desc, t_type, amt = r
                try:
                    dt = datetime.datetime.strptime(d_str, "%d/%m/%Y").date()

                    # Clean Description
                    c_desc = raw_desc.strip()
                    for pfx in PREFIXES:
                        if c_desc.lower().startswith(pfx.lower()):
                            c_desc = c_desc[len(pfx):].strip()
                            break
                    if not c_desc: continue

                    # Split Main Category
                    if " - " in c_desc:
                        main_c, _ = c_desc.split(" - ", 1)
                    else:
                        main_c = c_desc
                    main_c = main_c.strip()

                    # Only process valid operational categories
                    if main_c in hierarchy[t_root]['mains']:
                        is_credit = t_type in ['Credit', 'Incoming']
                        credit = float(amt) if is_credit else 0.0
                        debit = float(amt) if not is_credit else 0.0

                        if dt not in daily_totals:
                            daily_totals[dt] = {'expense_credit': 0.0, 'expense_debit': 0.0}
                        
                        daily_totals[dt]['expense_credit'] += credit
                        daily_totals[dt]['expense_debit'] += debit
                except Exception:
                    continue
        except Exception:
            pass

    process_transactions('Cash', "SELECT transaction_date, description, transaction_type, amount FROM capital_transactions")
    process_transactions('GPay', "SELECT transaction_date, description, transaction_type, amount FROM GpayAccount")
    
    conn.close()

    df_exp = pd.DataFrame.from_dict(daily_totals, orient='index')
    if not df_exp.empty:
        df_exp.index.name = 'date'
        df_exp = df_exp.reset_index()
    else:
        df_exp = pd.DataFrame(columns=['date', 'expense_credit', 'expense_debit'])
        
    return df_exp

def process_shop_data(df, category_name):
    """Extracts date, interest, and paper charges for a loan category."""
    if df is None or df.empty or 'date' not in df.columns:
        return pd.DataFrame(columns=['date', f'{category_name}_interest', f'{category_name}_paper', f'{category_name}_income'])
    
    temp = df.copy()
    temp['date'] = pd.to_datetime(temp['date']).dt.date
    
    int_col = 'total_overall_interest' if 'total_overall_interest' in temp.columns else 'calculated_interest'
    paper_col = 'total_paper' if 'total_paper' in temp.columns else 'paper_amount'
    
    temp[f'{category_name}_interest'] = temp[int_col] if int_col in temp.columns else 0.0
    temp[f'{category_name}_paper'] = temp[paper_col] if paper_col in temp.columns else 0.0
    temp[f'{category_name}_income'] = temp[f'{category_name}_interest'] + temp[f'{category_name}_paper']
    
    return temp.groupby('date')[[f'{category_name}_interest', f'{category_name}_paper', f'{category_name}_income']].sum().reset_index()

def process_outer_data(df, category_name):
    """Extracts date, outer interest paid, and doc charges for a loan category."""
    if df is None or df.empty or 'date' not in df.columns:
        return pd.DataFrame(columns=['date', f'{category_name}_outer_interest', f'{category_name}_outer_doc', f'{category_name}_outer_expense'])
    
    temp = df.copy()
    temp['date'] = pd.to_datetime(temp['date']).dt.date
    
    o_int_col = 'outer_interest' if 'outer_interest' in temp.columns else 'interest'
    o_doc_col = 'doc_charge' if 'doc_charge' in temp.columns else 'doc_charge_paid'
    
    temp[f'{category_name}_outer_interest'] = temp[o_int_col] if o_int_col in temp.columns else 0.0
    temp[f'{category_name}_outer_doc'] = temp[o_doc_col] if o_doc_col in temp.columns else 0.0
    temp[f'{category_name}_outer_expense'] = temp[f'{category_name}_outer_interest'] + temp[f'{category_name}_outer_doc']
    
    return temp.groupby('date')[[f'{category_name}_outer_interest', f'{category_name}_outer_doc', f'{category_name}_outer_expense']].sum().reset_index()

def render(n_data, n_out_cl, b_data, b_out_cl, box_data, box_out_cl):
    """
    Renders Master Profit & Loss page including calculated Daily Operational Credits and Debits.
    """
    st.subheader("🏆 Master Profit & Loss Analysis")
    st.info("💡 Complete financial view tracking Income, Expenses, and Net Profit across Normal, Big, and Box loan categories, plus Daily Operational Cash/GPay Credits & Debits.")

    # -------------------------------------------------------------------------
    # 1. PROCESS SHOP INCOMES & OUTER EXPENSES BY CATEGORY
    # -------------------------------------------------------------------------
    normal_shop = process_shop_data(n_data, 'normal')
    big_shop = process_shop_data(b_data, 'big')
    box_shop = process_shop_data(box_data, 'box')
    
    normal_outer = process_outer_data(n_out_cl, 'normal')
    big_outer = process_outer_data(b_out_cl, 'big')
    box_outer = process_outer_data(box_out_cl, 'box')

    # -------------------------------------------------------------------------
    # 2. FETCH OPERATIONAL CREDITS & DEBITS (CASH & GPAY)
    # -------------------------------------------------------------------------
    daily_exp = fetch_daily_credits_and_debits()

    # -------------------------------------------------------------------------
    # 3. MERGE ALL DATASETS INTO MASTER DATAFRAME
    # -------------------------------------------------------------------------
    dfs_to_merge = [normal_shop, big_shop, box_shop, normal_outer, big_outer, box_outer, daily_exp]
    
    master_pnl = None
    for df in dfs_to_merge:
        if master_pnl is None:
            master_pnl = df
        else:
            master_pnl = pd.merge(master_pnl, df, on='date', how='outer')

    if master_pnl is None or master_pnl.empty:
        st.warning("No financial records were found.")
        return

    master_pnl = master_pnl.fillna(0.0).sort_values('date').reset_index(drop=True)

    # Formula Calculations
    master_pnl['total_shop_income'] = master_pnl['normal_income'] + master_pnl['big_income'] + master_pnl['box_income']
    master_pnl['total_income'] = master_pnl['total_shop_income'] + master_pnl['expense_credit']
    
    master_pnl['total_outer_expense'] = master_pnl['normal_outer_expense'] + master_pnl['big_outer_expense'] + master_pnl['box_outer_expense']
    master_pnl['total_expenses'] = master_pnl['total_outer_expense'] + master_pnl['expense_debit']
    
    master_pnl['net_profit'] = master_pnl['total_income'] - master_pnl['total_expenses']

    # -------------------------------------------------------------------------
    # 4. DATE RANGE FILTER
    # -------------------------------------------------------------------------
    st.markdown("### 📅 Filter Date Range")
    min_date = master_pnl['date'].min()
    max_date = master_pnl['date'].max()

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        from_date = st.date_input("From Date", value=min_date, min_value=min_date, max_value=max_date)
    with col_d2:
        to_date = st.date_input("To Date", value=max_date, min_value=min_date, max_value=max_date)

    if from_date > to_date:
        st.error("Error: 'From Date' cannot be later than 'To Date'.")
        return

    filtered_pnl = master_pnl[(master_pnl['date'] >= from_date) & (master_pnl['date'] <= to_date)].copy()
    filtered_pnl['cumulative_profit'] = filtered_pnl['net_profit'].cumsum()
    filtered_pnl['month_year'] = pd.to_datetime(filtered_pnl['date']).dt.to_period('M').astype(str)

    if filtered_pnl.empty:
        st.warning("No financial transactions found within the selected date range.")
        return

    # -------------------------------------------------------------------------
    # 5. OVERALL KPI METRICS
    # -------------------------------------------------------------------------
    st.write("---")
    tot_inc = filtered_pnl['total_income'].sum()
    tot_exp = filtered_pnl['total_expenses'].sum()
    net_pnl = filtered_pnl['net_profit'].sum()
    margin = (net_pnl / tot_inc * 100) if tot_inc > 0 else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Income", f"₹ {tot_inc:,.2f}")
    k2.metric("Total Expenses", f"₹ {tot_exp:,.2f}")
    k3.metric("Net Profit / Loss", f"₹ {net_pnl:,.2f}", delta=f"{net_pnl:,.2f}")
    k4.metric("Profit Margin", f"{margin:.2f}%")

    # -------------------------------------------------------------------------
    # 6. CATEGORY SUB-AMOUNTS BREAKDOWN
    # -------------------------------------------------------------------------
    st.write("---")
    st.markdown("### 🏷️ Category Breakdown (Sub-Totals)")

    c_inc, c_exp = st.columns(2)

    with c_inc:
        st.markdown("#### 🟢 Income Sub-totals")
        inc_norm = filtered_pnl['normal_income'].sum()
        inc_big = filtered_pnl['big_income'].sum()
        inc_box = filtered_pnl['box_income'].sum()
        inc_other = filtered_pnl['expense_credit'].sum()

        st.write(f"• **Normal Loans Income**: ₹ {inc_norm:,.2f} *(Interest: ₹{filtered_pnl['normal_interest'].sum():,.2f} | Paper: ₹{filtered_pnl['normal_paper'].sum():,.2f})*")
        st.write(f"• **Big Loans Income**: ₹ {inc_big:,.2f} *(Interest: ₹{filtered_pnl['big_interest'].sum():,.2f} | Paper: ₹{filtered_pnl['big_paper'].sum():,.2f})*")
        st.write(f"• **Box Loans Income**: ₹ {inc_box:,.2f} *(Interest: ₹{filtered_pnl['box_interest'].sum():,.2f} | Paper: ₹{filtered_pnl['box_paper'].sum():,.2f})*")
        st.write(f"• **Other Daily Credits**: ₹ {inc_other:,.2f}")
        st.markdown(f"**Total Income**: **₹ {tot_inc:,.2f}**")

    with c_exp:
        st.markdown("#### 🔴 Expense Sub-totals")
        exp_norm = filtered_pnl['normal_outer_expense'].sum()
        exp_big = filtered_pnl['big_outer_expense'].sum()
        exp_box = filtered_pnl['box_outer_expense'].sum()
        exp_other = filtered_pnl['expense_debit'].sum()

        st.write(f"• **Normal Outer Expenses**: ₹ {exp_norm:,.2f} *(Interest Paid: ₹{filtered_pnl['normal_outer_interest'].sum():,.2f} | Doc Charge: ₹{filtered_pnl['normal_outer_doc'].sum():,.2f})*")
        st.write(f"• **Big Outer Expenses**: ₹ {exp_big:,.2f} *(Interest Paid: ₹{filtered_pnl['big_outer_interest'].sum():,.2f} | Doc Charge: ₹{filtered_pnl['big_outer_doc'].sum():,.2f})*")
        st.write(f"• **Box Outer Expenses**: ₹ {exp_box:,.2f} *(Interest Paid: ₹{filtered_pnl['box_outer_interest'].sum():,.2f} | Doc Charge: ₹{filtered_pnl['box_outer_doc'].sum():,.2f})*")
        st.write(f"• **Other Daily Debits**: ₹ {exp_other:,.2f}")
        st.markdown(f"**Total Expenses**: **₹ {tot_exp:,.2f}**")

    # -------------------------------------------------------------------------
    # 7. MONTHLY SUMMARY BREAKDOWN
    # -------------------------------------------------------------------------
    st.write("---")
    st.markdown("### 📅 Monthly Summary Breakdown")
    
    monthly_summary = filtered_pnl.groupby('month_year').agg(
        Normal_Income=('normal_income', 'sum'),
        Big_Income=('big_income', 'sum'),
        Box_Income=('box_income', 'sum'),
        Other_Daily_Credits=('expense_credit', 'sum'),
        Monthly_Total_Income=('total_income', 'sum'),
        Normal_Outer_Exp=('normal_outer_expense', 'sum'),
        Big_Outer_Exp=('big_outer_expense', 'sum'),
        Box_Outer_Exp=('box_outer_expense', 'sum'),
        Other_Daily_Debits=('expense_debit', 'sum'),
        Monthly_Total_Expenses=('total_expenses', 'sum'),
        Monthly_Net_Profit=('net_profit', 'sum')
    ).reset_index()

    st.dataframe(monthly_summary, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # 8. VISUAL ANALYTICS
    # -------------------------------------------------------------------------
    st.write("---")
    st.markdown("### 📊 Visual Analytics")

    fig1 = px.bar(
        monthly_summary, x='month_year', 
        y=['Normal_Income', 'Big_Income', 'Box_Income', 'Other_Daily_Credits'],
        title="Monthly Income Sub-totals by Category",
        labels={'value': 'Amount (₹)', 'variable': 'Income Category'},
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.bar(
        monthly_summary, x='month_year', 
        y=['Normal_Outer_Exp', 'Big_Outer_Exp', 'Box_Outer_Exp', 'Other_Daily_Debits'],
        title="Monthly Expense Sub-totals by Category",
        labels={'value': 'Amount (₹)', 'variable': 'Expense Category'},
        color_discrete_sequence=px.colors.qualitative.Pastel1
    )
    st.plotly_chart(fig2, use_container_width=True)
    