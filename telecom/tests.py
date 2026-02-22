from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

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


class PhoneLineStatusTest(TestCase):
    def setUp(self):
        self.sim = SIMcard.objects.create(
            iccid='8901123456789012348',
            carrier='TestTel3',
        )
        self.phone_line = PhoneLine.objects.create(
            phone_number='+5511999980000',
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )
        self.phone_line2 = PhoneLine.objects.create(
            phone_number='+5511999980001',
            sim_card=self.sim,
            status=PhoneLine.Status.ALLOCATED,
        )

        def test_filter_by_status(self):
            available_lines = PhoneLine.objects.filter(
                status=PhoneLine.Status.AVAILABLE)
            self.assertIn(self.phone_line, available_lines)
            self.assertNotIn(self.phone_line2, available_lines)

            allocated_lines = PhoneLine.objects.filter(
                status=PhoneLine.Status.ALLOCATED)
            self.assertIn(self.phone_line2, allocated_lines)
            self.assertNotIn(self.phone_line, allocated_lines)


class PhoneLinePaginationTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='testuser@example.com',
            password='password123',
        )
        self.client.force_login(self.user)
        for i in range(25):
            sim = SIMcard.objects.create(
                iccid=f'89011234567890123{i}',
                carrier='TestTelPagination',
            )
            PhoneLine.objects.create(
                phone_number=f'+55119999900{i}',
                sim_card=sim,
            )

    def test_pagination_works(self):

        response = self.client.get(
            reverse('telecom:phoneline_list') + '?page=1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['phone_lines']), 20)
