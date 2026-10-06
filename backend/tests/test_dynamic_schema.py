"""
Tests for the dynamic schema.

The property under test is honesty about capability: a shopkeeper must be able to
tell "this file cannot show profit" apart from "this month made no profit". Those
two facts look identical on a dashboard — a card either shows a number or it
doesn't — and only one of them is a statement about the business. Every test here
exists to make sure the schema says which one it is.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services import dynamic_schema


def _by(entries, key):
    return next(entry for entry in entries if entry["key"] == key)


@pytest.fixture
def full_frame(normalized):
    """The conftest export: every required field plus several optional ones."""
    return normalized


#: A normalised frame built by hand rather than through ``normalize_dataframe``.
#:
#: Worth noting why: ``normalize_dataframe`` hard-requires Cost Price, so a file
#: without it drops to zero rows and can never reach the dashboard at all. The
#: no-cost case is therefore not reachable end-to-end today — the schema module
#: still has to describe it correctly, because Cost Price being optional is an
#: explicit plan decision for the mapping screen, and a schema that assumed
#: otherwise would silently report "everything available" for a file that cannot
#: be loaded.
def _canonical(**overrides) -> pd.DataFrame:
    """A minimal post-normalisation frame, canonical columns only."""
    data = {
        "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "Category": ["Kurta", "Saree", "Shirt"],
        "Item": ["Cotton Kurta", "Silk Saree", "Formal Shirt"],
        "Quantity": [3, 2, 4],
        "Selling Price": [750.0, 3200.0, 900.0],
        "Cost Price": [300.0, 1800.0, 420.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


@pytest.fixture
def no_cost_frame():
    """
    A shop that has never tracked purchase cost.

    This is the case the schema exists for. A file like this is what a mapping
    screen offers when Cost Price is optional, and it is exactly the case where a
    silently-zero profit card would be most misleading — "no cost data" and "made
    no profit" look identical on a dashboard.
    """
    return _canonical(Branch=["MG Road", "Station Road", "MG Road"]).drop(
        columns=["Cost Price"]
    )


# ── Availability tracks the mapped columns ───────────────────────────────────


class TestTracksColumns:
    def test_full_file_unlocks_everything_it_has(self, full_frame):
        """The baseline: a file with cost, discount, stock and branch must not
        report any of them as unavailable. An over-strict schema is as unhelpful
        as a dishonest one — it would tell a paying shop they cannot see what
        they actually uploaded."""
        schema = dynamic_schema.build(full_frame)

        assert _by(schema["kpi_cards"], "revenue")["available"] is True
        assert _by(schema["kpi_cards"], "profit")["available"] is True
        assert _by(schema["kpi_cards"], "discount")["available"] is True
        assert _by(schema["kpi_cards"], "stock_on_hand")["available"] is True
        assert _by(schema["charts"], "revenue_by_branch")["available"] is True
        assert _by(schema["dimensions"], "branch")["available"] is True

    def test_missing_cost_price_disables_profit_and_says_why(self, no_cost_frame):
        schema = dynamic_schema.build(no_cost_frame)

        profit = _by(schema["kpi_cards"], "profit")
        assert profit["available"] is False
        assert "Cost Price" in profit["reason"]
        assert profit["blocked_by"] == ["Cost Price"]

        # Margin needs the same column, and the P&L is built from it.
        assert _by(schema["kpi_cards"], "margin_pct")["available"] is False
        assert _by(schema["charts"], "pnl")["available"] is False
        assert _by(schema["measures"], "margin_pct")["available"] is False

    def test_revenue_survives_without_cost_price(self, no_cost_frame):
        """Losing Cost Price must not cost the shop its revenue card. If a missing
        optional column took the whole dashboard down, the fix would be 'upload
        less data', which is backwards."""
        schema = dynamic_schema.build(no_cost_frame)

        assert _by(schema["kpi_cards"], "revenue")["available"] is True
        assert _by(schema["kpi_cards"], "units")["available"] is True
        assert _by(schema["charts"], "daily_trend")["available"] is True
        assert _by(schema["charts"], "top_items")["available"] is True
        assert _by(schema["dimensions"], "branch")["available"] is True

    def test_a_dimension_the_file_lacks_is_reported_not_omitted(self, no_cost_frame):
        """Payment Mode is in the registry but not in this file. It must appear
        with available=false and a reason — an omitted entry leaves the shopkeeper
        unable to tell a broken mapping from a feature that does not exist."""
        schema = dynamic_schema.build(no_cost_frame)

        payment = _by(schema["dimensions"], "payment_mode")
        assert payment["available"] is False
        assert "Payment Mode" in payment["reason"]

    def test_time_dimensions_come_from_date(self, full_frame):
        """day/weekday/month are derived from Date, not from a real column, so a
        naive column-presence check would report them all unavailable."""
        schema = dynamic_schema.build(full_frame)

        for key in ("day", "weekday", "month"):
            assert _by(schema["dimensions"], key)["available"] is True

    def test_every_registry_measure_is_accounted_for(self, full_frame):
        """Nothing silently dropped from the response: the schema covers the whole
        registry, available or not, so the UI can never show a control the API
        has never heard of."""
        from app.services.query_engine import MEASURES

        schema = dynamic_schema.build(full_frame)
        assert {m["key"] for m in schema["measures"]} == set(MEASURES)

    def test_every_registry_dimension_is_accounted_for(self, full_frame):
        from app.services.query_engine import DIMENSIONS

        schema = dynamic_schema.build(full_frame)
        assert {d["key"] for d in schema["dimensions"]} == set(DIMENSIONS)


# ── Entries are flagged, never omitted ───────────────────────────────────────


class TestNothingIsOmitted:
    def test_unavailable_entries_still_carry_a_reason(self, no_cost_frame):
        """An empty list says nothing about why nothing appeared. Every
        unavailable entry must say what would unlock it."""
        schema = dynamic_schema.build(no_cost_frame)

        unavailable = [
            entry
            for group in ("kpi_cards", "charts", "dimensions", "measures")
            for entry in schema[group]
            if not entry["available"]
        ]
        assert unavailable, "expected some entries to be unavailable"
        for entry in unavailable:
            assert entry["reason"], f"{entry['key']} is unavailable but gives no reason"

    def test_available_entries_have_no_reason(self, full_frame):
        schema = dynamic_schema.build(full_frame)

        for group in ("kpi_cards", "charts", "dimensions", "measures"):
            for entry in schema[group]:
                if entry["available"]:
                    assert entry["reason"] is None

    def test_available_entries_come_first(self, no_cost_frame):
        """The panel answers "what can I do with this file?". Available entries
        must not be buried under a list of things that cannot be done."""
        schema = dynamic_schema.build(no_cost_frame)

        for group in ("kpi_cards", "charts", "dimensions", "measures"):
            flags = [entry["available"] for entry in schema[group]]
            assert flags == sorted(flags, reverse=True), group


# ── Charts need enough data, not just the column ─────────────────────────────


class TestChartsNeedData:
    def test_single_branch_says_so_instead_of_drawing_one_bar(self, normalized):
        """A revenue-by-branch chart over one branch is a single rectangle that
        tells the shopkeeper nothing. Reporting it as unavailable is more useful
        than rendering it."""
        frame = normalized.copy()
        frame["Branch"] = "Only Store"

        schema = dynamic_schema.build(frame)
        branch_chart = _by(schema["charts"], "revenue_by_branch")

        assert branch_chart["available"] is False
        assert "enough data" in branch_chart["reason"]
        assert branch_chart["distinct_values"] == 1
        # The column *is* mapped — the problem is the data, and the reason says so
        # instead of telling them to remap a column they already mapped.
        assert _by(schema["dimensions"], "branch")["available"] is True

    def test_short_history_fails_the_heatmap(self, short_frame):
        schema = dynamic_schema.build(short_frame)
        heatmap = _by(schema["charts"], "weekday_heatmap")
        assert heatmap["available"] is False
        assert heatmap["min_categories"] == 14

    def test_full_history_unlocks_the_heatmap(self, full_frame):
        schema = dynamic_schema.build(full_frame)
        assert _by(schema["charts"], "weekday_heatmap")["available"] is True


# ── Degenerate input ─────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_frame_returns_a_valid_empty_schema(self):
        """A schema panel that raises would take the dashboard down with it. An
        empty frame must still produce something structurally valid."""
        schema = dynamic_schema.build(pd.DataFrame())

        assert schema["kpi_cards"]
        assert schema["charts"]
        assert schema["present_columns"] == []
        assert set(schema["missing_required_columns"]) == {
            "Date",
            "Category",
            "Item",
            "Quantity",
            "Selling Price",
            "Cost Price",
        }
        for entry in schema["kpi_cards"]:
            assert entry["available"] is False
            assert entry["reason"]

    def test_headers_only_frame_is_handled(self, raw_sales_frame):
        from app.utils.data_validator import normalize_dataframe

        frame, _errors = normalize_dataframe(raw_sales_frame.head(0), soft_fail=True)
        schema = dynamic_schema.build(frame)
        assert schema["present_columns"]

    def test_frame_without_a_date_does_not_explode(self, raw_sales_frame):
        """compute_data_date_range assumes a Date column. A frame without one must
        degrade to an empty range, not a 500."""
        frame = raw_sales_frame.drop(columns=["Bill Date"])
        from app.utils.data_validator import normalize_dataframe

        normalized, _errors = normalize_dataframe(
            frame,
            soft_fail=True,
            column_mapping={
                "Item Name": "Item",
                "Stock Group": "Category",
                "Qty.": "Quantity",
                "Rate/Unit": "Selling Price",
                "Purchase Rate": "Cost Price",
            },
        )
        schema = dynamic_schema.build(normalized)
        assert schema["date_range"] == {}

    def test_all_null_column_does_not_break_nunique(self):
        frame = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "Category": ["Kurta", "Saree"],
                "Item": ["A", "B"],
                "Quantity": [1, 2],
                "Selling Price": [100.0, 200.0],
                "Cost Price": [50.0, 100.0],
                "Branch": [None, None],
            }
        )
        schema = dynamic_schema.build(frame)
        branch_chart = _by(schema["charts"], "revenue_by_branch")
        assert branch_chart["available"] is False

    def test_result_is_json_serialisable(self, full_frame):
        import json

        json.dumps(dynamic_schema.build(full_frame))  # must not raise on numpy types

    def test_result_satisfies_the_api_schema(self, full_frame):
        """The route declares DynamicSchema as its response_model, so a key drift
        is a runtime 500 rather than a wrong value."""
        from app.models.schemas import DynamicSchema

        DynamicSchema(**dynamic_schema.build(full_frame))


# ── The mapping is echoed for diagnostics ────────────────────────────────────


class TestMappingEcho:
    def test_mapping_is_passed_through(self, full_frame, mapping):
        schema = dynamic_schema.build(full_frame, mapping=mapping)
        assert schema["mapped_columns"]["Bill Date"] == "Date"

    def test_missing_mapping_is_not_an_error(self, full_frame):
        assert dynamic_schema.build(full_frame)["mapped_columns"] == {}

    def test_present_columns_are_canonical(self, full_frame):
        """These are post-normalisation columns, so a raw header must not appear.
        The UI maps schema entries back onto mapping-screen rows by name."""
        schema = dynamic_schema.build(full_frame)
        assert "Bill Date" not in schema["present_columns"]
        assert "Date" in schema["present_columns"]
