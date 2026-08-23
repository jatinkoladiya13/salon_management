# Salon Details App API Documentation

The salon business record: name, contact details, address, logo and status.

Base URL: `/api/salon/`

## Where This Data Lives

`SalonDetails` rows live in the **public schema**, not in a tenant schema. A
salon record is created during signup and is then linked one-to-one to the
workspace that serves it. Because the data is cross-tenant, these endpoints are
restricted to a **public-schema superuser**; a `TenantAdmin` receives
`403 Forbidden`.

`Authorization: Bearer <access_token>` is required throughout.

---

## Salon Details

**Endpoint:** `/api/salon/details/`

### `GET /api/salon/details/`

- **Description:** Lists salon records.
- **Permissions:** Public-schema superuser with `read_SALON_details`.
- **Query parameters:** `search` (matches name), `page`, `page_size` (max 50),
  `get_all`.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "count": 1,
            "results": [
                {
                    "id": "uuid",
                    "name": "Bella Salon",
                    "slug": "bella-salon",
                    "phone_number": "+919876543210",
                    "organization_email": "hello@bellasalon.co",
                    "company_logo": "/media/company_logo/logo.png",
                    "description": "Hair and beauty",
                    "status": "active",
                    "location_url": "https://maps.example/bella",
                    "address": "12 High Street",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "country": "India",
                    "postal_code": "400001",
                    "created_at": "2026-08-01T09:00:00Z",
                    "updated_at": "2026-08-01T09:00:00Z"
                }
            ]
        },
        "message": "All Salon Details GET Successfully"
    }
    ```

### `GET /api/salon/details/{id}/`

- **Description:** Retrieves one salon, including the workspace it is linked to.
- **Permissions:** Public-schema superuser with `read_SALON_details`.
- **Success (200 OK):** the salon object plus:
    ```json
    "salong_for_tenant": {
        "id": "uuid",
        "name": "bellasalon",
        "schema_name": "bellasalon",
        "subscription_status": "active",
        "subscription_plan": {"id": "uuid", "name": "Pro Monthly"}
    }
    ```
  `salong_for_tenant` is `null` when no workspace has been provisioned yet.

### `POST /api/salon/details/`

- **Description:** Creates a salon record.
- **Permissions:** Public-schema superuser with `create_SALON_details`.
- **Content type:** `multipart/form-data` when sending `company_logo`.
- **Request body:**
    ```json
    {
        "name": "Bella Salon",
        "organization_email": "hello@bellasalon.co",
        "phone_number": "+919876543210",
        "status": "active",
        "address": "12 High Street",
        "city": "Mumbai",
        "state": "Maharashtra",
        "country": "India",
        "postal_code": "400001",
        "description": "Hair and beauty",
        "location_url": "https://maps.example/bella"
    }
    ```
- **`status`:** `active` or `inactive`.
- **`slug`:** generated from `name`; read-only.
- **`company_logo`:** optional upload, JPEG/JPG/PNG, max 1 MB.
- **Success (200 OK):** the created salon.
- **Errors:** `400 Bad Request` for an oversized or non-image logo, or an
  invalid `status`.

### `PUT` / `PATCH /api/salon/details/{id}/`

- **Permissions:** Public-schema superuser with `update_SALON_details`.
- The same logo rules apply. `id` and `slug` cannot be changed.

### `DELETE /api/salon/details/{id}/`

- **Permissions:** Public-schema superuser with `delete_SALON_details`.
- **Warning:** `Tenant.salonDetails` cascades, so deleting a salon deletes the
  workspace that points at it.

---

## Opening Hours

**Endpoint:** `/api/salon/opening-hours/`

Registered but not implemented - the viewset and serializer are placeholders.
Treat these routes as unavailable.

---

## Notes for Clients

- The salon logo returned at login (`company_logo` in the login response) comes
  from this record.
- `status: "inactive"` is a business flag on the salon record; it does not by
  itself disable the workspace. Access is controlled by the workspace's
  subscription state (see the `subscription` app).

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed - logo size or type, invalid status |
| `401` | Missing or invalid token |
| `403` | Not a public-schema superuser, or the role lacks the salon permission |
| `404` | Unknown salon |
| `500` | Unexpected server fault; the detail is logged, not returned |
