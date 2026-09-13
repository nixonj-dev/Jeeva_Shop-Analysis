import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import datetime
import numpy as np
import json

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def format_currency(val):
    if pd.isna(val): return "₹ 0"
    if val < 0:      return f"- ₹ {abs(val):,.0f}"
    return f"₹ {val:,.0f}"

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(val)
    except Exception:
        return 0.0

def parse_date(s):
    """Parse DD/MM/YYYY string → datetime or NaT."""
    return pd.to_datetime(str(s).strip(), format='%d/%m/%Y', errors='coerce')

# ──────────────────────────────────────────────────────────────────────────────
# SHOP VS OUTER DATA FETCHER
# ──────────────────────────────────────────────────────────────────────────────
def fetch_shop_vs_outer_data():
    """
    Fetches ALL active/overdue loans from Normal, Big, and Box loan tables.
    Maps active outer_transactions to each loan via form_no.
    Returns a DataFrame with one row per loan containing:
        form_no, loan_date, loan_type (Gold/Silver), category (Normal/Big/Box),
        principal_amount, outer_amt, shop_amt, state (Active/Overdue)
    """
    conn = sqlite3.connect('users.db')

    TABLES = [
        ('gold_loan',      'Gold',   'Normal'),
        ('silver_loan',    'Silver', 'Normal'),
        ('BigLoanGold',    'Gold',   'Big'),
        ('BigLoanSilver',  'Silver', 'Big'),
        ('BoxLoanGold',    'Gold',   'Box'),
        ('BoxLoanSilver',  'Silver', 'Box'),
    ]

    loan_rows = []
    for table, l_type, category in TABLES:
        try:
            df = pd.read_sql_query(
                f"SELECT form_no, loan_date, status, present_amount, total_given_amount "
                f"FROM {table} WHERE LOWER(status) NOT IN ('closed','sold')",
                conn
            )
            df['loan_type'] = l_type
            df['category']  = category
            loan_rows.append(df)
        except Exception:
            continue

    if not loan_rows:
        conn.close()
        return pd.DataFrame()

    loans = pd.concat(loan_rows, ignore_index=True)

    # Parse dates
    loans['loan_date'] = pd.to_datetime(
        loans['loan_date'], format='%d/%m/%Y', errors='coerce'
    )
    loans = loans.dropna(subset=['loan_date'])

    # Determine Active vs Overdue (same logic as dashboard.py)
    import datetime as _dt
    today = _dt.date.today()
    try:
        one_year_ago = today.replace(year=today.year - 1)
    except ValueError:
        one_year_ago = today.replace(year=today.year - 1, day=28)
    loans['state'] = loans['loan_date'].apply(
        lambda d: 'Overdue' if d.date() < one_year_ago else 'Active'
    )

    # Principal amount
    loans['present_amount']     = pd.to_numeric(loans['present_amount'],     errors='coerce').fillna(0)
    loans['total_given_amount'] = pd.to_numeric(loans['total_given_amount'], errors='coerce').fillna(0)
    loans['principal_amount']   = np.where(
        loans['present_amount'] > 0,
        loans['present_amount'],
        loans['total_given_amount']
    )

    # ── Outer amounts: only ACTIVE outer_transactions ─────────────────────────
    try:
        outer_df = pd.read_sql_query(
            """SELECT loan_nos as form_no, SUM(CAST(outer_amount AS REAL)) as outer_amt
               FROM outer_transactions
               WHERE LOWER(outer_loan_status) = 'active'
               GROUP BY loan_nos""",
            conn
        )
        outer_map = outer_df.set_index('form_no')['outer_amt'].to_dict()
    except Exception:
        outer_map = {}

    conn.close()

    loans['outer_amt'] = loans['form_no'].map(outer_map).fillna(0)
    loans['shop_amt']  = loans['principal_amount'] - loans['outer_amt']

    return loans[['form_no', 'loan_date', 'loan_type', 'category',
                  'principal_amount', 'outer_amt', 'shop_amt', 'state']].copy()


def _growth_pct(series: pd.Series) -> pd.Series:
    """Percentage change vs previous row; first row = 0%."""
    pct = series.pct_change() * 100
    return pct.fillna(0).round(2)


# ──────────────────────────────────────────────────────────────────────────────
# DATA PREFIXES / EXCLUSIONS (mirror daily_profit_analysis.py)
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# CORE DATA FETCHER
# ──────────────────────────────────────────────────────────────────────────────
def fetch_all_pnl_data():
    """
    Returns a single DataFrame with one row per date containing every P&L component.

    Columns produced
    ────────────────
    date                   : event date (datetime64)
    shop_interest          : total interest collected from customers (all 3 loan types)
    paper_income           : total paper/doc charges collected from customers
    outer_interest_paid    : interest paid OUT to outer lenders (closed outer loans)
    outer_doc_paid         : doc charges paid OUT to outer lenders (closed outer loans)
    daily_credit           : miscellaneous operational income (credit side of daily expenses)
    daily_debit            : operational expenses (debit side of daily expenses)
    """
    conn = sqlite3.connect('users.db')
    records = []   # list of {date, component, amount}

    # ── 1. LOAN INTEREST & PAPER INCOME ───────────────────────────────────────
    LOAN_TABLES = {
        'normal': ('gold_loan',    'silver_loan'),
        'big':    ('BigLoanGold',  'BigLoanSilver'),
        'box':    ('BoxLoanGold',  'BoxLoanSilver'),
    }

    SELECT_COLS = (
        "loan_date, closing_date, status, "
        "one_month_interest, close_total_interest, paper_amount, due_details_all"
    )

    for category, (tg, ts) in LOAN_TABLES.items():
        for table in (tg, ts):
            try:
                df = pd.read_sql_query(f"SELECT {SELECT_COLS} FROM {table}", conn)
            except Exception:
                continue

            for _, row in df.iterrows():
                db_status = str(row.get('status', '')).strip().lower()
                loan_date  = parse_date(row.get('loan_date', ''))
                close_date = parse_date(row.get('closing_date', ''))

                # ---- 1a. One-month interest & paper charge (recorded on loan date) ----
                if pd.notna(loan_date):
                    one_m = safe_float(row.get('one_month_interest'))
                    paper = safe_float(row.get('paper_amount'))
                    if one_m > 0:
                        records.append({'date': loan_date,
                                        'shop_interest': one_m,
                                        'paper_income': 0,
                                        'outer_interest_paid': 0,
                                        'outer_doc_paid': 0,
                                        'daily_credit': 0,
                                        'daily_debit': 0})
                    if paper > 0:
                        records.append({'date': loan_date,
                                        'shop_interest': 0,
                                        'paper_income': paper,
                                        'outer_interest_paid': 0,
                                        'outer_doc_paid': 0,
                                        'daily_credit': 0,
                                        'daily_debit': 0})

                # ---- 1b. Close interest (recorded on closing date) ----
                if pd.notna(close_date) and db_status in ('closed', 'sold'):
                    close_int = safe_float(row.get('close_total_interest'))
                    if close_int > 0:
                        records.append({'date': close_date,
                                        'shop_interest': close_int,
                                        'paper_income': 0,
                                        'outer_interest_paid': 0,
                                        'outer_doc_paid': 0,
                                        'daily_credit': 0,
                                        'daily_debit': 0})

                # ---- 1c. Due & extra interest (recorded on each due_date) ----
                due_raw = row.get('due_details_all')
                if pd.notna(due_raw) and str(due_raw).strip():
                    try:
                        details = json.loads(due_raw)
                        for d in details:
                            d_date = parse_date(d.get('due_date', d.get('date', '')))
                            if pd.isna(d_date):
                                continue
                            due_amt   = safe_float(d.get('amount_of_month')) if d.get('status') == 'Due' else 0.0
                            extra_amt = safe_float(d.get('extra_interest'))
                            total_due_int = due_amt + extra_amt
                            if total_due_int > 0:
                                records.append({'date': d_date,
                                                'shop_interest': total_due_int,
                                                'paper_income': 0,
                                                'outer_interest_paid': 0,
                                                'outer_doc_paid': 0,
                                                'daily_credit': 0,
                                                'daily_debit': 0})
                    except Exception:
                        pass

    # ── 2. OUTER LOANS (what the shop PAID OUT to outer lenders) ─────────────
    # We only record actual settled payments: outer_loan_status = 'outer closed'
    # Attributed on outer_loan_closing_date
    OUTER_TABLES = [
        'outer_transactions',   # shared across all categories
    ]
    try:
        outer_df = pd.read_sql_query(
            """SELECT outer_loan_closing_date, interest, doc_charge, outer_loan_status
               FROM outer_transactions
               WHERE LOWER(outer_loan_status) = 'outer closed'
            """, conn
        )
        for _, row in outer_df.iterrows():
            closing_dt = parse_date(row.get('outer_loan_closing_date', ''))
            if pd.isna(closing_dt):
                continue
            o_int  = safe_float(row.get('interest'))
            o_doc  = safe_float(row.get('doc_charge'))
            if o_int > 0:
                records.append({'date': closing_dt,
                                'shop_interest': 0,
                                'paper_income': 0,
                                'outer_interest_paid': o_int,
                                'outer_doc_paid': 0,
                                'daily_credit': 0,
                                'daily_debit': 0})
            if o_doc > 0:
                records.append({'date': closing_dt,
                                'shop_interest': 0,
                                'paper_income': 0,
                                'outer_interest_paid': 0,
                                'outer_doc_paid': o_doc,
                                'daily_credit': 0,
                                'daily_debit': 0})
    except Exception:
        pass

    # ── 3. DAILY OPERATIONAL EXPENSES & MISC INCOME ──────────────────────────
    # Mirror of daily_profit_analysis.py — reads capital_transactions + GpayAccount
    hierarchy = {'Cash': set(), 'GPay': set()}
    try:
        for t_key in ['Cash', 'GPay']:
            rows = conn.execute(
                "SELECT description FROM transaction_descriptions WHERE type=? ORDER BY description",
                (t_key,)
            ).fetchall()
            for r in rows:
                m_cat = r[0].strip()
                if m_cat not in EXCLUDED_KEYS:
                    hierarchy[t_key].add(m_cat)
    except Exception:
        pass

    def _process_tx(t_root, query):
        try:
            rows = conn.execute(query).fetchall()
            for r in rows:
                d_str, raw_desc, t_type, amt = r
                dt = parse_date(d_str)
                if pd.isna(dt):
                    continue
                c_desc = raw_desc.strip()
                for pfx in PREFIXES:
                    if c_desc.lower().startswith(pfx.lower()):
                        c_desc = c_desc[len(pfx):].strip()
                        break
                if not c_desc:
                    continue
                main_c = c_desc.split(' - ', 1)[0].strip()
                if main_c in hierarchy[t_root]:
                    is_credit = t_type in ['Credit', 'Incoming']
                    records.append({
                        'date': dt,
                        'shop_interest': 0,
                        'paper_income': 0,
                        'outer_interest_paid': 0,
                        'outer_doc_paid': 0,
                        'daily_credit': safe_float(amt) if is_credit else 0.0,
                        'daily_debit': safe_float(amt) if not is_credit else 0.0,
                    })
        except Exception:
            pass

    _process_tx('Cash', "SELECT transaction_date, description, transaction_type, amount FROM capital_transactions")
    _process_tx('GPay', "SELECT transaction_date, description, transaction_type, amount FROM GpayAccount")

    conn.close()

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date'])
    df = df.dropna(subset=['date'])

    # Aggregate to one row per date
    daily = (
        df.groupby(df['date'].dt.normalize())
        [['shop_interest', 'paper_income',
          'outer_interest_paid', 'outer_doc_paid',
          'daily_credit', 'daily_debit']]
        .sum()
        .reset_index()
    )

    # Derived columns
    daily['total_income']     = (daily['shop_interest']
                                 + daily['paper_income']
                                 + daily['daily_credit'])
    daily['total_deductions'] = (daily['outer_interest_paid']
                                 + daily['outer_doc_paid']
                                 + daily['daily_debit'])
    daily['net_profit']       = daily['total_income'] - daily['total_deductions']

    return daily.sort_values('date')


# ──────────────────────────────────────────────────────────────────────────────
# RENDER
# ──────────────────────────────────────────────────────────────────────────────
def render():
    st.title("💹 Final Master Profit & Loss")
    st.info(
        "💡 **Universal P&L Engine:** Combines every income and expense stream across "
        "all loan types (Normal / Big / Box), outer lender costs, and daily operational "
        "transactions into a single master ledger."
    )

    with st.spinner("🔄 Loading and computing P&L data from all sources..."):
        df = fetch_all_pnl_data()

    if df.empty:
        st.warning("No data found. Please make sure your database is in the correct location.")
        return

    # ── DATE FILTER ───────────────────────────────────────────────────────────
    db_min  = df['date'].min().date()
    db_max  = df['date'].max().date()
    today   = datetime.date.today()
    y_start = datetime.date(today.year, 1, 1)

    col_d, _ = st.columns([1, 3])
    with col_d:
        date_range = st.date_input(
            "📅 Select Analysis Window:",
            value=(max(db_min, y_start), min(db_max, today)),
            min_value=db_min,
            max_value=today
        )

    if len(date_range) != 2:
        return
    sd = pd.Timestamp(date_range[0])
    ed = pd.Timestamp(date_range[1])

    filt = df[(df['date'] >= sd) & (df['date'] <= ed)].copy()
    if filt.empty:
        st.warning("No data in the selected date range.")
        return

    # ── MONTH COLUMN ─────────────────────────────────────────────────────────
    filt['month'] = filt['date'].dt.to_period('M')

    # ── GLOBAL KPIs ───────────────────────────────────────────────────────────
    st.write("---")
    st.markdown("### 📊 Period Overview")

    t_shop_int  = filt['shop_interest'].sum()
    t_paper     = filt['paper_income'].sum()
    t_d_credit  = filt['daily_credit'].sum()
    t_out_int   = filt['outer_interest_paid'].sum()
    t_out_doc   = filt['outer_doc_paid'].sum()
    t_d_debit   = filt['daily_debit'].sum()
    t_income    = filt['total_income'].sum()
    t_deduct    = filt['total_deductions'].sum()
    t_net       = filt['net_profit'].sum()
    days        = len(filt['date'].unique())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💰 Total Income",         format_currency(t_income))
    k2.metric("💸 Total Deductions",     format_currency(t_deduct))
    delta_color = "normal" if t_net >= 0 else "inverse"
    k3.metric("📈 Net Profit / Loss",    format_currency(t_net),
              delta=f"{'Profit' if t_net >= 0 else 'Loss'}",
              delta_color=delta_color)
    k4.metric("📅 Active Trading Days",  f"{days} days",
              delta=f"Avg ₹{t_net/days:,.0f}/day" if days > 0 else "")

    st.write("---")

    # ── TABS ─────────────────────────────────────────────────────────────────
    t_summary, t_daily, t_monthly, t_charts, t_ledger, t_svo = st.tabs([
        "🏆 Income Breakdown",
        "📋 Daily P&L",
        "📆 Monthly P&L",
        "📊 Charts & Trends",
        "📂 Raw Ledger",
        "⚖️ Shop vs Outer (Live Capital)"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — INCOME BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════════
    with t_summary:
        st.markdown("### 🏆 Period Income & Deduction Breakdown")

        c_inc, c_ded = st.columns(2)

        with c_inc:
            st.markdown("#### ✅ Income Sources")
            income_df = pd.DataFrame({
                'Source': [
                    '🏦 Shop Interest Collected (Normal/Big/Box)',
                    '📄 Paper Charges Collected',
                    '💵 Operational Credits (Daily Expenses)',
                ],
                'Amount': [t_shop_int, t_paper, t_d_credit]
            })
            income_df['% of Total'] = (income_df['Amount'] / t_income * 100).round(1).astype(str) + '%' if t_income > 0 else '0%'
            income_df['Amount'] = income_df['Amount'].apply(format_currency)
            st.dataframe(income_df, hide_index=True, use_container_width=True)

            if t_income > 0:
                fig_inc = px.pie(
                    pd.DataFrame({
                        'Source': ['Shop Interest', 'Paper Charges', 'Daily Credits'],
                        'Amount': [t_shop_int, t_paper, t_d_credit]
                    }),
                    names='Source', values='Amount', hole=0.45,
                    title="Income Composition",
                    color_discrete_sequence=['#2ca02c', '#17becf', '#bcbd22']
                )
                fig_inc.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_inc, use_container_width=True)

        with c_ded:
            st.markdown("#### ❌ Deductions")
            deduct_df = pd.DataFrame({
                'Deduction': [
                    '🏢 Outer Shop Interest Paid',
                    '📑 Outer Shop Doc Charges Paid',
                    '💸 Operational Debits (Daily Expenses)',
                ],
                'Amount': [t_out_int, t_out_doc, t_d_debit]
            })
            deduct_df['% of Total'] = (deduct_df['Amount'] / t_deduct * 100).round(1).astype(str) + '%' if t_deduct > 0 else '0%'
            deduct_df['Amount'] = deduct_df['Amount'].apply(format_currency)
            st.dataframe(deduct_df, hide_index=True, use_container_width=True)

            if t_deduct > 0:
                fig_ded = px.pie(
                    pd.DataFrame({
                        'Type': ['Outer Interest', 'Outer Doc Charges', 'Daily Debits'],
                        'Amount': [t_out_int, t_out_doc, t_d_debit]
                    }),
                    names='Type', values='Amount', hole=0.45,
                    title="Deduction Composition",
                    color_discrete_sequence=['#d62728', '#ff7f0e', '#9467bd']
                )
                fig_ded.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_ded, use_container_width=True)

        st.write("---")
        st.markdown("### 🧮 Final P&L Summary")

        summary_rows = [
            ("(+) Shop Interest Collected",         t_shop_int,  "Income"),
            ("(+) Paper Charges Collected",          t_paper,     "Income"),
            ("(+) Daily Operational Credits",        t_d_credit,  "Income"),
            ("(-) Outer Shop Interest Paid",        -t_out_int,   "Deduction"),
            ("(-) Outer Shop Doc Charges Paid",     -t_out_doc,   "Deduction"),
            ("(-) Daily Operational Debits",        -t_d_debit,   "Deduction"),
            ("═══════════════════════════════",      None,         "Separator"),
            ("🟢 NET PROFIT / LOSS",                 t_net,        "Total"),
        ]
        s_df = pd.DataFrame(summary_rows, columns=['Line Item', 'Amount (₹)', 'Type'])
        s_df['Formatted'] = s_df['Amount (₹)'].apply(
            lambda v: "—" if v is None else format_currency(v)
        )
        st.dataframe(
            s_df[['Line Item', 'Formatted']].rename(columns={'Formatted': 'Amount (₹)'}),
            hide_index=True,
            use_container_width=True
        )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — DAILY P&L
    # ══════════════════════════════════════════════════════════════════════════
    with t_daily:
        st.markdown("### 📋 Day-by-Day P&L Ledger")
        st.info("Every income and deduction component shown per calendar date.")

        daily_disp = filt[[
            'date', 'shop_interest', 'paper_income', 'daily_credit',
            'outer_interest_paid', 'outer_doc_paid', 'daily_debit',
            'total_income', 'total_deductions', 'net_profit'
        ]].copy()

        daily_disp['date'] = daily_disp['date'].dt.strftime('%d/%m/%Y')

        for col in ['shop_interest', 'paper_income', 'daily_credit',
                    'outer_interest_paid', 'outer_doc_paid', 'daily_debit',
                    'total_income', 'total_deductions', 'net_profit']:
            daily_disp[col] = daily_disp[col].apply(format_currency)

        daily_disp = daily_disp.rename(columns={
            'date':                 'Date',
            'shop_interest':        '(+) Shop Interest',
            'paper_income':         '(+) Paper Charges',
            'daily_credit':         '(+) Daily Credits',
            'outer_interest_paid':  '(-) Outer Interest',
            'outer_doc_paid':       '(-) Outer Doc Fee',
            'daily_debit':          '(-) Daily Debits',
            'total_income':         'Total Income',
            'total_deductions':     'Total Deductions',
            'net_profit':           '✅ Net Profit'
        })

        st.dataframe(daily_disp.sort_values('Date', ascending=False),
                     hide_index=True, use_container_width=True)

        csv_daily = filt.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Daily P&L CSV", csv_daily,
                           file_name="daily_pnl.csv", mime="text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — MONTHLY P&L
    # ══════════════════════════════════════════════════════════════════════════
    with t_monthly:
        st.markdown("### 📆 Monthly P&L Ledger")

        monthly = filt.groupby('month').agg(
            Shop_Interest=    ('shop_interest',       'sum'),
            Paper_Income=     ('paper_income',        'sum'),
            Daily_Credits=    ('daily_credit',        'sum'),
            Outer_Int_Paid=   ('outer_interest_paid', 'sum'),
            Outer_Doc_Paid=   ('outer_doc_paid',      'sum'),
            Daily_Debits=     ('daily_debit',         'sum'),
            Total_Income=     ('total_income',        'sum'),
            Total_Deductions= ('total_deductions',    'sum'),
            Net_Profit=       ('net_profit',          'sum'),
        ).reset_index()

        monthly['MoM Growth %'] = (
            monthly['Net_Profit'].pct_change() * 100
        ).fillna(0).round(1).astype(str) + '%'

        monthly['month_str'] = monthly['month'].dt.strftime('%b %Y')

        monthly_disp = monthly.copy()
        for col in ['Shop_Interest', 'Paper_Income', 'Daily_Credits',
                    'Outer_Int_Paid', 'Outer_Doc_Paid', 'Daily_Debits',
                    'Total_Income', 'Total_Deductions', 'Net_Profit']:
            monthly_disp[col] = monthly_disp[col].apply(format_currency)

        monthly_disp = monthly_disp.rename(columns={
            'month_str':        'Month',
            'Shop_Interest':    '(+) Shop Interest',
            'Paper_Income':     '(+) Paper Charges',
            'Daily_Credits':    '(+) Daily Credits',
            'Outer_Int_Paid':   '(-) Outer Interest',
            'Outer_Doc_Paid':   '(-) Outer Doc Fee',
            'Daily_Debits':     '(-) Daily Debits',
            'Total_Income':     'Total Income',
            'Total_Deductions': 'Total Deductions',
            'Net_Profit':       '✅ Net Profit',
            'MoM Growth %':     'MoM Growth %'
        })

        st.dataframe(
            monthly_disp[['Month', '(+) Shop Interest', '(+) Paper Charges',
                           '(+) Daily Credits', '(-) Outer Interest',
                           '(-) Outer Doc Fee', '(-) Daily Debits',
                           'Total Income', 'Total Deductions',
                           '✅ Net Profit', 'MoM Growth %']],
            hide_index=True, use_container_width=True
        )

        csv_monthly = monthly.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Monthly P&L CSV", csv_monthly,
                           file_name="monthly_pnl.csv", mime="text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — CHARTS & TRENDS
    # ══════════════════════════════════════════════════════════════════════════
    with t_charts:
        st.markdown("### 📊 Visual Profit & Loss Analysis")

        # ─── CHART 1: Daily Net Profit Waterfall-Style Line ─────────────────
        st.markdown("#### 1️⃣ Daily Net Profit / Loss Trend")
        fig_net = go.Figure()
        fig_net.add_trace(go.Bar(
            x=filt['date'],
            y=filt['net_profit'],
            name='Net Profit',
            marker_color=np.where(filt['net_profit'] >= 0, '#2ca02c', '#d62728')
        ))
        fig_net.add_trace(go.Scatter(
            x=filt['date'], y=filt['net_profit'].rolling(7, min_periods=1).mean(),
            mode='lines', name='7-Day Avg',
            line=dict(color='black', width=2)
        ))
        fig_net.add_hline(y=0, line_dash='dot', line_color='red',
                          annotation_text='Break-Even')
        fig_net.update_layout(
            title="Daily Net Profit (Green = Profit, Red = Loss)",
            xaxis_title="Date", yaxis_title="Net Profit (₹)",
            hovermode='x unified'
        )
        st.plotly_chart(fig_net, use_container_width=True)

        # ─── CHART 2: Income vs Deductions Daily ────────────────────────────
        st.markdown("#### 2️⃣ Daily Income vs Deductions")
        fig_vs = go.Figure()
        fig_vs.add_trace(go.Bar(
            x=filt['date'], y=filt['total_income'],
            name='Total Income', marker_color='#2ca02c'
        ))
        fig_vs.add_trace(go.Bar(
            x=filt['date'], y=-filt['total_deductions'],
            name='Total Deductions', marker_color='#d62728'
        ))
        fig_vs.update_layout(
            barmode='relative',
            title="Daily Income vs Deductions",
            xaxis_title="Date", yaxis_title="Amount (₹)",
            hovermode='x unified'
        )
        st.plotly_chart(fig_vs, use_container_width=True)

        # ─── CHART 3: Monthly Stacked Income Breakdown ──────────────────────
        st.markdown("#### 3️⃣ Monthly Income Component Breakdown")
        monthly_plot = filt.groupby('month').agg(
            Shop_Interest=('shop_interest', 'sum'),
            Paper_Income= ('paper_income',  'sum'),
            Daily_Credits=('daily_credit',  'sum'),
        ).reset_index()
        monthly_plot['month_str'] = monthly_plot['month'].dt.strftime('%b %Y')

        fig_inc_stack = go.Figure()
        fig_inc_stack.add_trace(go.Bar(
            x=monthly_plot['month_str'], y=monthly_plot['Shop_Interest'],
            name='Shop Interest', marker_color='#1f77b4'
        ))
        fig_inc_stack.add_trace(go.Bar(
            x=monthly_plot['month_str'], y=monthly_plot['Paper_Income'],
            name='Paper Charges', marker_color='#17becf'
        ))
        fig_inc_stack.add_trace(go.Bar(
            x=monthly_plot['month_str'], y=monthly_plot['Daily_Credits'],
            name='Daily Credits', marker_color='#bcbd22'
        ))
        fig_inc_stack.update_layout(
            barmode='stack',
            title="Monthly Income by Source",
            xaxis_title="Month", yaxis_title="Amount (₹)"
        )
        st.plotly_chart(fig_inc_stack, use_container_width=True)

        # ─── CHART 4: Monthly Stacked Deduction Breakdown ───────────────────
        st.markdown("#### 4️⃣ Monthly Deduction Component Breakdown")
        monthly_ded = filt.groupby('month').agg(
            Outer_Int=   ('outer_interest_paid', 'sum'),
            Outer_Doc=   ('outer_doc_paid',      'sum'),
            Daily_Debits=('daily_debit',          'sum'),
        ).reset_index()
        monthly_ded['month_str'] = monthly_ded['month'].dt.strftime('%b %Y')

        fig_ded_stack = go.Figure()
        fig_ded_stack.add_trace(go.Bar(
            x=monthly_ded['month_str'], y=monthly_ded['Outer_Int'],
            name='Outer Interest Paid', marker_color='#d62728'
        ))
        fig_ded_stack.add_trace(go.Bar(
            x=monthly_ded['month_str'], y=monthly_ded['Outer_Doc'],
            name='Outer Doc Charges', marker_color='#ff7f0e'
        ))
        fig_ded_stack.add_trace(go.Bar(
            x=monthly_ded['month_str'], y=monthly_ded['Daily_Debits'],
            name='Daily Expenses', marker_color='#9467bd'
        ))
        fig_ded_stack.update_layout(
            barmode='stack',
            title="Monthly Deductions by Type",
            xaxis_title="Month", yaxis_title="Amount (₹)"
        )
        st.plotly_chart(fig_ded_stack, use_container_width=True)

        # ─── CHART 5: Monthly Net Profit Bar ────────────────────────────────
        st.markdown("#### 5️⃣ Monthly Net Profit / Loss")
        monthly_net = filt.groupby('month')['net_profit'].sum().reset_index()
        monthly_net['month_str'] = monthly_net['month'].dt.strftime('%b %Y')
        monthly_net['color'] = np.where(monthly_net['net_profit'] >= 0, '#2ca02c', '#d62728')

        fig_mon_net = go.Figure(go.Bar(
            x=monthly_net['month_str'],
            y=monthly_net['net_profit'],
            marker_color=monthly_net['color'],
            text=monthly_net['net_profit'].apply(format_currency),
            textposition='outside'
        ))
        fig_mon_net.add_hline(y=0, line_dash='dot', line_color='black')
        fig_mon_net.update_layout(
            title="Month-by-Month Net Profit",
            xaxis_title="Month", yaxis_title="Net Profit (₹)"
        )
        st.plotly_chart(fig_mon_net, use_container_width=True)

        # ─── CHART 6: Cumulative P&L ─────────────────────────────────────────
        st.markdown("#### 6️⃣ Cumulative Profit Growth (Running Total)")
        filt_sorted = filt.sort_values('date').copy()
        filt_sorted['cumulative_profit'] = filt_sorted['net_profit'].cumsum()

        fig_cum = px.area(
            filt_sorted, x='date', y='cumulative_profit',
            title="Cumulative Net Profit Over Time",
            labels={'date': 'Date', 'cumulative_profit': 'Cumulative Profit (₹)'},
            color_discrete_sequence=['#1f77b4']
        )
        fig_cum.add_hline(y=0, line_dash='dot', line_color='red',
                          annotation_text='Zero Line')
        st.plotly_chart(fig_cum, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5 — RAW LEDGER
    # ══════════════════════════════════════════════════════════════════════════
    with t_ledger:
        st.markdown("### 📂 Raw Daily Component Ledger")
        st.info("All raw numbers before formatting. Use the search/filter bar to drill down.")

        raw_disp = filt[[
            'date', 'shop_interest', 'paper_income', 'daily_credit',
            'outer_interest_paid', 'outer_doc_paid', 'daily_debit',
            'total_income', 'total_deductions', 'net_profit'
        ]].copy().sort_values('date', ascending=False)

        raw_disp['date'] = raw_disp['date'].dt.strftime('%d/%m/%Y')
        st.dataframe(raw_disp, hide_index=True, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 6 — SHOP VS OUTER (LIVE CAPITAL)
    # ══════════════════════════════════════════════════════════════════════════
    with t_svo:
        st.markdown("### ⚖️ Live Capital: Shop vs Outer (All Loan Types Combined)")
        st.info(
            "💡 **What is Outer Capital?** When the shop runs out of its own money, it gives "
            "the customer's pledged item to an **outer shop** as collateral and borrows money "
            "from them. That borrowed amount is **Outer Capital**. "
            "**Shop Capital** = Total Principal − Outer Capital."
        )

        with st.spinner("🔄 Loading live loan portfolio from all 6 tables..."):
            svo_df = fetch_shop_vs_outer_data()

        if svo_df.empty:
            st.warning("No active/overdue loan data found. Check your database.")
        else:
            # ── 1. GLOBAL KPIs ────────────────────────────────────────────────
            t_principal = svo_df['principal_amount'].sum()
            t_shop      = svo_df['shop_amt'].sum()
            t_outer     = svo_df['outer_amt'].sum()
            leverage_pct = (t_outer / t_principal * 100) if t_principal > 0 else 0
            shop_pct     = (t_shop  / t_principal * 100) if t_principal > 0 else 0
            total_loans  = len(svo_df)
            outer_loans  = len(svo_df[svo_df['outer_amt'] > 0])

            st.markdown("#### 📊 Overall Live Capital Snapshot (All Normal + Big + Box Loans)")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💼 Total Live Principal",  format_currency(t_principal),
                      f"{total_loans} active loans")
            k2.metric("🏢 Total Shop Capital",    format_currency(t_shop),
                      f"{shop_pct:.1f}% of portfolio")
            k3.metric("🤝 Total Outer Capital",   format_currency(t_outer),
                      f"{leverage_pct:.1f}% leverage ratio",
                      delta_color="inverse" if t_outer > 0 else "normal")
            k4.metric("🔗 Leveraged Loans",       f"{outer_loans} loans",
                      f"{total_loans - outer_loans} fully shop-funded")

            st.write("---")

            # ── 2. BREAKDOWN BY CATEGORY (Normal / Big / Box) ─────────────────
            st.markdown("#### 🗂️ Breakdown by Loan Category (Normal / Big / Box)")
            cat_grp = svo_df.groupby('category').agg(
                Loans          = ('form_no',         'count'),
                Total_Principal= ('principal_amount', 'sum'),
                Shop_Amount    = ('shop_amt',         'sum'),
                Outer_Amount   = ('outer_amt',        'sum'),
            ).reset_index()
            cat_grp['Shop %']  = (cat_grp['Shop_Amount']  / cat_grp['Total_Principal'] * 100).fillna(0).round(1).astype(str) + '%'
            cat_grp['Outer %'] = (cat_grp['Outer_Amount'] / cat_grp['Total_Principal'] * 100).fillna(0).round(1).astype(str) + '%'

            cat_display = cat_grp.copy()
            for c in ['Total_Principal', 'Shop_Amount', 'Outer_Amount']:
                cat_display[c] = cat_display[c].apply(format_currency)
            cat_display.rename(columns={
                'category': 'Loan Category', 'Loans': 'No. of Loans',
                'Total_Principal': 'Total Principal', 'Shop_Amount': 'Shop Capital',
                'Outer_Amount': 'Outer Capital'
            }, inplace=True)
            st.dataframe(cat_display, hide_index=True, use_container_width=True)

            # ── 3. BREAKDOWN BY LOAN TYPE (Gold / Silver) ─────────────────────
            st.markdown("#### 🪙 Breakdown by Loan Type (Gold / Silver)")
            type_grp = svo_df.groupby('loan_type').agg(
                Loans          = ('form_no',         'count'),
                Total_Principal= ('principal_amount', 'sum'),
                Shop_Amount    = ('shop_amt',         'sum'),
                Outer_Amount   = ('outer_amt',        'sum'),
            ).reset_index()
            type_grp['Shop %']  = (type_grp['Shop_Amount']  / type_grp['Total_Principal'] * 100).fillna(0).round(1).astype(str) + '%'
            type_grp['Outer %'] = (type_grp['Outer_Amount'] / type_grp['Total_Principal'] * 100).fillna(0).round(1).astype(str) + '%'

            type_display = type_grp.copy()
            for c in ['Total_Principal', 'Shop_Amount', 'Outer_Amount']:
                type_display[c] = type_display[c].apply(format_currency)
            type_display.rename(columns={
                'loan_type': 'Metal Type', 'Loans': 'No. of Loans',
                'Total_Principal': 'Total Principal', 'Shop_Amount': 'Shop Capital',
                'Outer_Amount': 'Outer Capital'
            }, inplace=True)
            st.dataframe(type_display, hide_index=True, use_container_width=True)

            # ── 4. BREAKDOWN BY CATEGORY × LOAN TYPE (full matrix) ────────────
            st.markdown("#### 📋 Full Matrix: Category × Metal Type")
            matrix_grp = svo_df.groupby(['category', 'loan_type']).agg(
                Loans          = ('form_no',         'count'),
                Total_Principal= ('principal_amount', 'sum'),
                Shop_Amount    = ('shop_amt',         'sum'),
                Outer_Amount   = ('outer_amt',        'sum'),
            ).reset_index()
            matrix_grp['Shop %']  = (matrix_grp['Shop_Amount']  / matrix_grp['Total_Principal'] * 100).fillna(0).round(1).astype(str) + '%'
            matrix_grp['Outer %'] = (matrix_grp['Outer_Amount'] / matrix_grp['Total_Principal'] * 100).fillna(0).round(1).astype(str) + '%'
            for c in ['Total_Principal', 'Shop_Amount', 'Outer_Amount']:
                matrix_grp[c] = matrix_grp[c].apply(format_currency)
            matrix_grp.rename(columns={
                'category': 'Category', 'loan_type': 'Metal',
                'Total_Principal': 'Total Principal', 'Shop_Amount': 'Shop Capital',
                'Outer_Amount': 'Outer Capital'
            }, inplace=True)
            st.dataframe(matrix_grp, hide_index=True, use_container_width=True)

            st.write("---")

            # ── 5. DAILY TABLE WITH GROWTH % ──────────────────────────────────
            st.markdown("#### 📋 Daily Dispersal Table — Shop vs Outer (with Growth %)")
            st.caption("Each row = loans dispersed on that date. Growth % vs previous active date.")

            daily_svo = svo_df.groupby(svo_df['loan_date'].dt.normalize()).agg(
                Loans          = ('form_no',         'count'),
                Total_Principal= ('principal_amount', 'sum'),
                Shop_Amount    = ('shop_amt',         'sum'),
                Outer_Amount   = ('outer_amt',        'sum'),
            ).reset_index().sort_values('loan_date')

            daily_svo['Shop Growth %']  = _growth_pct(daily_svo['Shop_Amount'])
            daily_svo['Outer Growth %'] = _growth_pct(daily_svo['Outer_Amount'])
            daily_svo['Shop %']         = (daily_svo['Shop_Amount']  / daily_svo['Total_Principal'] * 100).fillna(0).round(1)
            daily_svo['Outer %']        = (daily_svo['Outer_Amount'] / daily_svo['Total_Principal'] * 100).fillna(0).round(1)

            daily_disp_svo = daily_svo.copy()
            daily_disp_svo['loan_date'] = daily_disp_svo['loan_date'].dt.strftime('%d/%m/%Y')
            for c in ['Total_Principal', 'Shop_Amount', 'Outer_Amount']:
                daily_disp_svo[c] = daily_disp_svo[c].apply(format_currency)

            daily_disp_svo.rename(columns={
                'loan_date': 'Date', 'Loans': 'Loans Dispersed',
                'Total_Principal': 'Total Principal',
                'Shop_Amount': 'Shop Capital', 'Outer_Amount': 'Outer Capital',
                'Shop %': 'Shop % of Day', 'Outer %': 'Outer % of Day',
                'Shop Growth %': '📈 Shop Growth %', 'Outer Growth %': '📈 Outer Growth %'
            }, inplace=True)
            st.dataframe(
                daily_disp_svo.sort_values('Date', ascending=False),
                hide_index=True, use_container_width=True
            )

            st.write("---")

            # ── 6. MONTHLY TABLE WITH GROWTH % ────────────────────────────────
            st.markdown("#### 📆 Monthly Summary — Shop vs Outer (with Growth %)")

            svo_df['month_period'] = svo_df['loan_date'].dt.to_period('M')
            monthly_svo = svo_df.groupby('month_period').agg(
                Loans          = ('form_no',         'count'),
                Total_Principal= ('principal_amount', 'sum'),
                Shop_Amount    = ('shop_amt',         'sum'),
                Outer_Amount   = ('outer_amt',        'sum'),
            ).reset_index().sort_values('month_period')

            monthly_svo['Shop Growth %']  = _growth_pct(monthly_svo['Shop_Amount'])
            monthly_svo['Outer Growth %'] = _growth_pct(monthly_svo['Outer_Amount'])
            monthly_svo['Shop %']         = (monthly_svo['Shop_Amount']  / monthly_svo['Total_Principal'] * 100).fillna(0).round(1)
            monthly_svo['Outer %']        = (monthly_svo['Outer_Amount'] / monthly_svo['Total_Principal'] * 100).fillna(0).round(1)
            monthly_svo['Month']          = monthly_svo['month_period'].dt.strftime('%b %Y')

            monthly_disp_svo = monthly_svo.copy()
            for c in ['Total_Principal', 'Shop_Amount', 'Outer_Amount']:
                monthly_disp_svo[c] = monthly_disp_svo[c].apply(format_currency)
            monthly_disp_svo.rename(columns={
                'Month': 'Month', 'Loans': 'Loans Dispersed',
                'Total_Principal': 'Total Principal',
                'Shop_Amount': 'Shop Capital', 'Outer_Amount': 'Outer Capital',
                'Shop %': 'Shop % of Month', 'Outer %': 'Outer % of Month',
                'Shop Growth %': '📈 Shop Growth %', 'Outer Growth %': '📈 Outer Growth %'
            }, inplace=True)
            st.dataframe(
                monthly_disp_svo[['Month', 'Loans Dispersed', 'Total Principal',
                                   'Shop Capital', 'Shop % of Month', '📈 Shop Growth %',
                                   'Outer Capital', 'Outer % of Month', '📈 Outer Growth %']].sort_values('Month', ascending=False),
                hide_index=True, use_container_width=True
            )

            st.write("---")

            # ── 7. CHARTS ─────────────────────────────────────────────────────
            st.markdown("#### 📊 Visual Capital Analysis")

            # Chart A: Pie — Shop vs Outer split
            c_pie, c_bar_cat = st.columns(2)
            with c_pie:
                pie_data = pd.DataFrame({
                    'Source': ['🏢 Shop Capital', '🤝 Outer Capital'],
                    'Amount': [t_shop, t_outer]
                })
                fig_pie = px.pie(
                    pie_data, names='Source', values='Amount', hole=0.5,
                    title="Overall Capital Split (Live)",
                    color='Source',
                    color_discrete_map={'🏢 Shop Capital': '#1f77b4', '🤝 Outer Capital': '#ff7f0e'}
                )
                fig_pie.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)

            # Chart B: Bar — Shop vs Outer by category
            with c_bar_cat:
                cat_melt = cat_grp.copy()
                cat_melt = cat_melt[['category', 'Shop_Amount', 'Outer_Amount']].melt(
                    id_vars='category', var_name='Source', value_name='Amount'
                )
                cat_melt['Source'] = cat_melt['Source'].map(
                    {'Shop_Amount': 'Shop Capital', 'Outer_Amount': 'Outer Capital'}
                )
                fig_cat = px.bar(
                    cat_melt, x='category', y='Amount', color='Source', barmode='group',
                    title="Shop vs Outer by Loan Category",
                    color_discrete_map={'Shop Capital': '#1f77b4', 'Outer Capital': '#ff7f0e'},
                    labels={'category': 'Category', 'Amount': '₹ Amount'}
                )
                st.plotly_chart(fig_cat, use_container_width=True)

            # Chart C: Area chart — monthly shop vs outer over dispersal timeline
            st.markdown("##### 📈 Monthly Shop vs Outer Dispersal Timeline")
            monthly_plot = monthly_svo.copy()
            monthly_plot['month_dt'] = monthly_plot['month_period'].dt.to_timestamp()
            fig_area = go.Figure()
            fig_area.add_trace(go.Scatter(
                x=monthly_plot['month_dt'], y=monthly_plot['Shop_Amount'],
                mode='lines', name='Shop Capital',
                fill='tozeroy', line=dict(color='#1f77b4', width=2),
                fillcolor='rgba(31,119,180,0.3)'
            ))
            fig_area.add_trace(go.Scatter(
                x=monthly_plot['month_dt'], y=monthly_plot['Outer_Amount'],
                mode='lines', name='Outer Capital',
                fill='tozeroy', line=dict(color='#ff7f0e', width=2),
                fillcolor='rgba(255,127,14,0.3)'
            ))
            fig_area.update_layout(
                title="Monthly Shop Capital vs Outer Capital (by Loan Dispersal Date)",
                xaxis_title="Month", yaxis_title="Amount (₹)",
                hovermode='x unified', legend=dict(orientation='h')
            )
            st.plotly_chart(fig_area, use_container_width=True)

            # Chart D: Monthly growth % — line chart
            st.markdown("##### 📈 Month-over-Month Growth % (Shop vs Outer)")
            fig_growth = go.Figure()
            fig_growth.add_trace(go.Scatter(
                x=monthly_plot['month_dt'], y=monthly_svo['Shop Growth %'].values,
                mode='lines+markers', name='Shop Capital Growth %',
                line=dict(color='#2ca02c', width=2)
            ))
            fig_growth.add_trace(go.Scatter(
                x=monthly_plot['month_dt'], y=monthly_svo['Outer Growth %'].values,
                mode='lines+markers', name='Outer Capital Growth %',
                line=dict(color='#d62728', width=2)
            ))
            fig_growth.add_hline(y=0, line_dash='dot', line_color='gray')
            fig_growth.update_layout(
                title="Month-over-Month Growth % — Shop vs Outer Capital",
                xaxis_title="Month", yaxis_title="Growth %",
                hovermode='x unified'
            )
            st.plotly_chart(fig_growth, use_container_width=True)

            # Chart E: Stacked 100% bar — shop independence score by month
            st.markdown("##### 📊 Shop Independence % by Month (How much is YOURS?)")
            monthly_svo['Shop_100'] = monthly_svo['Shop %']
            monthly_svo['Outer_100'] = monthly_svo['Outer %']
            fig_stack = go.Figure()
            fig_stack.add_trace(go.Bar(
                x=monthly_plot['month_dt'], y=monthly_svo['Shop_100'].values,
                name='Shop Capital %', marker_color='#1f77b4'
            ))
            fig_stack.add_trace(go.Bar(
                x=monthly_plot['month_dt'], y=monthly_svo['Outer_100'].values,
                name='Outer Capital %', marker_color='#ff7f0e'
            ))
            fig_stack.update_layout(
                barmode='stack', title="Monthly Capital Composition (Shop % vs Outer %)",
                xaxis_title="Month", yaxis_title="% of Monthly Portfolio",
                hovermode='x unified'
            )
            st.plotly_chart(fig_stack, use_container_width=True)

            st.write("---")

            # ── 8. FUTURE GROWTH PROJECTION ───────────────────────────────────
            st.markdown("#### 🔮 Future Capital Growth Forecast")
            st.info(
                "Using the historical trend of how Shop Capital and Outer Capital have grown "
                "month by month, this engine projects the next 3 years and calculates **exactly "
                "how many years it will take for the shop to hold 100% of all loan capital "
                "without needing any external (outer) funding.**"
            )

            forecast_months = st.slider(
                "Forecast Horizon (Months):", min_value=6, max_value=60, value=36, step=6
            )

            m_data = monthly_svo[['month_period', 'Shop_Amount', 'Outer_Amount']].copy()
            m_data['month_dt'] = m_data['month_period'].dt.to_timestamp()

            if len(m_data) >= 3:
                x_hist = np.arange(len(m_data))
                x_fut  = np.arange(len(m_data), len(m_data) + forecast_months)
                last_dt = m_data['month_dt'].iloc[-1]
                fut_dates = pd.date_range(
                    start=last_dt + pd.DateOffset(months=1),
                    periods=forecast_months, freq='MS'
                )

                # Linear regression for shop and outer
                def _project(y_vals, x_h, x_f):
                    coef = np.polyfit(x_h, y_vals, 1)
                    poly = np.poly1d(coef)
                    return poly(x_f), coef[0]   # projected values, slope (₹/month)

                shop_fut, shop_slope   = _project(m_data['Shop_Amount'].values,  x_hist, x_fut)
                outer_fut, outer_slope = _project(m_data['Outer_Amount'].values, x_hist, x_fut)

                # KPI metrics from projection
                proj_shop_end  = shop_fut[-1]
                proj_outer_end = outer_fut[-1]
                proj_total_end = proj_shop_end + max(proj_outer_end, 0)

                pf1, pf2, pf3 = st.columns(3)
                pf1.metric(
                    f"Projected Shop Capital (Month {forecast_months})",
                    format_currency(max(proj_shop_end, 0)),
                    f"{'▲' if shop_slope > 0 else '▼'} ₹{abs(shop_slope):,.0f}/month trend"
                )
                pf2.metric(
                    f"Projected Outer Capital (Month {forecast_months})",
                    format_currency(max(proj_outer_end, 0)),
                    f"{'▲' if outer_slope > 0 else '▼'} ₹{abs(outer_slope):,.0f}/month trend",
                    delta_color="inverse" if outer_slope > 0 else "normal"
                )
                pf3.metric(
                    "Projected Total Principal",
                    format_currency(max(proj_total_end, 0))
                )

                st.write("---")

                # ── HOW MANY YEARS TO 100% SHOP CAPITAL ──────────────────────
                st.markdown("#### 🎯 Projection: Years Until 100% Shop Capital")

                current_outer = m_data['Outer_Amount'].iloc[-1]

                if outer_slope < 0 and current_outer > 0:
                    # Outer is declining → calculate months to zero
                    months_to_zero = int(np.ceil(current_outer / abs(outer_slope)))
                    years_to_zero  = months_to_zero / 12
                    st.success(
                        f"✅ **Great news!** Outer capital is declining at "
                        f"₹{abs(outer_slope):,.0f}/month. At this rate, the shop will "
                        f"hold **100% of all loan capital as its own money in approximately "
                        f"{years_to_zero:.1f} years** ({months_to_zero} months). "
                        f"Target date: **{(last_dt + pd.DateOffset(months=months_to_zero)).strftime('%B %Y')}**"
                    )
                    yy1, yy2 = st.columns(2)
                    yy1.metric("⏳ Months to Full Independence", f"{months_to_zero} months")
                    yy2.metric("📅 Years to Full Independence",  f"{years_to_zero:.1f} years")

                elif outer_slope == 0 and current_outer == 0:
                    st.success("🌟 The shop is already fully independent — no outer capital in use!")

                elif current_outer == 0:
                    st.success("🌟 Currently no outer capital in use. Shop is 100% self-funded!")

                else:
                    # Outer is flat or growing → warn
                    st.error(
                        f"⚠️ **Warning:** Outer capital is **growing** at "
                        f"₹{abs(outer_slope):,.0f}/month. At this trend, the shop will "
                        f"**never** become fully independent — outer dependency will keep rising. "
                        f"Consider a strategy to reduce outer borrowings."
                    )
                    st.metric(
                        "Outer Capital Growth Rate", f"+₹{outer_slope:,.0f}/month",
                        delta="Rising Dependency", delta_color="inverse"
                    )

                st.write("---")

                # ── FORECAST CHART ────────────────────────────────────────────
                hist_shop  = pd.DataFrame({'Date': m_data['month_dt'],  'Amount': m_data['Shop_Amount'],  'Type': 'Shop (Historical)'})
                hist_outer = pd.DataFrame({'Date': m_data['month_dt'],  'Amount': m_data['Outer_Amount'], 'Type': 'Outer (Historical)'})
                proj_shop  = pd.DataFrame({'Date': fut_dates,           'Amount': np.maximum(shop_fut, 0),  'Type': 'Shop (Projected)'})
                proj_outer = pd.DataFrame({'Date': fut_dates,           'Amount': np.maximum(outer_fut, 0), 'Type': 'Outer (Projected)'})

                combined = pd.concat([hist_shop, hist_outer, proj_shop, proj_outer], ignore_index=True)

                color_map = {
                    'Shop (Historical)':  '#1f77b4',
                    'Outer (Historical)': '#ff7f0e',
                    'Shop (Projected)':   '#aec7e8',
                    'Outer (Projected)':  '#ffbb78'
                }

                fig_proj = px.line(
                    combined, x='Date', y='Amount', color='Type',
                    title=f"Shop vs Outer Capital — Historical + {forecast_months}-Month Forecast",
                    color_discrete_map=color_map,
                    labels={'Amount': 'Capital Amount (₹)', 'Date': 'Month'}
                )
                # Make projected lines dashed
                for trace in fig_proj.data:
                    if 'Projected' in trace.name:
                        trace.line.dash = 'dot'
                        trace.line.width = 2

                fig_proj.add_hline(
                    y=0, line_dash='solid', line_color='red',
                    annotation_text="Zero Outer (Full Independence)"
                )
                fig_proj.update_layout(hovermode='x unified', legend=dict(orientation='h'))
                st.plotly_chart(fig_proj, use_container_width=True)

                # ── PROJECTION SUMMARY TABLE ──────────────────────────────────
                st.markdown("##### 📋 Projected Monthly Values")
                proj_table = pd.DataFrame({
                    'Month': [d.strftime('%b %Y') for d in fut_dates[::3]],
                    'Projected Shop Capital': [format_currency(max(v, 0)) for v in shop_fut[::3]],
                    'Projected Outer Capital': [format_currency(max(v, 0)) for v in outer_fut[::3]],
                    'Shop Dominance %': [
                        f"{(max(s,0) / (max(s,0) + max(o,0)) * 100):.1f}%" if (max(s,0) + max(o,0)) > 0 else "100%"
                        for s, o in zip(shop_fut[::3], outer_fut[::3])
                    ]
                })
                st.dataframe(proj_table, hide_index=True, use_container_width=True)

            else:
                st.warning("⚠️ Need at least 3 months of dispersal data to generate a forecast.")

        # ── 7A. CUMULATIVE GROWTH CHART ──────────────────────────────────
            st.markdown("#### 📈 Cumulative Capital Growth (Past + Future)")
            st.info(
                "This chart shows the **total accumulated capital** from all months "
                "(cumulative sum) for both Shop and Outer capital, plus 36-month projection."
            )
            
            cumulative_fig = create_cumulative_growth_chart(monthly_svo)
            if cumulative_fig:
                st.plotly_chart(cumulative_fig, use_container_width=True)
            else:
                st.warning("⚠️ Insufficient data for cumulative growth chart.")
            
            st.write("---")

            # ── 5A. DAILY CUMULATIVE GROWTH WITH TREND LINE ──────────────────
            st.markdown("#### 📈 Daily Cumulative Capital Growth (Actual vs Predicted Trend)")
            st.info(
                "**Solid lines** = Actual cumulative growth | **Dashed lines** = Predicted trend\n\n"
                "This shows if your daily dispersals are growing as expected. "
                "The trend line predicts future growth based on current momentum."
            )
            
            daily_cumul_fig = create_daily_cumulative_growth_chart(daily_svo)
            if daily_cumul_fig:
                st.plotly_chart(daily_cumul_fig, use_container_width=True)
            else:
                st.warning("⚠️ Insufficient daily data for cumulative growth chart.")
            
            st.write("---")


# ── CUMULATIVE GROWTH CHART (Add this function at the top with other helpers)
def create_cumulative_growth_chart(monthly_data):
    """
    Creates a cumulative growth chart showing total capital growth over time
    with past data and future projection.
    
    Parameters:
    -----------
    monthly_data : DataFrame with columns 'month_period', 'Shop_Amount', 'Outer_Amount'
    
    Returns:
    --------
    fig : plotly figure object
    """
    m_data = monthly_data[['month_period', 'Shop_Amount', 'Outer_Amount']].copy()
    m_data['month_dt'] = m_data['month_period'].dt.to_timestamp()
    m_data['Total_Amount'] = m_data['Shop_Amount'] + m_data['Outer_Amount']
    
    # Calculate cumulative growth (each month adds to previous)
    m_data['Cumulative_Shop'] = m_data['Shop_Amount'].cumsum()
    m_data['Cumulative_Outer'] = m_data['Outer_Amount'].cumsum()
    m_data['Cumulative_Total'] = m_data['Cumulative_Shop'] + m_data['Cumulative_Outer']
    
    # Future projection
    if len(m_data) >= 3:
        x_hist = np.arange(len(m_data))
        forecast_months = 36  # 3 years default
        x_fut = np.arange(len(m_data), len(m_data) + forecast_months)
        
        last_dt = m_data['month_dt'].iloc[-1]
        fut_dates = pd.date_range(
            start=last_dt + pd.DateOffset(months=1),
            periods=forecast_months, freq='MS'
        )
        
        # Project individual amounts
        def _project(y_vals, x_h, x_f):
            coef = np.polyfit(x_h, y_vals, 1)
            poly = np.poly1d(coef)
            return np.maximum(poly(x_f), 0)
        
        shop_fut = _project(m_data['Shop_Amount'].values, x_hist, x_fut)
        outer_fut = _project(m_data['Outer_Amount'].values, x_hist, x_fut)
        
        # Calculate cumulative for projection
        last_cumul_shop = m_data['Cumulative_Shop'].iloc[-1]
        last_cumul_outer = m_data['Cumulative_Outer'].iloc[-1]
        
        cumul_shop_fut = last_cumul_shop + np.cumsum(shop_fut)
        cumul_outer_fut = last_cumul_outer + np.cumsum(outer_fut)
        
        # Create figure with dual axis
        fig = go.Figure()
        
        # Historical cumulative lines
        fig.add_trace(go.Scatter(
            x=m_data['month_dt'], y=m_data['Cumulative_Shop'],
            mode='lines+markers', name='Shop Capital (Historical)',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=6)
        ))
        
        fig.add_trace(go.Scatter(
            x=m_data['month_dt'], y=m_data['Cumulative_Outer'],
            mode='lines+markers', name='Outer Capital (Historical)',
            line=dict(color='#ff7f0e', width=3),
            marker=dict(size=6)
        ))
        
        fig.add_trace(go.Scatter(
            x=m_data['month_dt'], y=m_data['Cumulative_Total'],
            mode='lines+markers', name='Total Capital (Historical)',
            line=dict(color='#2ca02c', width=3, dash='solid'),
            marker=dict(size=6)
        ))
        
        # Future projection (dashed lines)
        fig.add_trace(go.Scatter(
            x=fut_dates, y=cumul_shop_fut,
            mode='lines', name='Shop Capital (Projected)',
            line=dict(color='#1f77b4', width=2, dash='dot'),
            opacity=0.7
        ))
        
        fig.add_trace(go.Scatter(
            x=fut_dates, y=cumul_outer_fut,
            mode='lines', name='Outer Capital (Projected)',
            line=dict(color='#ff7f0e', width=2, dash='dot'),
            opacity=0.7
        ))
        
        fig.add_trace(go.Scatter(
            x=fut_dates, y=cumul_shop_fut + cumul_outer_fut,
            mode='lines', name='Total Capital (Projected)',
            line=dict(color='#2ca02c', width=2, dash='dot'),
            opacity=0.7
        ))
        
        # Add separator line between historical and future
        last_hist_date = m_data['month_dt'].iloc[-1]
        fig.add_vline(
            x=last_hist_date, line_dash='dash', line_color='gray',
            annotation_text='Forecast Start', annotation_position='top right'
        )
        
        fig.update_layout(
            title='📈 Cumulative Capital Growth: Historical & Projected (36 Months)',
            xaxis_title='Month',
            yaxis_title='Cumulative Capital Amount (₹)',
            hovermode='x unified',
            legend=dict(orientation='v', x=0.01, y=0.99),
            height=500,
            template='plotly_white'
        )
        
        return fig
    
    return None

def create_daily_cumulative_growth_chart(daily_data):
    """
    Creates a cumulative daily growth chart showing:
    1. Actual cumulative growth for Shop, Outer, and Total capital
    2. Trend line (linear regression prediction) to show if growth is on track
    3. Visual comparison between actual and predicted trend
    
    Parameters:
    -----------
    daily_data : DataFrame with columns 'loan_date', 'Shop_Amount', 'Outer_Amount', 'Total_Principal'
    
    Returns:
    --------
    fig : plotly figure object
    """
    if daily_data is None or len(daily_data) == 0:
        return None
    
    d_data = daily_data[['loan_date', 'Shop_Amount', 'Outer_Amount', 'Total_Principal']].copy()
    d_data = d_data.sort_values('loan_date').reset_index(drop=True)
    
    # Calculate cumulative sums
    d_data['Cumulative_Shop'] = d_data['Shop_Amount'].cumsum()
    d_data['Cumulative_Outer'] = d_data['Outer_Amount'].cumsum()
    d_data['Cumulative_Total'] = d_data['Total_Principal'].cumsum()
    
    if len(d_data) < 2:
        return None
    
    # Create numeric x-axis for regression
    x_actual = np.arange(len(d_data)).astype(float)
    
    # Linear regression (trend lines)
    def _get_trend_line(y_vals, x_vals):
        """Calculate linear regression and return predicted values and coefficients"""
        try:
            y_vals = np.asarray(y_vals, dtype=float)
            x_vals = np.asarray(x_vals, dtype=float)
            
            # Remove any NaN values
            mask = ~(np.isnan(y_vals) | np.isnan(x_vals))
            if mask.sum() < 2:
                return np.full_like(y_vals, np.nan, dtype=float), np.array([0.0, 0.0])
            
            coef = np.polyfit(x_vals[mask], y_vals[mask], 1)
            poly = np.poly1d(coef)
            predicted = poly(x_vals)
            return predicted, coef
        except Exception as e:
            return np.full_like(y_vals, np.nan, dtype=float), np.array([0.0, 0.0])
    
    shop_trend, shop_coef = _get_trend_line(d_data['Cumulative_Shop'].values, x_actual)
    outer_trend, outer_coef = _get_trend_line(d_data['Cumulative_Outer'].values, x_actual)
    total_trend, total_coef = _get_trend_line(d_data['Cumulative_Total'].values, x_actual)
    
    # Create figure
    fig = go.Figure()
    
    # ── ACTUAL CUMULATIVE LINES ──────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=d_data['loan_date'], y=d_data['Cumulative_Shop'],
        mode='lines', name='Shop Capital (Actual)',
        line=dict(color='#1f77b4', width=3),
        hovertemplate='<b>Date:</b> %{x|%d/%m/%Y}<br><b>Cumulative Shop:</b> ₹%{y:,.0f}<extra></extra>'
    ))
    
    fig.add_trace(go.Scatter(
        x=d_data['loan_date'], y=d_data['Cumulative_Outer'],
        mode='lines', name='Outer Capital (Actual)',
        line=dict(color='#ff7f0e', width=3),
        hovertemplate='<b>Date:</b> %{x|%d/%m/%Y}<br><b>Cumulative Outer:</b> ₹%{y:,.0f}<extra></extra>'
    ))
    
    fig.add_trace(go.Scatter(
        x=d_data['loan_date'], y=d_data['Cumulative_Total'],
        mode='lines', name='Total Capital (Actual)',
        line=dict(color='#2ca02c', width=3),
        hovertemplate='<b>Date:</b> %{x|%d/%m/%Y}<br><b>Cumulative Total:</b> ₹%{y:,.0f}<extra></extra>'
    ))
    
    # ── TREND LINES (Predictions) ────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=d_data['loan_date'], y=shop_trend,
        mode='lines', name='Shop Trend (Predicted)',
        line=dict(color='#1f77b4', width=2, dash='dash'),
        opacity=0.6,
        hovertemplate='<b>Date:</b> %{x|%d/%m/%Y}<br><b>Shop Trend:</b> ₹%{y:,.0f}<extra></extra>'
    ))
    
    fig.add_trace(go.Scatter(
        x=d_data['loan_date'], y=outer_trend,
        mode='lines', name='Outer Trend (Predicted)',
        line=dict(color='#ff7f0e', width=2, dash='dash'),
        opacity=0.6,
        hovertemplate='<b>Date:</b> %{x|%d/%m/%Y}<br><b>Outer Trend:</b> ₹%{y:,.0f}<extra></extra>'
    ))
    
    fig.add_trace(go.Scatter(
        x=d_data['loan_date'], y=total_trend,
        mode='lines', name='Total Trend (Predicted)',
        line=dict(color='#2ca02c', width=2, dash='dash'),
        opacity=0.6,
        hovertemplate='<b>Date:</b> %{x|%d/%m/%Y}<br><b>Total Trend:</b> ₹%{y:,.0f}<extra></extra>'
    ))
    
    # ── GROWTH RATE ANNOTATIONS ─────────────────────────────────────
    # Calculate daily growth rates (slope of trend lines)
    shop_daily_growth = shop_coef[0]  # ₹ per day
    outer_daily_growth = outer_coef[0]
    total_daily_growth = total_coef[0]
    
    # Add annotation box with trend analysis
    trend_text = (
        f"<b>Daily Growth Rates (Trend):</b><br>"
        f"🏢 Shop: ₹{shop_daily_growth:,.0f}/day {'📈' if shop_daily_growth > 0 else '📉'}<br>"
        f"🤝 Outer: ₹{outer_daily_growth:,.0f}/day {'📈' if outer_daily_growth > 0 else '📉'}<br>"
        f"📊 Total: ₹{total_daily_growth:,.0f}/day {'📈' if total_daily_growth > 0 else '📉'}"
    )
    
    fig.add_annotation(
        text=trend_text,
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="black",
        borderwidth=1,
        font=dict(size=11),
        align="left",
        xanchor="left", yanchor="top"
    )
    
    # ── HEALTH STATUS INDICATOR ─────────────────────────────────────
    # Check if actual is following trend (within 10% tolerance)
    latest_shop_actual = d_data['Cumulative_Shop'].iloc[-1]
    latest_shop_trend = shop_trend[-1] if not np.isnan(shop_trend[-1]) else latest_shop_actual
    
    if not np.isnan(latest_shop_trend) and latest_shop_trend != 0:
        shop_variance = abs(latest_shop_actual - latest_shop_trend) / latest_shop_trend * 100
    else:
        shop_variance = 0
    
    health_status = "✅ ON TRACK" if shop_variance < 10 else "⚠️ DEVIATION" if shop_variance < 20 else "🔴 OFF TRACK"
    health_color = "green" if shop_variance < 10 else "orange" if shop_variance < 20 else "red"
    
    fig.update_layout(
    title=(
        f"📈 Daily Cumulative Capital Growth — Actual vs Predicted Trend (Status: {health_status})"
    ),
    xaxis_title='Date',
    yaxis_title='Cumulative Capital Amount (₹)',
    hovermode='x unified',
    legend=dict(orientation='v', x=0.72, y=0.99),
    height=600,
    template='plotly_white'
    )
    
    # Add annotations separately
    fig.add_annotation(
        text=f"<b>{health_status}</b><br>Variance: {shop_variance:.1f}%",
        xref="paper", yref="paper",
        x=0.98, y=0.98,
        showarrow=False,
        bgcolor=health_color,
        font=dict(size=12, color='white'),
        borderwidth=2,
        xanchor="right", yanchor="top",
        bordercolor=health_color
    )
    
    return fig