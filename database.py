import sqlite3
import os
from datetime import datetime
import sys

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(get_base_path(), 'inventory_optimizer.db')

# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    """
    Returns a connection to the SQLite database.
    Creates the database file if it does not exist.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# INITIALISE DATABASE
# ============================================================

def initialise_database():
    """
    Creates the database tables if they do not already exist.
    Safe to call on every application start.

    Tables:
        RunSummary    — one row per optimization run
        ReorderReport — one row per item per run
    """

    conn = get_connection()
    cursor = conn.cursor()

    # RunSummary: records metadata about each pipeline execution
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS RunSummary (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date                TEXT    NOT NULL,
            total_analyzed          INTEGER NOT NULL,
            items_requiring_reorder INTEGER NOT NULL,
            items_sufficient        INTEGER NOT NULL
        )
    """)

    # ReorderReport: records every item flagged for reorder in a run
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ReorderReport (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id            INTEGER NOT NULL,
            item_code         TEXT    NOT NULL,
            item_description  TEXT    NOT NULL,
            unit_of_measure   TEXT    NOT NULL,
            forecasted_demand REAL    NOT NULL,
            current_stock     REAL    NOT NULL,
            recommended_order REAL    NOT NULL,
            urgency           TEXT    NOT NULL,
            reorder_by        TEXT    NOT NULL,
            FOREIGN KEY (run_id) REFERENCES RunSummary (id)
        )
    """)

    conn.commit()
    conn.close()

    print(f"Database initialised: {DB_PATH}")


# ============================================================
# SAVE RUN RESULTS
# ============================================================

def save_run(results_df, all_results_df, reorder_by_date):
    """
    Saves the results of one optimization run to the database.

    Inserts one row into RunSummary and one row per
    reorder item into ReorderReport.

    Parameters:
        results_df:      DataFrame of items requiring reorder
        all_results_df:  DataFrame of all items analyzed
        reorder_by_date: string date for the reorder deadline

    Returns:
        run_id: integer ID of the saved run
    """

    conn = get_connection()
    cursor = conn.cursor()

    run_date = datetime.today().strftime('%d/%m/%Y %H:%M')
    total = len(all_results_df)
    requiring = len(results_df)
    sufficient = total - requiring

    # Insert run summary
    cursor.execute("""
        INSERT INTO RunSummary
            (run_date, total_analyzed, items_requiring_reorder, items_sufficient)
        VALUES (?, ?, ?, ?)
    """, (run_date, total, requiring, sufficient))

    run_id = cursor.lastrowid

    # Insert one row per reorder item
    for _, row in results_df.iterrows():

        current = row['Current_Stock']
        forecast = row['Forecasted_Demand']

        if current <= 0:
            urgency = 'URGENT'
        elif current < forecast * 0.3:
            urgency = 'LOW'
        else:
            urgency = 'MONITOR'

        cursor.execute("""
            INSERT INTO ReorderReport (
                run_id, item_code, item_description, unit_of_measure,
                forecasted_demand, current_stock, recommended_order,
                urgency, reorder_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            str(row['Item Code']),
            str(row['Item Description']),
            str(row['Unit of Measure']),
            round(float(row['Forecasted_Demand']), 2),
            round(float(row['Current_Stock']), 2),
            round(float(row['Recommended_Order']), 2),
            urgency,
            reorder_by_date
        ))

    conn.commit()
    conn.close()

    print(f"Run saved to database (run_id={run_id})")

    return run_id


# ============================================================
# RETRIEVE HISTORY
# ============================================================

def get_run_history():
    """
    Returns a list of all past runs from RunSummary.
    Used to display history in the UI or reports.

    Returns:
        list of dicts with run metadata
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, run_date, total_analyzed,
               items_requiring_reorder, items_sufficient
        FROM RunSummary
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            'run_id':    r[0],
            'run_date':  r[1],
            'total':     r[2],
            'requiring': r[3],
            'sufficient':r[4]
        }
        for r in rows
    ]


def get_run_detail(run_id):
    """
    Returns all reorder items for a specific run.

    Parameters:
        run_id: integer ID from RunSummary

    Returns:
        list of dicts with item-level detail
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT item_code, item_description, unit_of_measure,
               forecasted_demand, current_stock,
               recommended_order, urgency, reorder_by
        FROM ReorderReport
        WHERE run_id = ?
        ORDER BY
            CASE urgency
                WHEN 'URGENT'  THEN 1
                WHEN 'LOW'     THEN 2
                WHEN 'MONITOR' THEN 3
            END,
            current_stock ASC
    """, (run_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            'item_code':         r[0],
            'item_description':  r[1],
            'unit_of_measure':   r[2],
            'forecasted_demand': r[3],
            'current_stock':     r[4],
            'recommended_order': r[5],
            'urgency':           r[6],
            'reorder_by':        r[7]
        }
        for r in rows
    ]


def get_latest_run_id():
    """
    Returns the ID of the most recent run.
    Returns None if no runs exist yet.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(id) FROM RunSummary")
    result = cursor.fetchone()[0]
    conn.close()

    return result


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == '__main__':

    initialise_database()

    history = get_run_history()

    if history:
        print(f"\nRun history ({len(history)} runs):")
        for run in history:
            print(
                f"  Run {run['run_id']} | {run['run_date']} | "
                f"Analyzed: {run['total']} | "
                f"Requiring reorder: {run['requiring']}"
            )

        latest = get_run_detail(history[0]['run_id'])
        print(f"\nLatest run — {len(latest)} items:")
        for item in latest[:5]:
            print(
                f"  [{item['urgency']:7}] "
                f"{item['item_description'][:40]:40} "
                f"Order: {item['recommended_order']}"
            )
    else:
        print("\nNo runs saved yet. Run the pipeline first.")
