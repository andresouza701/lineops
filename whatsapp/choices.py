from django.db import models


class MeowInstanceHealthStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    HEALTHY = "HEALTHY", "Healthy"
    DEGRADED = "DEGRADED", "Degraded"
    UNAVAILABLE = "UNAVAILABLE", "Unavailable"


class WhatsAppSessionStatus(models.TextChoices):
    PENDING_NEW_NUMBER = "PENDING_NEW_NUMBER", "Novo numero"
    PENDING_RECONNECT = "PENDING_RECONNECT", "Reconectar WhatsApp"
    CONNECTING = "CONNECTING", "Conectando"
    QR_PENDING = "QR_PENDING", "QR pendente"
    CONNECTED = "CONNECTED", "Conectado"
    DISCONNECTED = "DISCONNECTED", "Desconectado"
    ERROR = "ERROR", "Erro"


class WhatsAppActionType(models.TextChoices):
    HEALTH_CHECK = "HEALTH_CHECK", "Health check"
    CREATE_SESSION = "CREATE_SESSION", "Create session"
    GET_SESSION = "GET_SESSION", "Get session"
    CONNECT_SESSION = "CONNECT_SESSION", "Connect session"
    DELETE_SESSION = "DELETE_SESSION", "Delete session"
    GET_QR = "GET_QR", "Get QR"
    WEBHOOK_EVENT = "WEBHOOK_EVENT", "Webhook event"


class WhatsAppActionStatus(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    FAILURE = "FAILURE", "Failure"


class WhatsAppSchedulerJobCode(models.TextChoices):
    HEALTH_CHECK = "HEALTH_CHECK", "Health check"
    SESSION_SYNC = "SESSION_SYNC", "Session sync"
    SESSION_RECONCILE = "SESSION_RECONCILE", "Session reconcile"


class WhatsAppSchedulerJobStatus(models.TextChoices):
    IDLE = "IDLE", "Idle"
    RUNNING = "RUNNING", "Running"
    SUCCESS = "SUCCESS", "Success"
    FAILURE = "FAILURE", "Failure"
