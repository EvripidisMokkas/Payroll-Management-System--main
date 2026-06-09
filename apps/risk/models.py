"""Organization-scoped risk register records."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import OrganizationScopedModel


class RiskLikelihood(models.IntegerChoices):
    RARE = 1, "Rare"
    UNLIKELY = 2, "Unlikely"
    POSSIBLE = 3, "Possible"
    LIKELY = 4, "Likely"
    ALMOST_CERTAIN = 5, "Almost certain"


class RiskImpact(models.IntegerChoices):
    INSIGNIFICANT = 1, "Insignificant"
    MINOR = 2, "Minor"
    MODERATE = 3, "Moderate"
    MAJOR = 4, "Major"
    SEVERE = 5, "Severe"


class RiskStatus(models.TextChoices):
    OPEN = "open", "Open"
    MITIGATING = "mitigating", "Mitigating"
    ACCEPTED = "accepted", "Accepted"
    CLOSED = "closed", "Closed"


class RiskRegisterEntry(OrganizationScopedModel):
    title = models.CharField(max_length=200)
    description = models.TextField()
    likelihood = models.PositiveSmallIntegerField(choices=RiskLikelihood.choices)
    impact = models.PositiveSmallIntegerField(choices=RiskImpact.choices)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_risks")
    mitigation = models.TextField()
    review_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=RiskStatus.choices, default=RiskStatus.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("organization", "status", "review_date"), name="risk_org_status_review_idx")]

    @property
    def score(self):
        return self.likelihood * self.impact

    def clean(self):
        super().clean()
        if (
            self.owner_id
            and not self.owner.organization_memberships.filter(
                organization_id=self.organization_id, is_active=True
            ).exists()
        ):
            raise ValidationError({"owner": "Risk owner must be an active member of the organization."})
