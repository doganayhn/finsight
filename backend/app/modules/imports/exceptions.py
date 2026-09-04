"""Privacy-safe parser errors. Never interpolate document text into messages."""


class PDFTextExtractionError(ValueError):
    pass


class UnsupportedStatementError(ValueError):
    pass


class StatementParseError(ValueError):
    pass


class StatementValidationError(ValueError):
    pass
