from datetime import datetime, timezone

import numpy as np
import pandas as pd


TIMEFRAME_SECONDS = {
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
}


class HistoricalDataValidator:
    """
    Validates historical OHLC candle datasets for research.

    Checks:
    - Required columns
    - UTC-aware timestamps
    - Duplicate timestamps
    - Chronological ordering
    - Missing and non-finite values
    - Numeric data types
    - Positive price values
    - OHLC consistency
    - Non-negative volume and spread
    - Incomplete candles
    - Potential missing candle intervals

    Potential gaps are warnings because market closures
    and instrument trading sessions can create legitimate gaps.

    This validator does not modify the input dataset.
    """

    REQUIRED_COLUMNS = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
        "real_volume",
    ]

    PRICE_COLUMNS = [
        "open",
        "high",
        "low",
        "close",
    ]

    NON_NEGATIVE_COLUMNS = [
        "tick_volume",
        "spread",
        "real_volume",
    ]

    def validate(self, df, timeframe):
        """Validate one historical candle dataset."""

        result = {
            "status": "FAIL",
            "valid": False,
            "timeframe": timeframe,
            "candle_count": 0,
            "duplicate_timestamps": 0,
            "non_chronological_pairs": 0,
            "invalid_ohlc_rows": 0,
            "missing_values": 0,
            "non_finite_values": 0,
            "non_positive_price_rows": 0,
            "negative_value_rows": 0,
            "forming_candles": 0,
            "future_timestamps": 0,
            "gap_count": 0,
            "estimated_missing_intervals": 0,
            "gap_details": [],
            "errors": [],
            "warnings": [],
        }

        if timeframe not in TIMEFRAME_SECONDS:
            result["errors"].append(
                f"Unsupported timeframe: {timeframe}"
            )
            return result

        if not isinstance(df, pd.DataFrame):
            result["errors"].append(
                "Input must be a pandas DataFrame."
            )
            return result

        if df.empty:
            result["errors"].append(
                "Historical dataset is empty."
            )
            return result

        result["candle_count"] = len(df)

        missing_columns = [
            column
            for column in self.REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing_columns:
            result["errors"].append(
                f"Missing required columns: {missing_columns}"
            )
            return result

        # Work on a copy to protect the original dataset.
        data = df.copy()

        # Validate timestamp type and timezone.
        if not pd.api.types.is_datetime64_any_dtype(
            data["time"]
        ):
            result["errors"].append(
                "Timestamp column must contain datetime values."
            )
            return result

        if data["time"].dt.tz is None:
            result["errors"].append(
                "Timestamps must be timezone-aware."
            )
            return result

        if str(data["time"].dt.tz) != "UTC":
            result["errors"].append(
                "Timestamps must use UTC timezone."
            )
            return result

        # Check missing values across required columns.
        result["missing_values"] = int(
            data[self.REQUIRED_COLUMNS].isna().sum().sum()
        )

        if result["missing_values"] > 0:
            result["errors"].append(
                "Dataset contains missing values."
            )

        # Use valid timestamps for subsequent time calculations.
        valid_times = data["time"].dropna().reset_index(drop=True)

        # Check duplicate timestamps.
        result["duplicate_timestamps"] = int(
            data["time"].duplicated().sum()
        )

        if result["duplicate_timestamps"] > 0:
            result["errors"].append(
                "Duplicate candle timestamps detected."
            )

        # Check chronological order independently of DataFrame index.
        time_differences = valid_times.diff()

        result["non_chronological_pairs"] = int(
            (time_differences < pd.Timedelta(0)).sum()
        )

        if result["non_chronological_pairs"] > 0:
            result["errors"].append(
                "Candle timestamps are not chronological."
            )

        # Check future timestamps.
        current_time = datetime.now(timezone.utc)

        result["future_timestamps"] = int(
            (valid_times > current_time).sum()
        )

        if result["future_timestamps"] > 0:
            result["errors"].append(
                "Dataset contains future timestamps."
            )

        # Validate every numeric column instead of returning
        # immediately when the first invalid column is found.
        numeric_columns = (
            self.PRICE_COLUMNS
            + self.NON_NEGATIVE_COLUMNS
        )

        invalid_numeric_columns = []

        for column in numeric_columns:
            if not pd.api.types.is_numeric_dtype(data[column]):
                invalid_numeric_columns.append(column)

                result["errors"].append(
                    f"Column {column} must contain numeric values."
                )

        # Convert a working copy for safe numeric calculations.
        # Invalid text becomes NaN and is excluded from calculations.
        numeric_data = data[numeric_columns].apply(
            pd.to_numeric,
            errors="coerce",
        )

        numeric_array = numeric_data.to_numpy(
            dtype=float,
            na_value=np.nan,
        )

        non_finite_mask = np.isinf(numeric_array)

        result["non_finite_values"] = int(
            non_finite_mask.sum()
        )

        if result["non_finite_values"] > 0:
            result["errors"].append(
                "Dataset contains non-finite numeric values."
            )

        # Run price checks only when all price columns are numeric.
        if not any(
            column in invalid_numeric_columns
            for column in self.PRICE_COLUMNS
        ):

            price_data = numeric_data[self.PRICE_COLUMNS]

            valid_price_rows = (
                price_data.notna().all(axis=1)
                & np.isfinite(
                    price_data.to_numpy(dtype=float)
                ).all(axis=1)
            )

            non_positive_mask = (
                price_data <= 0
            ).any(axis=1) & valid_price_rows

            result["non_positive_price_rows"] = int(
                non_positive_mask.sum()
            )

            if result["non_positive_price_rows"] > 0:
                result["errors"].append(
                    "Dataset contains non-positive prices."
                )

            # Check OHLC consistency.
            invalid_ohlc_mask = (
                (price_data["high"] < price_data["open"])
                | (price_data["high"] < price_data["close"])
                | (price_data["high"] < price_data["low"])
                | (price_data["low"] > price_data["open"])
                | (price_data["low"] > price_data["close"])
            )

            invalid_ohlc_mask = (
                invalid_ohlc_mask & valid_price_rows
            )

            result["invalid_ohlc_rows"] = int(
                invalid_ohlc_mask.sum()
            )

            if result["invalid_ohlc_rows"] > 0:
                result["errors"].append(
                    "Dataset contains invalid OHLC relationships."
                )

        # Check non-negative volume and spread.
        if not any(
            column in invalid_numeric_columns
            for column in self.NON_NEGATIVE_COLUMNS
        ):

            non_negative_data = numeric_data[
                self.NON_NEGATIVE_COLUMNS
            ]

            valid_non_negative_rows = (
                non_negative_data.notna().all(axis=1)
                & np.isfinite(
                    non_negative_data.to_numpy(dtype=float)
                ).all(axis=1)
            )

            negative_mask = (
                non_negative_data < 0
            ).any(axis=1) & valid_non_negative_rows

            result["negative_value_rows"] = int(
                negative_mask.sum()
            )

            if result["negative_value_rows"] > 0:
                result["errors"].append(
                    "Dataset contains negative volume or spread values."
                )

        # Check incomplete candles.
        if "is_forming_candle" in data.columns:

            forming_values = data[
                "is_forming_candle"
            ].fillna(True)

            result["forming_candles"] = int(
                forming_values.astype(bool).sum()
            )

            if result["forming_candles"] > 0:
                result["errors"].append(
                    "Dataset contains incomplete candles."
                )

        # Detect potential gaps using positional comparisons.
        # The original DataFrame index is deliberately ignored.
        unique_times = (
            valid_times
            .drop_duplicates()
            .sort_values()
            .reset_index(drop=True)
        )

        expected_seconds = TIMEFRAME_SECONDS[timeframe]

        for position in range(1, len(unique_times)):

            previous_time = unique_times.iloc[position - 1]
            next_time = unique_times.iloc[position]

            gap = next_time - previous_time
            gap_seconds = int(gap.total_seconds())

            if gap_seconds <= expected_seconds:
                continue

            missing_intervals = max(
                int(gap_seconds // expected_seconds) - 1,
                1,
            )

            result["gap_details"].append({
                "previous_candle": previous_time.isoformat(),
                "next_candle": next_time.isoformat(),
                "gap_seconds": gap_seconds,
                "estimated_missing_intervals": missing_intervals,
            })

        result["gap_count"] = len(
            result["gap_details"]
        )

        result["estimated_missing_intervals"] = sum(
            gap["estimated_missing_intervals"]
            for gap in result["gap_details"]
        )

        if result["gap_count"] > 0:
            result["warnings"].append(
                "Potential candle gaps detected. "
                "Review broker trading sessions and market closures."
            )

        # Determine final validation status.
        if result["errors"]:
            result["status"] = "FAIL"
            result["valid"] = False

        elif result["warnings"]:
            result["status"] = "WARNING"
            result["valid"] = True

        else:
            result["status"] = "PASS"
            result["valid"] = True

        return result
