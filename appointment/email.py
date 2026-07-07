from celery import shared_task
from django.template.loader import render_to_string
from salon_management.celery import send_mail
from .models import Appointments


@shared_task
def send_appointment_reminder_email(appointment_id, reminder_type):
    """
    Sends a reminder email to both the customer and the staff member.
    """
    try:
        appointment = Appointments.objects.select_related(
            "customer", "staff", "service", "time_slot"
        ).get(id=appointment_id)
    except Appointments.DoesNotExist:
        return "Appointment not found."

    subject = f"Reminder: Your Appointment on {appointment.time_slot.slot_date}"
    context = {
        "appointment": appointment,
        "reminder_type": "24 hours" if reminder_type == "24_hour" else "15 minutes",
    }
    html_message = render_to_string("appointments/reminder_email.html", context)

    # Send to customer
    send_mail.apply_async(args=[subject, html_message, appointment.customer.email, "html"])
    # Send to staff
    send_mail.apply_async(args=[subject, html_message, appointment.staff.email, "html"])

    return f"Reminder emails sent for appointment {appointment_id}."

