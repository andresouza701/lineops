"""REL-14: integration gaps derived from REL-07 and REL-13-C."""

from datetime import date, datetime, time
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser


class _ReportPickerParser(HTMLParser):
    """Read successful hidden controls from the actual report picker."""

    def __init__(self):
        super().__init__()
        self.in_picker = False
        self.found_picker = False
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.in_picker = attrs.get("aria-label") == "Selecionar relatório"
            self.found_picker |= self.in_picker
        if self.in_picker and tag == "input" and attrs.get("type") == "hidden":
            if "disabled" not in attrs and attrs.get("name"):
                self.values[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_picker = False


class ReportPickerCrossReportIntegrationTests(TestCase):
    """REL-14 bloqueante: trocar de relatorio com `linha` preenchido para
    `daily_indicators` retornava 400. Causa: o form 'Selecionar relatorio'
    (picker) espelhava `linha` como campo comum, mas `daily_indicators`
    rejeita esse parametro (REL-13-C). Correcao: o picker (unico ponto sem
    JS que decide o que a troca envia) nunca mais espelha `linha`, para
    NENHUM relatorio de origem -- REL-07 (linha 672 da spec) so garante
    `data_inicial`/`data_final`/`incluir_excluidos` sobrevivendo a uma
    troca; `linha` nunca foi um requisito documentado, so uma generalizacao
    de REL-12-V-3 que deixou de valer com o sexto relatorio. Nao ha meio
    sem JavaScript de o picker saber qual destino sera escolhido antes do
    clique, entao a unica correcao compativel com os dois requisitos
    (funciona sem JS; nunca envia ao destino um filtro que ele pode
    rejeitar) e nunca enviar `linha` a partir do picker, para nenhum
    destino -- inclusive os 5 relatorios que ainda aceitam `linha` via seu
    proprio form 'Filtrar e gerar relatorio' (reaplicado ali, nao perdido)."""

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="rel14-admin@example.test", password="test-only-password",
            role=SystemUser.Role.ADMIN,
        )
        self.client.force_login(self.admin)
        self.url = reverse("reports_home")

    def test_switch_to_daily_indicators_after_line_filter_in_one_submission(self):
        """REL-07 clears incompatible filters; REL-13-C rejects direct linha."""
        source = self.client.get(self.url, {
            "relatorio": "line_inventory",
            "data_inicial": "2026-09-01", "data_final": "2026-09-01",
            "linha": "11999990000",
        })
        self.assertEqual(source.status_code, 200)
        picker = _ReportPickerParser()
        picker.feed(source.content.decode())
        self.assertTrue(picker.found_picker)
        self.assertEqual(picker.values["data_inicial"], "2026-09-01")
        # O picker real nunca contem `linha` na sua propria arvore DOM --
        # nao e "enviado e ignorado", e ausente por construcao.
        self.assertNotIn("linha", picker.values)
        # A native select change replaces only relatorio; hidden controls remain.
        picker.values["relatorio"] = "daily_indicators"
        destination = self.client.get(self.url, picker.values)
        self.assertEqual(destination.status_code, 200, destination.context["form"].errors)
        self.assertNotContains(destination, "Parâmetro não aplicável")
        self.assertNotIn("linha", destination.wsgi_request.GET)

    def test_switch_preserves_dates_and_incluir_excluidos_and_resets_page(self):
        """Datas e incluir_excluidos (comuns garantidos por REL-07) chegam
        ao destino; paginacao reinicia (o picker nunca contem `page`, com
        ou sem `linha` na origem). 55 linhas reais (PAGE_SIZE=50) tornam a
        pagina 2 da origem genuina, nao um numero de pagina invalido."""
        created_at = timezone.make_aware(datetime.combine(date(2026, 9, 3), time.min))
        for index in range(55):
            sim = SIMcard.objects.create(iccid=f"8900001{index:015d}", carrier="TIM")
            line = PhoneLine.objects.create(
                phone_number=f"1190000{index:04d}", sim_card=sim,
                status=PhoneLine.Status.AVAILABLE,
            )
            PhoneLine.all_objects.filter(pk=line.pk).update(created_at=created_at)

        source = self.client.get(self.url, {
            "relatorio": "line_inventory",
            "data_inicial": "2026-09-01", "data_final": "2026-09-08",
            "incluir_excluidos": "1", "page": "2",
        })
        self.assertEqual(source.status_code, 200)
        picker = _ReportPickerParser()
        picker.feed(source.content.decode())
        self.assertNotIn("page", picker.values)
        self.assertNotIn("linha", picker.values)
        picker.values["relatorio"] = "daily_indicators"
        destination = self.client.get(self.url, picker.values)
        self.assertEqual(destination.status_code, 200, destination.context["form"].errors)
        request_get = destination.wsgi_request.GET
        self.assertEqual(request_get["data_inicial"], "2026-09-01")
        self.assertEqual(request_get["data_final"], "2026-09-08")
        self.assertEqual(request_get["incluir_excluidos"], "1")
        self.assertNotIn("page", request_get)
        self.assertEqual(destination.context["result"].page_number, 1)

    def test_switch_between_linha_compatible_reports_no_longer_carries_linha(self):
        """Mudanca de comportamento deliberada (nao so para
        daily_indicators): como o picker nunca mais espelha `linha`,
        trocar entre dois relatorios que ACEITAM `linha`
        (line_inventory -> allocations) tambem deixa de transportar o
        valor -- consistente com REL-07 (linha 672), que nunca garantiu
        essa sobrevivencia. O usuario continua podendo filtrar por linha
        no destino, preenchendo de novo o campo visivel do form 'Filtrar e
        gerar relatorio' daquele relatorio (nao removido, so nao
        pre-preenchido pela troca)."""
        source = self.client.get(self.url, {
            "relatorio": "line_inventory",
            "data_inicial": "2026-09-01", "data_final": "2026-09-01",
            "linha": "11999990000",
        })
        self.assertEqual(source.status_code, 200)
        picker = _ReportPickerParser()
        picker.feed(source.content.decode())
        picker.values["relatorio"] = "allocations"
        destination = self.client.get(self.url, picker.values)
        self.assertEqual(destination.status_code, 200)
        self.assertNotIn("linha", destination.wsgi_request.GET)
        self.assertEqual(destination.context["form"].cleaned_data.get("linha"), "")

    def test_direct_query_to_daily_indicators_with_linha_still_rejected(self):
        """Regressao: a correcao do picker nao afrouxa a rejeicao estrita
        de `linha` numa consulta DIRETA a daily_indicators (REL-13-C)."""
        response = self.client.get(self.url, {
            "relatorio": "daily_indicators",
            "data_inicial": "2026-09-01", "data_final": "2026-09-01",
            "linha": "11999990000",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro não aplicável", status_code=400)

    def test_direct_export_to_daily_indicators_with_linha_still_rejected(self):
        """Mesma regressao, caminho de exportacao (REL-13-C/REL-13-E)."""
        export_url = reverse("reports_export", kwargs={"formato": "csv"})
        response = self.client.get(export_url, {
            "relatorio": "daily_indicators",
            "data_inicial": "2026-09-01", "data_final": "2026-09-01",
            "linha": "11999990000",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Parâmetro não aplicável", status_code=400)
