from decimal import Decimal

from sqlalchemy import MetaData, String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class DecimalText(TypeDecorator[Decimal]):
    """Stores Decimal values as TEXT so SQLite keeps them exact.

    SQLite has no native decimal type and SQLAlchemy's Numeric would round-trip
    through float, which breaks money and crypto quantity math.
    """

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)
