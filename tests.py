import pandas as pd
from preprocessing import run_preprocessing

full_df, monthly_df = run_preprocessing()

item = 'Clear HD Printed Polythene Bags  - Enns - Size: 20"*32.5"*38\'*120g'

check = full_df[full_df['Item Description'] == item]
print(check[['Item Code', 'Item Description', 'Month', 'In', 'Out', 'Closing Balance']])
print(f"\nTotal rows: {len(check)}")