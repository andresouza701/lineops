from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.apps import apps
from django.db import models


class SystemUserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class SystemUser(AbstractUser):
    # You can add additional fields here if needed
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        SUPER = "super", "Super"
        GERENTE = "gerente", "Gerente"
        OPERATOR = "operator", "Operator"

    SUPERVISOR_ROLES = (Role.SUPER,)
    EMPLOYEE_ACCESS_ROLES = (Role.ADMIN, Role.SUPER, Role.GERENTE)

    username = None
    email = models.EmailField(unique=True)

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OPERATOR)

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = SystemUserManager()

    def __str__(self):
        return f"{self.email} - {self.role}"

    @property
    def is_supervisor_role(self):
        return self.role in self.SUPERVISOR_ROLES

    @property
    def is_manager_role(self):
        return self.role == self.Role.GERENTE

    @property
    def can_access_employee_area(self):
        return self.role in self.EMPLOYEE_ACCESS_ROLES

    def scope_employee_queryset(self, queryset=None):
        employee_model = apps.get_model("employees", "Employee")
        queryset = queryset if queryset is not None else employee_model.objects.all()

        if self.role == self.Role.SUPER:
            return queryset.filter(corporate_email__iexact=self.email)
        if self.role == self.Role.GERENTE:
            return queryset.filter(manager_email__iexact=self.email)
        return queryset


# Create your models here.
