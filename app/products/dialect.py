from abc import ABC, abstractmethod


class SQLDialect(ABC):
    @abstractmethod
    def quote(self, identifier: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def contains(self, column: str, parameter: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def equals(self, column: str, parameter: str) -> str:
        raise NotImplementedError


class PostgreSQLDialect(SQLDialect):
    def quote(self, identifier):
        return f'"{identifier}"'

    def contains(self, column, parameter):
        return f'"{column}" ILIKE :{parameter}'

    def equals(self, column, parameter):
        return f'"{column}" = :{parameter}'


class MySQLDialect(SQLDialect):
    def quote(self, identifier):
        return f"`{identifier}`"

    def contains(self, column, parameter):
        return f"`{column}` LIKE :{parameter}"

    def equals(self, column, parameter):
        return f"`{column}` = :{parameter}"
