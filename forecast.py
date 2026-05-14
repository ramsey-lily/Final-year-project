import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================

# Minimum number of months of data required to train a model
MIN_MONTHS_REQUIRED = 4

# XGBoost hyperparameters
XGBOOST_PARAMS = {
    'n_estimators': 100,
    'learning_rate': 0.1,
    'max_depth': 3,
    'random_state': 42,
    'verbosity': 0
}


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def build_features(demand_series):
    """
    Creates time series features from a monthly demand series.
    These features are the inputs to the XGBoost model.

    Features created:
        lag1: demand from 1 month ago
        lag2: demand from 2 months ago
        lag3: demand from 3 months ago
        rolling_mean_3: average demand over last 3 months
        rolling_std_3: std deviation over last 3 months

    Parameters:
        demand_series: Series of monthly OUT values (ordered by time)

    Returns:
        feature_df: DataFrame with features and target
    """

    df = pd.DataFrame({'demand': demand_series.values})

    # Lag features
    df['lag1'] = df['demand'].shift(1)
    df['lag2'] = df['demand'].shift(2)
    df['lag3'] = df['demand'].shift(3)

    # Rolling statistics
    df['rolling_mean_3'] = df['demand'].shift(1).rolling(3).mean()
    df['rolling_std_3'] = df['demand'].shift(1).rolling(3).std().fillna(0)

    # Drop rows with NaN from lag creation
    df = df.dropna()

    return df


# ============================================================
# TRAIN MODEL FOR ONE ITEM
# ============================================================

def train_item_model(demand_series):
    """
    Trains an XGBoost regression model for one inventory item.

    Parameters:
        demand_series: ordered Series of monthly demand values

    Returns:
        model: trained XGBRegressor
        mae: mean absolute error on training data
        rmse: root mean squared error on training data
        feature_df: feature DataFrame used for training
    """

    feature_df = build_features(demand_series)

    if len(feature_df) < MIN_MONTHS_REQUIRED:
        return None, None, None, None

    feature_cols = ['lag1', 'lag2', 'lag3', 'rolling_mean_3', 'rolling_std_3']

    X = feature_df[feature_cols]
    y = feature_df['demand']

    model = XGBRegressor(**XGBOOST_PARAMS)
    model.fit(X, y)

    # Evaluate on training data
    y_pred = model.predict(X)
    mae = round(mean_absolute_error(y, y_pred), 2)
    rmse = round(np.sqrt(mean_squared_error(y, y_pred)), 2)

    return model, mae, rmse, feature_df


# ============================================================
# FORECAST NEXT MONTH FOR ONE ITEM
# ============================================================

def forecast_next_month(model, feature_df):
    """
    Uses the trained model to forecast demand for the next month.

    Parameters:
        model: trained XGBRegressor
        feature_df: feature DataFrame from training

    Returns:
        forecast: predicted demand for next month (float)
    """

    if model is None or feature_df is None:
        return None

    # Use the last row of features to predict the next period
    last_row = feature_df.iloc[-1]

    next_features = pd.DataFrame({
        'lag1': [last_row['demand']],
        'lag2': [last_row['lag1']],
        'lag3': [last_row['lag2']],
        'rolling_mean_3': [
            (last_row['demand'] + last_row['lag1'] + last_row['lag2']) / 3
        ],
        'rolling_std_3': [
            pd.Series([
                last_row['demand'],
                last_row['lag1'],
                last_row['lag2']
            ]).std()
        ]
    })

    forecast = model.predict(next_features)[0]

    # Forecast cannot be negative
    forecast = max(forecast, 0)

    return round(forecast, 2)


# ============================================================
# FORECAST ALL ITEMS
# ============================================================

def forecast_all_items(full_df):
    """
    Trains an XGBoost model and generates a 1-month demand
    forecast for every item in the dataset.

    Parameters:
        full_df: cleaned full DataFrame from preprocessing

    Returns:
        forecast_df: DataFrame with one row per item containing:
                     Item Code, Item Description, Unit of Measure,
                     Forecasted_Demand, MAE, RMSE, Status
    """

    print("=" * 50)
    print("RUNNING DEMAND FORECASTING")
    print("=" * 50) 
    items = (
        full_df[['Item Code', 'Item Description', 'Unit of Measure']]
        .groupby(['Item Code', 'Unit of Measure'])
        .agg(
            Item_Description=('Item Description', lambda x: x.value_counts().index[0])
        )
        .reset_index()
    )
    results = []
    for _, item_row in items.iterrows():

        item_code = item_row['Item Code']
        item_desc = item_row['Item_Description']
        unit      = item_row['Unit of Measure']

        # Filter by both Item Code AND Unit of Measure
        item_data = full_df[
            (full_df['Item Code'] == item_code) &
            (full_df['Unit of Measure'] == unit)
        ].sort_values('Month')

        demand_series = item_data['Out'].reset_index(drop=True)

        # Train model
        model, mae, rmse, feature_df = train_item_model(demand_series)

        if model is None:
            # Not enough data to model
            results.append({
                'Item Code': item_code,
                'Item Description': item_desc,
                'Unit of Measure': unit,
                'Forecasted_Demand': demand_series.mean(),
                'MAE': None,
                'RMSE': None,
                'Status': 'Insufficient data — used mean'
            })
            continue

        # Forecast next month
        forecast = forecast_next_month(model, feature_df)

        results.append({
            'Item Code': item_code,
            'Item Description': item_desc,
            'Unit of Measure': unit,
            'Forecasted_Demand': forecast,
            'MAE': mae,
            'RMSE': rmse,
            'Status': 'Forecasted'
        })

    forecast_df = pd.DataFrame(results)

    forecasted = len(forecast_df[forecast_df['Status'] == 'Forecasted'])
    fallback = len(forecast_df[forecast_df['Status'] != 'Forecasted'])

    print(f"\nForecasting complete")
    print(f"  Items forecasted with XGBoost: {forecasted}")
    print(f"  Items using mean fallback:     {fallback}")
    print(f"  Total items:                   {len(forecast_df)}")

    return forecast_df


if __name__ == '__main__':
    from preprocessing import run_preprocessing

    full_df, monthly_df = run_preprocessing()

    forecast_df = forecast_all_items(full_df)

    print("\nSample forecasts:")
    print(forecast_df.head(10).to_string(index=False))

    # Check test item
    test_item = 'Angle Board Size: 2.3M'
    test_row = forecast_df[forecast_df['Item Description'] == test_item]

    if not test_row.empty:
        print(f"\nTest item — {test_item}:")
        print(test_row.to_string(index=False))
    else:
        print(f"\nItem '{test_item}' not found")
