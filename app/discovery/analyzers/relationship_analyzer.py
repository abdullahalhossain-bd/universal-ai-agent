import re

from app.discovery.models import (
    DatabaseSchema,
    RelationshipInfo,
)


class RelationshipAnalyzer:

    ID_PATTERN = re.compile(
        r"^(.+)_id$",
        re.IGNORECASE,
    )

    def analyze(
        self,
        schema: DatabaseSchema,
    ) -> list[RelationshipInfo]:

        relationships = []

        tables = {
            table.name: table
            for table in schema.tables
        }

        for table in schema.tables:

            for column in table.columns:

                match = self.ID_PATTERN.match(
                    column.name
                )

                if not match:
                    continue

                base_name = match.group(1).lower()

                for target_table in tables:

                    if target_table == table.name:
                        continue

                    normalized_table = (
                        target_table.lower()
                        .rstrip("s")
                    )

                    if base_name.rstrip("s") != normalized_table:
                        continue

                    target_columns = tables[
                        target_table
                    ].columns

                    target_id = next(
                        (
                            c
                            for c in target_columns
                            if c.name.lower()
                            in {
                                "id",
                                f"{base_name}_id",
                            }
                        ),
                        None,
                    )

                    if not target_id:
                        continue

                    relationships.append(
                        RelationshipInfo(
                            source_table=table.name,
                            source_column=column.name,
                            target_table=target_table,
                            target_column=target_id.name,
                            relationship_type=(
                                "inferred_foreign_key"
                            ),
                            confidence=0.82,
                            reason=(
                                "Column naming pattern "
                                "suggests a relationship"
                            ),
                        )
                    )

        return relationships
