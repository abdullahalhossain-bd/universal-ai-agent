from sqlalchemy import create_engine, inspect

from app.discovery.models import (
    ColumnInfo,
    DatabaseSchema,
    TableInfo,
)


class SQLSchemaScanner:

    def __init__(self, database_url: str):
        self.database_url = database_url

    def scan(self) -> DatabaseSchema:
        engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
        )

        inspector = inspect(engine)

        tables: list[TableInfo] = []

        for table_name in inspector.get_table_names():

            columns = []

            for column in inspector.get_columns(table_name):
                columns.append(
                    ColumnInfo(
                        name=column["name"],
                        data_type=str(column["type"]),
                        nullable=column.get("nullable", True),
                    )
                )

            tables.append(
                TableInfo(
                    name=table_name,
                    columns=columns,
                )
            )

        engine.dispose()

        return DatabaseSchema(tables=tables)
