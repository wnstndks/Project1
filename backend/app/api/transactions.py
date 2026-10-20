from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.data.assets import resolve_symbol
from app.db.models import AssetType
from app.deps import get_transaction_service
from app.schemas.transactions import ConvertCurrencyIn, TransactionIn, TransactionOut
from app.services.transactions import TransactionService

router = APIRouter(prefix="/transactions", tags=["transactions"])


class DeletedOut(BaseModel):
    deleted: int


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    symbol: str | None = None,
    asset_type: AssetType | None = None,
    service: TransactionService = Depends(get_transaction_service),
):
    txs = service.list_all(symbol, asset_type)
    fx = service.trade_date_fx(txs)
    return [TransactionOut.model_validate(t).model_copy(update={"usd_krw": fx[t.id]}) for t in txs]


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionIn, service: TransactionService = Depends(get_transaction_service)
):
    return service.create(data)


@router.put("/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: int, data: TransactionIn, service: TransactionService = Depends(get_transaction_service)
):
    return service.update(tx_id, data)


@router.post("/convert-currency", response_model=list[TransactionOut])
def convert_currency(
    body: ConvertCurrencyIn, service: TransactionService = Depends(get_transaction_service)
):
    return service.convert_currency(resolve_symbol(body.symbol), body.currency)


@router.delete("", response_model=DeletedOut)
def delete_all_transactions(
    confirm: Literal["all", "imports"],
    service: TransactionService = Depends(get_transaction_service),
):
    """Delete every transaction (`confirm=all`) or only screenshot imports (`imports`).
    The required parameter keeps a stray DELETE on the collection from wiping the ledger."""
    return {"deleted": service.delete_all(only_imported=confirm == "imports")}


@router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    tx_id: int, service: TransactionService = Depends(get_transaction_service)
) -> Response:
    service.delete(tx_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
