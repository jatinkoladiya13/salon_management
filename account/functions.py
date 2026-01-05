import re
from rest_framework import serializers


def validate_user_data(attrs):
    password = attrs.get('password')
    role = attrs.get('role')
    dob = attrs.get('date_of_birth')
    mobile = attrs.get('mobile')

    # Role-based validation
    if role == "user" and not dob:
        raise serializers.ValidationError("Date of birth is required when role is 'user'.")

    # Password validations
    if password:
        if len(password) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", password):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r"[@$!%*?&]", password):
            raise serializers.ValidationError(
                "Password must contain at least one special character (@, $, !, %, *, ?, &)."
            )

    # Mobile number validation
    if mobile:
        pattern = r"^\+[1-9]\d{1,14}$"  # E.164 format
        if not re.match(pattern, mobile):
            raise serializers.ValidationError(
                {"error": "Mobile number must be in international format, e.g. +919876543210"}
            )

    return attrs