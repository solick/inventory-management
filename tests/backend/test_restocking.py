"""
Tests for the Restocking order-submission endpoints:
  - POST /api/orders            (create a restocking order)
  - GET  /api/orders/submitted  (list runtime-submitted restocking orders)
  - GET  /api/demand            (now carries unit_cost for recommendations)

Note: the backend stores data in-memory and appends new orders to a shared
list, so these tests measure deltas (before/after) rather than absolute counts.
"""
import pytest


SAMPLE_ITEMS = [
    {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 150, "unit_price": 12.50},
    {"sku": "GSK-203", "name": "High-Temperature Gasket", "quantity": 100, "unit_price": 8.20},
]


class TestRestockingEndpoints:
    """Test suite for restocking order submission."""

    def test_demand_forecasts_have_unit_cost(self, client):
        """Demand forecasts expose unit_cost so the UI can compute budget cost."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for forecast in data:
            assert "unit_cost" in forecast
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] >= 0

    def test_create_order_happy_path(self, client):
        """POST /api/orders creates a Processing restock order with correct fields."""
        response = client.post("/api/orders", json={"items": SAMPLE_ITEMS, "lead_time_days": 14})
        assert response.status_code == 200

        order = response.json()
        assert order["status"] == "Processing"
        assert order["source"] == "restock"
        assert order["order_number"].startswith("ORD-")
        assert order["items"] == SAMPLE_ITEMS
        # actual_delivery should not be set on a freshly submitted order
        assert order.get("actual_delivery") is None

    def test_create_order_total_value_calculation(self, client):
        """total_value equals the sum of quantity * unit_price across items."""
        response = client.post("/api/orders", json={"items": SAMPLE_ITEMS})
        assert response.status_code == 200

        order = response.json()
        expected = sum(i["quantity"] * i["unit_price"] for i in SAMPLE_ITEMS)
        assert abs(order["total_value"] - expected) < 0.01

    def test_create_order_lead_time_is_14_days(self, client):
        """expected_delivery is lead_time_days after order_date (ISO datetimes)."""
        from datetime import datetime

        response = client.post("/api/orders", json={"items": SAMPLE_ITEMS, "lead_time_days": 14})
        assert response.status_code == 200

        order = response.json()
        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert (expected_delivery - order_date).days == 14

    def test_create_order_custom_lead_time(self, client):
        """A custom lead_time_days is honored."""
        from datetime import datetime

        response = client.post("/api/orders", json={"items": SAMPLE_ITEMS, "lead_time_days": 7})
        assert response.status_code == 200

        order = response.json()
        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert (expected_delivery - order_date).days == 7

    def test_create_order_default_customer(self, client):
        """Omitting customer falls back to the internal restock label."""
        response = client.post("/api/orders", json={"items": SAMPLE_ITEMS})
        assert response.status_code == 200
        assert response.json()["customer"] == "Internal Restock"

    def test_create_order_missing_items_is_validation_error(self, client):
        """A request without items fails Pydantic validation (422)."""
        response = client.post("/api/orders", json={"lead_time_days": 14})
        assert response.status_code == 422

    def test_submitted_orders_reflects_new_order(self, client):
        """A submitted order appears in /api/orders/submitted; count grows by one."""
        before = client.get("/api/orders/submitted")
        assert before.status_code == 200
        before_count = len(before.json())

        created = client.post("/api/orders", json={"items": SAMPLE_ITEMS}).json()

        after = client.get("/api/orders/submitted")
        assert after.status_code == 200
        after_data = after.json()
        assert len(after_data) == before_count + 1

        # Every returned order is a restock order, and ours is present.
        assert all(o["source"] == "restock" for o in after_data)
        assert any(o["order_number"] == created["order_number"] for o in after_data)

    def test_submitted_order_also_in_main_orders_list(self, client):
        """A submitted order is retrievable through the standard orders list."""
        created = client.post("/api/orders", json={"items": SAMPLE_ITEMS}).json()

        response = client.get("/api/orders")
        assert response.status_code == 200
        order_numbers = [o["order_number"] for o in response.json()]
        assert created["order_number"] in order_numbers

    def test_submitted_route_not_shadowed_by_order_id(self, client):
        """/api/orders/submitted resolves to the list, not the get-by-id route."""
        response = client.get("/api/orders/submitted")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
