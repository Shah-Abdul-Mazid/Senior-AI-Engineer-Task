from fastapi import APIRouter, HTTPException, status
from app.schemas.item import ItemCreate, ItemResponse
from app.services.item_service import item_service

router = APIRouter(prefix="/items", tags=["Items"])


@router.get("/", response_model=list[ItemResponse])
async def read_items():
    return item_service.list_items()


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item_in: ItemCreate):
    return item_service.create_item(item_in)


@router.get("/{item_id}", response_model=ItemResponse)
async def read_item(item_id: int):
    item = item_service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
