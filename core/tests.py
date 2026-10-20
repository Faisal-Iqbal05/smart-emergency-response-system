from datetime import timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import GuardianRelationship, Incident, Notification, Society, User, VolunteerProfile
from .services import accept_assignment, create_incident, process_escalations, transition

class PlatformTests(TestCase):
    def setUp(self):
        self.resident = User.objects.create_user(username="resident", email="r@example.test", password="VeryStrong-pass-1937", role=User.Role.RESIDENT)
        self.other = User.objects.create_user(username="other", email="o@example.test", password="VeryStrong-pass-1937")
        self.coordinator = User.objects.create_user(username="coord", email="c@example.test", password="VeryStrong-pass-1937", role=User.Role.COORDINATOR)
        self.society = Society.objects.create(name="North Court"); self.society.coordinators.add(self.coordinator)

    def test_registration_creates_resident_and_rejects_bad(self):
        c = APIClient()
        response = c.post("/api/v1/auth/register/", {"username":"new", "email":"new@example.test", "password":"VeryStrong-pass-1937"}, format="json")
        self.assertEqual(response.status_code, 201); self.assertEqual(User.objects.get(username="new").role, User.Role.RESIDENT)
        self.assertEqual(c.post("/api/v1/auth/register/", {"username":"weak", "email":"bad", "password":"x"}, format="json").status_code, 400)

    def test_login_and_profile_role_read_only(self):
        c = APIClient(); token = c.post("/api/v1/auth/token/", {"username":"resident", "password":"VeryStrong-pass-1937"}, format="json")
        self.assertEqual(token.status_code, 200); c.credentials(HTTP_AUTHORIZATION="Bearer " + token.data["access"])
        result = c.patch("/api/v1/me/", {"locality":"Green Ward", "role":"coordinator"}, format="json")
        self.assertEqual(result.status_code, 200); self.resident.refresh_from_db(); self.assertEqual(self.resident.role, User.Role.RESIDENT)

    def test_incident_validation_manual_location_and_ownership(self):
        c = APIClient(); c.force_authenticate(self.resident)
        bad = c.post("/api/v1/incidents/", {"category":"unknown", "description":"Help"}, format="json"); self.assertEqual(bad.status_code, 400)
        response = c.post("/api/v1/incidents/", {"category":"medical", "description":"Needs help", "location_text":"Near the library"}, format="json")
        self.assertEqual(response.status_code, 201); self.assertTrue(response.data["reference"].startswith("NA-")); incident_id = response.data["id"]
        c.force_authenticate(self.other); self.assertEqual(c.get(f"/api/v1/incidents/{incident_id}/").status_code, 404)

    def test_coordinator_scope_and_guardian_isolation(self):
        incident = create_incident(requester=self.resident, category="medical", description="Need help")
        c = APIClient(); c.force_authenticate(self.coordinator)
        self.assertEqual(c.get(f"/api/v1/incidents/{incident.pk}/").status_code, 404)  # no society mapping means no community disclosure
        guardian = User.objects.create_user(username="guard", email="g@example.test", password="Strong-pass-55444", role=User.Role.GUARDIAN)
        GuardianRelationship.objects.create(resident=self.resident, guardian=guardian, primary=True, consented=True, verified=True)
        c.force_authenticate(guardian); self.assertEqual(c.get(f"/api/v1/incidents/{incident.pk}/").status_code, 200)

    def test_cancellation_and_transition_rules(self):
        incident = create_incident(requester=self.resident, category="fire", description="Smoke")
        incident = transition(incident, actor=self.resident, status=Incident.Status.CANCELLED)
        with self.assertRaises(ValueError): transition(incident, actor=self.resident, status=Incident.Status.IN_PROGRESS)

    def test_verified_volunteer_claim_once(self):
        v1 = User.objects.create_user(username="v1", email="v1@example.test", password="Strong-pass-55444", role=User.Role.VOLUNTEER)
        v2 = User.objects.create_user(username="v2", email="v2@example.test", password="Strong-pass-55444", role=User.Role.VOLUNTEER)
        for user in [v1,v2]: VolunteerProfile.objects.create(user=user, verified=True, available=True)
        incident = create_incident(requester=self.resident, category="accident", description="Road incident")
        accept_assignment(incident, v1)
        with self.assertRaises(ValueError): accept_assignment(incident, v2)

    def test_guardian_escalation_is_idempotent_and_simulated(self):
        primary = User.objects.create_user(username="p", email="p@example.test", password="Strong-pass-55444", role=User.Role.GUARDIAN)
        secondary = User.objects.create_user(username="s", email="s@example.test", password="Strong-pass-55444", role=User.Role.GUARDIAN)
        GuardianRelationship.objects.create(resident=self.resident, guardian=primary, primary=True, consented=True, verified=True)
        GuardianRelationship.objects.create(resident=self.resident, guardian=secondary, primary=False, consented=True, verified=True)
        incident = create_incident(requester=self.resident, category="medical", description="Need help")
        self.assertTrue(Notification.objects.filter(recipient=primary, state="simulated").exists())
        incident.escalation_due_at = timezone.now()-timedelta(seconds=1); incident.save()
        self.assertEqual(process_escalations(), 1); self.assertEqual(process_escalations(), 0)
        self.assertTrue(Notification.objects.filter(recipient=secondary, kind="escalation", state="simulated").exists())

    def test_pages_password_reset_and_pwa(self):
        from pathlib import Path
        from django.conf import settings
        for url in ["/", "/about/", "/offline/", "/service-worker.js", "/api/docs/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertTrue((Path(settings.BASE_DIR) / "static" / "manifest.webmanifest").is_file())
        self.assertEqual(self.client.get(reverse("password_reset")).status_code, 200)

    def test_filters_pagination_and_coordinator_only_page(self):
        for _ in range(22): create_incident(requester=self.resident, category="other", description="Test")
        c = APIClient(); c.force_authenticate(self.resident)
        data = c.get("/api/v1/incidents/?category=other")
        self.assertEqual(data.status_code, 200); self.assertEqual(data.data["count"], 22); self.assertIn("next", data.data)
        self.assertEqual(self.client.get("/command/").status_code, 302)
        self.assertEqual(self.client.get("/request-help/").status_code, 302)

