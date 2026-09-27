# Account App API Documentation

Authentication, user management, password reset and two-factor setup.

Base URL: `/api/account/`

## Conventions

Every response is wrapped in a common envelope:

```json
{
    "error": false,
    "data": { },
    "message": "Human readable summary"
}
```

On failure `error` is `true`, `data` is `{}` and `message` carries the reason.

### Authentication

All endpoints require a bearer token unless stated otherwise:

`Authorization: Bearer <access_token>`

The token is bound to the workspace (tenant) it was issued for. Requests are
routed by host name, so a token minted for `bella.example.com` is rejected on
any other workspace's host.

### Roles

| Role | Meaning |
| --- | --- |
| `SuperAdmin` | Platform operator, only in the public schema |
| `TenantAdmin` | Salon owner / workspace administrator |
| `Staff` | Salon staff member |
| `User` | Customer |

Several endpoints are additionally gated on role-based permissions that a
`TenantAdmin` can toggle (see the `core` app).

---

## 1. Login

### `POST /api/account/login/`

- **Description:** Exchanges credentials for an access and refresh token.
- **Permissions:** Public.
- **Request body:**
    ```json
    {
        "email": "owner@bellasalon.co",
        "password": "Str0ng@Pass1"
    }
    ```
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "refresh": "<refresh_token>",
            "access": "<access_token>",
            "user_data": {
                "id": "uuid",
                "username": "Mary Watson",
                "email": "owner@bellasalon.co",
                "role": "TenantAdmin"
            },
            "company_logo": "/media/company_logo/logo.png"
        },
        "message": "Login Successfully!!!"
    }
    ```
- **Errors:**
    - `401 Unauthorized` - wrong credentials, or the account is deactivated.
    - `400 Bad Request` - the host does not resolve to a known workspace.
    - `401 Unauthorized` - the workspace has no active subscription, or it has
      expired. The message states which.

## 2. Refresh Token

### `POST /api/account/refresh_token/`

- **Description:** Issues a new access token from a refresh token.
- **Permissions:** Public (the refresh token is the credential).
- **Request body:** `{"refresh": "<refresh_token>"}`
- **Success (200 OK):** `data` contains a new `access` token.
- **Errors:** `401 Unauthorized` if the refresh token is expired or invalid.

## 3. Register a New Workspace

### `POST /api/account/register/`

- **Description:** Creates a salon (workspace), its dedicated database schema,
  its domain and the first `TenantAdmin` user. The workspace starts on a 7-day
  free trial.
- **Permissions:** Public.
- **Request body:**
    ```json
    {
        "user_email": "owner@bellasalon.co",
        "user_first_name": "Mary Jane",
        "user_last_name": "Watson",
        "organization_email": "hello@bellasalon.co",
        "organisation_slug": "bellasalon",
        "organisation_name": "Bella Salon",
        "mobile_number": "+919876543210",
        "password": "Str0ng@Pass1",
        "confirm_password": "Str0ng@Pass1"
    }
    ```
- **Field rules:**
    - `user_email` must be a business address; public mailboxes (gmail, yahoo,
      outlook, hotmail, live, zoho, protonmail, aol, icloud) are rejected.
    - `user_first_name` / `user_last_name` accept letters and spaces only.
    - `organisation_slug` becomes the database schema name: letters and single
      underscores only, max 20 characters, normalised to lower case. Reserved
      names (`public`, `admin`, `api`, `www`, `template`, and the Postgres
      internal schemas) and names already in use are rejected.
    - `organisation_name` is optional and defaults to the slug.
    - `password` must satisfy the project password policy and match
      `confirm_password`.
- **Success (200 OK):** echoes the submitted workspace details.
- **Errors:** `400 Bad Request` with per-field messages.
- **Note:** The whole operation is transactional. If the schema cannot be built
  the workspace, its domain and its salon record are all rolled back, so the
  slug stays available.

## 4. User Management

**Endpoint:** `/api/account/usermanage/`

### `GET /api/account/usermanage/`

- **Description:** Lists users in the current workspace.
- **Permissions:** Authenticated, and the caller's role needs
  `read_own_account_only`.
- **Query parameters:**
    - `search` (string): matches `username` and `email`.
    - `page`, `page_size` (int): pagination, `page_size` max 50.
    - `get_all` (bool): return every row unpaginated.
    - `schema_name` (string): read another workspace. Public-schema superuser
      only.
- **Success (200 OK):** a paginated list of user objects.

### `GET /api/account/usermanage/{id}/`

- **Description:** Retrieves one user.
- **Permissions:** As for list.

### `POST /api/account/usermanage/`

- **Description:** Self-service customer registration inside an existing
  workspace. The new user is placed in the `User` group.
- **Permissions:** Public.
- **Request body:**
    ```json
    {
        "email": "customer@example.com",
        "password": "Str0ng@Pass1",
        "first_name": "Alex",
        "last_name": "Doe",
        "mobile": "+919876543210",
        "date_of_birth": "1990-05-01"
    }
    ```
- **Password policy:** at least one digit, one uppercase, one lowercase and one
  special character, and no spaces.
- **Success (200 OK):** the created user object (never includes the password).

### `PUT` / `PATCH /api/account/usermanage/{id}/`

- **Description:** Updates a user. A caller holding only
  `update_own_account_only` can update nothing but their own record.
- **Permissions:** Authenticated with `update_own_account_only`.
- **Notes:** `groups` accepts at most one group; sending more is a
  `400 Bad Request`.

### `DELETE /api/account/usermanage/{id}/`

- **Description:** Deletes a user.
- **Permissions:** `TenantAdmin` only.

### `POST /api/account/usermanage/staff/`

- **Description:** Creates a `Staff` member.
- **Permissions:** `TenantAdmin` only.
- **Request body:** same shape as user creation.
- **Success (200 OK):** the created staff user.

## 5. Forgot Password

### `POST /api/account/forgot-password/send-reset-link/`

- **Description:** Emails a password reset link.
- **Permissions:** Public.
- **Request body:** `{"email": "owner@bellasalon.co"}`
- **Success (200 OK):** always
  `"If the email is valid, a password reset link will be sent to the email."`
- **Note:** The response is deliberately identical whether or not the address is
  registered, so the endpoint cannot be used to discover which addresses exist.
- **Errors:** `400 Bad Request` only when `email` is missing entirely.

### `POST /api/account/forgot-password/reset-password/`

- **Description:** Sets a new password using the emailed `uid` and `token`.
- **Permissions:** Public.
- **Request body:**
    ```json
    {
        "uid": "<base64 user id from the email link>",
        "token": "<token from the email link>",
        "new_password": "BrandNew@123",
        "confirm_password": "BrandNew@123"
    }
    ```
- **Success (200 OK):** `"Password Reset Successfully!!!"`
- **Errors:** `400 Bad Request` for a malformed or tampered link, an expired
  token (valid for 120 minutes), a mismatch between the two passwords, or a
  password that fails the policy.

## 6. Two-Factor Authentication

### `POST /api/account/2fa-setup/`

- **Description:** Generates a TOTP secret and a QR code for an authenticator
  app.
- **Permissions:** Authenticated.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "qr_code": "<base64 PNG>",
            "secret": "JBSWY3DPEHPK3PXP"
        },
        "message": "Get qr code and secret successfully!!!"
    }
    ```
- **Errors:** `400 Bad Request` if 2FA is already enabled for the account.

### `POST /api/account/2fa-verify/`

- **Description:** Confirms the code from the authenticator app and enables 2FA.
- **Permissions:** Authenticated.
- **Request body:** `{"otp": "123456"}`
- **Success (200 OK):** `"2FA enabled successfully"`
- **Errors:** `400 Bad Request` for a missing or wrong code, or if
  `2fa-setup` has not been called for this account yet.

## 7. User Search (Elasticsearch)

### `POST /api/account/search/`

- **Description:** Re-indexes every user in the workspace into Elasticsearch.
- **Permissions:** `TenantAdmin` or public-schema superuser. This walks the
  whole user table, so it is not open to ordinary users.
- **Success (200 OK):** `{"success_count": 42, "errors": []}`

### `GET /api/account/search/`

- **Description:** Searches the user index.
- **Permissions:** `TenantAdmin` or public-schema superuser.
- **Query parameters:**
    - `search` (string): prefix match on `username` and `email`.
    - `role` (string): exact role name.
    - `is_active` (bool).
    - `start_date`, `end_date` (YYYY-MM-DD): filter on `last_login`.
- **Success (200 OK):** the matching user objects. Deactivated users are
  excluded. Index entries that no longer correspond to a real user are skipped
  rather than failing the request.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed; `message` holds the per-field detail |
| `401` | Missing, expired or invalid token, or bad credentials |
| `403` | Authenticated but the role lacks the required permission |
| `404` | The object does not exist, or is outside the caller's scope |
| `409` | The request conflicts with existing data (for example a duplicate) |
| `500` | Unexpected server fault; the detail is logged, not returned |
