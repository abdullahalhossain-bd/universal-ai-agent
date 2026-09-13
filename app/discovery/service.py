from app.core.config import settings

from app.discovery.analyzers.relationship_analyzer import (
    RelationshipAnalyzer,
)

from app.discovery.analyzers.semantic_analyzer import (
    SemanticAnalyzer,
)

from app.discovery.analyzers.table_role_analyzer import (
    TableRoleAnalyzer,
)

from app.discovery.confidence import ConfidenceEngine

from app.discovery.models import DiscoveryResult

from app.discovery.scanners.relationship_scanner import (
    SQLRelationshipScanner,
)

from app.discovery.scanners.sample_scanner import (
    SQLSampleScanner,
)

from app.discovery.scanners.sql_scanner import (
    SQLSchemaScanner,
)


class DiscoveryService:

    def __init__(
        self,
        database_url: str | None = None,
    ):
        self.database_url = (
            database_url
            or settings.database_url
        )

    def discover(self) -> DiscoveryResult:

        # -------------------------
        # 1. Schema
        # -------------------------

        schema_scanner = SQLSchemaScanner(
            self.database_url
        )

        schema = schema_scanner.scan()

        # -------------------------
        # 2. Samples
        # -------------------------

        sample_scanner = SQLSampleScanner(
            self.database_url
        )

        samples = []

        for table in schema.tables:

            table_samples = sample_scanner.scan_table(
                table.name
            )

            samples.extend(table_samples)

        # -------------------------
        # 3. Semantic fields
        # -------------------------

        semantic_analyzer = SemanticAnalyzer()

        mappings = semantic_analyzer.analyze(
            samples
        )

        # -------------------------
        # 4. Explicit relationships
        # -------------------------

        relationship_scanner = (
            SQLRelationshipScanner(
                self.database_url
            )
        )

        explicit_relationships = (
            relationship_scanner.scan()
        )

        # -------------------------
        # 5. Inferred relationships
        # -------------------------

        relationship_analyzer = (
            RelationshipAnalyzer()
        )

        inferred_relationships = (
            relationship_analyzer.analyze(schema)
        )

        # -------------------------
        # 6. Merge relationships
        # -------------------------

        relationships = (
            explicit_relationships
            + inferred_relationships
        )

        # -------------------------
        # 7. Table roles
        # -------------------------

        table_role_analyzer = (
            TableRoleAnalyzer()
        )

        table_roles = (
            table_role_analyzer.analyze(schema)
        )

        # -------------------------
        # 8. Confidence engine
        # -------------------------

        confidence_engine = ConfidenceEngine()

        mappings, questions = confidence_engine.process(
            mappings
        )

        return DiscoveryResult(
            db_schema=schema,
            candidates=mappings,
            relationships=relationships,
            table_roles=table_roles,
            questions=questions,
        )
