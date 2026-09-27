# Webhook Handler App API Documentation

Inbound callbacks from Stripe and Razorpay. These are called by the payment
gateways, not by your front end.

Base URL: `/api/webhook-handler/`

## Conventions

- **No authentication header.** Authenticity is established by verifying the
  gateway's signature against a stored webhook secret. A request that fails
  verification is rejected with `400`.
- **Raw body.** Signatures are computed over the exact bytes received, so these
  endpoints must not sit behind anything that rewrites the request body.
- **Acknowledge quickly.** A handled event returns `200 OK`. An event type that
  is not handled also returns `200 OK`, so the gateway does not retry it.
- **Retries are expected.** Both gateways redeliver, so every handler is
  idempotent: replaying an event does not double-charge stock, duplicate order
  lines or re-activate a subscription incorrectly.

---

## 1. Platform Subscription Webhook (Stripe)

### `POST /api/webhook-handler/stripe/`

Drives the salon's own SaaS subscription.

- **Signature header:** `Stripe-Signature`
- **Secret:** `DJSTRIPE_WEBHOOK_SECRET` from the environment.

**Events handled:**

| Event | Effect |
| --- | --- |
| `checkout.session.completed` | Activates the plan named in the session metadata and stores the Stripe subscription id |
| `invoice.payment_succeeded` | Renews the subscription, or completes a plan change when the invoice carries `type: upgrade_subscriptions` |
| `invoice.payment_failed` | Sets the workspace to `past_due` |
| `customer.subscription.deleted` | Sets the workspace to `expired` and clears its plan |

**Expiry:** a `month` plan extends access by 30 days, a `year` plan by 365.

**Metadata** expected on a new subscription checkout session:

```json
{
    "type": "new_subscription",
    "schema_name": "bellasalon",
    "plan_id": "uuid-of-subscription-plan",
    "user_id": "uuid",
    "uid": "uuid"
}
```

Sessions whose `payment_status` is not `paid`, or whose `type` is not
`new_subscription`, are ignored.

**Responses:** `200 OK` when accepted; `400 Bad Request` for an unparseable
payload or a bad signature.

---

## 2. Product Purchase Webhook (Stripe)

### `POST /api/webhook-handler/stripe-product-webhook/<tenant_id>/`

Settles a customer's product purchase for one salon.

- **Path parameter:** `tenant_id` - the workspace UUID.
- **Signature header:** `Stripe-Signature`
- **Secret:** the `webhook_secret` on that salon's active payment
  configuration.

**Event handled:** `checkout.session.completed`.

On receipt the handler, in a single transaction:

1. Resolves the customer from `customer_details.email`.
2. Returns `200 OK` immediately if an invoice already exists for this checkout
   session, so redelivery is a no-op.
3. Creates the invoice as `paid` / `confirmed`, converting Stripe's minor units
   into stored major units for the total, discount and tax.
4. Re-reads the line items from Stripe and creates one order line each, which
   deducts stock.
5. Recalculates the total from the lines.
6. Removes the purchased items from the customer's cart.

If any step fails - including a product that no longer exists - the whole
transaction is rolled back and `500` is returned so Stripe retries. A partially
written invoice is never committed.

**Product metadata** must be set on the checkout session line items; the
`checkout` app does this:

```json
{"product_id": "uuid", "cart_item_id": "uuid"}
```

**Responses:** `200 OK` accepted; `400 Bad Request` for a bad signature,
unparseable payload, missing customer email, or no active payment configuration;
`404 Not Found` for an unknown `tenant_id`; `500` when processing failed and the
event should be retried.

---

## 3. Razorpay Webhook

### `POST /api/webhook-handler/razorpay/<tenant_id>/`

- **Path parameter:** `tenant_id` - the workspace UUID.
- **Signature header:** `X-Razorpay-Signature`
- **Secret:** the `webhook_secret` on that salon's active payment
  configuration.

**Events handled:**

### `payment.captured`

Locks the order, and if it is not already paid marks it `paid` / `confirmed` and
stores the Razorpay payment id. The order's lines were written when the order
was created, so this step only clears the matching items from the customer's
cart. Redelivery changes nothing.

For orders created before lines were snapshotted at checkout, the handler falls
back to building them from the cart so the invoice is never left empty.

### `payment.failed`

Deletes the **unpaid** order, which returns the reserved stock to the products.
An order already marked `paid` is left untouched: Razorpay can deliver a
`payment.failed` for an earlier attempt after a later one succeeded, and that
must not destroy the record of a real purchase.

**Expected payload shape:**

```json
{
    "event": "payment.captured",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_XYZ789",
                "order_id": "order_ABC123"
            }
        }
    }
}
```

**Responses:** `200 OK` accepted (including for an unknown order id);
`400 Bad Request` for a bad signature or no active payment configuration;
`404 Not Found` for an unknown `tenant_id`.

---

## Configuring the Gateways

| Gateway | URL to register |
| --- | --- |
| Stripe, platform subscriptions | `https://<your-domain>/api/webhook-handler/stripe/` |
| Stripe, salon products | `https://<your-domain>/api/webhook-handler/stripe-product-webhook/<tenant_id>/` |
| Razorpay | `https://<your-domain>/api/webhook-handler/razorpay/<tenant_id>/` |

The per-salon secrets are stored through `POST /api/payments/configurations/`.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `200` | Accepted, or deliberately ignored - do not retry |
| `400` | Bad signature, unparseable payload, or no active payment configuration |
| `404` | Unknown tenant |
| `500` | Processing failed; the gateway should retry |
