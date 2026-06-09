"""Admin registrations for the taxation domain."""

from django.contrib import admin

from .models import (
    FilingAmendment,
    FilingExport,
    FilingPeriod,
    Jurisdiction,
    OrganizationTaxConfiguration,
    TaxLiability,
    TaxRuleVersion,
)

admin.site.register(Jurisdiction)
admin.site.register(TaxRuleVersion)
admin.site.register(OrganizationTaxConfiguration)
admin.site.register(FilingPeriod)
admin.site.register(TaxLiability)
admin.site.register(FilingAmendment)
admin.site.register(FilingExport)
