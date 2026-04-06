from django.db import models


class MeowInstanceHealthStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    HEALTHY = "HEALTHY", "Healthy"
    DEGRADED = "DEGRADED", "Degraded"
    UNAVAILABLE = "UNAVAILABLE", "Unavailable"


class WhatsAppSessionStatus(models.TextChoices):
    NEW = "NEW", "Nova"
    SESSION_REQUESTED = "SESSION_REQUESTED", "Sessao solicitada"
    QR_AVAILABLE = "QR_AVAILABLE", "QR disponivel"
    WAITING_SCAN = "WAITING_SCAN", "Aguardando leitura"
    CONNECTED = "CONNECTED", "Conectado"
    FAILED = "FAILED", "Falha"
    EXPIRED = "EXPIRED", "Expirado"
    DISCONNECTED = "DISCONNECTED", "Desconectado"


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


class WhatsAppIntegrationJobType(models.TextChoices):
    CREATE_SESSION = "CREATE_SESSION", "Create session"
    GENERATE_QR = "GENERATE_QR", "Generate QR"
    SYNC_STATUS = "SYNC_STATUS", "Sync status"
    DELETE_SESSION = "DELETE_SESSION", "Delete session"


class WhatsAppIntegrationJobStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    RETRY = "RETRY", "Retry"
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
