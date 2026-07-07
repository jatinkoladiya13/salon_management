from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db import models

from account.models import User
from .services import Services
from salon_management.behaviours import DateMixin
from core.constants import TENANTSTAFF_GROUP_NAME, TENANTUSER_GROUP_NAME

import uuid

class TimeSlot(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    staff = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name="time_solts"
    )

    slot_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    is_booked = models.BooleanField(default=False)

    class Meta:
        db_table = 'time_slots'
        verbose_name = "Time Slot"
        verbose_name_plural = "Time Slots"
        ordering = ["slot_date", "start_time"]
        indexes = [
            models.Index(fields=["staff"]),
            models.Index(fields=["slot_date"]),
            models.Index(fields=["is_booked"]),
        ] 
        unique_together = (
            "staff",
            "slot_date",
            "start_time",
        ) 

    def __str__(self):
        return (
            f"{self.staff.email} | "
            f"{self.slot_date} "
            f"{self.start_time}-{self.end_time}"
        )
    
    def clean(self):

        if self.staff.get_role != TENANTSTAFF_GROUP_NAME:
            raise ValidationError({
                "staff": "Selected user must have the Staff role."
            })

    def save(self,  *args, **kwargs):
        self.full_clean()   # Calls clean()
        return super().save(*args, **kwargs)

class Appointments(DateMixin, models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="customer_appointments",
    )

    staff = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="staff_appointments",
    )

    service = models.ForeignKey(Services, on_delete=models.CASCADE, related_name="appointments")

    time_slot = models.ForeignKey(
        TimeSlot,
        on_delete=models.PROTECT,
        related_name="appointment",
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    appointment_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        db_table = "appointments"
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["staff"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return (
            f"{self.customer.email} -> "
            f"{self.staff.email} "
            f"({self.status})"
        )
    
    def clean(self):
        print("Validating appointment...")
        print(f"Customer role: {self.customer.get_role}, Staff role: {self.staff.get_role}")
        if self.customer.get_role != TENANTUSER_GROUP_NAME:
            raise ValidationError({
                "customer": "Selected user must have the Customer role."
            })

        if self.staff.get_role != TENANTSTAFF_GROUP_NAME:
            raise ValidationError({
                "staff": "Selected user must have the Staff role."
            })

    def save(self,  *args, **kwargs):
        print("Saving appointment...")
        print(f"Customer role: {self.customer.get_role}, Staff role: {self.staff.get_role}")
        self.full_clean()   # Calls clean()
        return super().save(*args, **kwargs)

