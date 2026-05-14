import pandas as pd
import numpy as np
from pulp import (
    LpProblem, LpMinimize, LpVariable,
    LpBinary, lpSum, value, PULP_CBC_CMD
)
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================

# Cost parameters
# These are standard assumptions — cite in methodology
HOLDING_COST_RATE = 0.02     # 2% of item value per month
DEFAULT_UNIT_COST = 100      # Default unit cost in KES if unknown
ORDERING_COST = 500          # Fixed cost per order placed (KES)
STOCKOUT_PENALTY = 200       # Penalty per unit of unmet demand (KES)

# Lead time
LEAD_TIME_DAYS = 4


# ============================================================
# MILP MODEL FOR ONE ITEM
# ============================================================

def optimize_single_item(
    item_desc,
    forecasted_demand,
    current_stock,
    reorder_point,
    safety_stock,
    unit_cost=DEFAULT_UNIT_COST
):
    """
    Solves a single-period MILP inventory optimization problem
    for one item.

    Decision Variables:
        Q: order quantity (continuous, >= 0)
        Y: binary order decision (1 = place order, 0 = do not)

    Objective:
        Minimize total cost = holding cost + ordering cost
                            + stockout penalty

    Constraints:
        1. Inventory balance: ending stock >= 0
        2. Order activation: Q <= M * Y (order only if Y=1)
        3. Demand satisfaction: current + order >= forecast

    Parameters:
        item_desc:         item name (for labeling)
        forecasted_demand: predicted demand for next month
        current_stock:     current closing balance
        reorder_point:     threshold below which order is triggered
        safety_stock:      internal buffer (not shown in output)
        unit_cost:         cost per unit (KES)

    Returns:
        dict with: recommended_order, total_cost, order_decision, status
    """
    # Guard against NaN or inf values
    if any(
        pd.isna(v) or v == float('inf') or v == float('-inf')
        for v in [forecasted_demand, current_stock, reorder_point, safety_stock]
    ):
        return {
            'Recommended_Order': 0,
            'Total_Cost': 0,
            'Order_Decision': 'Skipped — invalid data',
            'Status': 'Skipped'
        }
    # If forecasted demand is zero or near zero there is nothing to order regardless of safety stock
    if forecasted_demand < 1:
        return {
            'Recommended_Order': 0,
            'Total_Cost': 0,
            'Order_Decision': 'No order needed',
            'Status': 'Zero demand forecast'
        }

    # If current stock is above reorder point, no order needed
    if current_stock > reorder_point:
        return {
            'Recommended_Order': 0,
            'Total_Cost': 0,
            'Order_Decision': 'No order needed',
            'Status': 'Sufficient stock'
        }

    # Big M constant for order activation constraint
    # Set to a large but reasonable number
    M = max(forecasted_demand * 10, 10000)

    # Create MILP problem
    model = LpProblem(name="inventory_optimization", sense=LpMinimize)

    # Decision variables
    Q = LpVariable("order_quantity", lowBound=0, cat='Continuous')
    Y = LpVariable("order_decision", cat='Binary')

    # Holding cost: cost of carrying leftover inventory
    holding_cost = HOLDING_COST_RATE * unit_cost * (
        current_stock + Q - forecasted_demand
    )

    # Ordering cost: fixed cost only if an order is placed
    ordering_cost = ORDERING_COST * Y

    # Shortfall variable: unmet demand if stock insufficient
    S = LpVariable("shortfall", lowBound=0, cat='Continuous')
    stockout_cost = STOCKOUT_PENALTY * S

    # Objective function
    model += holding_cost + ordering_cost + stockout_cost

    # Constraint 1: Inventory balance
    # Ending stock = current + ordered - demand + shortfall
    model += current_stock + Q - forecasted_demand + S >= 0

    # Constraint 2: Order activation (Big M method)
    # If Y=0 then Q must be 0
    model += Q <= M * Y

    # Constraint 3: Must cover at least safety stock
    model += current_stock + Q >= safety_stock

    # Solve silently
    model.solve(PULP_CBC_CMD(msg=0))

    # Extract results
    if model.status == 1:
        recommended_order = max(round(value(Q), 0), 0)
        total_cost = round(value(model.objective), 2)
        order_decision = 'Order recommended' if value(Y) > 0.5 else 'No order'

        return {
            'Recommended_Order': recommended_order,
            'Total_Cost': total_cost,
            'Order_Decision': order_decision,
            'Status': 'Optimal'
        }
    else:
        # Fallback if solver fails: order enough to cover demand
        fallback_order = max(forecasted_demand - current_stock, 0)
        return {
            'Recommended_Order': round(fallback_order, 0),
            'Total_Cost': None,
            'Order_Decision': 'Order recommended (fallback)',
            'Status': 'Solver fallback'
        }


# ============================================================
# OPTIMIZE ALL ITEMS
# ============================================================

def optimize_all_items(forecast_df, reorder_df, current_stock_df):
    """
    Runs the MILP optimization for every item and
    returns only items that require a reorder.

    Parameters:
        forecast_df:      output from forecast_all_items()
        reorder_df:       output from build_safety_stock_table()
        current_stock_df: output from get_current_stock()

    Returns:
        results_df: DataFrame of items requiring reorder
        all_results_df: DataFrame of all items including those not needing reorder
    """

    print("=" * 50)
    print("RUNNING MILP OPTIMIZATION")
    print("=" * 50)

    # Merge all required data
    merged = forecast_df.merge(
        reorder_df[[
            'Item Code', 'Unit of Measure',
            'Safety_Stock', 'Reorder_Point'
        ]],
        on=['Item Code', 'Unit of Measure'],
        how='left'
    )

    merged = merged.merge(
        current_stock_df[[
            'Item Code', 'Unit of Measure', 'Current_Stock'
        ]],
        on=['Item Code', 'Unit of Measure'],
        how='left'
    )

    merged = merged.drop_duplicates(
        subset=['Item Code', 'Unit of Measure']
    )
    # Fill any missing values
    merged['Current_Stock'] = pd.to_numeric(
        merged['Current_Stock'], errors='coerce'
    ).fillna(0)
    merged['Safety_Stock'] = pd.to_numeric(
        merged['Safety_Stock'], errors='coerce'
    ).fillna(0)
    merged['Reorder_Point'] = pd.to_numeric(
        merged['Reorder_Point'], errors='coerce'
    ).fillna(0)
    merged['Forecasted_Demand'] = pd.to_numeric(
        merged['Forecasted_Demand'], errors='coerce'
    ).fillna(0)

    # Drop any rows that still have NaN or inf after cleaning
    merged = merged.replace([float('inf'), float('-inf')], 0)
    merged = merged.dropna(subset=[
        'Forecasted_Demand', 'Current_Stock',
        'Safety_Stock', 'Reorder_Point'
    ])

    print(f"Items going into optimization: {len(merged)}")

    results = []

    for _, row in merged.iterrows():

        opt_result = optimize_single_item(
            item_desc=row['Item Description'],
            forecasted_demand=row['Forecasted_Demand'],
            current_stock=row['Current_Stock'],
            reorder_point=row['Reorder_Point'],
            safety_stock=row['Safety_Stock']
        )

        results.append({
            'Item Code': row['Item Code'],
            'Item Description': row['Item Description'],
            'Unit of Measure': row['Unit of Measure'],
            'Forecasted_Demand': row['Forecasted_Demand'],
            'Current_Stock': row['Current_Stock'],
            'Recommended_Order': opt_result['Recommended_Order'],
            'Optimization_Status': opt_result['Status']
        })

    all_results_df = pd.DataFrame(results)

    # Filter to only items needing reorder for output report
    results_df = all_results_df[
        all_results_df['Recommended_Order'] > 0
    ].reset_index(drop=True)

    print(f"\nOptimization complete")
    print(f"  Total items analyzed:       {len(all_results_df)}")
    print(f"  Items requiring reorder:    {len(results_df)}")
    print(f"  Items with sufficient stock: {len(all_results_df) - len(results_df)}")

    return results_df, all_results_df


if __name__ == '__main__':
    from preprocessing import run_preprocessing
    from safety_stock import build_safety_stock_table, get_current_stock
    from forecast import forecast_all_items

    full_df, monthly_df = run_preprocessing()

    reorder_df = build_safety_stock_table(full_df)
    current_stock_df = get_current_stock(full_df)
    forecast_df = forecast_all_items(full_df)

    results_df, all_results_df = optimize_all_items(
        forecast_df, reorder_df, current_stock_df
    )

    print("\nItems requiring reorder (first 10):")
    print(results_df.head(10).to_string(index=False))
