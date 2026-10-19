from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# Exact Decimal inside the app, plain JSON number on the wire so the frontend can do math.
# float keeps ~15 significant digits, enough for 8-decimal coin quantities and prices.
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
