from pydantic import BaseModel


class ColumnInfo(BaseModel):

    name: str
    data_type: str

    nullable: bool = True

    is_primary_key: bool = False


class TableInfo(BaseModel):

    name: str

    columns: list[ColumnInfo] = []


class DatabaseSchema(BaseModel):

    database_type: str

    tables: list[TableInfo] = []
