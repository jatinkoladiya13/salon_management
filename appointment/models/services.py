from django.core.exceptions import ValidationError
from django.db import models
from account.models import User
from salon_management.behaviours import DateMixin
from core.constants import TENANTSTAFF_GROUP_NAME
import uuid

class Services(DateMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    service_name = models.CharField(max_length=255, unique=True, blank=True)
    duration = models.PositiveIntegerField(
        help_text="Duration in minutes"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['service_name']
        db_table = 'salon_services'
        verbose_name = "Salon Service"
        verbose_name_plural = "Salon Services"
        indexes = [
            models.Index(fields=["service_name"]),
            models.Index(fields=["is_active"]),
        ]  

    def __str__(self):
        return self.service_name
     

class StaffServices(models.Model):
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name="staff_services"
    )
    service = models.ForeignKey(
        Services, 
        on_delete=models.CASCADE,
        related_name="salon_services"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'staff_services'
        unique_together = ("staff", "service")

    def __str__(self):
        return f"{self.user.email} - {self.service.service_name}"
    
    def clean(self):

        if self.staff.get_role != TENANTSTAFF_GROUP_NAME:
            raise ValidationError({
                "staff": "Selected user must have the Staff role."
            })

    def save(self,  *args, **kwargs):
        self.full_clean()   # Calls clean()
        return super().save(*args, **kwargs)
