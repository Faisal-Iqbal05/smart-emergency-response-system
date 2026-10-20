from django.urls import path
from rest_framework.routers import DefaultRouter
from .api import RegistrationView, LogoutView, MeView, IncidentViewSet, GuardianViewSet, NotificationViewSet, VolunteerProfileView
router = DefaultRouter()
router.register("incidents", IncidentViewSet, basename="incident")
router.register("guardians", GuardianViewSet, basename="guardian")
router.register("notifications", NotificationViewSet, basename="notification")
urlpatterns = [path("auth/register/", RegistrationView.as_view()), path("auth/logout/", LogoutView.as_view()), path("me/", MeView.as_view()), path("volunteer/profile/", VolunteerProfileView.as_view())] + router.urls
