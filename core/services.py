from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import AuditEvent, GuardianRelationship, Incident, IncidentAssignment, Notification, NotificationAttempt, User

TRANSITIONS = {
    Incident.Status.SUBMITTED: {Incident.Status.ACKNOWLEDGED, Incident.Status.ASSIGNED, Incident.Status.ESCALATED, Incident.Status.CANCELLED},
    Incident.Status.ACKNOWLEDGED: {Incident.Status.ASSIGNED, Incident.Status.IN_PROGRESS, Incident.Status.ESCALATED, Incident.Status.CANCELLED},
    Incident.Status.ASSIGNED: {Incident.Status.IN_PROGRESS, Incident.Status.ESCALATED, Incident.Status.CANCELLED},
    Incident.Status.IN_PROGRESS: {Incident.Status.RESOLVED, Incident.Status.ESCALATED},
    Incident.Status.ESCALATED: {Incident.Status.ACKNOWLEDGED, Incident.Status.ASSIGNED, Incident.Status.IN_PROGRESS, Incident.Status.RESOLVED, Incident.Status.CANCELLED},
    Incident.Status.RESOLVED: {Incident.Status.CLOSED}, Incident.Status.CANCELLED: {Incident.Status.CLOSED}, Incident.Status.CLOSED: set(),
}

def notify(recipient, incident, kind, message):
    notification = Notification.objects.create(recipient=recipient, incident=incident, kind=kind, message=message, state=Notification.State.SIMULATED)
    NotificationAttempt.objects.create(notification=notification, channel="in_app", result="simulated")
    return notification

@transaction.atomic
def create_incident(*, requester, category, description, location_text="", latitude=None, longitude=None):
    if latitude is not None and not (-90 <= float(latitude) <= 90): raise ValueError("Latitude must be between -90 and 90.")
    if longitude is not None and not (-180 <= float(longitude) <= 180): raise ValueError("Longitude must be between -180 and 180.")
    mapping = requester.flat_mappings.filter(verified=True).select_related("flat__block__society").first()
    society = mapping.flat.block.society if mapping else None
    incident = Incident.objects.create(requester=requester, society=society, category=category, description=description, location_text=location_text, latitude=latitude, longitude=longitude, escalation_due_at=timezone.now()+timedelta(minutes=settings.ESCALATION_TIMEOUT_MINUTES))
    AuditEvent.objects.create(incident=incident, actor=requester, event_type="submitted", detail="Emergency request submitted")
    for link in requester.guardian_links.filter(consented=True, verified=True, primary=True).select_related("guardian"):
        notify(link.guardian, incident, "guardian_alert", f"A resident you support requested help ({incident.reference}).")
    coordinators = User.objects.filter(coordinated_societies=society) if society else User.objects.none()
    for recipient in coordinators.distinct(): notify(recipient, incident, "incident_alert", f"New community request {incident.reference}.")
    return incident

@transaction.atomic
def transition(incident, *, actor, status, detail=""):
    incident = Incident.objects.select_for_update().get(pk=incident.pk)
    if status not in TRANSITIONS.get(incident.status, set()): raise ValueError(f"Cannot move an incident from {incident.get_status_display()} to {Incident.Status(status).label}.")
    incident.status = status
    if status == Incident.Status.ACKNOWLEDGED: incident.acknowledged_at = timezone.now()
    if status == Incident.Status.RESOLVED: incident.resolved_at = timezone.now(); incident.resolution_note = detail[:500]
    if status == Incident.Status.CLOSED: incident.closed_at = timezone.now()
    incident.save()
    AuditEvent.objects.create(incident=incident, actor=actor, event_type="status_changed", detail=f"Status changed to {incident.get_status_display()}. {detail}"[:300])
    for guardian in GuardianRelationship.objects.filter(resident=incident.requester, consented=True, verified=True).values_list("guardian", flat=True).distinct():
        notify(User.objects.get(pk=guardian), incident, "status_update", f"Request {incident.reference} is now {incident.get_status_display()}.")
    return incident

@transaction.atomic
def accept_assignment(incident, volunteer):
    incident = Incident.objects.select_for_update().get(pk=incident.pk)
    if volunteer.role != User.Role.VOLUNTEER: raise ValueError("Only volunteers may accept an assignment.")
    if not getattr(volunteer, "volunteer_profile", None) or not volunteer.volunteer_profile.available or not volunteer.volunteer_profile.verified: raise ValueError("Your volunteer profile must be verified and available.")
    if incident.status not in (Incident.Status.SUBMITTED, Incident.Status.ACKNOWLEDGED, Incident.Status.ESCALATED): raise ValueError("This incident is no longer open for assignment.")
    if incident.assignments.filter(declined_at__isnull=True).exists(): raise ValueError("This incident already has an active responder.")
    IncidentAssignment.objects.create(incident=incident, volunteer=volunteer)
    incident.status = Incident.Status.ASSIGNED
    incident.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(incident=incident, actor=volunteer, event_type="assigned", detail="Volunteer accepted assignment")
    notify(incident.requester, incident, "assignment", f"A community volunteer accepted request {incident.reference}.")
    return incident

@transaction.atomic
def assign_volunteer(incident, volunteer, actor):
    incident = Incident.objects.select_for_update().get(pk=incident.pk)
    if actor.role != User.Role.COORDINATOR and not actor.is_superuser: raise ValueError("Only a coordinator may assign a responder.")
    if incident.society_id and not actor.is_superuser and not incident.society.coordinators.filter(pk=actor.pk).exists(): raise ValueError("This incident is outside your community.")
    if volunteer.role != User.Role.VOLUNTEER or not getattr(volunteer, "volunteer_profile", None) or not volunteer.volunteer_profile.verified: raise ValueError("Choose a verified volunteer.")
    if incident.status not in (Incident.Status.SUBMITTED, Incident.Status.ACKNOWLEDGED, Incident.Status.ESCALATED): raise ValueError("This incident is not open for assignment.")
    if incident.assignments.filter(declined_at__isnull=True).exists(): raise ValueError("This incident already has an active responder.")
    IncidentAssignment.objects.create(incident=incident, volunteer=volunteer)
    incident.status = Incident.Status.ASSIGNED; incident.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(incident=incident, actor=actor, event_type="assigned", detail="Coordinator assigned volunteer")
    notify(incident.requester, incident, "assignment", f"A community volunteer was assigned to request {incident.reference}.")
    return incident

@transaction.atomic
def process_escalations(now=None):
    now = now or timezone.now()
    due = Incident.objects.select_for_update(skip_locked=True).filter(escalation_processed=False, acknowledged_at__isnull=True, escalation_due_at__lte=now, status__in=[Incident.Status.SUBMITTED, Incident.Status.ESCALATED])
    processed = 0
    for incident in due:
        incident.status = Incident.Status.ESCALATED
        incident.escalation_processed = True
        incident.save(update_fields=["status", "escalation_processed", "updated_at"])
        AuditEvent.objects.create(incident=incident, event_type="escalated", detail="Acknowledgement timeout reached")
        links = GuardianRelationship.objects.filter(resident=incident.requester, consented=True, verified=True, primary=False).select_related("guardian")
        for link in links: notify(link.guardian, incident, "escalation", f"Urgent: request {incident.reference} has not been acknowledged.")
        processed += 1
    return processed
