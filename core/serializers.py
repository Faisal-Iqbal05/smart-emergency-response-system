from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import GuardianRelationship, Incident, IncidentUpdate, Notification, User, VolunteerProfile

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User; fields = ["id", "username", "email", "first_name", "last_name", "role", "phone", "locality", "preferred_language"]; read_only_fields = ["id", "role"]

class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)
    class Meta:
        model = User; fields = ["username", "email", "password", "first_name", "last_name", "phone", "locality", "preferred_language"]
    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data); user.role = User.Role.RESIDENT
        try: validate_password(password, user)
        except DjangoValidationError as exc: raise serializers.ValidationError({"password": list(exc.messages)})
        user.set_password(password)
        try: user.full_clean()
        except DjangoValidationError as exc: raise serializers.ValidationError(exc.message_dict)
        user.save(); return user

class IncidentSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.get_full_name", read_only=True)
    class Meta:
        model = Incident; fields = ["id", "reference", "requester_name", "category", "description", "location_text", "latitude", "longitude", "status", "created_at", "updated_at", "resolved_at"]; read_only_fields = ["id", "reference", "requester_name", "status", "created_at", "updated_at", "resolved_at"]
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user.role == User.Role.VOLUNTEER and not instance.assignments.filter(volunteer=request.user, declined_at__isnull=True).exists():
            data.pop("requester_name", None); data.pop("latitude", None); data.pop("longitude", None); data.pop("location_text", None)
        return data

class GuardianSerializer(serializers.ModelSerializer):
    guardian_email = serializers.EmailField(source="guardian.email", read_only=True)
    class Meta:
        model = GuardianRelationship; fields = ["id", "guardian", "guardian_email", "primary", "consented", "verified"]; read_only_fields = ["id", "verified", "consented"]

class VolunteerSerializer(serializers.ModelSerializer):
    class Meta: model = VolunteerProfile; fields = ["skills", "service_area", "available", "verified"]; read_only_fields = ["verified"]

class UpdateSerializer(serializers.ModelSerializer):
    class Meta: model = IncidentUpdate; fields = ["id", "message", "created_at"]; read_only_fields = ["id", "created_at"]

class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model = Notification; fields = ["id", "incident", "kind", "message", "state", "created_at", "acknowledged_at"]; read_only_fields = fields

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
