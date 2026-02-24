from django.contrib.auth.models import User
from rest_framework.test import APIClient
#from lineops.allocations.models import Project, Resource


def test_admin_can_allocate(self):
    self.client.force_authenticate(user=self.admin_user)

    response = self.client.post('/api/allocate/', {
        'project': self.project.id,
        'phone_line': self.phone_line.id,
        'amount': 10,
    })
    assert response.status_code == 201

def test_user_cannot_allocate(self):
    self.client.force_authenticate(user=self.operator_user)

    response = self.client.post('/api/allocate/', {
        'project': self.project.id,
        'phone_line': self.phone_line.id,
        'amount': 10,
    })
    assert response.status_code == 403