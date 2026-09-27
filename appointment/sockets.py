from channels.layers import get_channel_layer
import asyncio
import logging

logger = logging.getLogger(__name__)


async def notify_user_via_socket_async(user_id, schema_name, appointment_id, message):
    """
    Asynchronously sends a notification to a specific user via WebSocket.
    """
    channel_layer = get_channel_layer()
    group_name = f"notification_{schema_name}_{user_id}"

    payload = {

        "type": "send_notification",
        "data":{
            "type":"appointment_reminder",
            "user_id": str(user_id),
            "appoinment_id": str(appointment_id),
            "message": message
        }
    }
      
    await channel_layer.group_send(
        group_name, payload
    )

def notify_user_via_socket(user_id, schema_name, appointment_id, message):
    """
    Fire-and-forget notification from synchronous code (Celery tasks, views).

    A websocket push must never take down the operation that triggered it, and
    asyncio.run() raises outright if a loop is already running on this thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        # Already inside an event loop - schedule instead of calling run().
        asyncio.ensure_future(
            notify_user_via_socket_async(
                user_id, schema_name, appointment_id, message
            )
        )
        return

    try:
        asyncio.run(
            notify_user_via_socket_async(
                user_id, schema_name, appointment_id, message
            )
        )
    except Exception:
        logger.warning(
            "Could not push websocket notification to user %s", user_id
        )