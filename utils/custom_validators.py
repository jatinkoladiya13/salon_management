import re
from django.core.exceptions import ValidationError


class OneSpecialCharacterValidator:
    def validate(self, password, user=None):
        special_chars = re.findall(r'[^A-Za-z0-9]', password)

        if len(special_chars) == 0:
            raise ValidationError(
                "Password must contain at least one special character."
            )

        if len(special_chars) > 1:
            raise ValidationError(
                "Password can contain only one special character."
            )

    def get_help_text(self):
        return "Password must contain exactly one special character."