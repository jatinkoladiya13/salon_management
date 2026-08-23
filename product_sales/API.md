# Product Sales App API Documentation

The retail side of the salon: product catalogue, shopping cart and orders.

Base URL: `/api/product-sales/`

All endpoints require `Authorization: Bearer <access_token>`.

## Amounts and Stock

- Every price in this app is in **major currency units** (rupees, not paise).
  Conversion to the smallest unit happens only at the payment gateway boundary.
- `Product.current_stock` is the single source of truth. It is decremented when
  an order line is created and restored when one is deleted, inside a
  transaction that locks the product row, so two concurrent orders cannot
  oversell the same units.

---

## 1. Product Categories

**Endpoint:** `/api/product-sales/product-categories/`

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user |
| Create / update | `POST`, `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

### `GET /api/product-sales/product-categories/`

- **Query parameters:** `search` (name, description), `name`, `description`,
  `page`, `page_size` (max 50), `get_all`.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "count": 1,
            "results": [
                {
                    "id": "uuid",
                    "name": "Hair Care",
                    "description": "Shampoos and conditioners",
                    "is_active": true
                }
            ]
        },
        "message": "Product categories retrieved successfully"
    }
    ```

### `POST /api/product-sales/product-categories/`

- **Request body:** `{"name": "Skin Care", "description": "Optional"}`
- **Success (201 Created):** the created category. New categories are active.

### `DELETE /api/product-sales/product-categories/{id}/`

- Deleting a category cascades to its products. `TenantAdmin` only.

---

## 2. Products

**Endpoint:** `/api/product-sales/products/`

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user |
| Create / update | `POST`, `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

### `GET /api/product-sales/products/`

- **Query parameters:** `search` (name, description), `name`, `description`,
  `selling_price`, `product_category`, `is_active`, `page`, `page_size`,
  `get_all`.
- **Success (200 OK):**
    ```json
    {
        "id": "uuid",
        "name": "Shampoo",
        "description": "Sulphate free",
        "product_category": "uuid",
        "unit": "bottle",
        "current_stock": 10,
        "minimum_stock": 2,
        "purchase_price": "100.00",
        "selling_price": "150.50",
        "is_active": true,
        "product_images": [
            {"id": "uuid", "image": "/media/product_images/x.png", "is_active": true}
        ]
    }
    ```

### `POST /api/product-sales/products/`

- **Content type:** `multipart/form-data` (images are file uploads).
- **Required:** `name` (unique), `product_category`, `selling_price`, and at
  least one `images` entry.
- **Image rules:** `.jpg`, `.jpeg`, `.png` or `.webp`, max 10 MB each.
- **Success (201 Created):** the created product.

### `PUT` / `PATCH /api/product-sales/products/{id}/`

- Sending `images` **replaces** the existing set. Omit the field to keep the
  current images.

---

## 3. Cart

**Endpoint:** `/api/product-sales/cart-items/`

A cart is scoped to the calling user. Every action reads and writes only that
user's rows; another user's cart item is simply not visible (`404`).

### `GET /api/product-sales/cart-items/`

- **Permissions:** Authenticated; returns the caller's own cart.
- **Query parameters:** `search` (product name/description), `product__name`,
  `quantity`, `page`, `page_size`, `get_all`.
- **Success (200 OK):**
    ```json
    {
        "id": "uuid",
        "product": "uuid",
        "quantity": 2,
        "price": "150.50",
        "subtotal": "301.00"
    }
    ```

### `POST /api/product-sales/cart-items/`

- **Description:** Adds a product to the cart. Adding a product already in the
  cart increases the quantity rather than creating a second row.
- **Request body:** `{"product": "uuid", "quantity": 2}`
- **Notes:** `price` is captured from the product's current `selling_price` and
  is read-only.
- **Success (201 Created):** the cart item.
- **Errors:** `400 Bad Request` when `quantity` is not positive or exceeds
  `current_stock`; the message names the product and the quantity available.

### `PATCH /api/product-sales/cart-items/{id}/`

- **Request body:** `{"quantity": 3}`
- **Errors:** `400 Bad Request` if the new quantity exceeds available stock.

### `DELETE /api/product-sales/cart-items/{id}/`

- **Permissions:** Authenticated. Owning the row is the authorisation, so a
  customer can always remove their own item.

---

## 4. Orders (Invoices)

**Endpoint:** `/api/product-sales/invoices/`

This is the **cash / pay-on-delivery** path. For card payments use the
`checkout` app, which drives Stripe or Razorpay and raises the invoice itself.

### `GET /api/product-sales/invoices/`

- **Description:** The caller's own orders, newest first.
- **Permissions:** Authenticated.
- **Success (200 OK):**
    ```json
    {
        "count": 1,
        "results": [
            {
                "id": "uuid",
                "invoice_number": "INV-20260801-K3F9QZ",
                "shipping_address": "12 High Street",
                "invoice_date": "2026-08-01",
                "discount": "0.00",
                "tax": "0.00",
                "total_amount": "301.00",
                "payment_method": "cod",
                "payment_status": "unpaid",
                "order_status": "pending",
                "items": [
                    {
                        "id": "uuid",
                        "product_name": "Shampoo",
                        "quantity": 2,
                        "price": "150.50",
                        "subtotal": "301.00"
                    }
                ]
            }
        ]
    }
    ```

### `GET /api/product-sales/invoices/{id}/`

- Retrieves one of the caller's own orders.

### `POST /api/product-sales/invoices/`

- **Description:** Turns the caller's whole cart into an order. Every cart line
  becomes an order line, stock is deducted, the cart is emptied and the total is
  recalculated - all in one transaction.
- **Permissions:** Authenticated.
- **Request body:**
    ```json
    {
        "shipping_address": "12 High Street",
        "payment_method": "cod",
        "discount": "0.00",
        "tax": "0.00"
    }
    ```
- **`payment_method`:** `card`, `upi` or `cod`.
- **Read-only fields:** `invoice_number` (generated), `invoice_date`,
  `total_amount` (derived), `payment_status`, `order_status`, `items`.
- **Success (201 Created):** the created order with its lines.
- **Errors:**
    - `400 Bad Request` - the cart is empty.
    - `400 Bad Request` - a product no longer has enough stock. The message
      names each affected product and nothing is written.

`total_amount` is always `sum(line subtotals) - discount + tax`.

---

## Field Reference

### Order status

`pending` -> `confirmed` -> `packed` -> `shipped` -> `delivered`, or
`cancelled`.

### Payment status

`unpaid` or `paid`.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed - insufficient stock, empty cart, bad quantity |
| `401` | Missing or invalid token |
| `403` | The role may not perform this action (for example a customer writing to the catalogue) |
| `404` | Unknown object, or one belonging to another user |
| `409` | Conflicts with existing data, such as a duplicate product name |
| `500` | Unexpected server fault; the detail is logged, not returned |
