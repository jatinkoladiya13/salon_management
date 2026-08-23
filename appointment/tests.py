from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.urls import reverse
from django.utils import timezone

from django_tenants.utils import schema_context

from rest_framework import status

from appointment.models import Appointments, Services, StaffServices, TimeSlot
from appointment.tasks import create_recurring_timeslots, send_appointment_reminders
from utils.testing import TenantAPITestCase


class AppointmentTestCase(TenantAPITestCase):
    """Shared fixtures for the appointment suites; holds no tests itself."""

    def make_service(self, name="Haircut", duration=45, price="30.00"):
        with schema_context(self.tenant.schema_name):
            service = Services.objects.create(
                service_name=name,
                duration=duration,
                price=price,
                description=f"{name} service",
            )
            # Bookings require the staff member to actually offer the service.
            StaffServices.objects.get_or_create(staff=self.staff, service=service)
            return service

    def future_slot(self, days=3, start=time(10, 0), end=time(11, 0)):
        with schema_context(self.tenant.schema_name):
            return TimeSlot.objects.create(
                staff=self.staff,
                slot_date=date.today() + timedelta(days=days),
                start_time=start,
                end_time=end,
                is_booked=False,
            )


class AppointmentApiTests(AppointmentTestCase):
    def test_service_crud_routes(self):
        self.authenticate(self.admin)

        list_url = reverse("services-list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = {
            "service_name": "Haircut",
            "duration": 45,
            "price": "30.00",
            "description": "Classic haircut",
        }
        create_response = self.client.post(list_url, payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        service_id = create_response.data["data"]["id"]

        detail_url = reverse("services-detail", args=[service_id])
        retrieve_response = self.client.get(detail_url)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data["data"]["service_name"], "Haircut")

        update_response = self.client.patch(
            detail_url, {"service_name": "Haircut Deluxe"}, format="json"
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["data"]["service_name"], "Haircut Deluxe")

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(Services.objects.filter(id=service_id).exists())

    def test_staff_service_crud_routes(self):
        self.authenticate(self.admin)

        service = Services.objects.create(
            service_name="Massage",
            duration=60,
            price="50.00",
            description="Relaxation massage",
        )

        list_url = reverse("staff-services-list")
        payload = {"staff": str(self.staff.id), "service": str(service.id)}
        create_response = self.client.post(list_url, payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        staff_service_id = create_response.data["data"]["id"]

        detail_url = reverse("staff-services-detail", args=[staff_service_id])
        retrieve_response = self.client.get(detail_url)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

        update_response = self.client.patch(
            detail_url, {"service": str(service.id)}, format="json"
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(StaffServices.objects.filter(id=staff_service_id).exists())

    def test_time_slot_and_appointment_flow(self):
        self.authenticate(self.admin)

        service = self.make_service("Nail Care", duration=30, price="25.00")

        timeslot_url = reverse("timeslots-list")
        timeslot_payload = {
            "staff": str(self.staff.id),
            "slot_date": "2030-01-15",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "is_booked": False,
        }
        timeslot_response = self.client.post(timeslot_url, timeslot_payload, format="json")
        self.assertEqual(timeslot_response.status_code, status.HTTP_201_CREATED)
        timeslot_id = timeslot_response.data["data"]["id"]

        detail_url = reverse("timeslots-detail", args=[timeslot_id])
        retrieve_response = self.client.get(detail_url)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

        self.authenticate(self.customer)
        appointment_payload = {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(timeslot_id),
            "notes": "First appointment",
            "status": "pending",
            "appointment_date": "2030-01-15",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }
        appointment_create_response = self.client.post(
            reverse("appointments-list"), appointment_payload, format="json"
        )
        self.assertEqual(appointment_create_response.status_code, status.HTTP_201_CREATED)

        appointment_id = appointment_create_response.data["data"]["id"]
        self.assertTrue(TimeSlot.objects.get(id=timeslot_id).is_booked)

        list_response = self.client.get(reverse("appointments-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_response.data["data"]["results"]), 1)

        retrieve_appointment_response = self.client.get(
            reverse("appointments-detail", args=[appointment_id])
        )
        self.assertEqual(retrieve_appointment_response.status_code, status.HTTP_200_OK)

        # Confirming is a staff/admin action, not something the customer who
        # booked it may do.
        self.authenticate(self.admin)
        update_appointment_response = self.client.patch(
            reverse("appointments-detail", args=[appointment_id]),
            {"status": "confirmed"},
            format="json",
        )
        self.assertEqual(update_appointment_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_appointment_response.data["data"]["status"], "confirmed")

        self.authenticate(self.admin)
        delete_response = self.client.delete(
            reverse("appointments-detail", args=[appointment_id])
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(Appointments.objects.filter(id=appointment_id).exists())

    def test_dashboard_summary_endpoint(self):
        self.authenticate(self.admin)

        with schema_context(self.tenant.schema_name):
            service_one = Services.objects.create(
                service_name="Pedicure",
                duration=45,
                price="35.00",
                description="Foot care",
            )
            service_two = Services.objects.create(
                service_name="Beard Trim",
                duration=30,
                price="20.00",
                description="Classic beard trim",
            )

            pending_slot = TimeSlot.objects.create(
                staff=self.staff,
                slot_date=date.today(),
                start_time=time(10, 0),
                end_time=time(11, 0),
                is_booked=False,
            )
            confirmed_slot = TimeSlot.objects.create(
                staff=self.staff,
                slot_date=date.today(),
                start_time=time(11, 0),
                end_time=time(12, 0),
                is_booked=True,
            )
            completed_slot = TimeSlot.objects.create(
                staff=self.staff,
                slot_date=date.today(),
                start_time=time(12, 0),
                end_time=time(13, 0),
                is_booked=True,
            )

            Appointments.objects.create(
                customer=self.customer,
                staff=self.staff,
                service=service_one,
                time_slot=pending_slot,
                notes="Pending visit",
                status="pending",
                appointment_date=date.today(),
                start_time=pending_slot.start_time,
                end_time=pending_slot.end_time,
            )
            Appointments.objects.create(
                customer=self.customer,
                staff=self.staff,
                service=service_one,
                time_slot=confirmed_slot,
                notes="Confirmed visit",
                status="confirmed",
                appointment_date=date.today(),
                start_time=confirmed_slot.start_time,
                end_time=confirmed_slot.end_time,
            )
            Appointments.objects.create(
                customer=self.customer,
                staff=self.staff,
                service=service_two,
                time_slot=completed_slot,
                notes="Completed visit",
                status="completed",
                appointment_date=date.today(),
                start_time=completed_slot.start_time,
                end_time=completed_slot.end_time,
            )

        response = self.client.get(reverse("appointments-dashboard"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["summary"]["total_appointments"], 3)
        self.assertEqual(response.data["data"]["summary"]["pending_appointments"], 1)
        self.assertEqual(response.data["data"]["summary"]["confirmed_appointments"], 1)
        self.assertEqual(response.data["data"]["summary"]["completed_appointments"], 1)
        self.assertEqual(response.data["data"]["summary"]["active_services"], 2)

    def test_available_slots_endpoint(self):
        self.authenticate(self.admin)

        with schema_context(self.tenant.schema_name):
            service = Services.objects.create(
                service_name="Facial",
                duration=45,
                price="40.00",
                description="Glow facial",
            )
            StaffServices.objects.create(staff=self.staff, service=service)

            available_slot = TimeSlot.objects.create(
                staff=self.staff,
                slot_date="2030-02-01",
                start_time=time(9, 0),
                end_time=time(10, 0),
                is_booked=False,
            )
            booked_slot = TimeSlot.objects.create(
                staff=self.staff,
                slot_date="2030-02-01",
                start_time=time(10, 0),
                end_time=time(11, 0),
                is_booked=True,
            )
            Appointments.objects.create(
                customer=self.customer,
                staff=self.staff,
                service=service,
                time_slot=booked_slot,
                notes="Booked slot",
                status="pending",
                appointment_date=booked_slot.slot_date,
                start_time=booked_slot.start_time,
                end_time=booked_slot.end_time,
            )

        self.authenticate(self.customer)
        response = self.client.post(
            reverse("appointments-available-slots"),
            {"date": "2030-02-01", "service_id": str(service.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"][0]["id"], str(available_slot.id))
        self.assertEqual(len(response.data["data"]), 1)

    def test_create_recurring_timeslots_task_creates_slots(self):
        with schema_context(self.tenant.schema_name):
            initial_count = TimeSlot.objects.count()

            create_recurring_timeslots()

            self.assertGreater(TimeSlot.objects.count(), initial_count)
            self.assertTrue(TimeSlot.objects.filter(staff=self.staff).exists())

    def test_notify_user_via_socket_sends_payload_to_channel_group(self):
        mock_channel_layer = SimpleNamespace(group_send=AsyncMock())

        with patch("appointment.sockets.get_channel_layer", return_value=mock_channel_layer):
            from appointment.sockets import notify_user_via_socket

            notify_user_via_socket("user-123", self.tenant.schema_name, "appt-456", "hello")

        mock_channel_layer.group_send.assert_awaited_once()

    def test_a_websocket_failure_does_not_propagate(self):
        """
        A push notification must never take down the operation that triggered
        it - a reminder run has to survive a dead channel layer.
        """
        with patch(
            "appointment.sockets.get_channel_layer",
            side_effect=RuntimeError("redis is down"),
        ):
            from appointment.sockets import notify_user_via_socket

            notify_user_via_socket("user-1", self.tenant.schema_name, "a-1", "hi")


class AppointmentBookingRulesTests(AppointmentTestCase):
    def test_booking_a_slot_marks_it_as_taken(self):
        service = self.make_service()
        slot = self.future_slot()

        self.authenticate(self.customer)
        response = self.client.post(reverse("appointments-list"), {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(slot.id),
            "appointment_date": str(slot.slot_date),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        with schema_context(self.tenant.schema_name):
            slot.refresh_from_db()
            self.assertTrue(slot.is_booked)

    def test_the_same_slot_cannot_be_booked_twice(self):
        service = self.make_service()
        slot = self.future_slot()
        payload = {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(slot.id),
            "appointment_date": str(slot.slot_date),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }

        self.authenticate(self.customer)
        first = self.client.post(reverse("appointments-list"), payload, format="json")
        second = self.client.post(reverse("appointments-list"), payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        with schema_context(self.tenant.schema_name):
            self.assertEqual(Appointments.objects.filter(time_slot=slot).count(), 1)

    def test_a_staff_member_who_does_not_offer_the_service_is_refused(self):
        with schema_context(self.tenant.schema_name):
            service = Services.objects.create(
                service_name="Massage", duration=60, price="50.00"
            )
        slot = self.future_slot()

        self.authenticate(self.customer)
        response = self.client.post(reverse("appointments-list"), {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(slot.id),
            "appointment_date": str(slot.slot_date),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_slot_in_the_past_cannot_be_booked(self):
        service = self.make_service()
        slot = self.future_slot(days=-2)

        self.authenticate(self.customer)
        response = self.client.post(reverse("appointments-list"), {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(slot.id),
            "appointment_date": str(slot.slot_date),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_inactive_service_cannot_be_booked(self):
        service = self.make_service()
        with schema_context(self.tenant.schema_name):
            service.is_active = False
            service.save(update_fields=["is_active"])
        slot = self.future_slot()

        self.authenticate(self.customer)
        response = self.client.post(reverse("appointments-list"), {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(slot.id),
            "appointment_date": str(slot.slot_date),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def book(self, service, slot):
        self.authenticate(self.customer)
        return self.client.post(reverse("appointments-list"), {
            "staff": str(self.staff.id),
            "service": str(service.id),
            "time_slot": str(slot.id),
            "appointment_date": str(slot.slot_date),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        }, format="json")

    def test_cancelling_an_appointment_frees_the_slot(self):
        """
        Otherwise the slot stays flagged as booked forever and can never be
        sold again.
        """
        service = self.make_service()
        slot = self.future_slot()
        appointment_id = self.book(service, slot).data["data"]["id"]

        self.authenticate(self.admin)
        response = self.client.patch(
            reverse("appointments-detail", args=[appointment_id]),
            {"status": "cancelled"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            slot.refresh_from_db()
            self.assertFalse(slot.is_booked)

    def test_deleting_an_appointment_frees_the_slot(self):
        service = self.make_service()
        slot = self.future_slot()
        appointment_id = self.book(service, slot).data["data"]["id"]

        self.authenticate(self.admin)
        response = self.client.delete(
            reverse("appointments-detail", args=[appointment_id])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            slot.refresh_from_db()
            self.assertFalse(slot.is_booked)

    def test_a_freed_slot_can_be_booked_again(self):
        service = self.make_service()
        slot = self.future_slot()
        appointment_id = self.book(service, slot).data["data"]["id"]

        self.authenticate(self.admin)
        self.client.patch(
            reverse("appointments-detail", args=[appointment_id]),
            {"status": "cancelled"},
            format="json",
        )

        rebooked = self.book(service, slot)
        self.assertEqual(rebooked.status_code, status.HTTP_201_CREATED)

    def test_a_customer_only_sees_their_own_appointments(self):
        service = self.make_service()
        slot = self.future_slot()
        self.book(service, slot)

        self.authenticate(self.staff)
        staff_view = self.client.get(reverse("appointments-list"))
        self.assertEqual(len(staff_view.data["data"]["results"]), 1)

        with schema_context(self.tenant.schema_name):
            from django.contrib.auth import get_user_model

            other = get_user_model().objects.create_user(
                email="other@tenant.test",
                password=self.PASSWORD,
                groups=[self.user_group],
            )

        self.authenticate(other)
        other_view = self.client.get(reverse("appointments-list"))
        self.assertEqual(len(other_view.data["data"]["results"]), 0)

    def test_a_customer_cannot_change_an_appointment_status(self):
        service = self.make_service()
        slot = self.future_slot()
        appointment_id = self.book(service, slot).data["data"]["id"]

        self.authenticate(self.customer)
        response = self.client.patch(
            reverse("appointments-detail", args=[appointment_id]),
            {"status": "completed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_customer_cannot_delete_an_appointment(self):
        service = self.make_service()
        slot = self.future_slot()
        appointment_id = self.book(service, slot).data["data"]["id"]

        self.authenticate(self.customer)
        response = self.client.delete(
            reverse("appointments-detail", args=[appointment_id])
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AppointmentReminderTaskTests(AppointmentTestCase):
    def confirmed_appointment(self, hours_away):
        service = self.make_service()
        start = timezone.localtime() + timedelta(hours=hours_away)

        with schema_context(self.tenant.schema_name):
            slot = TimeSlot.objects.create(
                staff=self.staff,
                slot_date=start.date(),
                start_time=start.time().replace(microsecond=0),
                end_time=start.time().replace(microsecond=0),
                is_booked=True,
            )
            return Appointments.objects.create(
                customer=self.customer,
                staff=self.staff,
                service=service,
                time_slot=slot,
                status="confirmed",
                appointment_date=slot.slot_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )

    @patch("appointment.tasks.notify_user_via_socket")
    @patch("appointment.tasks.send_appointment_reminder_email")
    def test_a_confirmed_appointment_inside_the_window_is_reminded(
        self, mock_email, mock_notify
    ):
        self.confirmed_appointment(hours_away=20)

        result = send_appointment_reminders()

        self.assertIn("Reminder task finished", result)
        self.assertEqual(mock_email.delay.call_count, 1)
        # Customer and staff each get a push.
        self.assertEqual(mock_notify.call_count, 2)

    @patch("appointment.tasks.notify_user_via_socket")
    @patch("appointment.tasks.send_appointment_reminder_email")
    def test_the_email_task_is_told_which_schema_to_read(
        self, mock_email, mock_notify
    ):
        """
        Appointments live in the tenant schema; a worker connected elsewhere
        would simply not find the row.
        """
        self.confirmed_appointment(hours_away=20)

        send_appointment_reminders()

        args = mock_email.delay.call_args.args
        self.assertEqual(args[-1], self.tenant.schema_name)

    @patch("appointment.tasks.notify_user_via_socket")
    @patch("appointment.tasks.send_appointment_reminder_email")
    def test_running_the_task_twice_does_not_remind_twice(
        self, mock_email, mock_notify
    ):
        """
        The old implementation keyed off a 15-minute slice of wall clock, so a
        repeated or delayed beat re-sent (or skipped) reminders.
        """
        self.confirmed_appointment(hours_away=20)

        send_appointment_reminders()
        send_appointment_reminders()

        self.assertEqual(mock_email.delay.call_count, 1)

    @patch("appointment.tasks.notify_user_via_socket")
    @patch("appointment.tasks.send_appointment_reminder_email")
    def test_an_appointment_beyond_the_window_is_not_reminded(
        self, mock_email, mock_notify
    ):
        self.confirmed_appointment(hours_away=72)

        send_appointment_reminders()

        self.assertEqual(mock_email.delay.call_count, 0)

    @patch("appointment.tasks.notify_user_via_socket")
    @patch("appointment.tasks.send_appointment_reminder_email")
    def test_an_unconfirmed_appointment_is_not_reminded(
        self, mock_email, mock_notify
    ):
        appointment = self.confirmed_appointment(hours_away=20)
        with schema_context(self.tenant.schema_name):
            appointment.status = "pending"
            appointment.save(update_fields=["status"])

        send_appointment_reminders()

        self.assertEqual(mock_email.delay.call_count, 0)
