# Stock Management App API Documentation

Recording supplier purchases, which is how product stock goes up.

Base URL: `/api/stock-management/`

All endpoints require `Authorization: Bearer <access_token>`.

## How Stock Moves

A stock purchase is a supplier invoice with one or more lines. Saving a line:

- adds its `quantity` to the product's `current_stock`;
- copies its `purchase_price` onto the product, so the product always carries
  the most recent cost price;
- recalculates the purchase total.

Editing a line moves only the difference. Deleting a line takes the units back
out. Everything happens inside a transaction with the product row locked, so
concurrent edits cannot corrupt the count.

---

## Stock Purchases

**Endpoint:** `/api/stock-management/stock-purchases/`

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user |
| Create / update | `POST`, `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

### `GET /api/stock-management/stock-purchases/`

- **Query parameters:**
    - `search` (string): matches `invoice_number`.
    - `payment_status` (`paid` | `unpaid`).
    - `purchase_date` (YYYY-MM-DD).
    - `ordering`: `purchase_date` or `total_amount`, prefix with `-` to reverse.
    - `page`, `page_size` (max 50), `get_all`.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "count": 1,
            "results": [
                {
                    "id": "uuid",
                    "supplier_details": {"name": "Acme Supplies"},
                    "invoice_number": "SUP-001",
                    "purchase_date": "2026-01-10",
                    "payment_status": "unpaid",
                    "total_amount": "900.00",
                    "items": [
                        {
                            "id": "uuid",
                            "product": "uuid",
                            "product_name": "Shampoo",
                            "quantity": 10,
                            "purchase_price": "90.00",
                            "subtotal": "900.00"
                        }
                    ]
                }
            ]
        },
        "message": "Stock purchase retrieved successfully"
    }
    ```

### `GET /api/stock-management/stock-purchases/{id}/`

- Retrieves one purchase with its lines.

### `POST /api/stock-management/stock-purchases/`

- **Description:** Records a supplier purchase and raises stock accordingly.
- **Permissions:** `TenantAdmin` or `Staff`.
- **Request body:**
    ```json
    {
        "invoice_number": "SUP-001",
        "purchase_date": "2026-01-10",
        "payment_status": "unpaid",
        "supplier_details": {
            "name": "Acme Supplies",
            "phone": "+919876543210"
        },
        "items": [
            {
                "product": "uuid",
                "quantity": 10,
                "purchase_price": "90.00"
            }
        ]
    }
    ```
- **Read-only fields:** `id`, `total_amount`, and each line's `subtotal` - all
  derived.
- **Success (200 OK):** the created purchase with its lines and totals.
- **Errors:** `400 Bad Request` when `items` is missing or empty, when a
  `quantity` is not greater than zero, when a `purchase_price` is negative, or
  when a `product` id is unknown.

### `PUT` / `PATCH /api/stock-management/stock-purchases/{id}/`

- **Description:** Edits a purchase and reconciles the stock difference.
- **Permissions:** `TenantAdmin` or `Staff`.
- **How `items` is interpreted:**
    - A line **with** an `id` updates that existing line.
    - A line **without** an `id` is added.
    - An existing line **absent** from the payload is deleted, and its units are
      taken back out of stock.
- **Request body:**
    ```json
    {
        "items": [
            {
                "id": "uuid-of-existing-line",
                "product": "uuid",
                "quantity": 4,
                "purchase_price": "90.00"
            },
            {
                "product": "uuid-of-another-product",
                "quantity": 2,
                "purchase_price": "45.00"
            }
        ]
    }
    ```
- **Errors:** `400 Bad Request` if an `id` belongs to a different purchase.
  Nothing is written in that case.

### `DELETE /api/stock-management/stock-purchases/{id}/`

- **Description:** Deletes a purchase and every line, taking the received units
  back out of stock.
- **Permissions:** `TenantAdmin`.
- **Errors:** `400 Bad Request` when reversing a line would push a product's
  stock below zero - that is, the units have already been sold on. The message
  names the product and the counts involved.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed, or the reversal would drive stock negative |
| `401` | Missing or invalid token |
| `403` | The role may not create, edit or delete purchases |
| `404` | Unknown purchase |
| `500` | Unexpected server fault; the detail is logged, not returned |

---

## Related

- Stock is consumed by orders in the `product_sales` app.
- `Product.minimum_stock` drives the `is_low_stock` flag, which is what a
  reorder report should key off.
