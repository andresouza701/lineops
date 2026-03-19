from django.test import TestCase

from .models import SystemUser


class SystemUserRoleTests(TestCase):
    def test_dev_role_is_available_in_choices(self):
        self.assertIn((SystemUser.Role.DEV, "Dev"), SystemUser.Role.choices)
