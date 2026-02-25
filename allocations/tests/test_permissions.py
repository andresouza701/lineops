from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from allocations.models import LineAllocation
from employees.models import Employee
from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class PermissionByRoleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPass123"
        self.admin = SystemUser.objects.create_user(
            email="admin.role@test.com",
            password=self.password,
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator.role@test.com",
            password=self.password,
            role=SystemUser.Role.OPERATOR,
        )

    def _access_token(self, email, password):
        response = self.client.post(
            "/api/token/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()["access"]

    def test_admin_can_access_admin_only_endpoint(self):
        token = self._access_token(self.admin.email, self.password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_operator_cannot_access_admin_only_endpoint(self):
        token = self._access_token(self.operator.email, self.password)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get("/api/admin-only/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AllocationRBACViewTests(TestCase):
    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin.alloc@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.operator = SystemUser.objects.create_user(
            email="operator.alloc@test.com",
            password="StrongPass123",
            role=SystemUser.Role.OPERATOR,
        )

        self.employee = Employee.objects.create(
            full_name="Alloc User",
            corporate_email="alloc@corp.com",
            employee_id="EMP-ALLOC",
            department="IT",
            status=Employee.Status.ACTIVE,
        )
        sim = SIMcard.objects.create(iccid="8900000000000000777", carrier="CarY")
        self.line = PhoneLine.objects.create(
            phone_number="+551199999777",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def test_admin_and_operator_can_access_registration_hub(self):
        url = reverse("allocations:allocation_list")

        self.client.force_login(self.admin)
        admin_resp = self.client.get(url)
        self.assertEqual(admin_resp.status_code, 200)

        self.client.force_login(self.operator)
        operator_resp = self.client.get(url)
        self.assertEqual(operator_resp.status_code, 200)

    def test_anonymous_redirected_to_login(self):
        url = reverse("allocations:allocation_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_release_view_respects_roles(self):
        # admin can allocate and release; operator can release; anonymous cannot
        self.client.force_login(self.admin)
        allocation = LineAllocation.objects.create(
            employee=self.employee,
            phone_line=self.line,
            allocated_by=self.admin,
            is_active=True,
        )

        url = reverse("allocations:allocation_release", args=[allocation.pk])

        # operator allowed
        self.client.force_login(self.operator)
        op_resp = self.client.post(url, follow=False)
        self.assertIn(op_resp.status_code, (302, 200))

        # anonymous blocked
        self.client.logout()
        anon_resp = self.client.post(url)
        self.assertEqual(anon_resp.status_code, 403)
