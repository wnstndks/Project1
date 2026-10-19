from fastapi import APIRouter, Depends, Response, status

from app.db.models import AssetType
from app.deps import get_transaction_service
from app.schemas.transactions import TransactionIn, TransactionOut
from app.services.transactions import TransactionService

router = APIRouter(prefix="/transactions", tags=["transactions"])


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


@router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    tx_id: int, service: TransactionService = Depends(get_transaction_service)
) -> Response:
    service.delete(tx_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
