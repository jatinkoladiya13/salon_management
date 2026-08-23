from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from core.constants import (
    CREATE_GROUPS,
    DELETE_GROUPS,
    READ_GROUPS,
    READ_PERMISSIONS_STATUS,
    SUPERADMIN_GROUP_NAME,
    UPDATE_GROUPS,
    UPDATE_PERMISSIONS_STATUS,
)
from core.models import CustomGroup, RoleBasePermissions, RoleBasePermissionsStatus
from utils.testing import TenantAPITestCase


class GroupApiPermissionTests(TenantAPITestCase):
    """
    Groups are this project's roles, so writing to them is a privileged action.

    These checks used to pass for everyone: the viewset spelled the hook
    ``get_permission`` instead of ``get_permissions``, so DRF never called it
    and every route fell back to plain IsAuthenticated.
    """

    def test_listing_groups_requires_the_read_permission(self):
        self.authenticate(self.customer)

        self.grant(self.user_group, READ_GROUPS, status=False)
        denied = self.client.get(reverse("customgroup-list"))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.grant(self.user_group, READ_GROUPS, status=True)
        allowed = self.client.get(reverse("customgroup-list"))
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_creating_a_group_requires_the_create_permission(self):
        self.authenticate(self.customer)
        self.grant(self.user_group, CREATE_GROUPS, status=False)

        response = self.client.post(
            reverse("customgroup-list"),
            {"name": "Receptionist", "level": 4},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        with schema_context(self.tenant.schema_name):
            self.assertFalse(
                CustomGroup.objects.filter(name="Receptionist").exists()
            )

    def test_a_permitted_user_can_create_a_group(self):
        self.authenticate(self.admin)
        self.grant(self.admin_group, CREATE_GROUPS, status=True)

        response = self.client.post(
            reverse("customgroup-list"),
            {"name": "Receptionist", "level": 4},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.assertTrue(
                CustomGroup.objects.filter(name="Receptionist").exists()
            )

    def test_updating_a_group_requires_the_update_permission(self):
        self.authenticate(self.customer)
        self.grant(self.user_group, UPDATE_GROUPS, status=False)

        response = self.client.patch(
            reverse("customgroup-detail", args=[self.staff_group.id]),
            {"name": "Renamed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_deleting_a_group_requires_the_delete_permission(self):
        self.authenticate(self.customer)
        self.grant(self.user_group, DELETE_GROUPS, status=False)

        response = self.client.delete(
            reverse("customgroup-detail", args=[self.staff_group.id])
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        with schema_context(self.tenant.schema_name):
            self.assertTrue(
                CustomGroup.objects.filter(id=self.staff_group.id).exists()
            )

    def test_the_superadmin_group_cannot_be_edited_or_deleted(self):
        with schema_context(self.tenant.schema_name):
            superadmin = CustomGroup.objects.create(
                name=SUPERADMIN_GROUP_NAME, level=0
            )

        self.authenticate(self.admin)
        self.grant(self.admin_group, UPDATE_GROUPS, status=True)
        self.grant(self.admin_group, DELETE_GROUPS, status=True)

        update = self.client.patch(
            reverse("customgroup-detail", args=[superadmin.id]),
            {"name": "Hijacked"},
            format="json",
        )
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)

        delete = self.client.delete(
            reverse("customgroup-detail", args=[superadmin.id])
        )
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

        with schema_context(self.tenant.schema_name):
            superadmin.refresh_from_db()
            self.assertEqual(superadmin.name, SUPERADMIN_GROUP_NAME)

    def test_anonymous_users_are_refused(self):
        response = self.client.get(reverse("customgroup-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class GroupSignalTests(TenantAPITestCase):
    def test_a_new_group_gets_a_status_row_for_every_permission(self):
        with schema_context(self.tenant.schema_name):
            RoleBasePermissions.objects.get_or_create(name=READ_GROUPS)
            RoleBasePermissions.objects.get_or_create(name=CREATE_GROUPS)
            permission_count = RoleBasePermissions.objects.count()

            group = CustomGroup.objects.create(name="Trainee", level=5)

            self.assertEqual(
                RoleBasePermissionsStatus.objects.filter(group=group).count(),
                permission_count,
            )

    def test_generated_permission_rows_default_to_denied(self):
        with schema_context(self.tenant.schema_name):
            RoleBasePermissions.objects.get_or_create(name=READ_GROUPS)

            group = CustomGroup.objects.create(name="Trainee", level=5)

            self.assertFalse(
                RoleBasePermissionsStatus.objects.filter(
                    group=group, status=True
                ).exists()
            )


class PermissionStatusApiTests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        self.grant(self.admin_group, READ_PERMISSIONS_STATUS, status=True)
        self.grant(self.admin_group, UPDATE_PERMISSIONS_STATUS, status=True)
        self.row = self.grant(self.user_group, READ_GROUPS, status=False)

    def test_listing_permission_status_requires_the_read_permission(self):
        self.authenticate(self.customer)
        self.grant(self.user_group, READ_PERMISSIONS_STATUS, status=False)

        response = self.client.get(reverse("rolebasepermissionsstatus-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_toggle_a_permission(self):
        self.authenticate(self.admin)

        response = self.client.put(
            reverse("rolebasepermissionsstatus-detail", args=[self.row.id]),
            {"status": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.row.refresh_from_db()
            self.assertTrue(self.row.status)

    def test_bulk_update_applies_every_row(self):
        second = self.grant(self.user_group, CREATE_GROUPS, status=False)
        self.authenticate(self.admin)

        response = self.client.put(
            reverse("rolebasepermissionsstatus-update-bulk-permissions"),
            {
                "data": [
                    {"id": str(self.row.id), "status": True},
                    {"id": str(second.id), "status": True},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.row.refresh_from_db()
            second.refresh_from_db()
            self.assertTrue(self.row.status)
            self.assertTrue(second.status)

    def test_bulk_update_rolls_back_completely_when_one_row_is_unknown(self):
        """
        A half-applied permission set is worse than a rejected one: it leaves
        the role in an authorisation state nobody asked for.
        """
        self.authenticate(self.admin)
        unknown_id = "11111111-1111-1111-1111-111111111111"

        response = self.client.put(
            reverse("rolebasepermissionsstatus-update-bulk-permissions"),
            {
                "data": [
                    {"id": str(self.row.id), "status": True},
                    {"id": unknown_id, "status": True},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        with schema_context(self.tenant.schema_name):
            self.row.refresh_from_db()
            self.assertFalse(self.row.status)

    def test_bulk_update_rejects_a_malformed_payload(self):
        self.authenticate(self.admin)

        for payload in (
            {"data": [{"id": str(self.row.id)}]},
            {"data": [{"status": True}]},
            {"data": ["not-an-object"]},
            {"data": [{"id": str(self.row.id), "status": "yes"}]},
        ):
            response = self.client.put(
                reverse("rolebasepermissionsstatus-update-bulk-permissions"),
                payload,
                format="json",
            )

            self.assertEqual(
                response.status_code, status.HTTP_400_BAD_REQUEST, payload
            )

    def test_bulk_update_with_no_data_is_rejected(self):
        self.authenticate(self.admin)

        response = self.client.put(
            reverse("rolebasepermissionsstatus-update-bulk-permissions"),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
