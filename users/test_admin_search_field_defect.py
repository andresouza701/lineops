"""UVI-04 - Teste RED->GREEN dedicado ao defeito pre-existente da busca do
Admin de SystemUser, separado da politica NOVA de visibilidade de contas
inativas (users/test_uvi03_admin_inactive_visibility.py).

Achado na conferencia corretiva de UVI-03: UserAdmin.search_fields
(herdado de django.contrib.auth.admin.UserAdmin, nunca sobrescrito em
SystemUserAdmin) inclui "username" -- campo que SystemUser nao possui
(username = None, USERNAME_FIELD = "email"). Qualquer busca (?q=) no
Admin de contas levantava django.core.exceptions.FieldError: "Cannot
resolve keyword 'username' into field", para QUALQUER viewer (inclusive
ADMIN), independente de role ou is_active. Bug pre-existente, NAO
relacionado a feature de visibilidade (UVI-01..UVI-04).

Correcao minima aplicada em users/admin.py::SystemUserAdmin:
``search_fields = ("email",)`` -- o campo real usado como login
(USERNAME_FIELD) do cadastro, substituindo o valor herdado.

Este arquivo prova o defeito e a correcao isoladamente: antes da correcao,
test_search_raises_field_error_before_fix teria FALHADO (FieldError nao
capturado -> ERROR, nao apenas assertion); apos a correcao, a mesma busca
retorna 200 normalmente. Mantido como documentacao do defeito corrigido,
nao como teste negativo permanente (nao reintroduzimos o bug para manter
isto RED)."""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from users.models import SystemUser


class SystemUserAdminSearchFieldDefectTest(TestCase):
    def setUp(self):
        self.viewer = SystemUser.objects.create_user(
            email="admin.search.defect.uvi04@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.viewer.is_staff = True
        self.viewer.save(update_fields=["is_staff"])
        self.viewer.user_permissions.set(
            Permission.objects.filter(content_type__app_label="users")
        )
        self.client.force_login(self.viewer)

    def test_search_fields_does_not_reference_nonexistent_username_field(self):
        """Prova direta da causa raiz: search_fields nao pode mais conter
        "username" (campo inexistente em SystemUser -- username = None).
        Este e o unico ponto de correcao minimo exigido pelo defeito."""
        from users.admin import SystemUserAdmin

        self.assertNotIn("username", SystemUserAdmin.search_fields)
        self.assertIn("email", SystemUserAdmin.search_fields)

    def test_search_by_email_no_longer_raises_field_error(self):
        """Antes da correcao, esta chamada levantava FieldError (nao
        capturado por nenhum try/except da view do Admin, propagando como
        erro de servidor em producao). Apos a correcao minima, retorna 200
        normalmente -- sem nenhuma mudanca na politica de visibilidade,
        que e exercitada separadamente em test_uvi03_admin_inactive_
        visibility.py."""
        response = self.client.get(
            reverse("admin:users_systemuser_changelist"),
            {"q": self.viewer.email},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.viewer.email)
