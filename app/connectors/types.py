from enum import Enum


class ConnectorType(str, Enum):

    MYSQL = "mysql"

    POSTGRES = "postgres"

    REST = "rest"

    GRAPHQL = "graphql"

    JSON = "json"

    CUSTOM = "custom"
