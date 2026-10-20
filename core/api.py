from django.db import IntegrityError
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema
from .models import GuardianRelationship, Incident, IncidentUpdate, Notification, User, VolunteerProfile
from .serializers import GuardianSerializer, IncidentSerializer, LogoutSerializer, NotificationSerializer, RegistrationSerializer, UpdateSerializer, UserSerializer, VolunteerSerializer
from .services import accept_assignment, assign_volunteer, create_incident, transition

class SOSRateThrottle(UserRateThrottle): scope = "sos"
class RegistrationView(CreateAPIView): queryset = User.objects.all(); serializer_class = RegistrationSerializer; permission_classes = [permissions.AllowAny]

class LogoutView(APIView):
    serializer_class = LogoutSerializer
    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        token = request.data.get("refresh")
        if not token: return Response({"detail": "Refresh token is required."}, status=400)
        try: RefreshToken(token).blacklist()
        except Exception: return Response({"detail": "Refresh token is invalid or already revoked."}, status=400)
        return Response(status=204)
class MeView(RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    # Role is read only in the serializer, so ordinary users cannot self promote.
    def get_object(self): return self.request.user

class IncidentViewSet(viewsets.ModelViewSet):
    serializer_class = IncidentSerializer
    filterset_fields = ["category", "status"]
    search_fields = ["reference", "description"]
    ordering_fields = ["created_at", "status"]
    def get_throttles(self): return [SOSRateThrottle()] if self.action == "create" else super().get_throttles()
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False): return Incident.objects.none()
        user = self.request.user
        if user.is_superuser or user.role == User.Role.COORDINATOR:
            return Incident.objects.all() if user.is_superuser else Incident.objects.filter(society__coordinators=user)
        if user.role == User.Role.GUARDIAN:
            return Incident.objects.filter(requester__guardian_links__guardian=user, requester__guardian_links__consented=True, requester__guardian_links__verified=True).distinct()
        if user.role == User.Role.VOLUNTEER:
            return Incident.objects.filter(status__in=[Incident.Status.SUBMITTED, Incident.Status.ACKNOWLEDGED, Incident.Status.ESCALATED]) | Incident.objects.filter(assignments__volunteer=user)
        if user.role == User.Role.SECURITY:
            societies = user.flat_mappings.values_list("flat__block__society_id", flat=True)
            return Incident.objects.filter(society_id__in=societies)
        return Incident.objects.filter(requester=user)
    def perform_create(self, serializer):
        if self.request.user.role != User.Role.RESIDENT: raise PermissionDenied("Only residents can submit a request.")
        try:
            self.instance = create_incident(requester=self.request.user, **serializer.validated_data)
        except ValueError as exc: raise ValidationError({"location": str(exc)})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True); self.perform_create(serializer)
        return Response(self.get_serializer(self.instance).data, status=status.HTTP_201_CREATED)
    def _can_coordinate(self, incident):
        return self.request.user.is_superuser or (incident.society_id and incident.society.coordinators.filter(pk=self.request.user.pk).exists())
    def _can_participate(self, incident):
        user = self.request.user
        return incident.requester_id == user.id or self._can_coordinate(incident) or incident.assignments.filter(volunteer=user, declined_at__isnull=True).exists() or (user.role == User.Role.GUARDIAN and incident.requester.guardian_links.filter(guardian=user, consented=True, verified=True).exists())
    def retrieve(self, request, *args, **kwargs):
        incident = self.get_object()
        if not self._can_participate(incident) and request.user.role not in [User.Role.SECURITY, User.Role.VOLUNTEER]: raise PermissionDenied("You cannot view this incident.")
        return Response(self.get_serializer(incident).data)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        incident = self.get_object()
        if incident.requester_id != request.user.id: raise PermissionDenied("Only the resident who submitted this request may cancel it.")
        try: transition(incident, actor=request.user, status=Incident.Status.CANCELLED)
        except ValueError as exc: raise ValidationError({"status": str(exc)})
        return Response(self.get_serializer(incident).data)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        incident = self.get_object()
        if not (request.user.role in [User.Role.COORDINATOR, User.Role.SECURITY] or request.user.is_superuser or request.user.role == User.Role.GUARDIAN): raise PermissionDenied()
        try: incident = transition(incident, actor=request.user, status=Incident.Status.ACKNOWLEDGED)
        except ValueError as exc: raise ValidationError({"status": str(exc)})
        return Response(self.get_serializer(incident).data)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        try: incident = accept_assignment(self.get_object(), request.user)
        except ValueError as exc: raise ValidationError({"assignment": str(exc)})
        return Response(self.get_serializer(incident).data)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        incident = self.get_object()
        if not self._can_coordinate(incident) and not request.user.is_superuser: raise PermissionDenied("Coordinator access required.")
        try: volunteer = User.objects.get(pk=request.data.get("volunteer_id"))
        except (User.DoesNotExist, ValueError, TypeError): raise ValidationError({"volunteer_id": "Choose an existing volunteer account."})
        try: incident = assign_volunteer(incident, volunteer, request.user)
        except ValueError as exc: raise ValidationError({"assignment": str(exc)})
        return Response(self.get_serializer(incident).data)
    @action(detail=True, methods=["get", "post"])
    def updates(self, request, pk=None):
        incident = self.get_object()
        if not self._can_participate(incident): raise PermissionDenied()
        if request.method == "GET":
            return Response(UpdateSerializer(incident.updates.all(), many=True).data)
        serializer = UpdateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        serializer.save(incident=incident, author=request.user)
        return Response(serializer.data, status=201)
    @action(detail=True, methods=["post"])
    def status_update(self, request, pk=None):
        incident = self.get_object()
        if not (self._can_coordinate(incident) or request.user.is_superuser or incident.assignments.filter(volunteer=request.user, declined_at__isnull=True).exists()): raise PermissionDenied()
        try: incident = transition(incident, actor=request.user, status=request.data.get("status"), detail=request.data.get("detail", ""))
        except (ValueError, TypeError) as exc: raise ValidationError({"status": str(exc)})
        return Response(self.get_serializer(incident).data)
    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        incident = self.get_object()
        if not self._can_participate(incident): raise PermissionDenied()
        return Response([{"type": e.event_type, "detail": e.detail, "at": e.created_at, "actor": e.actor.get_full_name() if e.actor else None} for e in incident.events.all()])

class GuardianViewSet(viewsets.ModelViewSet):
    serializer_class = GuardianSerializer
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False): return GuardianRelationship.objects.none()
        return GuardianRelationship.objects.filter(resident=self.request.user).select_related("guardian")
    def perform_create(self, serializer):
        guardian = serializer.validated_data["guardian"]
        if guardian.role not in [User.Role.GUARDIAN, User.Role.RESIDENT] or guardian == self.request.user: raise ValidationError({"guardian": "Choose another registered community member."})
        serializer.save(resident=self.request.user)

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False): return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user).order_by("-created_at")
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        note = self.get_object(); note.acknowledged_at = timezone.now(); note.save(update_fields=["acknowledged_at"])
        if note.incident and note.kind in ["guardian_alert", "escalation"]:
            try: transition(note.incident, actor=request.user, status=Incident.Status.ACKNOWLEDGED, detail="Guardian acknowledged notification")
            except ValueError: pass
        return Response(self.get_serializer(note).data)

class VolunteerProfileView(RetrieveUpdateAPIView):
    serializer_class = VolunteerSerializer
    def get_object(self):
        if self.request.user.role != User.Role.VOLUNTEER: raise PermissionDenied()
        profile, _ = VolunteerProfile.objects.get_or_create(user=self.request.user)
        return profile
