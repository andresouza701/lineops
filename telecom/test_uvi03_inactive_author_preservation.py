"""
UVI-03 - Controle positivo (GREEN esperado): historico/timeline de linha
preservam a identidade do autor mesmo apos a conta ser desativada.

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md
(UVI-01/UVI-02). Node ID T10 do checklist derivado em UVI-02 (U19).

telecom/line_timeline.py resolve autores via SystemUser.objects.filter(
pk__in=actor_ids), sem filtro de is_active (confirmado em UVI-02): este
teste prova que a consulta de fato retorna e rotula o autor inativo, nao
apenas que a rota foi alcancada. Nomeado com prefixo "test_" (nao
"tests_") para ser coletado pelo pytest (pytest.ini python_files = tests.py
test_*.py *_tests.py); arquivo na raiz do app, sem pacote telecom/tests/,
seguindo a mesma observacao de descoberta documentada em
telecom/tests_line_timeline.py.
"""

from django.test import TestCase

from telecom.line_timeline import _actor_label_legacy, get_line_timeline_filter_options
from telecom.models import PhoneLine, PhoneLineHistory, SIMcard
from users.models import SystemUser


class T10_InactiveAuthorIdentityPreservedInTimelineTest(TestCase):
    def setUp(self):
        self.inactive_author = SystemUser.objects.create_user(
            email="autor.inativo.timeline.uvi03@test.com",
            password="StrongPass123",
            role=SystemUser.Role.ADMIN,
        )
        self.inactive_author.is_active = False
        self.inactive_author.save(update_fields=["is_active"])

        self.sim_card = SIMcard.objects.create(
            iccid="8900000000000000902",
            carrier="CarrierTimelineUvi03",
            status=SIMcard.Status.AVAILABLE,
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number="+551199999902",
            sim_card=self.sim_card,
            status=PhoneLine.Status.ALLOCATED,
        )
        PhoneLineHistory.objects.filter(phone_line=self.phone_line).delete()
        self.history = PhoneLineHistory.objects.create(
            phone_line=self.phone_line,
            action=PhoneLineHistory.ActionType.STATUS_CHANGED,
            old_value="A",
            new_value="B",
            changed_by=self.inactive_author,
            description="",
        )

    def test_actor_label_still_resolves_inactive_author_email(self):
        label = _actor_label_legacy(self.history)

        self.assertEqual(label, self.inactive_author.email)

    def test_filter_options_still_include_inactive_author_as_actor_choice(self):
        options = get_line_timeline_filter_options(self.phone_line)

        actor_ids = [actor_id for actor_id, _label in options.actor_choices]
        self.assertIn(self.inactive_author.pk, actor_ids)
