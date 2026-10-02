"""Adiciona situação de ativação, categoria, plano e valor mensal do selo
WHATS LINEOPS à linha telefônica, com backfill dos registros existentes.

Fonte da verdade: docs/superpowers/specs/2026-09-30-whatsapp-seal-
activation-value-design.md (contrato técnico, SEV-04, T10).

Backfill: toda linha com whatsapp_seal preenchido (vindo da migração 0021)
é classificada ACTIVE — "selos existentes considerados ativos, preservando
datas" (aprovação do usuário). Categoria, plano e valor mensal ficam vazios/
nulos: não há dado de origem para inferir esses três campos em legados, e
inferir pelo tipo do selo foi explicitamente reprovado (T20). Linhas sem
selo (whatsapp_seal="") não são tocadas.

Usa apps.get_model (modelo histórico) e .update() em massa, sem chamar
full_clean/normalize_seal_fields/validate_seal_fields (serviços atuais) —
o backfill é responsabilidade exclusiva desta migração, isolada de mudanças
futuras no domínio da aplicação. O manager histórico de PhoneLine não tem
SoftDeleteManager anexado (use_in_migrations não foi declarado em
SoftDeleteManager), portanto reflete TODAS as linhas, inclusive is_deleted
=True — confirmado por teste real em telecom/test_whatsapp_seal_activation_
migration.py.

Reversão: apenas remove as 4 colunas novas (reverse padrão de AddField);
RunPython.noop porque não há dado anterior à feature para restaurar nesses
campos. Os 5 campos antigos de selo (whatsapp_seal e demais) não são
alterados por este arquivo em nenhum sentido, preservando-os intactos no
rollback.
"""

from django.db import migrations, models


def backfill_activation_status(apps, schema_editor):
    PhoneLine = apps.get_model("telecom", "PhoneLine")
    PhoneLine.objects.using(schema_editor.connection.alias).exclude(
        whatsapp_seal=""
    ).update(whatsapp_seal_activation_status="ACTIVE")


class Migration(migrations.Migration):

    dependencies = [
        ('telecom', '0021_phoneline_whatsapp_seal_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='phoneline',
            name='whatsapp_seal_activation_status',
            field=models.CharField(blank=True, choices=[('NOT_ACTIVATED', 'Não ativado'), ('ACTIVE', 'Ativo')], default='', max_length=20),
        ),
        migrations.AddField(
            model_name='phoneline',
            name='whatsapp_seal_category',
            field=models.CharField(blank=True, choices=[('CREATORS_BUSINESSES', 'Criadores / Empresas'), ('PERSONAL_CREATOR', 'Pessoa Física (Uso Pessoal / Criador)'), ('BUSINESS_SME', 'Pessoa Jurídica (Empresas / PMEs)'), ('BUSINESS', 'Pessoa Jurídica (Empresas)')], default='', max_length=30),
        ),
        migrations.AddField(
            model_name='phoneline',
            name='whatsapp_seal_monthly_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='phoneline',
            name='whatsapp_seal_plan',
            field=models.CharField(blank=True, choices=[('ONE_ESSENTIAL', 'One Essencial'), ('STANDARD', 'Standard'), ('BUSINESS_BASIC', 'Business Básico'), ('BUSINESS_PLUS', 'Business Plus')], default='', max_length=30),
        ),
        migrations.RunPython(
            backfill_activation_status,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
