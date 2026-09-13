import streamlit as st
import sqlite3
import pandas as pd
import json
import datetime
import math
from calendar import monthrange
import normal_loan_analysis
import big_loan_analysis # <-- Added import for Big Loan Analysis
import master_final_report
import unique_customer_analysis
import box_loan_analysis
import final_tally_analysis
import daily_profit_analysis
import master_profit_loss

st.set_page_config(page_title="Loan Business Dashboard", layout="wide")

def get_latest_global_settings():
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='global_settings'")
        if cursor.fetchone():
            # FIX: Fetch loan_close_settings instead of loan_settings
            cursor.execute("SELECT setting_value FROM global_settings WHERE setting_key='loan_close_settings'")
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
    except Exception as e:
        pass
    finally:
        if 'conn' in locals(): conn.close()
    
    return {} # Return empty dict to rely on safe fallbacks in calculation

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "":
            return 0.0
        return float(val)
    except Exception:
        return 0.0

def calculate_exact_months(loan_date, end_date):
    if end_date < loan_date: 
        return 0.0

    months = (end_date.year - loan_date.year) * 12 + (end_date.month - loan_date.month)
    anniversary_day = loan_date.day
    try:
        this_month_anniversary = end_date.replace(day=anniversary_day)
    except ValueError:
        this_month_anniversary = end_date.replace(day=monthrange(end_date.year, end_date.month)[1])

    if end_date < this_month_anniversary:
        months -= 1

    last_anniversary_month = loan_date.month + months
    last_anniversary_year = loan_date.year + (last_anniversary_month - 1) // 12
    last_anniversary_month = (last_anniversary_month - 1) % 12 + 1

    try:
        last_anniversary_date = datetime.date(last_anniversary_year, last_anniversary_month, loan_date.day)
    except ValueError:
        last_anniversary_date = datetime.date(last_anniversary_year, last_anniversary_month, monthrange(last_anniversary_year, last_anniversary_month)[1])

    days_into_current_month = (end_date - last_anniversary_date).days

    fraction = 0.0
    if days_into_current_month > 15:
        fraction = 1.0
    elif days_into_current_month >= 1:
        fraction = 0.5

    return float(months + fraction)

def calculate_live_interest(row, settings, loan_type, parsed_loan_date, loan_category="regular"):
    try:
        today = datetime.date.today()
        total_months = calculate_exact_months(parsed_loan_date, today)
        
        # 1. Try to get the frozen historical rates from the loan row first
        active_settings = settings
        applied_rates_str = row.get('applied_rates')
        if pd.notna(applied_rates_str) and str(applied_rates_str).strip() != "":
            try:
                snapshot = json.loads(applied_rates_str)
                if "close_settings" in snapshot and snapshot["close_settings"]:
                    active_settings = snapshot["close_settings"]
            except Exception:
                pass
                
        # Helper to safely grab prefixed settings, falling back to generic ones
        def get_rate(key, fallback):
            val = active_settings.get(f"{loan_category}_{key}")
            if val is None and loan_category == "regular": 
                val = active_settings.get(key)
            return safe_float(val) if val is not None else fallback

        threshold = get_rate("close_penalty_threshold_months", 18)
        
        if loan_type == 'gold':
            normal_rate = get_rate("close_gold_normal_rate", 1.75) / 100.0
            penalty_rate = get_rate("close_gold_penalty_rate", 2.0) / 100.0
        else:
            normal_rate = get_rate("close_silver_normal_rate", 3.0) / 100.0
            penalty_rate = get_rate("close_silver_penalty_rate", 3.5) / 100.0
            
        interest_rate = penalty_rate if total_months > threshold else normal_rate
        
        due_month_count = safe_float(row.get('due_month_count'))
        one_mth_paid = safe_float(row.get('one_month_interest'))
        
        final_month_count = (total_months - 1.0 if one_mth_paid > 0 else total_months) - due_month_count
        if final_month_count < 0: 
            final_month_count = 0.0
            
        pres_amt = safe_float(row.get('present_amount'))
        base_amount = pres_amt if pres_amt > 0 else safe_float(row.get('total_given_amount'))
        
        total_int = (base_amount * interest_rate) * final_month_count
        rounded_int = math.ceil(total_int / 10) * 10
        
        return rounded_int, total_months, due_month_count, final_month_count
    except Exception as e:
        return 0, 0.0, 0.0, 0.0

def get_weighted_rate(start_date, end_date, place_name, rates_df):
    if rates_df is None or rates_df.empty: return 0.015
    shop_rates = rates_df[rates_df['place_name'] == place_name].sort_values('effective_date')
    if shop_rates.empty: return 0.015
    
    days = (end_date - start_date).days
    if days <= 0: return 0.015
    
    date_list = [start_date + datetime.timedelta(days=x) for x in range(days)]
    rates_series = []
    for d in date_list:
        applicable = shop_rates[shop_rates['effective_date'] <= d]
        if applicable.empty: rates_series.append(0.015)
        else: rates_series.append(applicable.iloc[-1]['interest_rate'])
    
    return sum(rates_series) / len(rates_series)

def get_current_doc_rate(place_name, rates_df):
    if rates_df is None or rates_df.empty: return 0.0
    shop_rates = rates_df[rates_df['place_name'] == place_name].sort_values('effective_date')
    if shop_rates.empty: return 0.0
    
    today = datetime.date.today()
    applicable = shop_rates[shop_rates['effective_date'] <= today]
    if applicable.empty: return 0.0
    return safe_float(applicable.iloc[-1].get('doc_charge_rate', 0.0))

@st.cache_data
def load_and_process_data(loan_category="normal"): 
    conn = sqlite3.connect('users.db')
    
    try:
        rates_df = pd.read_sql_query("SELECT * FROM outer_loan_rates", conn)
        rates_df['effective_date'] = pd.to_datetime(rates_df['effective_date'], format='%d/%m/%Y').dt.date
    except Exception:
        rates_df = pd.DataFrame()

    # --- 1. PROPERLY ASSIGN TABLES FOR ALL 3 CATEGORIES ---
    if loan_category == "big":
        table_gold = "BigLoanGold"
        table_silver = "BigLoanSilver"
    elif loan_category == "box":
        table_gold = "BoxLoanGold"
        table_silver = "BoxLoanSilver"
    else:
        table_gold = "gold_loan"
        table_silver = "silver_loan"

    # 🟢 FIX 1: Added 'applied_rates' to the end of the SELECT statements
    query_gold = f"SELECT id, form_no, loan_date, closing_date, status, total_given_amount, present_amount, due_month_count, one_month_interest, due_details_all, close_total_interest, paper_amount, applied_rates FROM {table_gold}"
    
    query_silver = f"SELECT id, form_no, loan_date, closing_date, status, total_given_amount, present_amount, due_month_count, one_month_interest, due_details_all, close_total_interest, paper_amount, applied_rates FROM {table_silver}"
    
    # --- 2. PROPERLY DISABLE OUTER LOANS JUST FOR BOX ---
    if loan_category == "box":
        query_gold = f"SELECT id, form_no, loan_date, closing_date, status, total_given_amount, present_amount, due_month_count, one_month_interest, due_details_all, close_total_interest, paper_amount, applied_rates FROM {table_gold}"
    
    query_silver = f"SELECT id, form_no, loan_date, closing_date, status, total_given_amount, present_amount, due_month_count, one_month_interest, due_details_all, close_total_interest, paper_amount, applied_rates FROM {table_silver}"
    
    # --- 1. ACTIVE OUTER LOANS (ENRICHED WITH PAPER AMOUNT) ---
    query_outer_gold = f"""
    SELECT o.transaction_date as date, o.place_name as shop, o.outer_amount as amount, 'Gold' as loan_type, o.loan_nos as form_no,
           g.present_amount, g.total_given_amount, g.loan_date as core_date, g.one_month_interest, g.due_details_all, g.due_month_count, g.paper_amount
    FROM outer_transactions o
    JOIN {table_gold} g ON o.loan_nos = g.form_no
    WHERE LOWER(o.outer_loan_status) = 'active' AND LOWER(g.status) IN ('active', 'overdue')
    """
    
    query_outer_silver = f"""
    SELECT o.transaction_date as date, o.place_name as shop, o.outer_amount as amount, 'Silver' as loan_type, o.loan_nos as form_no,
           s.present_amount, s.total_given_amount, s.loan_date as core_date, s.one_month_interest, s.due_details_all, s.due_month_count, s.paper_amount
    FROM outer_transactions o
    JOIN {table_silver} s ON o.loan_nos = s.form_no
    WHERE LOWER(o.outer_loan_status) = 'active' AND LOWER(s.status) IN ('active', 'overdue')
    """
    
    # --- 2. OUTER CLOSED LOANS (ENRICHED WITH PAPER AND DOC CHARGE) ---
    query_outer_closed_gold = f"""
    SELECT o.outer_loan_closing_date as date, 'Gold' as loan_type, o.loan_nos as form_no,
           o.place_name as shop, o.outer_amount as outer_amount,
           g.present_amount, g.total_given_amount, g.paper_amount,
           g.close_total_interest, g.one_month_interest, g.due_details_all, 
           o.interest as outer_interest, o.doc_charge,
           o.transaction_date as outer_start_date, g.closing_date as core_closing_date
    FROM outer_transactions o
    JOIN {table_gold} g ON o.loan_nos = g.form_no
    WHERE LOWER(o.outer_loan_status) = 'outer closed'
    """
    
    query_outer_closed_silver = f"""
    SELECT o.outer_loan_closing_date as date, 'Silver' as loan_type, o.loan_nos as form_no,
           o.place_name as shop, o.outer_amount as outer_amount,
           s.present_amount, s.total_given_amount, s.paper_amount,
           s.close_total_interest, s.one_month_interest, s.due_details_all, 
           o.interest as outer_interest, o.doc_charge,
           o.transaction_date as outer_start_date, s.closing_date as core_closing_date
    FROM outer_transactions o
    JOIN {table_silver} s ON o.loan_nos = s.form_no
    WHERE LOWER(o.outer_loan_status) = 'outer closed'
    """
        
    gold_df = pd.read_sql_query(query_gold, conn)
    silver_df = pd.read_sql_query(query_silver, conn)
    

    settings = get_latest_global_settings()
    
    # Active Outer Process
    outer_gold_df = pd.read_sql_query(query_outer_gold, conn)
    outer_silver_df = pd.read_sql_query(query_outer_silver, conn)
    outer_analysis_df = pd.concat([outer_gold_df, outer_silver_df], ignore_index=True)
    if not outer_analysis_df.empty:
        outer_analysis_df['date'] = pd.to_datetime(outer_analysis_df['date'], format='%d/%m/%Y', errors='coerce')
        outer_analysis_df = outer_analysis_df.dropna(subset=['date'])
        
        active_shop_int_list = []
        active_outer_int_list = []
        live_doc_charge_list = []
        
        today = datetime.date.today()
        
        for _, row in outer_analysis_df.iterrows():
            core_date_str = str(row.get('core_date', '')).strip()
            core_date_dt = pd.to_datetime(core_date_str, format='%d/%m/%Y', errors='coerce')
            
            calculated_int = 0
            if pd.notna(core_date_dt):
                # 🟢 FIX 2: Passed loan_category to calculate_live_interest for outer loans
                calculated_int, _, _, _ = calculate_live_interest(row, settings, str(row['loan_type']).lower(), core_date_dt.date(), loan_category)
                
            one_mth_amt = safe_float(row.get('one_month_interest'))
            d_int = 0.0
            due_data = row.get('due_details_all')
            if pd.notna(due_data) and str(due_data).strip() != "":
                try:
                    details = json.loads(due_data)
                    for d in details:
                        if d.get('status', '') == "Due":
                            d_int += safe_float(d.get('amount_of_month', 0))
                except Exception:
                    pass
                    
            total_shop_int = calculated_int + one_mth_amt + d_int
            active_shop_int_list.append(total_shop_int)
            
            outer_start_date = row['date'].date()
            if outer_start_date > today:
                active_outer_int_list.append(0.0)
                live_doc_charge_list.append(0.0)
                continue
                
            outer_months = calculate_exact_months(outer_start_date, today)
            outer_rate = get_weighted_rate(outer_start_date, today, row['shop'], rates_df)
            outer_amt = safe_float(row['amount'])
            
            o_int_val = outer_amt * outer_rate * outer_months
            active_outer_int_list.append(o_int_val)
            
            doc_rate = get_current_doc_rate(row['shop'], rates_df)
            live_doc_charge_list.append(math.ceil(outer_amt * doc_rate))
            
        outer_analysis_df['shop_total_interest'] = active_shop_int_list
        outer_analysis_df['outer_expected_interest'] = active_outer_int_list
        outer_analysis_df['live_doc_charge'] = live_doc_charge_list

    # Closed Outer Process
    outer_closed_gold_df = pd.read_sql_query(query_outer_closed_gold, conn)
    outer_closed_silver_df = pd.read_sql_query(query_outer_closed_silver, conn)
    outer_closed_df = pd.concat([outer_closed_gold_df, outer_closed_silver_df], ignore_index=True)
    
    if not outer_closed_df.empty:
        outer_closed_df['date'] = pd.to_datetime(outer_closed_df['date'], format='%d/%m/%Y', errors='coerce')
        outer_closed_df = outer_closed_df.dropna(subset=['date'])
        
        outer_months_list = []
        shop_int_list = []
        
        for _, row in outer_closed_df.iterrows():
            start_str = str(row.get('outer_start_date', '')).strip()
            end_str = str(row.get('core_closing_date', '')).strip()
            
            start_dt = pd.to_datetime(start_str, format='%d/%m/%Y', errors='coerce')
            end_dt = pd.to_datetime(end_str, format='%d/%m/%Y', errors='coerce')
            
            if pd.notna(start_dt) and pd.notna(end_dt):
                mths = calculate_exact_months(start_dt.date(), end_dt.date())
                outer_months_list.append(mths)
            else:
                outer_months_list.append(0.0)
                
            c_int = safe_float(row.get('close_total_interest'))
            o_int = safe_float(row.get('one_month_interest'))
            d_int = 0.0
            
            due_data = row.get('due_details_all')
            if pd.notna(due_data) and str(due_data).strip() != "":
                try:
                    details = json.loads(due_data)
                    for d in details:
                        if d.get('status', '') == "Due":
                            d_int += safe_float(d.get('amount_of_month', 0))
                except Exception:
                    pass
                
            shop_int_list.append(c_int + o_int + d_int)
                
        outer_closed_df['calculated_outer_months'] = outer_months_list
        outer_closed_df['shop_total_interest'] = shop_int_list
        
    conn.close()
    
    events = []
    active_overdue_records = []
    
    def process_loans(df, loan_type):
        for _, row in df.iterrows():
            db_status = str(row['status']).strip().lower()
            date_str = str(row['loan_date']).strip()
            
            if db_status not in ['closed', 'sold'] and date_str != "" and date_str.lower() != "nan":
                loan_date_dt = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce')
                
                if pd.notna(loan_date_dt):
                    parsed_loan_date = loan_date_dt.date()
                    today = datetime.date.today()
                    
                    try:
                        one_year_ago = today.replace(year=today.year - 1)
                    except ValueError:
                        one_year_ago = today.replace(year=today.year - 1, day=28)
                        
                    state = 'Overdue' if parsed_loan_date < one_year_ago else 'Active'
                    
                    # 🟢 FIX 3: Passed loan_category here to ensure it uses the correct rates
                    calculated_int, t_mths, d_mths, f_mths = calculate_live_interest(row, settings, loan_type, parsed_loan_date, loan_category)
                    
                    pres_amt = safe_float(row.get('present_amount'))
                    amt = pres_amt if pres_amt > 0 else safe_float(row.get('total_given_amount'))
                    
                    one_mth_amt = safe_float(row.get('one_month_interest'))
                    return_1_val = 1 if one_mth_amt > 0 else 0
                    
                    active_overdue_records.append({
                        'id': row['id'],
                        'form_no': row['form_no'],
                        'loan_date': loan_date_dt,
                        'loan_type': loan_type.capitalize(),
                        'state': state,
                        'principal_amount': amt,
                        'calculated_interest': calculated_int,
                        'total_month': t_mths,
                        'due_month': d_mths,
                        'final_month': f_mths,
                        'one_month': one_mth_amt,
                        'return_1': return_1_val 
                    })

            if date_str != "" and date_str.lower() != "nan":
                events.append({
                    'date': date_str,
                    f'{loan_type}_amount': safe_float(row.get('total_given_amount')),
                    f'{loan_type}_count': 1,
                    f'{loan_type}_1m_int': safe_float(row.get('one_month_interest')),
                    f'{loan_type}_1m_count': 1 if safe_float(row.get('one_month_interest')) > 0 else 0,
                    f'{loan_type}_due_int': 0, f'{loan_type}_due_count': 0,
                    f'{loan_type}_extra_int': 0, f'{loan_type}_extra_count': 0,
                    f'{loan_type}_close_int': 0, f'{loan_type}_close_count': 0,
                    f'{loan_type}_paper': safe_float(row.get('paper_amount'))
                })
                
            close_date_str = str(row.get('closing_date', '')).strip()
            if close_date_str != "" and close_date_str.lower() != "nan":
                events.append({
                    'date': close_date_str,
                    f'{loan_type}_amount': 0, f'{loan_type}_count': 0,
                    f'{loan_type}_1m_int': 0, f'{loan_type}_1m_count': 0,
                    f'{loan_type}_due_int': 0, f'{loan_type}_due_count': 0,
                    f'{loan_type}_extra_int': 0, f'{loan_type}_extra_count': 0,
                    f'{loan_type}_close_int': safe_float(row.get('close_total_interest')),
                    f'{loan_type}_close_count': 1 if safe_float(row.get('close_total_interest')) > 0 else 0,
                    f'{loan_type}_paper': 0
                })
                
            due_data = row['due_details_all']
            if pd.notna(due_data) and str(due_data).strip() != "":
                try:
                    details_list = json.loads(due_data)
                    for detail in details_list:
                        status = detail.get('status', '')
                        due_date = detail.get('due_date', detail.get('date', ''))
                        if due_date:
                            due_amt = safe_float(detail.get('amount_of_month')) if status == "Due" else 0
                            extra_amt = safe_float(detail.get('extra_interest'))
                            if due_amt > 0 or extra_amt > 0:
                                events.append({
                                    'date': due_date,
                                    f'{loan_type}_amount': 0, f'{loan_type}_count': 0,
                                    f'{loan_type}_1m_int': 0, f'{loan_type}_1m_count': 0,
                                    f'{loan_type}_close_int': 0, f'{loan_type}_close_count': 0,
                                    f'{loan_type}_paper': 0,
                                    f'{loan_type}_due_int': due_amt,
                                    f'{loan_type}_due_count': 1 if due_amt > 0 else 0,
                                    f'{loan_type}_extra_int': extra_amt,
                                    f'{loan_type}_extra_count': 1 if extra_amt > 0 else 0
                                })
                except Exception: pass

    process_loans(gold_df, 'gold')
    process_loans(silver_df, 'silver')
    
    events_df = pd.DataFrame(events)
    ao_df = pd.DataFrame(active_overdue_records)
    
    if events_df.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    events_df['date'] = pd.to_datetime(events_df['date'], format='%d/%m/%Y', errors='coerce')
    events_df = events_df.dropna(subset=['date'])
    
    cols_to_fill = [
        'gold_amount', 'silver_amount', 'gold_count', 'silver_count', 
        'gold_1m_int', 'silver_1m_int', 'gold_due_int', 'silver_due_int',
        'gold_extra_int', 'silver_extra_int', 'gold_close_int', 'silver_close_int',
        'gold_1m_count', 'silver_1m_count', 'gold_due_count', 'silver_due_count',
        'gold_extra_count', 'silver_extra_count', 'gold_close_count', 'silver_close_count',
        'gold_paper', 'silver_paper'
    ]
    for col in cols_to_fill:
        if col not in events_df.columns: events_df[col] = 0
            
    daily_totals = events_df.groupby('date').sum().reset_index()
    daily_totals = daily_totals.sort_values('date')
    
    daily_totals['total_loan_amount'] = daily_totals['gold_amount'] + daily_totals['silver_amount']
    daily_totals['total_count'] = daily_totals['gold_count'] + daily_totals['silver_count']
    daily_totals['total_paper'] = daily_totals['gold_paper'] + daily_totals['silver_paper']
    
    daily_totals['total_1m_int'] = daily_totals['gold_1m_int'] + daily_totals['silver_1m_int']
    daily_totals['total_1m_count'] = daily_totals['gold_1m_count'] + daily_totals['silver_1m_count']
    daily_totals['total_due_int'] = daily_totals['gold_due_int'] + daily_totals['silver_due_int']
    daily_totals['total_due_count'] = daily_totals['gold_due_count'] + daily_totals['silver_due_count']
    daily_totals['total_extra_int'] = daily_totals['gold_extra_int'] + daily_totals['silver_extra_int']
    daily_totals['total_extra_count'] = daily_totals['gold_extra_count'] + daily_totals['silver_extra_count']
    daily_totals['total_close_int'] = daily_totals['gold_close_int'] + daily_totals['silver_close_int']
    daily_totals['total_close_count'] = daily_totals['gold_close_count'] + daily_totals['silver_close_count']
    daily_totals['total_overall_interest'] = daily_totals['total_1m_int'] + daily_totals['total_due_int'] + daily_totals['total_extra_int'] + daily_totals['total_close_int']
    daily_totals['total_overall_count'] = daily_totals['total_1m_count'] + daily_totals['total_due_count'] + daily_totals['total_extra_count'] + daily_totals['total_close_count']
    daily_totals['day_of_week'] = daily_totals['date'].dt.day_name()
    
    return daily_totals, ao_df, outer_analysis_df, outer_closed_df

# --- Updated Navigation & Routing ---
st.sidebar.title("🧭 Main Navigation")
page = st.sidebar.radio("Select Dashboard:", [
    "Normal Loan Analysis", 
    "Big Loan Analysis", 
    "Box Loan Analysis",
    "Unique Customer Analysis",
    "Daily Profit & Expenses",
    "Final Tally Analysis",
    "Master Final Report",
    "💹 Master P&L (Income & Loss)"
])

if page == "Normal Loan Analysis":
    n_data, n_ao, n_outer, n_out_cl = load_and_process_data(loan_category="normal")
    normal_loan_analysis.render(n_data, n_ao, n_outer, n_out_cl)

elif page == "Big Loan Analysis":
    b_data, b_ao, b_outer, b_out_cl = load_and_process_data(loan_category="big")
    big_loan_analysis.render(b_data, b_ao, b_outer, b_out_cl)

elif page == "Box Loan Analysis":
    box_data, box_ao, box_outer, box_out_cl = load_and_process_data(loan_category="box")
    box_loan_analysis.render(box_data, box_ao, box_outer, box_out_cl)

elif page == "Unique Customer Analysis":
    unique_customer_analysis.render() # Assumes your render function doesn't need passed data

elif page == "Daily Profit & Expenses":
    daily_profit_analysis.render() # Assumes your render function doesn't need passed data

elif page == "Final Tally Analysis":
    final_tally_analysis.render() # Assumes your render function doesn't need passed data

elif page == "💹 Master P&L (Income & Loss)":
    master_profit_loss.render()

elif page == "Master Final Report":
    with st.spinner("Fetching and combining Normal, Big, and Box Loan data..."):
        n_data, n_ao, n_outer, n_out_cl = load_and_process_data(loan_category="normal")
        b_data, b_ao, b_outer, b_out_cl = load_and_process_data(loan_category="big")
        box_data, box_ao, box_outer, box_out_cl = load_and_process_data(loan_category="box")
        
    # Pass ALL 3 portfolios to the Master Report
    master_final_report.render(
     n_data, n_ao, n_outer, n_out_cl,
     b_data, b_ao, b_outer, b_out_cl,
     box_data, box_ao, box_outer, box_out_cl
 )