"""Re-encrypt recoverable sensitive fields with the active key."""

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.employees.models import EmployeeBankAccount, EmployeePersonalInformation, EmployeeTaxProfile

TARGETS = (
    (User, ("mfa_secret",)),
    (
        EmployeePersonalInformation,
        (
            "legal_name_encrypted",
            "date_of_birth_encrypted",
            "personal_email_encrypted",
            "personal_phone_encrypted",
            "residential_address_encrypted",
            "emergency_contact_encrypted",
        ),
    ),
    (EmployeeBankAccount, ("account_holder_encrypted", "routing_details_encrypted")),
    (EmployeeTaxProfile, ("elections_encrypted",)),
)


class Command(BaseCommand):
    help = "Encrypt legacy plaintext and rotate encrypted fields to the first configured key."

    def handle(self, *args, **options):
        updated = 0
        for model, fields in TARGETS:
            for instance in model.objects.all().iterator(chunk_size=500):
                populated = tuple(field for field in fields if getattr(instance, field))
                if populated:
                    instance.save(update_fields=populated)
                    updated += 1
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {updated} sensitive records."))
