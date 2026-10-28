from typing import List, Optional
from app.schemas.item import ItemCreate, ItemResponse
from app.models.item import Item
from app.repositories.item_repository import item_repo


class ItemService:
    def list_items(self) -> List[ItemResponse]:
        return [
            ItemResponse(id=i.id, title=i.title, description=i.description, price=i.price)
            for i in item_repo.get_all()
        ]

    def get_item(self, item_id: int) -> Optional[ItemResponse]:
        item = item_repo.get_by_id(item_id)
        if not item:
            return None
        return ItemResponse(id=item.id, title=item.title, description=item.description, price=item.price)

    def create_item(self, data: ItemCreate) -> ItemResponse:
        item = Item(title=data.title, description=data.description, price=data.price)
        saved = item_repo.create(item)
        return ItemResponse(id=saved.id, title=saved.title, description=saved.description, price=saved.price)


item_service = ItemService()
