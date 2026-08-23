# Appointment App API Documentation

Salon services, staff skills, bookable time slots and appointments.

Base URL: `/api/appointment/`

## Authentication

All endpoints require a bearer token:

`Authorization: Bearer <your_jwt_token>`

Responses use the project envelope:

```json
{
    "error": false,
    "data": { },
    "message": "Human readable summary"
}
```

List endpoints are paginated, so `data` is `{count, next, previous, results}`.
Pass `page`, `page_size` (max 50) or `get_all=true`.

## Booking Model

1. A **Service** is something the salon sells - a haircut, a facial - with a
   duration and a price.
2. A **StaffService** records that a particular staff member performs a
   particular service. This is what makes them bookable for it.
3. A **TimeSlot** is a concrete bookable window for one staff member. Slots are
   generated nightly for the next 15 days (09:00-17:00, hourly) by the
   `create_recurring_timeslots` Celery task, and can also be managed by hand.
4. An **Appointment** binds a customer, a staff member, a service and a slot.
   Booking marks the slot `is_booked`, and cancelling releases it.

---

## 1. Services

**Endpoint:** `/api/appointment/services/`

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user |
| Create / update | `POST`, `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

### `GET /api/appointment/services/`

- **Query parameters:** `search` (name, description), `is_active`, `price`,
  `duration`, plus pagination.
- **Success (200 OK):**
    ```json
    {
        "id": "uuid",
        "service_name": "Haircut",
        "duration": 30,
        "price": "25.00",
        "description": "Standard haircut.",
        "is_active": true,
        "created_at": "2026-08-01T09:00:00Z",
        "updated_at": "2026-08-01T09:00:00Z"
    }
    ```
  Only active services are listed.

### `POST /api/appointment/services/`

- **Request body:**
    ```json
    {
        "service_name": "Manicure",
        "duration": 45,
        "price": "35.00",
        "description": "Nail care and polish.",
        "is_active": true
    }
    ```
- **Rules:** `service_name` is required and unique; `duration` is a positive
  number of minutes; `price` must be greater than zero.
- **Success (201 Created):** the created service.

### `PUT` / `PATCH` / `DELETE /api/appointment/services/{id}/`

Standard update and delete. Deleting a service cascades to its appointments, so
prefer `is_active: false` for something you may still need to report on.

---

## 2. Staff Services

**Endpoint:** `/api/appointment/staff-services/`

Links staff to the services they perform. A customer cannot book a staff member
for a service that is not linked here.

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user |
| Create / update | `POST`, `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

### `GET /api/appointment/staff-services/`

- **Query parameters:** `staff`, `service`, `service__is_active`,
  `service__price`, `service__duration`, `search`, plus pagination.
- **Success (200 OK):**
    ```json
    {"id": "uuid", "staff": "staff_user_id", "service": "service_id"}
    ```

### `POST /api/appointment/staff-services/`

- **Request body:** `{"staff": "uuid", "service": "uuid"}`
- **Rules:** the user must hold the `Staff` role; the pair must be unique.
- **Success (201 Created):** the created link.

---

## 3. Time Slots

**Endpoint:** `/api/appointment/timeslots/`

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user |
| Create / update | `POST`, `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

### `GET /api/appointment/timeslots/`

- **Query parameters:** `staff`, `slot_date`, `is_booked`, `start_time`,
  `end_time`, `search`, plus pagination.
- **Success (200 OK):**
    ```json
    {
        "id": "uuid",
        "staff": "staff_user_id",
        "slot_date": "2026-08-05",
        "start_time": "10:00:00",
        "end_time": "11:00:00",
        "is_booked": false
    }
    ```

### `POST /api/appointment/timeslots/`

- **Request body:**
    ```json
    {
        "staff": "uuid",
        "slot_date": "2026-08-05",
        "start_time": "10:00:00",
        "end_time": "11:00:00",
        "is_booked": false
    }
    ```
- **Rules:** the user must hold the `Staff` role, and the combination of staff,
  date and start time must be unique.

### `DELETE /api/appointment/timeslots/{id}/`

Removes a slot - useful for blocking out time. A slot that an appointment points
at is protected and cannot be deleted; cancel the appointment first.

---

## 4. Appointments

**Endpoint:** `/api/appointment/appointments/`

| Action | Method | Permission |
| --- | --- | --- |
| List / retrieve | `GET` | Any authenticated user, scoped by role |
| Create | `POST` | Any authenticated user |
| Update | `PUT`, `PATCH` | `TenantAdmin` or `Staff` |
| Delete | `DELETE` | `TenantAdmin` |

**Visibility:** a `TenantAdmin` sees every appointment, a `Staff` member sees
their own, a customer sees theirs.

### `GET /api/appointment/appointments/`

- **Query parameters:** `status`, `customer`, `staff`, `service`,
  `time_slot__slot_date`, `search`, plus pagination.
- **Success (200 OK):**
    ```json
    {
        "id": "uuid",
        "customer": {"id": "uuid", "username": "Alex Doe", "email": "alex@example.com"},
        "staff": {"id": "uuid", "username": "Sam Stylist"},
        "service": {"id": "uuid", "service_name": "Haircut", "price": "25.00"},
        "time_slot": {
            "id": "uuid",
            "slot_date": "2026-08-05",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "is_booked": true
        },
        "notes": "First visit",
        "status": "confirmed",
        "created_at": "2026-08-01T09:00:00Z",
        "updated_at": "2026-08-01T09:00:00Z"
    }
    ```

### `POST /api/appointment/appointments/`

- **Description:** Books an appointment and marks the slot taken.
- **Permissions:** Any authenticated user. A customer books for themselves - the
  `customer` field is ignored and taken from the token. An admin or staff member
  may book on a customer's behalf by supplying `customer`.
- **Request body:**
    ```json
    {
        "staff": "uuid",
        "service": "uuid",
        "time_slot": "uuid",
        "appointment_date": "2026-08-05",
        "start_time": "10:00:00",
        "end_time": "11:00:00",
        "notes": "Optional customer notes."
    }
    ```
- **Success (201 Created):** the created appointment.
- **Errors (all `400 Bad Request`):**
    - The slot is already booked. The slot is locked for the duration of the
      booking, so of two simultaneous requests exactly one succeeds.
    - The slot belongs to a different staff member.
    - `appointment_date`, `start_time` or `end_time` does not match the slot.
    - The staff member does not perform the selected service.
    - The service is no longer active.
    - The slot is in the past.
    - The customer does not hold the `User` role, or the staff member does not
      hold the `Staff` role.

### `PATCH /api/appointment/appointments/{id}/`

- **Description:** Used by admins and staff to move an appointment through its
  lifecycle or amend the notes.
- **Permissions:** `TenantAdmin` or `Staff`. A customer cannot change the status
  of their own appointment.
- **Request body:** `{"status": "completed"}`
- **Statuses:** `pending`, `confirmed`, `in_progress`, `completed`,
  `cancelled`, `no_show`.
- **Side effect:** setting `cancelled` or `no_show` releases the slot so it can
  be sold again; moving back to an active status takes it again.

### `DELETE /api/appointment/appointments/{id}/`

- **Permissions:** `TenantAdmin`.
- **Side effect:** the slot is released.

### `POST /api/appointment/appointments/available_slots/`

- **Description:** Finds bookable slots for a service on a date.
- **Permissions:** Any authenticated user.
- **Request body:**
    ```json
    {"date": "2026-08-05", "service_id": "uuid"}
    ```
- **Success (200 OK):** the free slots across every active staff member who
  performs that service.
    ```json
    {
        "error": false,
        "data": [
            {
                "id": "uuid",
                "staff": "staff_user_id",
                "slot_date": "2026-08-05",
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "is_booked": false
            }
        ],
        "message": "Available slots retrieved"
    }
    ```
  Slots already in the past are excluded, and a past date returns an empty list.
  If no staff member performs the service the list is empty with the message
  `"No staff available for this service."`
- **Errors:** `404 Not Found` when `service_id` does not exist.

### `GET /api/appointment/appointments/dashboard/`

- **Description:** Appointment counts by status, scoped the same way as the
  list endpoint.
- **Permissions:** Any authenticated user.
- **Success (200 OK):**
    ```json
    {
        "error": false,
        "data": {
            "summary": {
                "total_appointments": 5,
                "pending_appointments": 2,
                "confirmed_appointments": 1,
                "in_progress_appointments": 1,
                "completed_appointments": 1,
                "cancelled_appointments": 0,
                "no_show_appointments": 0,
                "active_services": 3
            }
        },
        "message": "Dashboard summary retrieved successfully"
    }
    ```

---

## 5. WebSocket Notifications

**Endpoint:** `ws://<your_domain>/ws/notifications/?token=<access_token>`

- **Description:** Pushes real-time notifications, currently appointment
  reminders, to the authenticated user.
- **Authentication:** the JWT access token as a `token` query parameter. The
  connection is closed immediately if it is missing, invalid or does not resolve
  to a user.
- **On connect** the server sends:
    ```json
    {
        "type": "connection",
        "status": "connected",
        "user_id": "uuid",
        "message": "WebSocket connected successfully"
    }
    ```
- **Server to client:**
    ```json
    {
        "type": "appointment_reminder",
        "user_id": "uuid",
        "appoinment_id": "uuid",
        "message": "Reminder: Your appointment for Haircut is in 24 hours."
    }
    ```
- **Client to server:** the connection is primarily for receiving. `{"action":
  "ping"}` is answered with `{"type": "pong"}`; anything else returns an error
  message.

---

## 6. Background Tasks

Both run under Celery beat and iterate every tenant.

### `create_recurring_timeslots`

Runs daily at midnight. Creates hourly 09:00-17:00 slots for the next 15 days
for every active staff member in every workspace. Idempotent, so a repeated run
creates nothing new.

### `send_appointment_reminders`

Runs every 15 minutes. Emails and pushes a reminder for every `confirmed`
appointment starting within the next 24 hours, and again within the next 15
minutes. Each reminder is recorded against the appointment once it is sent, so a
late or repeated run neither double-sends nor skips a customer.

---

## Error Reference

| Status | Meaning |
| --- | --- |
| `400` | Validation failed - slot taken, in the past, staff/service mismatch |
| `401` | Missing or invalid token |
| `403` | The role may not perform this action |
| `404` | Unknown object, or one outside the caller's scope |
| `409` | Conflicts with existing data, such as a duplicate slot |
| `500` | Unexpected server fault; the detail is logged, not returned |
