import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    class Role(models.TextChoices):
        RESIDENT = "resident", "Resident"; GUARDIAN = "guardian", "Guardian"; VOLUNTEER = "volunteer", "Volunteer"; SECURITY = "security", "Security personnel"; COORDINATOR = "coordinator", "Society coordinator"
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT)
    phone = models.CharField(max_length=20, blank=True)
    locality = models.CharField(max_length=180, blank=True)
    preferred_language = models.CharField(max_length=20, default="en")

class Society(models.Model):
    name = models.CharField(max_length=160, unique=True)
    locality = models.CharField(max_length=180, blank=True)
    coordinators = models.ManyToManyField(User, blank=True, related_name="coordinated_societies")
    def __str__(self): return self.name

class Block(models.Model):
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name="blocks")
    name = models.CharField(max_length=80)
    class Meta: constraints = [models.UniqueConstraint(fields=["society", "name"], name="unique_block_per_society")]
    def __str__(self): return f"{self.society}: {self.name}"

class Flat(models.Model):
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="flats")
    number = models.CharField(max_length=40)
    class Meta: constraints = [models.UniqueConstraint(fields=["block", "number"], name="unique_flat_per_block")]
    def __str__(self): return f"{self.block} / {self.number}"

class ResidentFlatMapping(models.Model):
    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name="flat_mappings")
    flat = models.ForeignKey(Flat, on_delete=models.CASCADE, related_name="residents")
    verified = models.BooleanField(default=False)
    class Meta: constraints = [models.UniqueConstraint(fields=["resident", "flat"], name="unique_resident_flat")]

class GuardianRelationship(models.Model):
    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(User, on_delete=models.CASCADE, related_name="resident_links")
    primary = models.BooleanField(default=False)
    consented = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    class Meta: constraints = [models.UniqueConstraint(fields=["resident", "guardian"], name="unique_guardian_link"), models.UniqueConstraint(fields=["resident"], condition=models.Q(primary=True), name="one_primary_guardian")]

class VolunteerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="volunteer_profile")
    skills = models.CharField(max_length=300, blank=True, help_text="Comma-separated skills")
    service_area = models.CharField(max_length=180, blank=True)
    available = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)

class Incident(models.Model):
    class Category(models.TextChoices):
        MEDICAL = "medical", "Medical emergency"; FIRE = "fire", "Fire"; ACCIDENT = "accident", "Accident"; SAFETY = "safety", "Personal safety / security"; OTHER = "other", "Other"
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"; ACKNOWLEDGED = "acknowledged", "Acknowledged"; ASSIGNED = "assigned", "Volunteer assigned"; IN_PROGRESS = "in_progress", "Assistance in progress"; ESCALATED = "escalated", "Escalated"; RESOLVED = "resolved", "Resolved"; CANCELLED = "cancelled", "Cancelled"; CLOSED = "closed", "Closed"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=12, unique=True, editable=False)
    requester = models.ForeignKey(User, on_delete=models.PROTECT, related_name="incidents")
    society = models.ForeignKey(Society, null=True, blank=True, on_delete=models.SET_NULL, related_name="incidents")
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=500)
    location_text = models.CharField(max_length=220, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    escalation_due_at = models.DateTimeField(null=True, blank=True)
    escalation_processed = models.BooleanField(default=False)
    resolution_note = models.CharField(max_length=500, blank=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"]), models.Index(fields=["category", "created_at"])]
    def save(self, *args, **kwargs):
        if not self.reference: self.reference = "NA-" + uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

class IncidentAssignment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="assignments")
    volunteer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="assignments")
    accepted_at = models.DateTimeField(default=timezone.now)
    declined_at = models.DateTimeField(null=True, blank=True)
    progress_note = models.CharField(max_length=500, blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=["incident"], condition=models.Q(declined_at__isnull=True), name="one_active_assignment_per_incident")]

class AuditEvent(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=60)
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["created_at"]

class IncidentUpdate(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["created_at"]

class Notification(models.Model):
    class State(models.TextChoices): QUEUED = "queued", "Queued"; SIMULATED = "simulated", "Simulated"; SENT = "sent", "Sent"; FAILED = "failed", "Failed"
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=40)
    message = models.CharField(max_length=240)
    state = models.CharField(max_length=12, choices=State.choices, default=State.SIMULATED)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

class NotificationAttempt(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="attempts")
    channel = models.CharField(max_length=20, default="in_app")
    result = models.CharField(max_length=20, default="simulated")
    failure_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
