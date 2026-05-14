import pandas as pd
import numpy as np

# ============================================================
# CONFIGURATION
# ============================================================

# Use a raw string for Windows paths to avoid escape sequence warning
EXCEL_FILE = r'C:\project year 4\progs\data\Stock Card - Main.xlsx'

MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]

REQUIRED_COLUMNS = [
    'Item Code',
    'Item Description',
    'Unit of Measure',
    'Opening Balance',
    'In',
    'Out',
    'Closing Balance'
]

NUMERIC_COLUMNS = [
    'Opening Balance', 'In', 'Out', 'Closing Balance'
]

# Correct month order for sorting
MONTH_ORDER = [
    'November 17', 'December 17',
    'January 18', 'February 18', 'March 18', 'April 18',
    'May 18', 'June 18', 'July 18', 'August 18',
    'September 18', 'October 18', 'November 18'
]


# ============================================================
# LOAD ALL MONTHLY SHEETS
# ============================================================

def load_all_monthly_sheets(excel_file=EXCEL_FILE):
    """
    Loads all monthly inventory sheets from the Excel workbook
    and stacks them into one clean DataFrame.
    """

    xl = pd.ExcelFile(excel_file)
    all_sheets = xl.sheet_names

    # Detect monthly sheets by checking if any month name
    # appears in the sheet name (strip spaces first)
    monthly_sheets = [
        s for s in all_sheets
        if any(m in s.strip() for m in MONTH_NAMES)
    ]

    print(f"Monthly sheets found: {len(monthly_sheets)}")
    for s in monthly_sheets:
        print(f"  '{s}'")

    all_data = []

    for sheet in monthly_sheets:
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet)

            # Strip whitespace from column names
            df.columns = df.columns.str.strip()

            # Drop unnamed columns
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

            # Check required columns exist
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                print(f"Skipped '{sheet}': missing columns {missing}")
                print(f"  Found columns: {df.columns.tolist()}")
                continue

            df = df[REQUIRED_COLUMNS].copy()

            # Use stripped sheet name as month tag
            df['Month'] = sheet.strip()

            all_data.append(df)
            print(f"Loaded: {sheet.strip()}")

        except Exception as e:
            print(f"Error in '{sheet}': {e}")

    if len(all_data) == 0:
        raise ValueError("No sheets loaded. Check your Excel file.")

    full_df = pd.concat(all_data, ignore_index=True)

    return full_df


# ============================================================
# CLEAN THE DATA
# ============================================================

def clean_data(full_df):
    """
    Cleans the stacked DataFrame.
    """

    # Clean numeric columns
    for col in NUMERIC_COLUMNS:
        full_df[col] = pd.to_numeric(
            full_df[col], errors='coerce'
        ).fillna(0)
    # Clamp negative values closing balances are manually entered values Negative values are not physically valid
    full_df['Closing Balance'] = full_df['Closing Balance'].clip(lower=0)
    # Strip whitespace from text columns
    full_df['Item Code'] = full_df['Item Code'].astype(str).str.strip()
    full_df['Item Description'] = (
        full_df['Item Description'].astype(str).str.strip()
    )
    full_df['Unit of Measure'] = (
        full_df['Unit of Measure'].astype(str).str.strip()
    )
    full_df['Month'] = full_df['Month'].astype(str).str.strip()

    # Remove blank rows
    full_df = full_df[full_df['Item Description'] != '']
    full_df = full_df[full_df['Item Description'] != 'nan']
    full_df = full_df[full_df['Item Code'] != '']
    full_df = full_df[full_df['Item Code'] != 'nan']

    # Remove separator rows (dashes, equals signs etc)
    full_df = full_df[
        ~full_df['Item Description'].str.match(r'^[-=\s]+$', na=False)
    ]

    # Remove rows where Item Code looks like a total row
    full_df = full_df[
        ~full_df['Item Code'].str.lower().str.contains(
            'total|grand|sum', na=False
        )
    ]

    # Sort by month using MONTH_ORDER
    # Only include months that actually exist in the data
    existing_months = [
        m for m in MONTH_ORDER
        if m in full_df['Month'].unique()
    ]

    # Add any months not in MONTH_ORDER at the end
    extra_months = [
        m for m in full_df['Month'].unique()
        if m not in MONTH_ORDER
    ]

    final_order = existing_months + extra_months

    # Map each month to a sort number
    month_sort = {m: i for i, m in enumerate(final_order)}
    full_df['_month_sort'] = full_df['Month'].map(month_sort)
    full_df = full_df.sort_values(
        ['_month_sort', 'Item Code']
    ).drop(columns=['_month_sort']).reset_index(drop=True)

    print(f"\nData cleaned successfully")
    print(f"Total rows:    {len(full_df)}")
    print(f"Unique items:  {full_df['Item Description'].nunique()}")
    print(f"Months loaded: {full_df['Month'].nunique()}")
    print(f"Months in data: {full_df['Month'].unique().tolist()}")

    return full_df


# ============================================================
# PREPARE MONTHLY AGGREGATES
# ============================================================

def get_monthly_aggregates(full_df):
    """
    Aggregates data by item and month.
    Produces one row per item per month.
    Used for ML feature engineering.
    """
     #Normalize description per Item Code + Unit combination
    # Takes most common description to handle minor typos
    dominant_desc = (
        full_df
        .groupby(['Item Code', 'Unit of Measure'])['Item Description']
        .agg(lambda x: x.value_counts().index[0])
        .reset_index()
        .rename(columns={'Item Description': 'Dominant_Desc'})
    )

    full_df = full_df.merge(
        dominant_desc,
        on=['Item Code', 'Unit of Measure'],
        how='left'
    )
    full_df['Item Description'] = full_df['Dominant_Desc']
    full_df = full_df.drop(columns=['Dominant_Desc'])

    # Group by Item Code + Unit of Measure + Month
    monthly_df = (
        full_df
        .groupby(
            ['Item Code', 'Unit of Measure', 'Month'],
            sort=False
        )
        .agg(
            Item_Description=('Item Description', 'first'),
            Opening_Balance=('Opening Balance', 'first'),
            Total_In=('In', 'sum'),
            Total_Out=('Out', 'sum'),
            Closing_Balance=('Closing Balance', 'last')
        )
        .reset_index()
        .rename(columns={'Item_Description': 'Item Description'})
    )

    return monthly_df


# ============================================================
# RUN PREPROCESSING PIPELINE
# ============================================================

def run_preprocessing(excel_file=EXCEL_FILE):
    """
    Full preprocessing pipeline.
    Returns cleaned full_df and monthly_df.
    """

    print("=" * 50)
    print("LOADING DATA")
    print("=" * 50)

    full_df = load_all_monthly_sheets(excel_file)
    full_df = clean_data(full_df)

    # Diagnostic check
    print(f"\nOut column total:          {full_df['Out'].sum():,.1f}")
    print(f"Non-zero Out rows:         {(full_df['Out'] > 0).sum()}")

    monthly_df = get_monthly_aggregates(full_df)

    print(f"\nMonthly aggregates shape:  {monthly_df.shape}")
    print(f"Monthly Total_Out sum:     {monthly_df['Total_Out'].sum():,.1f}")

    # Quick check — show one item across all months to verify
    sample_item = full_df[full_df['Out'] > 0]['Item Description'].iloc[0]
    sample = monthly_df[
        monthly_df['Item Description'] == sample_item
    ][['Item Description', 'Month', 'Total_Out']]
    print(f"\nSample item across months ({sample_item}):")
    print(sample.to_string(index=False))

    return full_df, monthly_df


if __name__ == '__main__':
    full_df, monthly_df = run_preprocessing()
