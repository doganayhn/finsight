from uuid import UUID


class ImportProblem(Exception):
    """Only static public codes and a scoped batch ID, never uploaded data."""

    def __init__(self, code: str, status: int, batch_id: UUID | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.batch_id = batch_id
