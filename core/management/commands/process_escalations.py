from django.core.management.base import BaseCommand
from core.services import process_escalations

class Command(BaseCommand):
    help = "Process due guardian escalation jobs once. Schedule periodically with Task Scheduler/cron."
    def handle(self, *args, **options):
        count = process_escalations()
        self.stdout.write(self.style.SUCCESS(f"Processed {count} due escalation(s)."))
