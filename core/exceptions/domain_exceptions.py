class BusinessLogicError(Exception):
    """Custom exception for business logic errors in the allocation process."""
    pass


class BusinessRuleException(BusinessLogicError):
    """Alias for business rule violations that aligns with tests."""
    pass
