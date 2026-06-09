"""Tenant-safe payroll API examples."""

from rest_framework import generics, serializers

from apps.organizations.mixins import OrganizationAccessMixin
from apps.organizations.models import OrganizationRole
from apps.organizations.services import membership_for

from .models import PayrollRecord


class PayrollRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRecord
        fields = ("id", "employee", "employee_name", "gross_amount", "status")
        read_only_fields = ("id",)


class PayrollRecordListCreateView(OrganizationAccessMixin, generics.ListCreateAPIView):
    serializer_class = PayrollRecordSerializer
    required_action = "payroll.read"

    def get_queryset(self):
        qs = PayrollRecord.objects.for_user(self.request.user).for_organization(self.get_organization())
        member = membership_for(self.request.user, self.get_organization())
        if member and member.role == OrganizationRole.EMPLOYEE:
            return qs.filter(employee=self.request.user)
        return qs

    def perform_create(self, serializer):
        from apps.organizations.services import authorize, membership_for

        organization = self.get_organization()
        authorize(self.request.user, organization, "payroll.write")
        employee = serializer.validated_data.get("employee")
        if employee and not membership_for(employee, organization):
            raise serializers.ValidationError({"employee": "Employee account must belong to the payroll organization."})
        serializer.save(organization=organization)
