import logging

from celery import shared_task
from datetime import date, timedelta, datetime, time
from django_tenants.utils import schema_context
from django.db.models import Q
from django.utils import timezone

from account.models import User
from .models import TimeSlot, Appointments
from .email import send_appointment_reminder_email
from .sockets import notify_user_via_socket
from tenant.models import Tenant
from core.constants import TENANTSTAFF_GROUP_NAME

logger = logging.getLogger(__name__)

# Working hours and slot length for generated slots.
WORK_START_TIME = time(9, 0)
WORK_END_TIME = time(17, 0)
SLOT_DURATION_MINUTES = 60
SLOT_HORIZON_DAYS = 15


def _create_timeslots_for_current_schema():
    """Generate the rolling slot window for the schema that is already active."""
    staff_members = User.objects.filter(
        is_active=True, groups__name=TENANTSTAFF_GROUP_NAME
    ).distinct()

    start_date = date.today()
    end_date = start_date + timedelta(days=SLOT_HORIZON_DAYS)
    created_count = 0

    for staff in staff_members:
        current_date = start_date
        while current_date <= end_date:
            current_time = datetime.combine(current_date, WORK_START_TIME)
            end_datetime = datetime.combine(current_date, WORK_END_TIME)

            while current_time < end_datetime:
                slot_start_time = current_time.time()
                slot_end = current_time + timedelta(minutes=SLOT_DURATION_MINUTES)

                # Do not create a slot that would run past the end of the day.
                if slot_end > end_datetime:
                    break

                # get_or_create is idempotent, preventing duplicates
                _, created = TimeSlot.objects.get_or_create(
                    staff=staff,
                    slot_date=current_date,
                    start_time=slot_start_time,
                    defaults={'end_time': slot_end.time()},
                )
                created_count += int(created)

                current_time = slot_end
            current_date += timedelta(days=1)

    return staff_members.count(), created_count


@shared_task
def create_recurring_timeslots():
    """
    A daily task to create timeslots for the next 15 days for all staff members.
    This task should be scheduled to run once every day.

    Staff, time slots and appointments all live in the tenant schemas, so the
    task has to walk the tenants. Run against whatever schema Celery happened to
    be connected to, it only ever looked at the public schema - which holds no
    staff - and therefore created nothing at all.
    """
    total_staff = 0
    total_created = 0

    for tenant in Tenant.objects.exclude(schema_name="public"):
        with schema_context(tenant.schema_name):
            staff_count, created_count = _create_timeslots_for_current_schema()

        total_staff += staff_count
        total_created += created_count
        logger.info(
            "Created %s time slots for %s staff in %s",
            created_count,
            staff_count,
            tenant.schema_name,
        )

    return (
        f"Created {total_created} time slots for {total_staff} staff members "
        f"across all tenants."
    )


def _starting_within(now, horizon):
    """
    Q object for appointments starting between ``now`` and ``now + horizon``.

    The start is stored as a separate date and time, so the window has to be
    expressed as "an earlier day, or the boundary day up to the boundary time"
    rather than a single datetime comparison.
    """
    upper = now + horizon

    not_yet_started = Q(appointment_date__gt=now.date()) | Q(
        appointment_date=now.date(), start_time__gte=now.time()
    )
    before_upper = Q(appointment_date__lt=upper.date()) | Q(
        appointment_date=upper.date(), start_time__lte=upper.time()
    )

    return not_yet_started & before_upper


@shared_task
def send_appointment_reminders():
    """
    Sends reminders for appointments that are 24 hours or 15 minutes away.
    This task should be scheduled to run every 15 minutes.

    Reminders are driven by "is it due and has it been sent", not by a 15-minute
    slice of wall clock, so a late or repeated run neither double-sends nor
    skips a customer.
    """
    now = timezone.localtime()

    reminder_rules = (
        ("reminder_24h_sent_at", timedelta(hours=24), "24_hour", "24 hours"),
        ("reminder_15min_sent_at", timedelta(minutes=15), "15_minute", "15 minutes"),
    )

    tenants = Tenant.objects.exclude(schema_name='public')
    sent = 0

    for tenant in tenants:
        with schema_context(tenant.schema_name):
            for sent_field, horizon, reminder_type, human in reminder_rules:
                appointments = (
                    Appointments.objects.select_related(
                        "customer", "staff", "service"
                    )
                    .filter(_starting_within(now, horizon), status="confirmed")
                    .filter(**{f"{sent_field}__isnull": True})
                )

                for appt in appointments:
                    # Mark first: a crash mid-send is better than a customer
                    # being emailed on every subsequent run.
                    Appointments.objects.filter(pk=appt.pk).update(
                        **{sent_field: timezone.now()}
                    )

                    send_appointment_reminder_email.delay(
                        str(appt.id), reminder_type, tenant.schema_name
                    )
                    notify_user_via_socket(
                        appt.customer.id,
                        tenant.schema_name,
                        appt.id,
                        f"Reminder: Your appointment for "
                        f"{appt.service.service_name} is in {human}.",
                    )
                    notify_user_via_socket(
                        appt.staff.id,
                        tenant.schema_name,
                        appt.id,
                        f"Reminder: Your appointment with "
                        f"{appt.customer.username} is in {human}.",
                    )
                    sent += 1

    return f"Reminder task finished for all tenants. {sent} reminders sent."
