from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.http import HttpResponse
from pathlib import Path
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from .models import GuardianRelationship, Incident, IncidentUpdate, User, VolunteerProfile
from .services import accept_assignment, create_incident, transition

def home(request): return render(request, "home.html")
def about(request): return render(request, "about.html")
def offline(request): return render(request, "offline.html")
def service_worker(request):
    response = HttpResponse((settings.BASE_DIR / "static" / "service-worker.js").read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        email = request.POST.get("email", "").strip().lower()
        if not email or User.objects.filter(email__iexact=email).exists(): form.add_error(None, "Enter an email address that is not already registered.")
        elif form.is_valid():
            user = form.save(commit=False); user.email = email; user.phone = request.POST.get("phone", "")[:20]; user.first_name = request.POST.get("first_name", "")[:150]; user.last_name = request.POST.get("last_name", "")[:150]; user.locality = request.POST.get("locality", "")[:180]; user.role = User.Role.RESIDENT; user.save(); login(request, user); return redirect("dashboard")
    else: form = UserCreationForm()
    return render(request, "registration/register.html", {"form": form})

@login_required
def dashboard(request):
    user = request.user
    if user.role == User.Role.COORDINATOR or user.is_superuser: return redirect("command")
    if user.role == User.Role.VOLUNTEER: return redirect("volunteer")
    if user.role == User.Role.GUARDIAN:
        incidents = Incident.objects.filter(requester__guardian_links__guardian=user, requester__guardian_links__consented=True, requester__guardian_links__verified=True).distinct()[:10]
    else: incidents = Incident.objects.filter(requester=user)[:10]
    return render(request, "dashboard.html", {"incidents": incidents, "open_count": Incident.objects.filter(requester=user).exclude(status__in=["resolved", "cancelled", "closed"]).count()})

@login_required
def request_help(request):
    if request.user.role != User.Role.RESIDENT: messages.error(request, "Only resident accounts can submit help requests."); return redirect("dashboard")
    if request.method == "POST":
        category = request.POST.get("category", ""); description = request.POST.get("description", "").strip(); location = request.POST.get("location_text", "").strip()
        try:
            if category not in Incident.Category.values or not description or len(description) > 500: raise ValueError("Choose a category and enter a short description (up to 500 characters).")
            incident = create_incident(requester=request.user, category=category, description=description, location_text=location[:220], latitude=request.POST.get("latitude") or None, longitude=request.POST.get("longitude") or None)
            messages.success(request, f"Request confirmed by NeighbourAid. Reference: {incident.reference}. Notifications are simulated in this development setup.")
            return redirect("incident_detail", pk=incident.pk)
        except (ValueError, TypeError) as exc: messages.error(request, str(exc))
    return render(request, "request_help.html", {"categories": Incident.Category.choices})

def _visible_incident(user, incident):
    if user.is_superuser or incident.requester_id == user.id: return True
    if user.role == User.Role.COORDINATOR: return bool(incident.society and incident.society.coordinators.filter(pk=user.pk).exists())
    if user.role == User.Role.GUARDIAN: return incident.requester.guardian_links.filter(guardian=user, consented=True, verified=True).exists()
    if user.role == User.Role.VOLUNTEER: return incident.status in ["submitted", "acknowledged", "escalated"] or incident.assignments.filter(volunteer=user).exists()
    if user.role == User.Role.SECURITY: return incident.society_id in user.flat_mappings.values_list("flat__block__society_id", flat=True)
    return False

@login_required
def incident_list(request):
    user = request.user; incidents = Incident.objects.all()
    if user.is_superuser: pass
    elif user.role == User.Role.COORDINATOR: incidents = incidents.filter(society__coordinators=user)
    elif user.role == User.Role.GUARDIAN: incidents = incidents.filter(requester__guardian_links__guardian=user, requester__guardian_links__consented=True, requester__guardian_links__verified=True)
    elif user.role == User.Role.VOLUNTEER: incidents = incidents.filter(status__in=["submitted", "acknowledged", "escalated"])
    elif user.role == User.Role.SECURITY: incidents = incidents.filter(society__in=[m.flat.block.society for m in user.flat_mappings.select_related("flat__block__society")])
    else: incidents = incidents.filter(requester=user)
    if request.GET.get("status"): incidents = incidents.filter(status=request.GET["status"])
    if request.GET.get("category"): incidents = incidents.filter(category=request.GET["category"])
    return render(request, "incident_list.html", {"page_obj": Paginator(incidents.distinct(), 20).get_page(request.GET.get("page")), "categories": Incident.Category.choices, "statuses": Incident.Status.choices})

@login_required
def incident_detail(request, pk):
    incident = get_object_or_404(Incident.objects.prefetch_related("events", "updates", "assignments"), pk=pk)
    if not _visible_incident(request.user, incident): raise Http404
    if request.method == "POST" and request.POST.get("action") == "update":
        message = request.POST.get("message", "").strip()
        if message and len(message) <= 500 and (incident.requester_id == request.user.id or incident.assignments.filter(volunteer=request.user).exists() or request.user.role in [User.Role.COORDINATOR, User.Role.SECURITY]): IncidentUpdate.objects.create(incident=incident, author=request.user, message=message); messages.success(request, "Update added.")
        return redirect("incident_detail", pk=pk)
    if request.method == "POST" and request.POST.get("action") == "cancel":
        if incident.requester_id != request.user.id: raise Http404
        try: transition(incident, actor=request.user, status=Incident.Status.CANCELLED); messages.success(request, "Request cancelled.")
        except ValueError as exc: messages.error(request, str(exc))
        return redirect("incident_detail", pk=pk)
    return render(request, "incident_detail.html", {"incident": incident})

@login_required
def profile(request):
    if request.method == "POST":
        request.user.first_name = request.POST.get("first_name", "")[:150]; request.user.last_name = request.POST.get("last_name", "")[:150]; request.user.phone = request.POST.get("phone", "")[:20]; request.user.locality = request.POST.get("locality", "")[:180]; request.user.preferred_language = request.POST.get("preferred_language", "en")[:20]; request.user.save(); messages.success(request, "Profile updated."); return redirect("profile")
    return render(request, "profile.html")

@login_required
def contacts(request):
    if request.method == "POST":
        guardian = User.objects.filter(email__iexact=request.POST.get("email", "").strip()).first()
        if not guardian or guardian == request.user: messages.error(request, "If that account is eligible, you can add it as a contact. Check the address and try again.")
        else:
            try: GuardianRelationship.objects.create(resident=request.user, guardian=guardian, primary=request.POST.get("primary") == "on", consented=False)
            except Exception: messages.error(request, "That contact already exists or another primary guardian is set.")
            else: messages.success(request, "Contact request saved. A coordinator must verify it before alerts are delivered.")
        return redirect("contacts")
    return render(request, "contacts.html", {"links": request.user.guardian_links.select_related("guardian")})

@login_required
def notifications(request): return render(request, "notifications.html", {"items": request.user.notifications.all()[:100]})

@login_required
def volunteer(request):
    if request.user.role != User.Role.VOLUNTEER: raise Http404
    profile, _ = VolunteerProfile.objects.get_or_create(user=request.user)
    if request.method == "POST" and request.POST.get("action") == "profile":
        profile.available = request.POST.get("available") == "on"; profile.skills = request.POST.get("skills", "")[:300]; profile.service_area = request.POST.get("service_area", "")[:180]; profile.save(); messages.success(request, "Volunteer settings saved.")
    if request.method == "POST" and request.POST.get("action") == "accept":
        incident = get_object_or_404(Incident, pk=request.POST.get("incident"))
        try: accept_assignment(incident, request.user); messages.success(request, "Assignment accepted.")
        except ValueError as exc: messages.error(request, str(exc))
    open_incidents = Incident.objects.filter(status__in=["submitted", "acknowledged", "escalated"]).order_by("created_at")[:30]
    assigned = Incident.objects.filter(assignments__volunteer=request.user, assignments__declined_at__isnull=True).distinct()
    return render(request, "volunteer.html", {"profile": profile, "open_incidents": open_incidents, "assigned": assigned})

@login_required
def command(request):
    user = request.user
    if not user.is_superuser and user.role != User.Role.COORDINATOR: raise Http404
    queryset = Incident.objects.all() if user.is_superuser else Incident.objects.filter(society__coordinators=user)
    if request.GET.get("status"): queryset = queryset.filter(status=request.GET["status"])
    if request.GET.get("category"): queryset = queryset.filter(category=request.GET["category"])
    return render(request, "command.html", {"incidents": queryset.select_related("requester", "society")[:100], "counts": queryset.values("status").annotate(total=Count("id")), "categories": Incident.Category.choices, "statuses": Incident.Status.choices})
