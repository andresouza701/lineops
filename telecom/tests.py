from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import PhoneLine, SIMcard


class SIMcardModelTest(TestCase):
    def setUp(self):
        self.base_data = {
            'iccid': '8901123456789012345',
            'carrier': 'LineCarriers',
        }

    def test_create_simcard_with_unique_iccid(self):
        sim = SIMcard.objects.create(**self.base_data)
        stored = SIMcard.objects.get(iccid=self.base_data['iccid'])
        self.assertEqual(sim.pk, stored.pk)

    def test_duplicate_iccid_is_blocked(self):
        SIMcard.objects.create(**self.base_data)

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                SIMcard.objects.create(**self.base_data)

    def test_status_change_is_persisted(self):
        sim = SIMcard.objects.create(**self.base_data)
        sim.status = SIMcard.Status.BLOCKED
        sim.save(update_fields=['status', 'updated_at'])

        reloaded = SIMcard.objects.get(pk=sim.pk)
        self.assertEqual(reloaded.status, SIMcard.Status.BLOCKED)


class PhoneLineModelTest(TestCase):
    def setUp(self):
        self.sim = SIMcard.objects.create(
            iccid='8901123456789012346',
            carrier='TestTel',
        )
        self.phone_number = '+5511999990000'

    def test_create_phone_line_with_sim(self):
        line = PhoneLine.objects.create(
            phone_number=self.phone_number,
            sim_card=self.sim,
        )
        self.assertEqual(line.sim_card, self.sim)
        self.assertEqual(line.status, PhoneLine.Status.AVAILABLE)

    def test_same_sim_cannot_link_multiple_lines(self):
        PhoneLine.objects.create(
            phone_number=self.phone_number, sim_card=self.sim)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PhoneLine.objects.create(
                    phone_number='+5511888880000', sim_card=self.sim)

    def test_phone_number_uniqueness_enforced(self):
        PhoneLine.objects.create(
            phone_number=self.phone_number, sim_card=self.sim)
        second_sim = SIMcard.objects.create(
            iccid='8901123456789012347', carrier='TestTel2')
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PhoneLine.objects.create(
                    phone_number=self.phone_number, sim_card=second_sim)
