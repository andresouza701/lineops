from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import SystemUser


class SystemUserRoleTests(TestCase):
    def test_dev_role_is_available_in_choices(self):
        self.assertIn((SystemUser.Role.DEV, "Dev"), SystemUser.Role.choices)

    def test_backoffice_role_is_available_in_choices(self):
        self.assertIn(
            (SystemUser.Role.BACKOFFICE, "Backoffice"),
            SystemUser.Role.choices,
        )

    def test_backoffice_requires_linked_supervisor(self):
        user = SystemUser(
            email="backoffice.missing@test.com",
            role=SystemUser.Role.BACKOFFICE,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Backoffice precisa de supervisor",
        ):
            user.full_clean()

    def test_backoffice_requires_supervisor_role_as_link(self):
        SystemUser.objects.create_user(
            email="gerente.backoffice@test.com",
            password="StrongPass123",
            role=SystemUser.Role.GERENTE,
        )
        user = SystemUser(
            email="backoffice.invalid@test.com",
            role=SystemUser.Role.BACKOFFICE,
            supervisor_email="gerente.backoffice@test.com",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Selecione um supervisor valido",
        ):
            user.full_clean()
