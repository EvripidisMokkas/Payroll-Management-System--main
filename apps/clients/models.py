"""Client legal identity, billing details, agreements, and lifecycle."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import ArchivableOrganizationModel, EffectiveDatedOrganizationModel, LifecycleStatus
from apps.organizations.validators import validate_currency, validate_identifier


class Client(ArchivableOrganizationModel):
    code = models.CharField(max_length=50, validators=[validate_identifier])
    display_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=100, blank=True, validators=[validate_identifier])
    tax_identifier_reference = models.CharField(
        max_length=255, blank=True, help_text="Token or encrypted reference; never store plaintext tax IDs."
    )
    jurisdiction = models.CharField(max_length=2)
    status = models.CharField(
        max_length=20, choices=LifecycleStatus.choices, default=LifecycleStatus.DRAFT, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "code"), name="unique_client_code_per_org"),
            models.UniqueConstraint(
                fields=("organization", "registration_number"),
                condition=~models.Q(registration_number=""),
                name="unique_client_registration_per_org",
            ),
        ]
        indexes = [models.Index(fields=("organization", "status"), name="client_org_status_idx")]

    def clean(self):
        super().clean()
        if self.jurisdiction and (len(self.jurisdiction) != 2 or not self.jurisdiction.isupper()):
            raise ValidationError({"jurisdiction": "Use an uppercase ISO 3166-1 alpha-2 country code."})

    def __str__(self):
        return self.display_name


class ClientBillingProfile(ArchivableOrganizationModel):
    client = models.OneToOneField(Client, on_delete=models.PROTECT, related_name="billing_profile")
    billing_email = models.EmailField()
    billing_contact = models.CharField(max_length=200, blank=True)
    billing_address = models.TextField()
    currency = models.CharField(max_length=3, validators=[validate_currency])
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    purchase_order_required = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=("organization", "billing_email"), name="client_bill_email_idx")]

    def clean(self):
        super().clean()
        if self.client_id and self.organization_id != self.client.organization_id:
            raise ValidationError({"client": "Client must belong to the same organization."})


class ServiceAgreement(EffectiveDatedOrganizationModel):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="service_agreements")
    agreement_number = models.CharField(max_length=100, validators=[validate_identifier])
    status = models.CharField(
        max_length=20, choices=LifecycleStatus.choices, default=LifecycleStatus.DRAFT, db_index=True
    )
    description = models.TextField(blank=True)
    billing_frequency = models.CharField(
        max_length=20,
        choices=[("weekly", "Weekly"), ("monthly", "Monthly"), ("quarterly", "Quarterly"), ("annual", "Annual")],
        default="monthly",
    )
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    termination_notice_days = models.PositiveSmallIntegerField(default=30)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "agreement_number"), name="unique_agreement_number_per_org"
            ),
            models.CheckConstraint(condition=models.Q(fee_amount__gte=0), name="service_fee_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="service_agreement_dates_valid",
            ),
        ]
        indexes = [models.Index(fields=("client", "status", "effective_from"), name="agreement_client_status_idx")]

    def clean(self):
        super().clean()
        if self.client_id and self.organization_id != self.client.organization_id:
            raise ValidationError({"client": "Client must belong to the same organization."})
