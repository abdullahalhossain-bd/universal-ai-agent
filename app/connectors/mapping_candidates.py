from dataclasses import dataclass


@dataclass
class MappingCandidate:

    field: str

    column: str

    confidence: float

    reason: str
