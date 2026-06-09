from django.urls import path

from .views import PayrollRecordListCreateView

app_name = "payroll"
urlpatterns = [
    path("organizations/<int:organization_id>/records/", PayrollRecordListCreateView.as_view(), name="records")
]
