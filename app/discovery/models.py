from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    tables: list[TableInfo] = Field(default_factory=list)


class FieldCandidate(BaseModel):
    table: str
    column: str
    semantic_type: str
    confidence: float
    reason: str


class ColumnSample(BaseModel):
    table: str
    column: str
    data_type: str
    samples: list[str] = Field(default_factory=list)
    null_count: int = 0
    unique_count: int = 0


class SemanticMapping(BaseModel):
    table: str
    column: str
    semantic_type: str
    confidence: float
    status: str = "unknown"
    evidence: list[str] = Field(default_factory=list)


class MappingQuestion(BaseModel):
    semantic_type: str
    candidates: list[SemanticMapping]
    question: str


class RelationshipInfo(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str
    confidence: float
    reason: str


class TableRole(BaseModel):
    table: str
    role: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class DiscoveryResult(BaseModel):
    """Discovery payload.

    Field is named ``db_schema`` so it does not shadow ``BaseModel.schema``
    (Pydantic UserWarning). JSON still uses the key ``"schema"`` via aliases.
    """

    model_config = ConfigDict(populate_by_name=True)

    db_schema: DatabaseSchema = Field(
        validation_alias="schema",
        serialization_alias="schema",
    )
    candidates: list[SemanticMapping] = Field(
        default_factory=list
    )
    relationships: list[RelationshipInfo] = Field(
        default_factory=list
    )
    table_roles: list[TableRole] = Field(
        default_factory=list
    )
    questions: list[MappingQuestion] = Field(
        default_factory=list
    )
