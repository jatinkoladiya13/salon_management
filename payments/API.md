# Payments App API Documentation

Per-salon payment gateway configuration.

Base URL: `/api/payments/`

All endpoints require `Authorization: Bearer <access_token>`.

## Model

Each salon stores its own gateway credentials. Exactly one configuration is
active at a time: saving a configuration with `is_active: true` deactivates any
other. The checkout and webhook flows both read the active configuration.

## Handling of Secrets

Gateway secrets are **write-only**. `payment_credentials` and `webhook_secret`
are accepted on create and update but are never returned by the API. Reads
instead expose `payment_credentials_summary`, which shows public identifiers in
full and replaces every secret with `********`:

```json
"payment_credentials_summary": {
    "razorpay_key_id": "rzp_test_public",
    "razorpay_key_secret": "********",
    "mode": "test"
}
```

Masked keys: `stripe_secret_key`, `razorpay_key_secret`, `paypal_client_secret`.

---

## Payment Configurations

**Endpoint:** `/api/payments/configurations/`

All actions require `TenantAdmin` (or a public-schema superuser). Staff and
customers get `403 Forbidden`.

### `GET /api/payments/configurations/`

- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": [
            {
                "id": "uuid",
                "provider": "razorpay",
                "is_active": true,
                "currency": "INR",
                "payment_credentials_summary": {
                    "razorpay_key_id": "rzp_test_public",
                    "razorpay_key_secret": "********",
                    "mode": "test"
                },
                "branding_details": {
                    "shop_name": "Bella Salon",
                    "description": "Hair and beauty"
                },
                "brand_logo": "/media/payment_branding_logos/logo.png",
                "created_at": "2026-01-10T09:00:00Z"
            }
        ],
        "message": "Payment configurations retrieved successfully"
    }
    ```

### `GET /api/payments/configurations/{id}/`

Retrieves one configuration, with the same masking.

### `POST /api/payments/configurations/`

- **Description:** Adds a gateway configuration. The credentials are verified
  against the live gateway before the record is saved.
- **Request body (Stripe):**
    ```json
    {
        "provider": "stripe",
        "is_active": true,
        "currency": "INR",
        "webhook_secret": "whsec_...",
        "payment_credentials": {
            "stripe_public_key": "pk_test_...",
            "stripe_secret_key": "sk_test_...",
            "mode": "test"
        },
        "branding_details": {
            "shop_name": "Bella Salon",
            "description": "Hair and beauty"
        }
    }
    ```
- **Request body (Razorpay):**
    ```json
    {
        "provider": "razorpay",
        "is_active": true,
        "currency": "INR",
        "webhook_secret": "your_webhook_secret",
        "payment_credentials": {
            "razorpay_key_id": "rzp_test_...",
            "razorpay_key_secret": "...",
            "mode": "test"
        }
    }
    ```
- **`provider`:** `stripe`, `razorpay` or `paypal`. PayPal can be stored but has
  no checkout implementation.
- **`mode`:** `test` or `live`. For Stripe, `live` also switches on automatic
  tax and tax-id collection at checkout.
- **`branding_details`:** optional, but when present must contain both
  `shop_name` and `description`.
- **`brand_logo`:** optional upload, JPEG/JPG/PNG, max 2 MB.
- **Success (201 Created):** the created configuration, secrets masked.
- **Errors:** `400 Bad Request` for missing credential fields, an invalid
  `mode`, credentials the gateway rejects, or incomplete branding details.

### `PUT` / `PATCH /api/payments/configurations/{id}/`

- **Description:** Updates a configuration.
- **Note:** On a partial update the provider is taken from the stored record if
  it is not in the payload, so credentials are still validated against the right
  gateway. A patch that does not include `payment_credentials` leaves the stored
  credentials untouched.

### `DELETE /api/payments/configurations/{id}/`

- Deletes a configuration. If it was the active one, the salon has no gateway
  until another is activated, and product checkout will return
  `400 Bad Request`.

---

## Webhook Endpoints to Register

Once a configuration exists, point the gateway at the matching callback. The
tenant id is the workspace's `Tenant.id`.

| Gateway | URL |
| --- | --- |
| Stripe (products) | `/api/webhook-handler/stripe-product-webhook/<tenant_id>/` |
| Razorpay | `/api/webhook-handler/razorpay/<tenant_id>/` |
| Stripe (platform subscriptions) | `/api/webhook-handler/stripe/` |

The `webhook_secret` stored here is what each callback verifies signatures
against.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed, or the gateway rejected the credentials |
| `401` | Missing or invalid token |
| `403` | Not a workspace administrator |
| `404` | Unknown configuration |
| `500` | Unexpected server fault; the detail is logged, not returned |
