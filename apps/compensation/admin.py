"""Admin registrations for compensation policies and recommendations."""

from django.contrib import admin

from .models import CompensationApproval, CompensationPolicy, CompensationRecommendation, ScoringRule


@admin.register(CompensationPolicy)
class CompensationPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "organization", "effective_from", "effective_to", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "version", "organization__name")


@admin.register(ScoringRule)
class ScoringRuleAdmin(admin.ModelAdmin):
    list_display = ("policy", "criterion", "weight", "effective_from", "effective_to")
    list_filter = ("criterion",)


class CompensationApprovalInline(admin.TabularInline):
    model = CompensationApproval
    extra = 0
    readonly_fields = ("actor", "action", "created_at", "snapshot")


@admin.register(CompensationRecommendation)
class CompensationRecommendationAdmin(admin.ModelAdmin):
    list_display = ("employee", "policy", "as_of_date", "status", "proposed_min", "proposed_max", "created_at")
    list_filter = ("status", "as_of_date")
    inlines = [CompensationApprovalInline]
