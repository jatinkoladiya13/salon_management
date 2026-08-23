from contextlib import nullcontext

from celery import shared_task
from django.template.loader import render_to_string
from django_tenants.utils import schema_context
from salon_management.celery import send_mail
from .models import Appointments


@shared_task
def send_appointment_reminder_email(appointment_id, reminder_type, schema_name=None):
    """
    Sends a reminder email to both the customer and the staff member.

    ``schema_name`` is passed explicitly by the caller: appointments live in the
    tenant schemas, and a worker that picked this job up while connected to
    another schema would simply not find the row.
    """
    with schema_context(schema_name) if schema_name else nullcontext():
        appointment = (
            Appointments.objects.select_related(
                "customer", "staff", "service", "time_slot"
            )
            .filter(id=appointment_id)
            .first()
        )

        if appointment is None:
            return "Appointment not found."

        subject = f"Reminder: Your Appointment on {appointment.time_slot.slot_date}"
        context = {
            "appointment": appointment,
            "reminder_type": "24 hours" if reminder_type == "24_hour" else "15 minutes",
        }
        html_message = render_to_string("appointments/reminder_email.html", context)

        customer_email = appointment.customer.email
        staff_email = appointment.staff.email

    # Send to customer
    send_mail.apply_async(args=[subject, html_message, customer_email, "html"])
    # Send to staff
    send_mail.apply_async(args=[subject, html_message, staff_email, "html"])

    return f"Reminder emails sent for appointment {appointment_id}."

