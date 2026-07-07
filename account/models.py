from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from core.models.group import CustomGroup

from core.constants import SUPERADMIN_GROUP_NAME
import uuid

# Create your models here.

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password, groups, **extra_fields):
        """
        Create and save a user with the given email and password
        """

        for group in groups:
            if not CustomGroup.objects.filter(id=group.id).exists():
                raise Exception(
                    f"Please run create_superadmin_group command first for group create for {group} group" 
                )
        
        if not email:
            raise ValueError(_("The Email must be set"))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        for group in groups:
            print("Adding group to user:", group.name, group.id)
            user.groups.add(get_object_or_404(CustomGroup, id=group.id))
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True"))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True"))
        
        superadmin_group_obj = get_object_or_404(
            CustomGroup, name__exact=SUPERADMIN_GROUP_NAME
        )

        return self.create_user(email, password, [superadmin_group_obj], **extra_fields)


class User(AbstractUser):

    GENDER_CHOICE = (
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ) 

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, blank=True)
    mobile = models.CharField(max_length=15, unique=True, null=True, blank=True)
    groups = models.ManyToManyField(
        CustomGroup,
        verbose_name=_("groups"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="user_set",
        related_query_name="user",
    )

    is_staff = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_verify = models.BooleanField(default=False)

    gender = models.CharField(choices=GENDER_CHOICE, max_length=10, default="male")
    date_of_birth = models.DateField(null=True, blank=True)

    address = models.CharField(max_length=255, blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ("username",)

    class Meta:
        ordering = ("id",)
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [models.Index(fields=["email"])]

    def __str__(self) -> str:
        return self.email + " - " + str(self.pk)
    
    @property
    def get_role(self):
        group = self.groups.first()
        print(
            "^^^^^^1^^^^^^^",
            group.name if group else None,
            self.email,
            self.groups.all(),
        )
        return group.name if group else None
    
    def save(self, *args, **kwargs):
        if not self.username:
            full_name = " ".join(
                part for part in [self.first_name, self.last_name] if part
            ).strip()
            self.username = full_name or self.email or "user"
        super(User, self).save(*args, **kwargs)

class TwoFactorAuth(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    secret = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=False)        