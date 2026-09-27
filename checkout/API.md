# Checkout App API Documentation

Starts payment flows: subscription checkout for the salon itself, and product
checkout for its customers.

Base URL: `/api/checkout/`

All endpoints require `Authorization: Bearer <access_token>`.

## Currency Handling

Stored amounts (`Product.selling_price`, `CartItem.price`,
`Invoice.total_amount`) are in **major units** - rupees, not paise. Stripe and
Razorpay both bill in the **smallest** unit. The conversion happens once, at the
gateway boundary, in `payments.money`:

- `to_minor_units(Decimal("150.50"))` -> `15050`
- `from_minor_units(15050)` -> `Decimal("150.50")`

Zero-decimal currencies such as JPY are passed through unscaled.

---

## 1. Subscription Checkout

### `POST /api/checkout/create-checkout-session/`

- **Description:** Opens a Stripe Checkout session so the salon can subscribe to
  a paid plan. Creates the Stripe customer for the workspace on first use.
- **Permissions:** `TenantAdmin` (or public-schema superuser).
- **Request body:**
    ```json
    {"price_id": "price_1Sabc..."}
    ```
- **`price_id`** accepts either the Stripe price id (`price_...`) or djstripe's
  numeric key.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "checkout_url": "https://checkout.stripe.com/c/pay/...",
            "address": true
        },
        "message": "Checkout session created successfully!!!"
    }
    ```
- **Errors:**
    - `400 Bad Request` - `price_id` missing.
    - `400 Bad Request` - no active plan matches that price.
    - `400 Bad Request` - the workspace already has a non-trial subscription;
      use the upgrade endpoint in the `subscription` app instead.
- **Session lifetime:** 30 minutes. Promotion codes are accepted. On completion
  Stripe calls `/api/webhook-handler/stripe/`, which activates the plan.

---

## 2. Product Checkout

### `POST /api/checkout/product-checkout-session/`

- **Description:** Starts payment for selected cart items using whichever
  gateway the salon has configured (see the `payments` app).
- **Permissions:** Authenticated. Only the caller's own cart items are eligible.
- **Request body:**
    ```json
    {"cart_item_ids": ["uuid-1", "uuid-2"]}
    ```
- **Success (200 OK), Stripe:**
    ```json
    {
        "error": false,
        "data": {
            "checkout_url": "https://checkout.stripe.com/c/pay/...",
            "user": {
                "name": "Alex Doe",
                "email": "alex@example.com",
                "mobile": "+919876543210"
            }
        },
        "message": "Checkout session created successfully!!!"
    }
    ```
- **Success (200 OK), Razorpay:**
    ```json
    {
        "error": false,
        "data": {
            "razorpay_order_id": "order_ABC123",
            "amount": 30100,
            "currency": "INR",
            "razorpay_key": "rzp_test_public_key",
            "user": {
                "name": "Alex Doe",
                "email": "alex@example.com",
                "mobile": "+919876543210"
            }
        },
        "message": "Checkout session created successfully!!!"
    }
    ```
  `amount` is in paise, ready to hand to Razorpay's checkout.js. The
  `razorpay_key` is the public key only.
- **Errors:**
    - `400 Bad Request` - a cart item id is unknown or belongs to someone else.
    - `400 Bad Request` - a product is inactive or no longer has enough stock.
      The response lists the affected products under `data.products`, and no
      payment is started.
    - `400 Bad Request` - the salon has no active payment configuration.
    - `400 Bad Request` - the configured provider has no checkout implementation
      (PayPal is a valid choice but is not wired up).

### Razorpay ordering behaviour

For Razorpay the order is recorded **before** the customer pays:

1. An `Invoice` is created with `payment_status: "unpaid"` and
   `order_status: "pending"`.
2. Its lines are written from the selected cart items, which reserves the stock
   for the duration of the payment and freezes the prices the customer was
   quoted.
3. On `payment.captured` the webhook flips the invoice to paid and clears the
   matching cart items.
4. On `payment.failed` the webhook deletes the unpaid invoice, returning the
   reserved stock. A paid invoice is never deleted.

---

## 3. Verify a Razorpay Payment

### `POST /api/checkout/verify-razorpay-payment/`

- **Description:** Client-side confirmation after Razorpay's checkout widget
  succeeds. Verifies the signature and marks the order paid. This complements
  the webhook - whichever arrives first settles the order, and the other is a
  no-op.
- **Permissions:** Authenticated. Only the caller's own order.
- **Request body:**
    ```json
    {
        "razorpay_order_id": "order_ABC123",
        "razorpay_payment_id": "pay_XYZ789",
        "razorpay_signature": "generated_signature"
    }
    ```
- **Success (200 OK):** `"Payment verified successfully"`
- **Errors:**
    - `400 Bad Request` - a parameter is missing.
    - `400 Bad Request` - the signature does not verify.
    - `400 Bad Request` - the order is already marked paid.
    - `400 Bad Request` - Razorpay is not configured for this salon.
    - `404 Not Found` - no such order for this user.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed, stock unavailable, gateway not configured, or signature mismatch |
| `401` | Missing or invalid token |
| `403` | The role may not start a subscription checkout |
| `404` | Unknown order, or one belonging to another user |
| `500` | Unexpected server fault; the detail is logged, not returned |

---

## Related

- `payments` - configuring which gateway is active and its credentials.
- `webhook_handler` - the gateway callbacks that settle these payments.
- `product_sales` - the cart and the resulting orders.
