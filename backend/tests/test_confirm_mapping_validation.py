"""
Tests for Module 2.2 — Backend validation of confirm-mapping payload.

Verifies:
1. Valid Path A mapping (Date + Line Total) succeeds.
2. Valid Path B mapping (Date + Quantity + Selling Price) succeeds.
3. Unknown canonical field rejected with HTTP 400.
4. Duplicate canonical mapping rejected with HTTP 400.
5. Nonexistent raw column rejected with HTTP 400.
6. Legitimate empty/ignored column values ("") are preserved and allowed.
"""

from __future__ import annotations

import io
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.auth_verifier import get_current_user

OWNER = "test-owner-user-mod22"


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: OWNER
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_csv_file_id(client):
    """Upload a CSV with multiple headers for mapping testing."""
    df = pd.DataFrame(
        {
            "Bill Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "Item Name": ["Shirt", "Pants", "Kurta"],
            "Qty": [2, 1, 3],
            "Rate": [500.0, 1000.0, 750.0],
            "Net Amt": [1000.0, 1000.0, 2250.0],
            "Notes": ["Fast delivery", "Gift wrap", "None"],
        }
    )
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    res = client.post(
        "/upload/",
        files={"file": ("test_sales.csv", buffer, "text/csv")},
        data={"ai_consent": "false"},
    )
    assert res.status_code == 201
    return res.json()["file_id"]


def test_confirm_mapping_valid_path_a(client, sample_csv_file_id):
    """Path A: Date + Line Total + optional fields."""
    mapping = {
        "Bill Date": "Date",
        "Net Amt": "Line Total",
        "Item Name": "Item",
        "Notes": "",  # ignored column
    }
    res = client.post(f"/upload/{sample_csv_file_id}/confirm-mapping", json={"mapping": mapping})
    assert res.status_code == 200
    data = res.json()
    assert data["valid_count"] == 3
    assert data["error_count"] == 0


def test_confirm_mapping_valid_path_b(client, sample_csv_file_id):
    """Path B: Date + Quantity + Selling Price."""
    mapping = {
        "Bill Date": "Date",
        "Qty": "Quantity",
        "Rate": "Selling Price",
        "Item Name": "Item",
        "Net Amt": "",  # ignored
        "Notes": "",    # ignored
    }
    res = client.post(f"/upload/{sample_csv_file_id}/confirm-mapping", json={"mapping": mapping})
    assert res.status_code == 200
    data = res.json()
    assert data["valid_count"] == 3
    assert data["error_count"] == 0


def test_confirm_mapping_unknown_canonical_field(client, sample_csv_file_id):
    """Reject unknown or fabricated canonical targets."""
    mapping = {
        "Bill Date": "Date",
        "Net Amt": "Line Total",
        "Notes": "FabricatedCustomField",
    }
    res = client.post(f"/upload/{sample_csv_file_id}/confirm-mapping", json={"mapping": mapping})
    assert res.status_code == 400
    assert "not a valid canonical field" in res.json()["detail"]


def test_confirm_mapping_duplicate_canonical_field(client, sample_csv_file_id):
    """Reject duplicate mappings to the same canonical target."""
    mapping = {
        "Bill Date": "Date",
        "Net Amt": "Line Total",
        "Rate": "Line Total",  # duplicate!
    }
    res = client.post(f"/upload/{sample_csv_file_id}/confirm-mapping", json={"mapping": mapping})
    assert res.status_code == 400
    assert "Duplicate mapping detected" in res.json()["detail"]
    assert "Line Total" in res.json()["detail"]


def test_confirm_mapping_nonexistent_raw_column(client, sample_csv_file_id):
    """Reject column names not in the uploaded file."""
    mapping = {
        "Bill Date": "Date",
        "Net Amt": "Line Total",
        "Ghost Column": "Customer",  # doesn't exist
    }
    res = client.post(f"/upload/{sample_csv_file_id}/confirm-mapping", json={"mapping": mapping})
    assert res.status_code == 400
    assert "Ghost Column" in res.json()["detail"]
    assert "does not exist in the uploaded file" in res.json()["detail"]


def test_confirm_mapping_preserves_empty_ignored_columns(client, sample_csv_file_id):
    """Multiple columns can legitimately be left empty/ignored without duplicate error."""
    mapping = {
        "Bill Date": "Date",
        "Net Amt": "Line Total",
        "Item Name": "",
        "Qty": "",
        "Rate": "",
        "Notes": "",
    }
    res = client.post(f"/upload/{sample_csv_file_id}/confirm-mapping", json={"mapping": mapping})
    assert res.status_code == 200
    data = res.json()
    assert data["valid_count"] == 3
