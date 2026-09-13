from enum import Enum


class AnswerType(str, Enum):

    TEXT = "text"

    PRODUCT_LIST = "product_list"

    PRODUCT_DETAIL = "product_detail"

    MIXED = "mixed"

    NO_RESULT = "no_result"
