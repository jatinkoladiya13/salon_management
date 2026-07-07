from celery import shared_task
from datetime import date, timedelta, datetime, time
from django_tenants.utils import schema_context
from django.conf import settings
from django.db.models import Q

from account.models import User
from .models import TimeSlot, Appointments
from .email import send_appointment_reminder_email
from .sockets import notify_user_via_socket
from tenant.models import Tenant
from core.constants import TENANTSTAFF_GROUP_NAME


@shared_task
def create_recurring_timeslots():
    """
    A daily task to create timeslots for the next 15 days for all staff members.
    This task should be scheduled to run once every day.
    """
    print("Starting to create recurring time slots...")
    staff_members = User.objects.filter(is_active=True, groups__name=TENANTSTAFF_GROUP_NAME).distinct()
    start_date = date.today()
    end_date = start_date + timedelta(days=15)

    # Define working hours and slot duration (can be moved to a settings model later)
    work_start_time = time(9, 0)
    work_end_time = time(17, 0)
    slot_duration_minutes = 60

    for staff in staff_members:
        print(f"Processing staff: {staff.email}")
        current_date = start_date
        while current_date <= end_date:
            current_time = datetime.combine(current_date, work_start_time)
            end_datetime = datetime.combine(current_date, work_end_time)

            while current_time < end_datetime:
                slot_start_time = current_time.time()
                slot_end_time = (current_time + timedelta(minutes=slot_duration_minutes)).time()

                # Avoid creating slots past the work end time
                if slot_end_time > work_end_time and not (slot_end_time.hour == work_end_time.hour and slot_end_time.minute == work_end_time.minute):
                    break

                # get_or_create is idempotent, preventing duplicates
                slot, created = TimeSlot.objects.get_or_create(
                    staff=staff,
                    slot_date=current_date,
                    start_time=slot_start_time,
                    defaults={'end_time': slot_end_time}
                )
                if created:
                    print(f"  Created slot for {staff.email} on {current_date} at {slot_start_time}")

                current_time += timedelta(minutes=slot_duration_minutes)
            current_date += timedelta(days=1)
    print("Finished creating recurring time slots.")
    return f"Time slots created for {staff_members.count()} staff members up to {end_date}."


@shared_task
def send_appointment_reminders():
    """
    Sends reminders for appointments that are 24 hours or 15 minutes away.
    This task should be scheduled to run every 15 minutes.
    """
    now = datetime.now().astimezone()
    print(f"Running appointment reminders at {now}")

    # Time windows for reminders
    reminder_24h_start = now + timedelta(hours=24)
    reminder_24h_end = reminder_24h_start + timedelta(minutes=15)

    reminder_15min_start = now + timedelta(minutes=15)
    reminder_15min_end = reminder_15min_start + timedelta(minutes=15)

    tenants = Tenant.objects.exclude(schema_name='public')

    for tenant in tenants:
        with schema_context(tenant.schema_name):
           # Find appointments needing a 24-hour reminder
            appointments_24h = Appointments.objects.filter(
                status='confirmed',
                time_slot__slot_date=reminder_24h_start.date(),
                time_slot__start_time__gte=reminder_24h_start.time(),
                time_slot__start_time__lt=reminder_24h_end.time()
            )

            for appt in appointments_24h:
                print(f"Sending 24-hour reminder for appointment {appt.id}")
                send_appointment_reminder_email.delay(appt.id, "24_hour")
                notify_user_via_socket(appt.customer.id, tenant.schema_name, appt.id, f"Reminder: Your appointment for {appt.service.service_name} is in 24 hours.")
                notify_user_via_socket(appt.staff.id, tenant.schema_name, appt.id, f"Reminder: Your appointment with {appt.customer.username} is in 24 hours.")

            # Find appointments needing a 15-minute reminder
            appointments_15min = Appointments.objects.filter(
                status='confirmed',
                time_slot__slot_date=reminder_15min_start.date(),
                time_slot__start_time__gte=reminder_15min_start.time(),
                time_slot__start_time__lt=reminder_15min_end.time()
            )

            for appt in appointments_15min:
                print(f"Sending 15-minute reminder for appointment {appt.id}")
                send_appointment_reminder_email.delay(appt.id, "15_minute")
                notify_user_via_socket(appt.customer.id, tenant.schema_name, appt.id, f"Your appointment for {appt.service.service_name} is in 15 minutes.")
                notify_user_via_socket(appt.staff.id, tenant.schema_name, appt.id, f"Your appointment with {appt.customer.username} is in 15 minutes.")
    
    return f"Reminder task finished for all tenants."
