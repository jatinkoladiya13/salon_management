from contextlib import nullcontext
from datetime import date, time, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from appointment.models import Appointments, Services, StaffServices, TimeSlot
from appointment.tasks import create_recurring_timeslots, send_appointment_reminders
from core.constants import (
    TENANTADMIN_GROUP_NAME,
    TENANTSTAFF_GROUP_NAME,
    TENANTUSER_GROUP_NAME,
)
from core.models import CustomGroup

User = get_user_model()


class AppointmentApiTests(TenantTestCase):
    HOST = "test.localhost"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain.domain = cls.HOST
        cls.domain.save()

        cls.tenant.create_schema(check_if_exists=True, verbosity=0)
        call_command(
            "migrate_schemas",
            schema_name=cls.tenant.schema_name,
            interactive=False,
            verbosity=0,
        )

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.defaults["HTTP_HOST"] = self.HOST

        with schema_context(self.tenant.schema_name):
            CustomGroup.objects.all().delete()

            self.admin_group = CustomGroup.objects.create(
                id=1, name=TENANTADMIN_GROUP_NAME, level=1
            )
            self.staff_group = CustomGroup.objects.create(
                id=2, name=TENANTSTAFF_GROUP_NAME, level=2
            )
            self.user_group = CustomGroup.objects.create(
                id=3, name=TENANTUSER_GROUP_NAME, level=3
            )

            self.admin = User.objects.create_user(
                email="admin@appointment.test",
                password="Password@123",
                first_name="Admin",
                last_name="User",
                is_active=True,
                groups=[self.admin_group],
            )
            self.staff = User.objects.create_user(
                email="staff@appointment.test",
                password="Password@123",
                first_name="Staff",
                last_name="Member",
                is_active=True,
                groups=[self.staff_group],
            )
            self.customer = User.objects.create_user(
                email="customer@appointment.test",
                password="Password@123",
                first_name="Customer",
                last_name="User",
                is_active=True,
                groups=[self.user_group],
            )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

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

        service = Services.objects.create(
            service_name="Nail Care",
            duration=30,
            price="25.00",
            description="Manicure",
        )

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
        self.assertGreaterEqual(len(list_response.data["data"]), 1)

        retrieve_appointment_response = self.client.get(
            reverse("appointments-detail", args=[appointment_id])
        )
        self.assertEqual(retrieve_appointment_response.status_code, status.HTTP_200_OK)

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

    @patch("appointment.tasks.notify_user_via_socket")
    @patch("appointment.tasks.send_appointment_reminder_email")
    def test_send_appointment_reminders_task_dispatches_notifications(
        self, mock_send_email, mock_notify
    ):
        appointment = SimpleNamespace(
            id="appt-123",
            customer=SimpleNamespace(id="cust-123", username="customer"),
            staff=SimpleNamespace(id="staff-123", username="staff"),
            service=SimpleNamespace(service_name="Haircut"),
        )

        with patch("appointment.tasks.Tenant.objects.exclude", return_value=[SimpleNamespace(schema_name=self.tenant.schema_name)]), patch(
            "appointment.tasks.Appointments.objects.filter", return_value=[appointment]
        ), patch(
            "appointment.tasks.schema_context", side_effect=lambda schema_name: nullcontext()
        ):
            result = send_appointment_reminders()

        self.assertIn("Reminder task finished", result)
        self.assertGreaterEqual(mock_send_email.delay.call_count, 1)
        self.assertGreaterEqual(mock_notify.call_count, 2)

    def test_notify_user_via_socket_sends_payload_to_channel_group(self):
        mock_channel_layer = SimpleNamespace(group_send=AsyncMock())

        with patch("appointment.sockets.get_channel_layer", return_value=mock_channel_layer):
            from appointment.sockets import notify_user_via_socket

            notify_user_via_socket("user-123", self.tenant.schema_name, "appt-456", "hello")

        mock_channel_layer.group_send.assert_awaited_once()
