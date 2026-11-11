class AuthorizationError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status


class CartInputError(ValueError):
    pass


class CommerceError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
