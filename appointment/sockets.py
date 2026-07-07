from channels.layers import get_channel_layer
import asyncio


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
    asyncio.run(notify_user_via_socket_async(user_id, schema_name, appointment_id, message))