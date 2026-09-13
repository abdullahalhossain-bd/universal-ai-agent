"""
Async PostgreSQL connector using asyncpg.

`asyncpg` is an optional dependency — we import it lazily inside the
constructor so that this module can be imported even when asyncpg is
not installed (the rest of the project keeps working).
"""


class PostgreSQLConnector:
    """
    Async PostgreSQL connector constructed from individual connection
    parameters.
    """

    def __init__(
        self,
        host,
        port,
        username,
        password,
        database,
    ):
        self.config = {
            "host": host,
            "port": port,
            "user": username,
            "password": password,
            "database": database,
        }

    async def test_connection(self):
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError(
                "asyncpg is required for the async PostgreSQL connector. "
                "Install it with: pip install asyncpg"
            ) from exc

        connection = await asyncpg.connect(
            host=self.config["host"],
            port=self.config["port"],
            user=self.config["user"],
            password=self.config["password"],
            database=self.config["database"],
        )

        await connection.close()

        return True
