from pydantic import BaseModel


class ConnectorCapability(BaseModel):

    products: bool = False
    stock: bool = False
    price: bool = False
    orders: bool = False
    customers: bool = False
