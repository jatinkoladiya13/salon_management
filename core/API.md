# Core App API Documentation

Roles (groups) and the role-based permission matrix that gates the rest of the
platform.

Base URL: `/api/core/`

## How Authorisation Works

The project has two layers:

1. **Groups** - every user belongs to exactly one group: `SuperAdmin`,
   `TenantAdmin`, `Staff` or `User`. A group is a role.
2. **Role permissions** - a named permission (for example `read_groups`) is
   switched on or off *per group* by a `RoleBasePermissionsStatus` row. A view
   guarded by `CustomPermission("read_groups")` allows the request only when the
   caller's group has that row set to `true`.

When a group is created, a status row is generated for every known permission,
switched off. A `TenantAdmin` then enables what that role should be able to do.

All endpoints require `Authorization: Bearer <access_token>`.

---

## 1. Groups (Roles)

**Endpoint:** `/api/core/groups/`

### `GET /api/core/groups/`

- **Description:** Lists the roles defined in the workspace.
- **Permissions:** `read_groups`.
- **Query parameters:**
    - `search` (string): matches the role name.
    - `page`, `page_size` (int): `page_size` max 50.
    - `get_all` (bool): return every row unpaginated.
    - `schema_name` (string): read another workspace's roles. Public-schema
      superuser only.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "count": 3,
            "next": null,
            "previous": null,
            "results": [
                {"id": 1, "name": "TenantAdmin", "level": 1}
            ]
        },
        "message": "All Groups Get Successfully"
    }
    ```

### `GET /api/core/groups/{id}/`

- **Description:** Retrieves one role.
- **Permissions:** `read_groups`.

### `POST /api/core/groups/`

- **Description:** Creates a role. Permission rows for every known permission
  are generated automatically, all switched off.
- **Permissions:** `create_groups`.
- **Request body:**
    ```json
    {"name": "Receptionist", "level": 4}
    ```
- **Success (200 OK):** the created role.

### `PUT` / `PATCH /api/core/groups/{id}/`

- **Description:** Renames a role or changes its level.
- **Permissions:** `update_groups`.
- **Errors:** `403 Forbidden` when the target is the `SuperAdmin` role, which is
  immutable.

### `DELETE /api/core/groups/{id}/`

- **Description:** Deletes a role. Its permission rows go with it.
- **Permissions:** `delete_groups`.
- **Errors:** `403 Forbidden` for the `SuperAdmin` role.

---

## 2. Permission Status

**Endpoint:** `/api/core/permission_status/`

### `GET /api/core/permission_status/`

- **Description:** The full permission matrix - one row per (role, permission)
  pair with its on/off state.
- **Permissions:** `read_permission_status`.
- **Query parameters:**
    - `search` (string): matches role name, permission name or status.
    - `group__id` (int): restrict to one role.
    - `page`, `page_size`, `get_all`.
    - `schema_name` (string): public-schema superuser only.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "count": 22,
            "results": [
                {
                    "id": "uuid",
                    "group": {"id": 3, "name": "User", "level": 3},
                    "role_permission": {
                        "id": "uuid",
                        "name": "read_own_account_only",
                        "description": "For only get own account details"
                    },
                    "status": true
                }
            ]
        },
        "message": "All Permissions with Role GET Successfully"
    }
    ```

### `PUT` / `PATCH /api/core/permission_status/{id}/`

- **Description:** Turns a single permission on or off for a role.
- **Permissions:** `update_permission_status`.
- **Request body:** `{"status": true}`
- **Errors:** `403 Forbidden` when the row belongs to the `SuperAdmin` role.

### `PUT /api/core/permission_status/update_bulk_permissions/`

- **Description:** Applies many permission changes at once, typically when
  saving a permissions screen.
- **Permissions:** `update_permission_status`.
- **Request body:**
    ```json
    {
        "data": [
            {"id": "uuid-1", "status": true},
            {"id": "uuid-2", "status": false}
        ]
    }
    ```
- **Success (200 OK):** every updated row, in full.
- **Errors:**
    - `400 Bad Request` - `data` is not a list, an entry is missing `id` or
      `status`, or `status` is not a boolean.
    - `403 Forbidden` - an entry targets the `SuperAdmin` role.
    - `404 Not Found` - `data` is absent or empty, or an `id` does not exist.
- **Note:** The batch is applied in a single transaction. If any entry is
  rejected, none of the changes are kept - a role is never left with a half-
  applied permission set.

---

## Permission Names

| Name | Controls |
| --- | --- |
| `read_SALON_details`, `create_SALON_details`, `update_SALON_details`, `delete_SALON_details` | Salon records |
| `read_groups`, `create_groups`, `update_groups`, `delete_groups` | Roles |
| `read_permission_status`, `update_permission_status` | This permission matrix |
| `read_own_account_only`, `update_own_account_only`, `delete_own_account_only` | The caller's own account |
| `read_users_account`, `create_users_account`, `update_users_account`, `delete_users_account` | Any user account |
| `read_staff_users_account_only`, `create_staff_users_account_only`, `update_staff_users_account_only`, `delete_staff_users_account_only` | Staff accounts |
| `manage_subscription` | Subscription management |

Seed them per workspace with:

```
python manage.py role_base_permissions <schema_name>
python manage.py create_tenantadmin_group <schema_name>
python manage.py create_staff_group <schema_name>
python manage.py create_user_group <schema_name>
```

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Malformed payload |
| `401` | Missing or invalid token |
| `403` | The caller's role does not hold the required permission, or the target is the protected `SuperAdmin` role |
| `404` | Unknown role or permission row |
| `500` | Unexpected server fault; the detail is logged, not returned |
