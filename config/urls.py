from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"), path("about/", views.about, name="about"), path("offline/", views.offline, name="offline"), path("service-worker.js", views.service_worker, name="service_worker"),
    path("accounts/", include("django.contrib.auth.urls")), path("register/", views.register, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"), path("request-help/", views.request_help, name="request_help"),
    path("incidents/", views.incident_list, name="incident_list"), path("incidents/<uuid:pk>/", views.incident_detail, name="incident_detail"),
    path("profile/", views.profile, name="profile"), path("contacts/", views.contacts, name="contacts"),
    path("notifications/", views.notifications, name="notifications"), path("volunteer/", views.volunteer, name="volunteer"),
    path("command/", views.command, name="command"),
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"), path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/", include("core.api_urls")), path("api/schema/", SpectacularAPIView.as_view(), name="schema"), path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
