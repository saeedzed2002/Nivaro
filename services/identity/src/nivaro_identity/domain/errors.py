class IdentityError(Exception):
    def __init__(self, code: str, status: int = 401, retry_after: int | None = None):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        super().__init__(code)
