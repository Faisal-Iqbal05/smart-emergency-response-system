from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Society, Block, Flat, ResidentFlatMapping, VolunteerProfile

class Command(BaseCommand):
    help = "Create fictional demo users and one community; all passwords are set by the operator."
    def add_arguments(self, parser): parser.add_argument("--password", required=True)
    def handle(self, *args, **opts):
        User = get_user_model(); password = opts["password"]
        records = {}
        for username, role, email in [("demo-resident", "resident", "resident@example.test"), ("demo-guardian", "guardian", "guardian@example.test"), ("demo-volunteer", "volunteer", "volunteer@example.test"), ("demo-coordinator", "coordinator", "coordinator@example.test")]:
            user, made = User.objects.get_or_create(username=username, defaults={"role": role, "email": email, "first_name": username.split("-")[-1].title()})
            if made: user.set_password(password); user.save()
            records[role] = user
        society, _ = Society.objects.get_or_create(name="Example Community", defaults={"locality": "Demo locality"}); society.coordinators.add(records["coordinator"])
        block, _ = Block.objects.get_or_create(society=society, name="A"); flat, _ = Flat.objects.get_or_create(block=block, number="101")
        ResidentFlatMapping.objects.get_or_create(resident=records["resident"], flat=flat, defaults={"verified": True})
        VolunteerProfile.objects.get_or_create(user=records["volunteer"], defaults={"skills": "First aid", "service_area": "Example Community", "available": True, "verified": True})
        self.stdout.write(self.style.SUCCESS("Fictional demo accounts ready. Set a guardian contact in the resident account. Password is supplied via --password."))
