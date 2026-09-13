class SchemaScanner:

    async def scan(self, connector):

        tables = await connector.list_tables()

        result = []

        for table in tables:

            columns = await (
                connector.list_columns(
                    table
                )
            )

            result.append({
                "table": table,
                "columns": columns,
            })

        return result
