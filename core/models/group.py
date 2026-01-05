from django.contrib.auth.models import Group
from django.db import models

# Create your models here.
class CustomGroup(Group):
    level = models.PositiveIntegerField()

    def __str__(self):
        return self.name + "|" + str(self.level)