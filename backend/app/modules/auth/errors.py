class AuthProblem(Exception):
    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status
        super().__init__(code)
