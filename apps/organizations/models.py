"""Organizations, tenant memberships, and reusable scoped models."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .validators import validate_currency, validate_identifier


class LifecycleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    TERMINATED = "terminated", "Terminated"
    ARCHIVED = "archived", "Archived"


class Organization(models.Model):
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(unique=True)
    registration_number = models.CharField(
        max_length=100, null=True, blank=True, unique=True, validators=[validate_identifier]
    )
    tax_identifier_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Token or encrypted reference only; never store a plaintext tax identifier.",
    )
    jurisdiction = models.CharField(max_length=2, default="US", help_text="ISO 3166-1 alpha-2 country code.")
    billing_email = models.EmailField(blank=True)
    billing_address = models.TextField(blank=True)
    default_currency = models.CharField(max_length=3, default="USD", validators=[validate_currency])
    status = models.CharField(
        max_length=20, choices=LifecycleStatus.choices, default=LifecycleStatus.DRAFT, db_index=True
    )
    is_active = models.BooleanField(default=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("status", "legal_name"), name="org_status_legal_idx")]

    def clean(self):
        super().clean()
        if self.jurisdiction and (len(self.jurisdiction) != 2 or not self.jurisdiction.isupper()):
            raise ValidationError({"jurisdiction": "Use an uppercase ISO 3166-1 alpha-2 country code."})
        if self.status == LifecycleStatus.ARCHIVED and not self.archived_at:
            raise ValidationError({"archived_at": "Archived organizations require an archive timestamp."})
        if self.archived_at and self.status != LifecycleStatus.ARCHIVED:
            raise ValidationError({"status": "An organization with an archive timestamp must be archived."})

    def archive(self, *, retention_until=None):
        self.status = LifecycleStatus.ARCHIVED
        self.is_active = False
        self.archived_at = timezone.now()
        self.retention_until = retention_until
        self.full_clean()
        self.save(update_fields=("status", "is_active", "archived_at", "retention_until", "updated_at"))

    def __str__(self):
        return self.name


class OrganizationRole(models.TextChoices):
    ADMINISTRATOR = "administrator", "Administrator"
    PAYROLL_OPERATOR = "payroll_operator", "Payroll operator"
    EMPLOYEE = "employee", "Employee"
    AUDITOR = "auditor", "Auditor"
    CLIENT = "client", "Client"


class OrganizationMembership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization_memberships"
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=OrganizationRole.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "organization"), name="unique_user_organization")]

    def _sync_role_groups(self):
        from django.contrib.auth.models import Group

        role_names = self.user.organization_memberships.filter(is_active=True).values_list("role", flat=True)
        role_groups = Group.objects.filter(name__in=OrganizationRole.values)
        self.user.groups.remove(*role_groups)
        self.user.groups.add(*Group.objects.filter(name__in=role_names))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_role_groups()

    def delete(self, *args, **kwargs):
        from django.contrib.auth.models import Group

        user = self.user
        result = super().delete(*args, **kwargs)
        role_names = user.organization_memberships.filter(is_active=True).values_list("role", flat=True)
        user.groups.remove(*Group.objects.filter(name__in=OrganizationRole.values))
        user.groups.add(*Group.objects.filter(name__in=role_names))
        return result


class OrganizationScopedQuerySet(models.QuerySet):
    def for_organization(self, organization):
        return self.filter(organization=organization)

    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self
        return self.filter(organization__memberships__user=user, organization__memberships__is_active=True).distinct()


class OrganizationScopedModel(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    objects = OrganizationScopedQuerySet.as_manager()

    class Meta:
        abstract = True


class ArchivableOrganizationModel(OrganizationScopedModel):
    """Soft-deletable tenant data retained until its legal retention date."""

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    retention_until = models.DateField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    def archive(self, *, retention_until=None):
        self.archived_at = timezone.now()
        self.retention_until = retention_until
        self.save(update_fields=("archived_at", "retention_until"))


class EffectiveDatedOrganizationModel(ArchivableOrganizationModel):
    """Base for immutable-in-practice payroll inputs with non-overlapping periods."""

    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date cannot precede the start date."})

    @classmethod
    def as_of(cls, date):
        return cls.objects.filter(effective_from__lte=date).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=date)
        )
