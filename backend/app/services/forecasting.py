"""
Feature 2 — revenue forecasting, implemented in NumPy only.

Why not Prophet / statsmodels
-----------------------------
Both are heavy installs (Prophet needs a C++ toolchain) and would make the
backend hard to deploy on a small Python host — the exact place this app runs.
For daily shop revenue, a recency-weighted trend plus weekday seasonality
captures nearly all of the signal, and every step of it is inspectable.

The model
---------
1. Build the zero-filled daily revenue series (a closed day is a real 0, not a
   missing value).
2. Fit a straight trend line by **weighted least squares**, weights decaying
   exponentially with a 14-day half-life, so last week matters more than a
   month ago.
3. Compute **weekday seasonal indices**: the median of ``actual ÷ trend`` per
   weekday, normalised to average 1.0 and clamped, so one festival Saturday
   can't triple every future Saturday.
4. Forecast ``ŷ(t) = trend(t) × index(weekday(t))``, floored at 0.
5. Confidence band from the in-sample residual spread:
   ``ŷ ± 1.28 σ √(1 + h/n)`` — an 80% interval that widens with the horizon.
6. **Backtest**: hold out the last 7 days, forecast them from the rest, and
   report accuracy as ``100 − MAPE`` so the user can see how much to trust it.

Honesty rules
-------------
Under ``MIN_DAYS_FOR_FORECAST`` days of history the response comes back with
``available=false`` and a reason instead of a line on a chart. Between that and
``MIN_DAYS_FOR_SEASONALITY`` the trend is fitted but weekday seasonality is
switched off, because you cannot estimate seven weekday effects from ten days.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.schemas import ForecastPoint, ForecastResponse, ItemForecast
from app.services.sales_calculations import _prepare, _zero_fill_daily
from app.utils.safe_json import safe_float

# ── Tuning constants ────────────────────────────────────────────────────────

#: Below this many days of history, no forecast is produced at all.
MIN_DAYS_FOR_FORECAST = 14
#: Below this many days, the trend is used without weekday seasonality.
MIN_DAYS_FOR_SEASONALITY = 21
#: Recency weighting: a day this old counts half as much as today.
WEIGHT_HALF_LIFE_DAYS = 14.0
#: Weekday indices are clamped here so a single outlier day can't dominate.
SEASONAL_INDEX_CLAMP = (0.3, 3.0)
#: z for an 80% two-sided interval (chosen over 95% to keep the band readable).
Z_80_PERCENT = 1.2816
#: Days held back for the accuracy backtest.
BACKTEST_DAYS = 7
#: A trend flatter than this share of the daily average is reported as "flat".
FLAT_TREND_RATIO = 0.01
#: Cap on how many items get an individual demand forecast.
MAX_ITEM_FORECASTS = 20


def compute_forecast(df: pd.DataFrame, horizon_days: int = 14) -> ForecastResponse:
    """
    Project revenue ``horizon_days`` into the future from an already-filtered
    slice, and forecast per-item demand over the same period.

    Returns ``available=False`` with a plain-language ``reason`` whenever the
    history is too short to model honestly.
    """
    horizon = max(1, min(int(horizon_days), 90))

    if df.empty:
        return ForecastResponse(
            available=False,
            reason="There are no transactions in this period to forecast from.",
            horizon_days=horizon,
        )

    prepped = _prepare(df)
    series = _daily_series(prepped)
    history_days = len(series)

    if history_days < MIN_DAYS_FOR_FORECAST:
        return ForecastResponse(
            available=False,
            reason=(
                f"Only {history_days} day(s) of sales history here. A forecast needs at least "
                f"{MIN_DAYS_FOR_FORECAST} days to be meaningful — try the 'All Time' filter or "
                "upload a longer export."
            ),
            horizon_days=horizon,
        )

    dates = pd.to_datetime(series["_day"])
    values = series["revenue"].astype(float).to_numpy()
    positions = np.arange(history_days, dtype=float)

    # ── Trend ──
    slope, intercept = _weighted_linear_fit(positions, values)
    fitted = intercept + slope * positions

    # ── Seasonality ──
    use_seasonality = history_days >= MIN_DAYS_FOR_SEASONALITY
    weekday_indices = (
        _weekday_indices(dates, values, fitted) if use_seasonality else {}
    )

    # ── In-sample residual spread → confidence band width ──
    seasonal_fit = fitted * _index_vector(dates, weekday_indices)
    residual_sigma = float(np.std(values - seasonal_fit)) if history_days > 2 else 0.0

    # ── Points: history (actuals) followed by the projection ──
    points: list[ForecastPoint] = [
        ForecastPoint(date=str(day.date()), actual=safe_float(value, default=0.0), is_future=False)
        for day, value in zip(dates, values)
    ]

    last_date = dates.iloc[-1]
    expected_total = 0.0
    lower_total = 0.0
    upper_total = 0.0

    for step in range(1, horizon + 1):
        future_date = last_date + pd.Timedelta(days=step)
        position = history_days - 1 + step
        base = intercept + slope * position
        index = weekday_indices.get(future_date.strftime("%a"), 1.0)
        # Revenue can't be negative, so a falling trend flattens at zero
        # instead of predicting the shop paying customers.
        point_forecast = max(base * index, 0.0)
        # Uncertainty grows with distance from the last observed day.
        spread = Z_80_PERCENT * residual_sigma * np.sqrt(1.0 + step / history_days)

        expected_total += point_forecast
        lower_total += max(point_forecast - spread, 0.0)
        upper_total += point_forecast + spread

        points.append(
            ForecastPoint(
                date=str(future_date.date()),
                forecast=safe_float(point_forecast, default=0.0),
                lower=safe_float(max(point_forecast - spread, 0.0), default=0.0),
                upper=safe_float(point_forecast + spread, default=0.0),
                is_future=True,
            )
        )

    # Bridge point: repeat the last actual as a forecast value too, so the
    # dashed projection line starts exactly where the solid line ends instead
    # of leaving a visual gap.
    points[history_days - 1] = points[history_days - 1].model_copy(
        update={"forecast": safe_float(values[-1], default=0.0)}
    )

    daily_average = float(np.mean(values))
    direction = "flat"
    if abs(slope) > max(daily_average * FLAT_TREND_RATIO, 1e-9):
        direction = "rising" if slope > 0 else "falling"

    return ForecastResponse(
        available=True,
        horizon_days=horizon,
        points=points,
        expected_revenue=safe_float(expected_total, default=0.0) or 0.0,
        expected_revenue_lower=safe_float(lower_total, default=0.0) or 0.0,
        expected_revenue_upper=safe_float(upper_total, default=0.0) or 0.0,
        daily_average=safe_float(daily_average, default=0.0) or 0.0,
        trend_per_day=safe_float(slope, default=0.0) or 0.0,
        trend_direction=direction,
        accuracy_pct=_backtest_accuracy(dates, values),
        seasonality_applied=use_seasonality,
        weekday_indices={k: safe_float(v, digits=3, default=1.0) or 1.0 for k, v in weekday_indices.items()},
        item_forecasts=_item_forecasts(prepped, horizon),
        reason=(
            None
            if use_seasonality
            else (
                f"Weekday patterns need {MIN_DAYS_FOR_SEASONALITY}+ days of history, so this "
                "projection uses the overall trend only."
            )
        ),
    )


# ── Model pieces ────────────────────────────────────────────────────────────


def _daily_series(prepped: pd.DataFrame) -> pd.DataFrame:
    """Zero-filled daily revenue for the slice, oldest day first."""
    daily = (
        prepped.assign(_day=prepped["Date"].dt.date)
        .groupby("_day", as_index=False)
        .agg(revenue=("_row_revenue", "sum"))
        .sort_values("_day")
    )
    return _zero_fill_daily(daily, prepped["Date"].min(), prepped["Date"].max())


def _weighted_linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """
    Weighted least squares fit of ``y = intercept + slope·x``.

    Weights halve every ``WEIGHT_HALF_LIFE_DAYS`` going backwards, so the line
    tracks the shop's current behaviour rather than being anchored by whatever
    happened three months ago. Falls back to a flat line at the mean when the
    series is degenerate (all weights on one point).
    """
    age = x[-1] - x
    weights = 0.5 ** (age / WEIGHT_HALF_LIFE_DAYS)

    weight_sum = float(np.sum(weights))
    mean_x = float(np.sum(weights * x) / weight_sum)
    mean_y = float(np.sum(weights * y) / weight_sum)
    variance = float(np.sum(weights * (x - mean_x) ** 2))
    if variance <= 0:
        return 0.0, mean_y

    slope = float(np.sum(weights * (x - mean_x) * (y - mean_y)) / variance)
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _weekday_indices(dates: pd.Series, values: np.ndarray, fitted: np.ndarray) -> dict[str, float]:
    """
    Multiplicative weekday factors: median of ``actual ÷ trend`` per weekday,
    normalised so the seven of them average 1.0.

    The median (not the mean) is used so one exceptional day doesn't set the
    factor for every future occurrence of that weekday.
    """
    safe_fit = np.where(fitted > 0, fitted, np.nan)
    ratios = values / safe_fit

    frame = pd.DataFrame({"weekday": dates.dt.strftime("%a"), "ratio": ratios}).dropna()
    if frame.empty:
        return {}

    medians = frame.groupby("weekday")["ratio"].median()
    average = float(medians.mean())
    if not np.isfinite(average) or average <= 0:
        return {}

    normalised = (medians / average).clip(*SEASONAL_INDEX_CLAMP)
    return {str(day): float(factor) for day, factor in normalised.items()}


def _index_vector(dates: pd.Series, indices: dict[str, float]) -> np.ndarray:
    """Seasonal index for each historical date (1.0 when seasonality is off)."""
    if not indices:
        return np.ones(len(dates))
    return dates.dt.strftime("%a").map(lambda d: indices.get(d, 1.0)).to_numpy(dtype=float)


def _backtest_accuracy(dates: pd.Series, values: np.ndarray) -> float | None:
    """
    Hold out the last ``BACKTEST_DAYS`` days, refit on the rest, and score the
    prediction as ``100 − MAPE`` (clamped to 0–100).

    Days with zero actual revenue are excluded from the percentage error —
    dividing by zero would make MAPE meaningless. Returns ``None`` when the
    history isn't long enough to hold anything back.
    """
    if len(values) < MIN_DAYS_FOR_FORECAST + BACKTEST_DAYS:
        return None

    split = len(values) - BACKTEST_DAYS
    train_positions = np.arange(split, dtype=float)
    slope, intercept = _weighted_linear_fit(train_positions, values[:split])
    indices = _weekday_indices(
        dates.iloc[:split], values[:split], intercept + slope * train_positions
    )

    errors: list[float] = []
    for offset in range(BACKTEST_DAYS):
        actual = float(values[split + offset])
        if actual <= 0:
            continue
        position = split + offset
        index = indices.get(dates.iloc[position].strftime("%a"), 1.0)
        predicted = max((intercept + slope * position) * index, 0.0)
        errors.append(abs(actual - predicted) / actual)

    if not errors:
        return None

    mape = float(np.mean(errors)) * 100.0
    return safe_float(max(0.0, min(100.0, 100.0 - mape)), digits=1)


def _item_forecasts(prepped: pd.DataFrame, horizon: int) -> list[ItemForecast]:
    """
    Expected units per item over the horizon: recent velocity × trend factor,
    capped to the busiest ``MAX_ITEM_FORECASTS`` items so the payload and the
    compute both stay bounded. This is what the reorder table consumes.
    """
    window_days = max(int((prepped["Date"].max() - prepped["Date"].min()).days) + 1, 1)
    third = max(window_days // 3, 1)
    early_end = prepped["Date"].min() + pd.Timedelta(days=third)
    late_start = prepped["Date"].max() - pd.Timedelta(days=third) + pd.Timedelta(days=1)

    totals = prepped.groupby("Item")["Quantity"].sum().sort_values(ascending=False)
    early = prepped[prepped["Date"] < early_end].groupby("Item")["Quantity"].sum()
    late = prepped[prepped["Date"] >= late_start].groupby("Item")["Quantity"].sum()

    forecasts: list[ItemForecast] = []
    for item in totals.head(MAX_ITEM_FORECASTS).index:
        velocity = float(totals[item]) / window_days
        early_rate = float(early.get(item, 0.0)) / third
        late_rate = float(late.get(item, 0.0)) / third
        if early_rate > 0 and late_rate > 0:
            trend = late_rate / early_rate
        elif late_rate > 0:
            trend = 2.0  # only recent sales — treat as clearly accelerating
        else:
            trend = 0.5  # sold early, nothing lately
        trend = float(np.clip(trend, 0.25, 4.0))

        forecasts.append(
            ItemForecast(
                item=str(item),
                expected_units=safe_float(velocity * trend * horizon, digits=1, default=0.0) or 0.0,
                velocity_per_day=safe_float(velocity, digits=3, default=0.0) or 0.0,
                trend_factor=safe_float(trend, digits=2, default=1.0) or 1.0,
            )
        )
    return forecasts
