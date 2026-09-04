from app.modules.imports.errors import ImportProblem
from app.modules.imports.parsers.base import StatementParser
from app.modules.imports.parsers.yapikredi_tlcard import YapiKrediTLCardPDFParser
from app.modules.imports.schemas import ExtractedDocument


class ParserRegistry:
    def __init__(self, parsers: tuple[StatementParser, ...] | None = None):
        self.parsers = parsers if parsers is not None else (YapiKrediTLCardPDFParser(),)

    def resolve(self, document: ExtractedDocument) -> StatementParser:
        matches = [parser for parser in self.parsers if parser.can_parse(document)]
        if not matches:
            raise ImportProblem("unsupported_statement", 415)
        if len(matches) != 1:
            raise ImportProblem("ambiguous_statement_parser", 422)
        return matches[0]
