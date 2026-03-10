# Stripe Integration Guide

This document explains how **Stripe payments** work in this project.

It covers:

- Stripe setup
- Subscription plans
- Checkout session creation
- Webhook handling
- Credit system
- Subscription lifecycle
- Region-based payment methods
- Example end-to-end flow

---

# 1. Stripe Setup

## Install Required Packages

```bash
pip install stripe dj-stripe
```

## Add to Installed Apps

```python
INSTALLED_APPS = [
    "djstripe",
]
```

## Add Stripe Keys

```env
STRIPE_SECRET_KEY=your_secret_key
STRIPE_PUBLIC_KEY=your_public_key
STRIPE_WEBHOOK_SECRET=your_webhook_secret
```

---

# 2. Stripe Dashboard Setup

## Steps

1. Create Product
2. Create Price
3. Copy required keys

### Example

- **Product:** Pro Plan  
- **Price:** $29/month  

### Sync Stripe Data to Local Database

```bash
python manage.py djstripe_sync_models Product Price
```

This command syncs **Stripe models** to the **Django database**.

---

# 3. Subscription Plan Model

Create your own **Subscription Plan model**.

### Example Fields

- `name`
- `slug`
- `price` (ForeignKey to `djstripe Price`)
- `is_active`
- `credits_minutes`
- `interval`
- `description`

This allows your **system to control plan configuration**, while **Stripe manages billing**.

---

# 4. API Endpoints

## Create Subscription Checkout Session

**POST**

```
/checkout/create-checkout-session/
```

### Request Body

```json
{
  "subscription_plan_id": 2,
  "quantity": 1
}
```

### Purpose

- Create Stripe checkout session
- Start subscription payment

---

## Buy Credits (One-Time Payment)

**POST**

```
/checkout/buy-credit/
```

### Request Body

```json
{
  "price_id": "price_credit_100",
  "quantity": 1
}
```

### Purpose

- Purchase extra call credits
- One-time payment

---

## Webhook Handler

**POST**

```
/webhook-handler/stripe/
```

Handles Stripe events.

---

## Upgrade Subscription

**POST**

```
/subscription/mysubscriptions/upgrade-subscriptions/
```

Example:

```
Basic → Pro
```

---

## Cancel Subscription

**POST**

```
/subscription/mysubscriptions/cancel-subscription/
```

---

## Get Subscription Details

**GET**

```
/subscription/mysubscriptions/
```

Returns:

- active plan
- billing cycle
- status

---

## Call Credit History

**GET**

```
/subscription/mysubscriptions/call-credits/
```

Returns:

- credit usage timeline
- credit balance

---

## Credit Pricing

**GET**

```
/subscription/mysubscriptions/call-credit-pricing/
```

Returns available credit packages.

---

# 5. Stripe Checkout Session Creation

### Example Subscription Session

```python
import stripe

stripe.checkout.Session.create(
    mode="subscription",
    line_items=[
        {
            "price": price_id,
            "quantity": quantity
        }
    ],
    success_url="https://example.com/payment-success",
    cancel_url="https://example.com/payment-cancel",
    customer_email=user.email,
    automatic_payment_methods={"enabled": True},
    metadata={
        "tenant_id": tenant.id,
        "subscription_plan_id": plan.id
    }
)
```

### Purpose of Metadata

- `tenant_id`
- `subscription_plan_id`

This helps identify **which user purchased the subscription**.

---

# 6. Buy Credits Checkout Session

### Example

```python
stripe.checkout.Session.create(
    mode="payment",
    line_items=[
        {
            "price": price_id,
            "quantity": quantity
        }
    ],
    success_url=SUCCESS_URL,
    cancel_url=CANCEL_URL,
    automatic_payment_methods={"enabled": True}
)
```

Used for:

- One-time credit purchase

---

# 7. Stripe Webhook Events

### Webhook Endpoint

```
POST /webhook-handler/stripe/
```

Important events to handle.

---

## 1. checkout.session.completed

Triggered when **payment completes**.

### Purpose

- Confirm successful checkout
- Create or activate subscription
- Process one-time credit purchase

### Example Logic

```python
if event["type"] == "checkout.session.completed":

    session = event["data"]["object"]

    tenant_id = session["metadata"]["tenant_id"]
    plan_id = session["metadata"]["subscription_plan_id"]

    activate_subscription(tenant_id, plan_id)
```

---

## 2. invoice.payment_succeeded

Triggered **every billing cycle**.

### Purpose

- Confirm recurring payment
- Add monthly credits
- Extend subscription

### Example

```python
if event["type"] == "invoice.payment_succeeded":

    invoice = event["data"]["object"]
    subscription_id = invoice["subscription"]

    subscription = get_subscription(subscription_id)

    add_monthly_credits(
        tenant=subscription.tenant,
        credits=subscription.plan.credits_minutes
    )
```

---

## 3. customer.subscription.deleted

Triggered when **subscription is canceled**.

### Purpose

- Deactivate subscription
- Stop future billing

### Example

```python
if event["type"] == "customer.subscription.deleted":
    deactivate_subscription(subscription_id)
```

---

# 8. Middleware Credit Check

Use middleware to prevent usage when **credits are exhausted**.

### Example

```python
def check_tenant_credits(request):

    tenant = request.tenant

    if tenant.available_credits <= 0:
        raise PermissionDenied("No call credits remaining")
```

Used before **API endpoints that consume credits**.

---

# 9. Region-Based Payment Methods

Stripe supports different payment methods depending on:

- Customer country
- Stripe account country
- Currency
- Enabled payment methods

---

## India

Available payment methods may include:

- Card
- UPI
- Wallets
- Netbanking

UPI apps include:

- Google Pay
- PhonePe
- Paytm

Note:

- **UPI usually supports one-time payments**
- **Subscriptions usually require cards**

---

## Europe

Common payment methods:

- Card
- SEPA Debit
- iDEAL
- Bancontact
- Klarna

---

## United States

Common payment methods:

- Card
- ACH Bank Debit
- Cash App Pay
- Link

---

# 10. Recommended Payment Strategy

### Subscription Payments

Use:

```
Card
```

### One-Time Payments

Use:

```
Card + Local Methods
```

### Example Strategy

| Region | Payment Methods |
|------|------|
| India | Card + UPI |
| Europe | Card + SEPA |
| USA | Card + ACH |

This improves **payment success rates**.

---

# 11. Complete Example Flow

### Scenario

User purchases **Pro Plan**.

| Plan | Value |
|-----|-----|
| Name | Pro Plan |
| Price | $29/month |
| Credits | 500 minutes |
| Interval | Monthly |

---

## Step 1 — User Selects Plan

Frontend sends:

```
POST /checkout/create-checkout-session/
```

---

## Step 2 — Create Checkout Session

Backend creates Stripe session.

Stripe redirects user to checkout.

---

## Step 3 — User Pays on Stripe

User completes payment.

Stripe redirects to:

```
/payment-success
```

But the **real confirmation happens via webhook**.

---

## Step 4 — Webhook Trigger

Stripe sends:

```
checkout.session.completed
```

Backend:

- Activate subscription
- Save Stripe subscription ID
- Store tenant subscription

---

## Step 5 — Monthly Billing

Stripe triggers:

```
invoice.payment_succeeded
```

Backend:

- Add monthly credits
- Extend billing cycle

Example:

```
Pro Plan → 500 credits added
```

---

## Step 6 — Credit Usage

User performs calls.

Middleware checks:

```
tenant credits > 0
```

Credits are deducted as usage occurs.

---

## Step 7 — Buy Extra Credits

User buys additional credits.

Endpoint:

```
POST /checkout/buy-credit/
```

Webhook:

```
checkout.session.completed
```

Backend:

```
add purchased credits
```

---

## Step 8 — Upgrade Plan

Endpoint:

```
POST /subscription/mysubscriptions/upgrade-subscriptions/
```

Stripe handles:

- proration billing
- plan change

---

## Step 9 — Cancel Subscription

Endpoint:

```
POST /subscription/mysubscriptions/cancel-subscription/
```

Stripe triggers:

```
customer.subscription.deleted
```

Backend:

```
mark subscription inactive
```

Credits remain valid **until billing cycle ends**.

---

# 12. Full Flow Summary

```
User selects plan
        ↓
Create checkout session
        ↓
Stripe checkout payment
        ↓
checkout.session.completed
        ↓
Activate subscription
        ↓
invoice.payment_succeeded
        ↓
Add monthly credits
        ↓
Middleware checks credits
        ↓
User consumes credits
```

---

# Final Architecture

```
Frontend
   ↓
Django API
   ↓
Stripe Checkout
   ↓
Stripe Webhook
   ↓
Subscription Activation
   ↓
Credit Allocation
   ↓
Tenant Credit Middleware
```