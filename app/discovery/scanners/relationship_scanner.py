from sqlalchemy import create_engine, inspect

from app.discovery.models import RelationshipInfo


class SQLRelationshipScanner:

    def __init__(self, database_url: str):
        self.database_url = database_url

    def scan(self) -> list[RelationshipInfo]:

        engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
        )

        inspector = inspect(engine)

        relationships: list[RelationshipInfo] = []

        for table in inspector.get_table_names():

            foreign_keys = inspector.get_foreign_keys(
                table
            )

            for fk in foreign_keys:

                referred_table = fk.get(
                    "referred_table"
                )

                constrained_columns = fk.get(
                    "constrained_columns",
                    [],
                )

                referred_columns = fk.get(
                    "referred_columns",
                    [],
                )

                if not referred_table:
                    continue

                for source_column, target_column in zip(
                    constrained_columns,
                    referred_columns,
                ):

                    relationships.append(
                        RelationshipInfo(
                            source_table=table,
                            source_column=source_column,
                            target_table=referred_table,
                            target_column=target_column,
                            relationship_type="foreign_key",
                            confidence=0.99,
                            reason="Database foreign-key constraint",
                        )
                    )

        engine.dispose()

        return relationships
