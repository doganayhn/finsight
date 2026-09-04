from enum import StrEnum


class SourceType(StrEnum):
    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    GMAIL = "GMAIL"


class FileFormat(StrEnum):
    PDF = "PDF"
    CSV = "CSV"
    XLSX = "XLSX"


class ImportStatus(StrEnum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
