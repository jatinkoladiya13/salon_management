# MCP + OpenAI Integration Guide

This guide explains how to connect an AI assistant to salon-management data
using the Model Context Protocol (MCP). It covers the MCP server, the OpenAI
client, the tool-call loop, local setup, and the changes needed to connect this
example to the salon's authenticated Django API.

## What MCP does

MCP is a standard way for an AI application (the **host**) to discover and call
tools exposed by another application (the **MCP server**). MCP does not itself
provide an AI model. In this project:

- **OpenAI** interprets the user's question and decides whether to call a tool.
- **`ai_client.py`** is the host: it sends the question to OpenAI, runs any
  requested MCP tool, and returns the tool result to OpenAI.
- **`mcp_server/server.py`** defines MCP tools and calls salon application APIs.
- **Django REST API** owns the salon appointment data.

```text
User
  | question
  v
ai_client.py (host) ---- question / tool result ----> OpenAI Responses API
  |                                                     |
  | MCP list_tools / call_tool                         | function call request
  v                                                     |
mcp_server/server.py <----------------------------------+
  |
  | authenticated HTTP request (configure for your deployment)
  v
Django appointment API
```

OpenAI does not connect directly to the MCP server. The host translates between
OpenAI's function-call format and MCP's `list_tools` / `call_tool` operations.

## Current example: important integration details

The files in this example currently behave as follows:

1. `ai_client.py` imports `mcp` and uses `Client(mcp)`. This is an **in-process**
   connection. Running `python mcp_server/server.py` in a second terminal is
   not needed for this mode.
2. MCP currently exposes `get_appointments(date: str)`.
3. OpenAI is offered a no-argument function named `get_today_appointments`.
   When OpenAI requests it, the host calls MCP's `get_appointments` using
   today's local date (`date.today().isoformat()`).
4. The MCP server sample currently calls
   `http://localhost:8000/appointments?date=...`.

That last URL is an illustrative adapter, **not the Django appointment route
documented in this repository**. The Django route is
`/api/appointment/appointments/`, and its documented list endpoint requires an
authenticated user and applies role/tenant scoping. Before using real salon
data, update the MCP server to use the correct Django URL, authentication
credentials, tenant hostname, and filtering/query parameters for your
deployment. Do not expose customer appointment data through an unauthenticated
or cross-tenant endpoint.

The sample API's response shape may also differ from the Django endpoint's
paginated appointment response. Update the tool's result formatting/counting
based on the actual API response; do not assume that the number of returned
items is the total count unless pagination metadata confirms it.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `mcp_server/server.py` | Declares MCP tools and calls the salon API. |
| `ai_client.py` | Connects to MCP and OpenAI, manages user input and tool calls. |
| `.env` | Stores local secrets such as `OPENAI_API_KEY`; do not commit it. |

Keep the OpenAI function schema in `ai_client.py` consistent with the MCP tool
contract. The OpenAI-facing tool name can differ from the MCP tool name, but the
host must explicitly map between them, as the current appointment example does.

## Prerequisites

- Python and the project's virtual environment.
- An OpenAI API key with access to the selected model.
- The salon Django API running and reachable from the MCP server.
- A tenant/user authentication method authorized to read the intended
  appointment data.

The repository's current `requirements.txt` does not declare the packages used
by these example files. Install the integration dependencies into the active
virtual environment if they are not already present:

```powershell
.\env\Scripts\Activate.ps1
python -m pip install mcp openai python-decouple httpx
```

For a repeatable deployment, record the chosen MCP and OpenAI package versions
in the project's dependency manifest after validating those versions.

## Configure the OpenAI key

Create a root-level `.env` file (or set the variable in the process
environment):

```env
OPENAI_API_KEY=your-openai-api-key
```

Do not commit `.env` or print the key in logs. `ai_client.py` reads the key with
`python-decouple` and stops with an error if it is missing.

## Run the current in-process example

Start the Django API and required dependencies using the project's normal
development setup. Then run:

```powershell
.\env\Scripts\Activate.ps1
python ai_client.py
```

Ask about today's appointments. Type `exit` or `quit` to close the interactive
client.

Because `ai_client.py` imports `mcp` directly and passes it to `Client`, the
MCP server code runs in the same Python process. The standalone command below
is a different server mode; it is not required by the in-process client:

```powershell
python mcp_server/server.py
```

## MCP server: adding a tool

An MCP tool is an ordinary Python function registered with `@mcp.tool()`. Its
name, parameters, and docstring are used to advertise it to MCP clients.

The current server pattern is:

```python
from mcp.server import MCPServer
import httpx

mcp = MCPServer("Salon Management MCP")


@mcp.tool()
async def get_appointments(date: str):
    """Get appointments for a specific date."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8000/appointments?date={date}"
        )
        response.raise_for_status()
        return response.json()
```

For production, configure the API base URL outside the code, use the
deployment's authentication and tenant-selection mechanism, and validate the
requested date. Keep authorization checks in the trusted API/service layer;
instructions to the model are not a security boundary.

An MCP tool should:

- Have a clear, narrow purpose and typed inputs.
- Validate inputs before making requests.
- Call only the API operations that the current user is allowed to access.
- Raise or report failed HTTP requests instead of returning fabricated or
  success-shaped fallback data.
- Return the minimum necessary customer data.

## Host: discover and call MCP tools

The MCP Python client returns a `ListToolsResult`; the actual tool definitions
are in its `.tools` property:

```python
async with Client(mcp) as mcp_client:
    tools_result = await mcp_client.list_tools()
    available_tools = tools_result.tools
    available_names = {tool.name for tool in available_tools}
```

Do not iterate over the `ListToolsResult` itself or treat it like a tuple.
Validate that the required tool is present before accepting user questions.

To execute a tool, call it through MCP:

```python
result = await mcp_client.call_tool(
    "get_appointments",
    {"date": "2026-10-11"},
)
```

Check the result's `is_error` field and handle failures explicitly. The current
client's `serialize_result()` helper prefers structured content, then text
content, then a JSON representation of the result.

## Host: OpenAI function calling

The host separately describes the operation to OpenAI using the Responses API
tool schema. The current `get_today_appointments` function has no arguments,
so the host determines the date and passes it to MCP.

The request/response cycle is:

1. Send the user question and available OpenAI function definitions to
   `ai.responses.create(...)`.
2. Inspect `response.output` for items whose `type` is `"function_call"`.
3. Parse and validate `call.arguments`.
4. Map the OpenAI function name to an allowed MCP tool and call it.
5. Return a `function_call_output` with the original `call_id`.
6. Send those outputs to OpenAI with `previous_response_id` so the model can
   produce its user-facing answer.

The current client uses this mapping:

```text
OpenAI function: get_today_appointments (no arguments)
        |
        +--> MCP tool: get_appointments({"date": today's ISO date})
```

Only dispatch explicitly allowed function names. Do not let a model-provided
name select arbitrary Python functions, URLs, or tools. Validate decoded
arguments against the expected schema even when the OpenAI tool schema is
strict.

## Connecting to a standalone MCP server

The MCP server can also run separately with Streamable HTTP on
`localhost:8001`:

```powershell
python mcp_server/server.py
```

In this mode, change the host to connect to the running server rather than
importing and passing the local `mcp` object. For MCP Python SDK versions whose
`Client` accepts a Streamable HTTP URL, the connection is typically:

```python
async with Client("http://localhost:8001/mcp") as mcp_client:
    ...
```

Check the installed SDK's server/client transport configuration if you change
the HTTP path, transport, or MCP SDK version. The Django API still needs to be
reachable from the MCP server, and the MCP endpoint itself should be protected
appropriately when exposed beyond a trusted local development environment.

Choose one mode:

| Mode | Host connection | Start MCP server separately? |
| --- | --- | --- |
| In-process (current `ai_client.py`) | `Client(mcp)` | No |
| Streamable HTTP | `Client("http://localhost:8001/mcp")` | Yes |

## Connecting to this repository's Django API

The Django appointment API is documented at
`/api/appointment/appointments/`. Its documented `GET` operation is
authenticated, scoped according to the role, and tenant-specific. A real MCP
adapter therefore needs to account for:

- Correct base URL and appointment endpoint.
- Tenant domain/host selection used by the application.
- A securely stored access token or another service authentication strategy.
- Token refresh/expiry and upstream `401` / `403` responses.
- API query parameters, filtering, pagination, and the response envelope.
- Limiting the result to data the requesting salon/user is permitted to see.
- Avoiding disclosure of unnecessary personal information to the model.

The current sample MCP function accepts `date`, but the Django API documentation
describes filtering by `time_slot__slot_date`. Confirm the actual filter and
pagination behavior in the running API before wiring the adapter. If an
appointment list is paginated, follow all relevant pages (or use a dedicated
count endpoint) before telling the model a total.

## Error handling and privacy

- Keep API keys, tokens, tenant credentials, and customer data out of source
  control and logs.
- Treat tool output as untrusted input. Return only the fields the assistant
  needs.
- Report API/tool errors to the model as errors; do not replace failures with
  empty appointment lists or invented counts.
- Enforce authentication, tenant isolation, and user permissions at the API or
  service boundary, not solely in the system prompt.
- Use HTTPS and appropriate access controls outside local development.
- Review OpenAI data-handling requirements for the customer information sent
  through the Responses API.

## Troubleshooting

| Symptom | Likely cause / check |
| --- | --- |
| `OPENAI_API_KEY is not set` | Add the key to `.env` or the process environment. |
| `AttributeError: 'tuple' object has no attribute 'name'` | The client is treating the list-tools response as a sequence. Read
  `tools_result.tools` and iterate over that list. |
| `MCP appointment tool was not found` | Ensure the registered MCP name matches
  the name checked by the host (`get_appointments` in this example). |
| HTTP connection refused | Start Django and verify the API URL is reachable
  from the MCP process. |
| HTTP `401` or `403` | Configure a valid identity, token, and tenant context;
  check the caller's permissions. |
| HTTP `404` | The sample URL may not match the Django route. The repository route
  is `/api/appointment/appointments/`. |
| AI gives an incorrect total | Check pagination and the API response envelope;
  provide a verified count or all matching records to the model. |
| Separate MCP client cannot connect | Confirm the standalone server is
  running, the configured transport/path match, and the client uses the
  Streamable HTTP URL. |

## Adding another AI-accessible operation

For each new capability:

1. Add a narrow, authorized MCP tool that calls the salon API.
2. Verify its input schema and returned data shape.
3. Add a matching OpenAI function schema.
4. Add an explicit dispatch mapping from the OpenAI function name to the MCP
   tool, including argument validation.
5. Add user-facing instructions that accurately describe when the tool should
   be used. Treat those instructions as guidance, not authorization.
6. Test the MCP tool directly, then test the full question → function call →
   MCP result → final answer flow, including API and permission failures.

## APIs the frontend can use

The frontend should call the Django REST API directly for normal screens and
use MCP-backed AI tools only for conversational queries. These are existing
API routes documented in this repository; they are not automatically exposed
by the current MCP server. The frontend must send the signed-in user's bearer
token, use the correct tenant hostname, and respect the role and permissions
described by each endpoint. List responses may be paginated.

| Frontend screen / feature | API route(s) | What the frontend can display or do |
| --- | --- | --- |
| Sign in and session renewal | `POST /api/account/login/`; `POST /api/account/refresh_token/` | Sign in, show the current user's identity/role and salon logo, and renew an expired access token. |
| Customer registration | `POST /api/account/usermanage/` | Register a customer in the current workspace. |
| Appointment booking | `GET /api/appointment/services/`; `GET /api/appointment/staff-services/`; `POST /api/appointment/appointments/available_slots/`; `GET /api/appointment/timeslots/`; `POST /api/appointment/appointments/` | Browse active services, find staff who offer them, show availability, and submit a booking. |
| My appointments / salon calendar | `GET /api/appointment/appointments/`; `GET /api/appointment/appointments/{id}/`; `GET /api/appointment/appointments/dashboard/` | Display the signed-in user's appointments; staff/admin views are scoped by their role. Show status summaries from the dashboard endpoint. |
| Appointment operations | `PATCH /api/appointment/appointments/{id}/`; `DELETE /api/appointment/appointments/{id}/` | Let permitted staff/admin users update statuses or notes and let tenant admins delete. Customers cannot change appointment status. |
| Appointment reminders | `ws://<tenant-domain>/ws/notifications/?token=<access_token>` | Receive appointment reminder events in real time; use `wss://` in production. |
| Retail catalogue | `GET /api/product-sales/product-categories/`; `GET /api/product-sales/products/` | Display categories, product descriptions/images, selling prices, and stock availability. |
| Shopping cart and orders | `/api/product-sales/cart-items/`; `/api/product-sales/invoices/` | Read/update the current user's cart and display only their own orders. |
| Product payment | `POST /api/checkout/product-checkout-session/`; `POST /api/checkout/verify-razorpay-payment/` | Start the configured payment-provider flow and verify a Razorpay payment when applicable. Use the checkout documentation for the gateway-specific response shape. |
| Staff/admin product management | `POST`, `PUT`, `PATCH`, `DELETE /api/product-sales/products/` and `/api/product-sales/product-categories/` | Manage catalogue items and categories; writes are role-restricted. Product image uploads use `multipart/form-data`. |
| Inventory screens | `/api/stock-management/stock-purchases/` | Display supplier purchases; permitted staff/admin users can record or edit purchases, while deletion is tenant-admin-only. Purchases change product stock. |
| Subscription / billing UI | `GET /api/subscription/get-own-subscription/`; `GET /api/subscription/invoice/`; subscription checkout/upgrade routes | Show the workspace's plan and status, and show tenant-admin billing history or launch a hosted plan checkout/upgrade. |
| Salon directory / platform admin | `/api/salon/details/` | Display and manage salon records only in the public-schema superuser interface; this is not a tenant-admin salon settings API. |

For exact request/response fields, filters, pagination, and permissions, refer
to the owning app's API document:

- [Appointments, services, availability, dashboard, and notifications](./appointment/API.md)
- [Accounts and authentication](./account/API.md)
- [Products, cart, and retail orders](./product_sales/API.md)
- [Inventory purchases](./stock_management/API.md)
- [Checkout and payment flows](./checkout/API.md)
- [Plans and billing](./subscription/API.md)
- [Platform salon records](./salonDetails/API.md)

### Suggested AI features for the frontend

The current `ai_client.py` is a terminal demo, not a browser-facing API. To put
the assistant in a web frontend, create a backend chat endpoint (or a separate
authenticated AI service) that:

1. Authenticates the user and determines their tenant and role from trusted
   server-side request context.
2. Calls only MCP tools allowed for that identity and passes the identity
   securely to the data/API layer.
3. Returns the assistant's answer to the frontend without exposing OpenAI or
   salon API secrets to browser code.

Useful read-only assistant features, once their tools enforce the same API
authorization and tenant scoping, include:

- "What appointments do I have today?" using the caller-scoped appointments
  endpoint.
- "How many appointments are confirmed?" using the appointment dashboard or a
  complete, correctly filtered appointment query.
- "What services do you offer?" using the active services endpoint.
- "When is the next available slot for this service?" using the availability
  endpoint.
- "Is this product in stock and what does it cost?" using the product catalogue.
- "What is the status of my order?" using the caller's own invoices.
- Tenant-admin questions about salon appointment summaries or stock, subject
  to the corresponding role permissions.

Do not offer a role-independent AI tool that can retrieve every tenant's
appointments, customer profiles, invoices, or payment configuration. Keep
write operations such as booking, cancelling, changing appointment status,
placing orders, or changing subscriptions behind explicit authorization and
confirmation in the frontend and backend. Payment credentials and secrets
must never be sent to the model or returned to browser clients.
