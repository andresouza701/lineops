from django.contrib import admin
from django.test import Client, TestCase
from django.urls import reverse

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class LineAllocationAdminTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = SystemUser.objects.create_superuser(
            email="root@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.superuser)

        self.employee = Employee.objects.create(
            full_name="Admin Allocation User",
            corporate_email="admin.alloc.user@test.com",
            employee_id="EMP-ADMIN-1",
            teams="IT",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(
            iccid="8900000000000099991",
            carrier="Carrier Admin",
            status=SIMcard.Status.ACTIVE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+5511999991111",
            sim_card=sim,
            status=PhoneLine.Status.ALLOCATED,
        )
        self.allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.phone_line,
            allocated_by=self.superuser,
            is_active=True,
        )

    def test_line_allocation_admin_disables_delete_permission(self):
        model_admin = admin.site._registry[LineAllocation]

        self.assertFalse(model_admin.has_delete_permission(self.client.request().wsgi_request))

    def test_delete_view_returns_forbidden_instead_of_server_error(self):
        url = reverse("admin:allocations_lineallocation_delete", args=[self.allocation.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)
