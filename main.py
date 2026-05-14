from preprocessing import run_preprocessing
from safety_stock import build_safety_stock_table, get_current_stock
from forecast import forecast_all_items
from milp_model import optimize_all_items
from report_generator import generate_report
from database import initialise_database, save_run

from datetime import datetime, timedelta


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_pipeline(excel_file, progress_callback=None):
    """
    Full pipeline from Excel file to output report.

    Stages:
        1. Initialise database
        2. Load and clean all monthly sheets
        3. Calculate safety stock and reorder points
        4. Forecast demand using XGBoost
        5. Optimize order quantities using MILP
        6. Generate Excel report
        7. Save results to database

    Parameters:
        excel_file:        path to the Excel workbook
        progress_callback: optional function(str) to send
                           status messages back to the UI

    Returns:
        output_path: path to the generated report file
        summary:     dict with counts for display in UI
    """

    def update(msg):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    # Stage 1
    update("Initialising database...")
    initialise_database()

    # Stage 2
    update("Loading and cleaning data...")
    full_df, monthly_df = run_preprocessing(excel_file)

    # Stage 3
    update("Calculating safety stock and reorder points...")
    reorder_df = build_safety_stock_table(full_df)
    current_stock_df = get_current_stock(full_df)

    # Stage 4
    update("Running demand forecasting (XGBoost)...")
    forecast_df = forecast_all_items(full_df)

    # Stage 5
    update("Running inventory optimization (MILP)...")
    results_df, all_results_df = optimize_all_items(
        forecast_df, reorder_df, current_stock_df
    )

    # Stage 6
    update("Generating Excel report...")
    reorder_by = (
        datetime.today() + timedelta(days=4)
    ).strftime('%d/%m/%Y')

    output_path = generate_report(results_df, all_results_df)

    # Stage 7
    update("Saving results to database...")
    run_id = save_run(results_df, all_results_df, reorder_by)

    summary = {
        'total':      len(all_results_df),
        'reorder':    len(results_df),
        'sufficient': len(all_results_df) - len(results_df),
        'output':     output_path,
        'run_id':     run_id
    }

    update("Pipeline complete.")

    return output_path, summary


# ============================================================
# ALLOW RUNNING DIRECTLY FROM TERMINAL WITHOUT UI
# ============================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        excel_file = r'C:\project year 4\progs\data\Stock Card - Main.xlsx'
    else:
        excel_file = sys.argv[1]

    print(f"Running pipeline on: {excel_file}")
    print("=" * 50)

    output_path, summary = run_pipeline(excel_file)

    print("\n" + "=" * 50)
    print("RESULTS SUMMARY")
    print("=" * 50)
    print(f"Total products analyzed:        {summary['total']}")
    print(f"Products requiring reorder:     {summary['reorder']}")
    print(f"Products with sufficient stock: {summary['sufficient']}")
    print(f"Run saved to database (ID):     {summary['run_id']}")
    print(f"Report saved to:                {summary['output']}")