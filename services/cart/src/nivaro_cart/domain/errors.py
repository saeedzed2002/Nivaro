class AuthorizationError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
