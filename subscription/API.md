# Subscription App API Documentation

The salon's own SaaS subscription: plans, current status, upgrades,
cancellation and billing history.

Base URL: `/api/subscription/`

All endpoints require `Authorization: Bearer <access_token>`.

## Concepts

- A **workspace (tenant)** carries `subscription_plan`, `subscription_status`
  and `subscription_end_date`.
- **Statuses:** `inactive`, `active`, `cancelled`, `expired`, `past_due`,
  `trial`.
- **Intervals:** `month`, `year`, `trial`. New workspaces start on the free
  trial plan for 7 days.
- Authentication itself enforces this: once a workspace has no plan, is not
  `active`, or is past `subscription_end_date`, every API call on that workspace
  returns `401 Unauthorized` with the reason.

### `price_id`

Endpoints that take a `price_id` accept **either** the Stripe price id
(`price_1Sabc...`) **or** djstripe's numeric key. An unknown value is reported
as an invalid plan, not a server error.

---

## 1. Stripe Product Catalogue

### `GET /api/subscription/stripe-product-list/`

- **Description:** Syncs products and prices from the Stripe dashboard into the
  local database, then returns them. This is how new plan pricing reaches the
  application.
- **Permissions:** Public-schema superuser only.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": [
            {
                "id": "prod_ABC",
                "djstripe_id": 1,
                "name": "Pro",
                "description": "For growing salons",
                "active": true,
                "prices": [
                    {
                        "id": "price_1Sabc",
                        "djstripe_id": 7,
                        "currency": "inr",
                        "amount": 999.0,
                        "type": "recurring",
                        "active": true
                    }
                ]
            }
        ],
        "message": "All Product with price data get Successfully!!!"
    }
    ```
  `amount` is in major units (Stripe's `unit_amount` divided by 100).

---

## 2. Subscription Plans

**Endpoint:** `/api/subscription/subscription_plan/`

Plans are platform-wide, so every action is restricted to a **public-schema
superuser**. A `TenantAdmin` gets `403 Forbidden`.

### `GET /api/subscription/subscription_plan/`

- **Query parameters:** `search` (name, slug), `page`, `page_size` (max 50),
  `get_all`.
- **Success (200 OK):** active plans only.
    ```json
    {
        "id": "uuid",
        "name": "Pro Monthly",
        "description": "For growing salons",
        "features": {"staff_limit": 10},
        "stripe_price": {
            "id": "price_1Sabc",
            "djstripe_id": 7,
            "currency": "inr",
            "amount": 999.0,
            "type": "recurring",
            "active": true
        },
        "interval": "month",
        "plan_type": "pro",
        "is_active": true
    }
    ```

### `POST`, `PUT`, `PATCH`, `DELETE /api/subscription/subscription_plan/{id}/`

Standard CRUD on plans. `plan_type` is `free`, `pro` or `enterprise`;
`interval` is `month`, `year` or `trial`.

---

## 3. Current Subscription

### `GET /api/subscription/get-own-subscription/`

- **Description:** The calling workspace's subscription state.
- **Permissions:** Any authenticated user.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "id": "uuid",
            "name": "bellasalon",
            "schema_name": "bellasalon",
            "subscription_status": "active",
            "subscription_end_date": "2026-09-01T00:00:00Z",
            "subscription_plan": {
                "id": "uuid",
                "name": "Pro Monthly",
                "interval": "month",
                "plan_type": "pro"
            },
            "stripe_customer_id": "cus_ABC"
        },
        "message": "Subscription data get Successfully!!!"
    }
    ```

---

## 4. Cancel

### `GET /api/subscription/cancel-subscription/`

- **Description:** Cancels the workspace's paid subscription at the end of the
  current billing period, so access continues until then.
- **Permissions:** `TenantAdmin`.
- **Success (200 OK):** `"Subscription cancelled successfully"`
- **Errors:**
    - `400 Bad Request` - the workspace is on the trial plan, or its status is
      `inactive` / `expired`, so there is nothing to cancel.
    - `400 Bad Request` - Stripe refused the cancellation.
    - `403 Forbidden` - called against the public schema, or by a non-admin.

The final status change arrives asynchronously through
`customer.subscription.deleted` on the platform webhook.

---

## 5. Upgrade or Downgrade

### `POST /api/subscription/upgrade-subscription/`

- **Description:** Moves the workspace to a different plan on the same billing
  interval. Returns a hosted invoice URL; the plan changes once that invoice is
  paid.
- **Permissions:** `TenantAdmin`.
- **Request body:** `{"price_id": "price_1Sxyz..."}`
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {"url": "https://invoice.stripe.com/i/..."},
        "message": "Pay the invoice to upgrade or downgrade the plan"
    }
    ```
- **Errors (all `400 Bad Request`):**
    - `price_id` missing.
    - No active plan matches that price.
    - The workspace is on the trial plan, or is `inactive` / `expired` - start a
      subscription through the `checkout` app instead.
    - The target plan bills on a different interval; monthly and yearly cannot
      be swapped here.
    - The target plan is the one already in force.
    - No active Stripe subscription was found for the workspace.
    - Stripe produced no invoice for the change.

---

## 6. Billing History

**Endpoint:** `/api/subscription/invoice/`

### `GET /api/subscription/invoice/`

- **Description:** Stripe invoices for the calling workspace. Invoices are
  synced from Stripe on each request.
- **Permissions:** `TenantAdmin`.
- **Scope:** A workspace sees **only its own** invoices. The tenant filter
  applies regardless of which other query parameters are supplied. A workspace
  with no Stripe customer yet gets an empty list.
- **Query parameters:**
    - `start_date`, `end_date` (YYYY-MM-DD): both required together.
    - `stripe_customer_id`, `customer_email`: public-schema superuser only,
      for looking up another customer's invoices.
    - `page`, `page_size` (max 50), `get_all`.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "count": 1,
            "results": [
                {
                    "id": "in_ABC",
                    "invoice_number": "ABCD-0001",
                    "status": "paid",
                    "amount_paid": 999.0,
                    "currency": "INR",
                    "plan_name": "Pro Monthly",
                    "invoice_pdf": "https://pay.stripe.com/invoice/.../pdf",
                    "created": "2026-08-01T09:00:00Z",
                    "billing_reason": "subscription_cycle",
                    "customer_email": "owner@bellasalon.co",
                    "customer_phone": null,
                    "customer": "cus_ABC",
                    "metadata": {}
                }
            ]
        },
        "message": "All invoice fetched successfully"
    }
    ```
  `amount_paid` is in major units.
- **Errors:** `400 Bad Request` when `start_date` or `end_date` is not
  `YYYY-MM-DD`.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed, or the plan change is not permitted |
| `401` | Missing or invalid token, or the workspace subscription is inactive or expired |
| `403` | Not a workspace administrator, or not a public-schema superuser |
| `404` | Unknown plan |
| `500` | Unexpected server fault; the detail is logged, not returned |

---

## Related

- `checkout` - starting a first paid subscription.
- `webhook_handler` - the Stripe events that activate, renew and expire it.
