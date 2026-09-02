from sqlalchemy import create_engine, inspect, text

from app.discovery.models import ColumnSample


class SQLSampleScanner:

    def __init__(self, database_url: str):
        self.database_url = database_url

    def scan_table(
        self,
        table_name: str,
        limit: int = 20,
    ) -> list[ColumnSample]:

        engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
        )

        inspector = inspect(engine)

        columns = inspector.get_columns(table_name)

        column_names = [
            column["name"]
            for column in columns
        ]

        if not column_names:
            engine.dispose()
            return []

        # Quote identifiers safely using SQLAlchemy identifier preparation.
        preparer = engine.dialect.identifier_preparer

        quoted_table = preparer.quote(table_name)

        quoted_columns = ", ".join(
            preparer.quote(name)
            for name in column_names
        )

        query = text(
            f"""
            SELECT {quoted_columns}
            FROM {quoted_table}
            LIMIT :limit
            """
        )

        with engine.connect() as conn:
            rows = conn.execute(
                query,
                {"limit": limit},
            ).mappings().all()

        result = []

        for column in columns:

            name = column["name"]

            values = [
                str(row[name])
                for row in rows
                if row[name] is not None
            ]

            null_count = sum(
                1
                for row in rows
                if row[name] is None
            )

            unique_count = len(set(values))

            result.append(
                ColumnSample(
                    table=table_name,
                    column=name,
                    data_type=str(column["type"]),
                    samples=values[:10],
                    null_count=null_count,
                    unique_count=unique_count,
                )
            )

        engine.dispose()

        return result
