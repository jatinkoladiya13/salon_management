# Tenant App API Documentation

Workspace (tenant) and domain administration for the platform operator.

Base URL: `/api/tenant/`

## Multi-Tenancy Model

Each salon is a **tenant** with its own Postgres schema. Requests are routed to
a tenant by host name through its `Domain` record, so `bella.example.com`
resolves to the `bella` schema. The `public` schema holds the cross-tenant
tables: tenants, domains, salon records, subscription plans.

Access tokens carry the schema they were issued for, and a token is rejected on
any other workspace's host.

## Permissions

**Every endpoint in this app requires a public-schema superuser** - the platform
operator. A `TenantAdmin` administers their own salon through the other apps,
not through these routes, and receives `403 Forbidden` here.

`Authorization: Bearer <access_token>` is required throughout.

---

## 1. List Tenants

### `GET /api/tenant/`

- **Success (200 OK):**
    ```json
    [
        {
            "id": "uuid",
            "name": "bellasalon",
            "schema_name": "bellasalon",
            "salonDetails": "uuid",
            "stripe_customer_id": "cus_ABC",
            "stripe_subscription_id": "sub_ABC",
            "subscription_plan": {
                "id": "uuid",
                "name": "Pro Monthly",
                "interval": "month"
            },
            "subscription_status": "active",
            "subscription_end_date": "2026-09-01T00:00:00Z",
            "created_on": "2026-08-01"
        }
    ]
    ```

### `GET /api/tenant/{id}/`

Retrieves one workspace.

---

## 2. Find a Tenant by Salon

### `GET /api/tenant/get-tenant/?salon_id=<uuid>`

- **Description:** The workspaces linked to a salon record.
- **Query parameters:** `salon_id` (uuid, required).
- **Success (200 OK):** a list of matching workspaces.
- **Errors:** `400 Bad Request` when `salon_id` is missing.

---

## 3. Create a Tenant

### `POST /api/tenant/create-tenant/`

- **Description:** Provisions a workspace: the tenant row, its primary domain
  and its database schema, on the free trial plan for 7 days.
- **Request body:**
    ```json
    {
        "tenant_name": "bellasalon",
        "domain_name": "bellasalon.example.com",
        "salon": "uuid-of-salon-details"
    }
    ```
- **`tenant_name`** becomes the schema name.
- **`salon`** is the `SalonDetails` UUID.
- **Success (201 Created):** the submitted details.
- **Errors (all `400 Bad Request`):**
    - A tenant with that name or schema already exists.
    - That domain is already registered.
    - That salon already has a workspace.
    - The salon record does not exist.
    - No free trial plan is configured. Seed one before provisioning.
- **Note:** The tenant row, domain and schema are created in one transaction. If
  schema creation fails nothing is kept, so the name stays available rather than
  being occupied by an unusable workspace.

Self-service signup at `POST /api/account/register/` runs this same flow and
does not need an operator.

---

## 4. Rename a Domain

### `PUT` / `PATCH /api/tenant/{tenant_id}/update-domain/`

- **Description:** Changes a workspace's primary domain.
- **Request body:** `{"domain_name": "newname.example.com"}`
- **Success (200 OK):** `"Domain updated successfully"`
- **Errors:**
    - `400 Bad Request` - `domain_name` missing, or already used by another
      workspace.
    - `404 Not Found` - unknown tenant, or the tenant has no domain.

### `PUT` / `PATCH /api/tenant/{salon_id}/update-domain-by-salon/`

- **Description:** The same rename, addressed by salon id instead of tenant id.
- **Request body:** `{"domain_name": "newname.example.com"}`
- **Errors:** as above; `404 Not Found` when no workspace is linked to that
  salon.

---

## Subscription Fields

| Field | Meaning |
| --- | --- |
| `subscription_status` | `inactive`, `active`, `cancelled`, `expired`, `past_due`, `trial` |
| `subscription_end_date` | When access lapses. Past this point every API call on the workspace returns `401` |
| `stripe_customer_id` | Stripe customer, created on first checkout |
| `stripe_subscription_id` | The active Stripe subscription |

These are normally maintained by the Stripe webhooks rather than edited by hand.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed, or a name/domain/salon is already taken |
| `401` | Missing or invalid token |
| `403` | Not a public-schema superuser |
| `404` | Unknown tenant, salon or domain |
| `500` | Unexpected server fault; the detail is logged, not returned |

---

## Related Management Commands

```
python manage.py create_public_tenant
python manage.py create_new_schema <schema_name>
python manage.py setup_project
```
