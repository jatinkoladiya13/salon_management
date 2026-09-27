from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # core/signals.py seeds a RoleBasePermissionsStatus row for every
        # permission whenever a group is created. Without this import the
        # module was never loaded, the receiver never connected, and a role
        # created through the API came out with no permission rows at all -
        # leaving it unusable and impossible to configure.
        import core.signals  # noqa: F401
