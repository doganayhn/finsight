from typing import Protocol

from app.modules.imports.schemas import ExtractedDocument, ParsedStatement, StatementValidation


class StatementParser(Protocol):
    def can_parse(self, document: ExtractedDocument) -> bool: ...

    def parse(self, document: ExtractedDocument) -> ParsedStatement: ...

    def validate(self, statement: ParsedStatement) -> StatementValidation: ...
