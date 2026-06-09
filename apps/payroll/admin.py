from django.contrib import admin

from .models import (
    CalculationRun,
    EmployeePayrollInput,
    PaymentBatch,
    PayrollApproval,
    PayrollCorrection,
    PayrollLineItem,
    PayrollPeriod,
    PayrollRecord,
    PaySchedule,
    Payslip,
)

admin.site.register(
    [
        PaySchedule,
        PayrollPeriod,
        EmployeePayrollInput,
        CalculationRun,
        PayrollLineItem,
        PayrollApproval,
        PayrollCorrection,
        Payslip,
        PaymentBatch,
        PayrollRecord,
    ]
)
