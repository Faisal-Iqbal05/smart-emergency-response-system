from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *

@admin.register(User)
class CommunityUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Community profile", {"fields": ("role", "phone", "locality", "preferred_language")}),)
    list_display = ["username", "email", "role", "is_staff"]
    list_filter = ["role", "is_staff"]

for model in [Society, Block, Flat, ResidentFlatMapping, GuardianRelationship, VolunteerProfile, Incident, IncidentAssignment, AuditEvent, IncidentUpdate, Notification, NotificationAttempt]:
    admin.site.register(model)
