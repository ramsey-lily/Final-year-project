import pandas as pd
import numpy as np

# ============================================================
# CONFIGURATION
# ============================================================

# 95% service level — standard academic assumption
Z_SCORE = 1.645

# Lead time: 4 days expressed as fraction of a 30-day month
LEAD_TIME_DAYS = 4
LEAD_TIME_MONTHS = LEAD_TIME_DAYS / 30


# ============================================================
# SAFETY STOCK CALCULATION
# ============================================================

def calculate_safety_stock(demand_series):
    """
    Calculates safety stock for one item using the formula:
    SS = Z x sigma x sqrt(lead_time)

    Where:
        Z     = service level factor (1.645 for 95%)
        sigma = standard deviation of monthly demand
        LT    = lead time as fraction of month

    Parameters:
        demand_series: Series of monthly OUT values for one item

    Returns:
        safety_stock: float
    """

    sigma = demand_series.std()

    # Handle edge cases
    if pd.isna(sigma) or sigma == 0:
        # If demand never varies, use 10% of mean as minimal buffer
        mean = demand_series.mean()
        sigma = mean * 0.1 if not pd.isna(mean) else 0

    safety_stock = Z_SCORE * sigma * np.sqrt(LEAD_TIME_MONTHS)

    return round(max(safety_stock, 0), 2)


# ============================================================
# REORDER POINT CALCULATION
# ============================================================

def calculate_reorder_point(avg_daily_demand, safety_stock):
    """
    Calculates the reorder point for one item.
    Reorder Point = (avg daily demand x lead time days) + safety stock

    When current stock falls below this value,
    the system recommends placing an order.

    Parameters:
        avg_daily_demand: average units demanded per day
        safety_stock: buffer stock calculated from safety_stock fn

    Returns:
        reorder_point: float
    """

    reorder_point = (avg_daily_demand * LEAD_TIME_DAYS) + safety_stock

    return round(max(reorder_point, 0), 2)


# ============================================================
# BUILD SAFETY STOCK TABLE FOR ALL ITEMS
# ============================================================

def build_safety_stock_table(full_df):
    """
    Computes safety stock and reorder point for every item.
    This table is used internally by the MILP model.
    It is never shown directly in the output report.

    Parameters:
        full_df: cleaned full DataFrame from preprocessing

    Returns:
        reorder_df: DataFrame with one row per item containing:
                    Item Code, Item Description, Unit of Measure,
                    Avg_Monthly_Demand, Avg_Daily_Demand,
                    Safety_Stock, Reorder_Point
    """
    avg_monthly = (
        full_df
        .groupby(['Item Code', 'Unit of Measure'], sort=False)
        .agg(
            Item_Description=('Item Description', lambda x: x.value_counts().index[0]),
            Avg_Monthly_Demand=('Out', 'mean')
        )
        .reset_index()
        .rename(columns={'Item_Description': 'Item Description'})
    )

    avg_monthly['Avg_Daily_Demand'] = (
        avg_monthly['Avg_Monthly_Demand'] / 30
    ).round(4)

    safety_stock = (
        full_df
        .groupby(['Item Code', 'Unit of Measure'])['Out']
        .apply(calculate_safety_stock)
        .reset_index()
        .rename(columns={'Out': 'Safety_Stock'})
    )

    reorder_df = avg_monthly.merge(
        safety_stock[['Item Code', 'Unit of Measure', 'Safety_Stock']],
        on=['Item Code', 'Unit of Measure'],
        how='left'
    )

    reorder_df['Reorder_Point'] = reorder_df.apply(
        lambda row: calculate_reorder_point(
            row['Avg_Daily_Demand'],
            row['Safety_Stock']
        ),
        axis=1
    )

    reorder_df = reorder_df.drop_duplicates(
        subset=['Item Code', 'Unit of Measure']
    )

    return reorder_df


# ============================================================
# GET CURRENT STOCK PER ITEM
# ============================================================

def get_current_stock(full_df):
    """
    Gets the most recent closing balance per item.
    This represents current stock at time of running the model.

    Parameters:
        full_df: cleaned full DataFrame

    Returns:
        current_stock_df: DataFrame with Item Description and Current_Stock
    """

    # Get the last row per item based on sort order
    # Sort order was already set correctly in preprocessing
    current_stock_df = (
        full_df
        .groupby(['Item Code', 'Unit of Measure'], sort=False)
        .agg(
            Item_Description=('Item Description', lambda x: x.value_counts().index[0]),
            Current_Stock=('Closing Balance', 'last')
        )
        .reset_index()
        .rename(columns={'Item_Description': 'Item Description'})
    )
     # Ensure current stock is never negative
    current_stock_df['Current_Stock'] = current_stock_df['Current_Stock'].clip(lower=0)

    return current_stock_df


if __name__ == '__main__':
    from preprocessing import run_preprocessing

    full_df, monthly_df = run_preprocessing()

    print("\n" + "=" * 50)
    print("COMPUTING SAFETY STOCK AND REORDER POINTS")
    print("=" * 50)

    reorder_df = build_safety_stock_table(full_df)
    current_stock_df = get_current_stock(full_df)

    print("\nReorder table (first 10 items):")
    print(reorder_df.head(10).to_string(index=False))

    print("\nCurrent stock (first 10 items):")
    print(current_stock_df.head(10).to_string(index=False))

    # Sanity check on test item
    test_item = 'Angle Board Size: 2.3M'
    test_row = reorder_df[reorder_df['Item Description'] == test_item]

    if not test_row.empty:
        print(f"\nTest item — {test_item}:")
        print(test_row.to_string(index=False))
    else:
        print(f"\nItem '{test_item}' not found. Items containing 'Angle':")
        matches = full_df[
            full_df['Item Description'].str.contains('Angle', case=False, na=False)
        ]['Item Description'].unique()
        print(matches)
