# Appointment App API Documentation

This document provides details on the API endpoints available in the `appointment` app.

The base URL for these endpoints is `/api/appointment/`.

## Authentication

All endpoints require token-based authentication. The token should be included in the `Authorization` header as a Bearer token.

`Authorization: Bearer <your_jwt_token>`

---

## 1. Services Endpoints

**Endpoint:** `/api/appointment/services/`

This endpoint manages salon services.

### `GET /api/appointment/services/`

-   **Description:** Retrieves a list of all salon services.
-   **Permissions:** Authenticated users.
-   **Success Response (200 OK):**
    ```json
    [
        {
            "id": "uuid-string",
            "service_name": "Haircut",
            "duration": 30,
            "price": "25.00",
            "description": "Standard haircut.",
            "is_active": true
        }
    ]
    ```

### `GET /api/appointment/services/{id}/`

-   **Description:** Retrieves a single service by its ID.
-   **Permissions:** Authenticated users.
-   **Success Response (200 OK):**
    ```json
    {
        "id": "uuid-string",
        "service_name": "Haircut",
        "duration": 30,
        "price": "25.00",
        "description": "Standard haircut.",
        "is_active": true
    }
    ```

### `POST /api/appointment/services/`

-   **Description:** Creates a new service.
-   **Permissions:** Admin users.
-   **Request Body:**
    ```json
    {
        "service_name": "Manicure",
        "duration": 45,
        "price": "35.00",
        "description": "Nail care and polish.",
        "is_active": true
    }
    ```
-   **Success Response (201 Created):** The newly created service object.

### `PUT /api/appointment/services/{id}/`

-   **Description:** Updates a service completely. All fields are required.
-   **Permissions:** Admin users.
-   **Request Body:** Same as `POST`.
-   **Success Response (200 OK):** The updated service object.

### `PATCH /api/appointment/services/{id}/`

-   **Description:** Partially updates a service. Any subset of fields can be provided.
-   **Permissions:** Admin users.
-   **Request Body:**
    ```json
    {
        "price": "27.50",
        "is_active": false
    }
    ```
-   **Success Response (200 OK):** The updated service object.

### `DELETE /api/appointment/services/{id}/`

-   **Description:** Deletes a service.
-   **Permissions:** Admin users.
-   **Success Response (204 No Content):**

---

## 2. Staff Services Endpoints

**Endpoint:** `/api/appointment/staff-services/`

This endpoint links staff members to the services they provide.

### `GET /api/  `

-   **Description:** Lists which staff members provide which services.
-   **Query Parameters:**
    -   `staff_id` (uuid): Filter by staff member ID.
    -   `service_id` (uuid): Filter by service ID.
-   **Permissions:** Authenticated users.
-   **Success Response (200 OK):**
    ```json
    [
        {
            "id": "uuid-string",
            "staff": "staff_user_id",
            "service": "service_id"
        }
    ]
    ```

### `POST /api/appointment/staff-services/`

-   **Description:** Assigns a service to a staff member.
-   **Permissions:** Admin users.
-   **Request Body:**
    ```json
    {
        "staff": "staff_user_id",
        "service": "service_id"
    }
    ```
-   **Success Response (201 Created):** The newly created staff-service link object.

### `DELETE /api/appointment/staff-services/{id}/`

-   **Description:** Unassigns a service from a staff member.
-   **Permissions:** Admin users.
-   **Success Response (204 No Content):**

---

## 3. Time Slots Endpoints

**Endpoint:** `/api/appointment/timeslots/`

Manages time slots for staff members. Time slots are generally created automatically by a recurring background task (`create_recurring_timeslots`), but these endpoints allow for manual management.

### `GET /api/appointment/timeslots/`

-   **Description:** Retrieves time slots. Can be filtered.
-   **Query Parameters:**
    -   `staff_id` (uuid): Filter by staff member.
    -   `start_date` (YYYY-MM-DD): Filter by start date.
    -   `end_date` (YYYY-MM-DD): Filter by end date.
    -   `is_booked` (boolean): Filter by booking status.
-   **Permissions:** Admin or Staff users.
-   **Success Response (200 OK):**
    ```json
    [
        {
            "id": "uuid-string",
            "staff": "staff_user_id",
            "slot_date": "YYYY-MM-DD",
            "start_time": "HH:MM:SS",
            "end_time": "HH:MM:SS",
            "is_booked": false
        }
    ]
    ```

---

## 5. WebSocket API

This section documents the WebSocket endpoints for real-time communication.

### Notifications Endpoint

**Endpoint:** `ws://<your_domain>/ws/notifications/`

-   **Description:** This endpoint provides real-time notifications to authenticated users. Once connected, the server will push messages to the client, such as appointment reminders.
-   **Connection:**
    -   To authenticate, you must provide your JWT access token as a query parameter in the connection URL.
    -   Example URL: `ws://example.com/ws/notifications/?token=<your_jwt_access_token>`
-   **Server-to-Client Messages:**
    -   The server sends JSON-formatted messages.
    -   **Example Payload (Appointment Reminder):**
        ```json
        {
            "type": "notification",
            "message": "Reminder: Your appointment for Haircut is in 24 hours."
        }
        ```
-   **Client-to-Server Messages:**
    -   This connection is primarily for receiving messages from the server. Clients are not expected to send messages.

### `GET /api/appointment/timeslots/{id}/`

-   **Description:** Retrieves a single time slot by its ID.
-   **Permissions:** Admin or Staff users.
-   **Success Response (200 OK):** A single time slot object.

### `DELETE /api/appointment/timeslots/{id}/`

-   **Description:** Deletes a specific time slot. This is useful for blocking out time or correcting errors.
-   **Permissions:** Admin users.
-   **Success Response (204 No Content):**

---

## 4. Appointments Endpoints

**Endpoint:** `/api/appointment/appointments/`

Manages appointments for customers.

### `GET /api/appointment/appointments/`

-   **Description:** Retrieves a list of appointments. The list is filtered based on the user's role (Admin sees all, Staff sees their own, Customer sees their own).
-   **Permissions:** Authenticated users.
-   **Query Parameters:**
    -   `status` (string): Filter by appointment status (e.g., 'confirmed', 'completed').
    -   `start_date` (YYYY-MM-DD): Filter by start date.
    -   `end_date` (YYYY-MM-DD): Filter by end date.
-   **Success Response (200 OK):**
    ```json
    [
        {
            "id": "uuid-string",
            "customer": { "id": "uuid", "username": "customer_name" },
            "staff": { "id": "uuid", "username": "staff_name" },
            "service": { "id": "uuid", "service_name": "Haircut" },
            "time_slot": "timeslot_id",
            "status": "confirmed",
            "notes": "Some notes.",
            "appointment_date": "YYYY-MM-DD",
            "start_time": "HH:MM:SS",
            "end_time": "HH:MM:SS"
        }
    ]
    ```

### `GET /api/appointment/appointments/{id}/`

-   **Description:** Retrieves a single appointment by its ID.
-   **Permissions:** Authenticated user who is part of the appointment (customer or staff) or an Admin.
-   **Success Response (200 OK):** A single appointment object.

### `POST /api/appointment/appointments/`

-   **Description:** Creates (books) a new appointment.
-   **Permissions:** Authenticated users.
-   **Request Body:**
    ```json
    {
        "service_id": "uuid-string",
        "time_slot_id": "uuid-string",
        "notes": "Optional customer notes."
    }
    ```
-   **Success Response (201 Created):** The newly created appointment object.

### `PATCH /api/appointment/appointments/{id}/`

-   **Description:** Partially updates an appointment. Primarily used by Admins or Staff to change the `status` (e.g., to 'completed' or 'cancelled') or add notes.
-   **Permissions:** Admin or assigned Staff user.
-   **Request Body:**
    ```json
    {
        "status": "completed"
    }
    ```
-   **Success Response (200 OK):** The updated appointment object.

### `POST /api/appointment/appointments/available_slots/`

-   **Description:** Finds available time slots for a specific service on a given date.
-   **Permissions:** Authenticated users.
-   **Request Body:**
    ```json
    {
        "date": "YYYY-MM-DD",
        "service_id": "uuid-string"
    }
    ```
-   **Success Response (200 OK):**
    ```json
    [
        {
            "timeslot_id": "uuid-string",
            "start_time": "HH:MM:SS",
            "end_time": "HH:MM:SS",
            "staff_id": "uuid-string"
        }
    ]
    ```
