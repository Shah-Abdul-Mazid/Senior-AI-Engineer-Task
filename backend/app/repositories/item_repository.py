"""Item repository — encapsulates all DB queries for items."""
from typing import List, Optional
from app.models.item import Item


class ItemRepository:
    def __init__(self):
        self._store: List[Item] = []
        self._counter: int = 0

    def get_all(self) -> List[Item]:
        return self._store

    def get_by_id(self, item_id: int) -> Optional[Item]:
        return next((i for i in self._store if i.id == item_id), None)

    def create(self, item: Item) -> Item:
        self._counter += 1
        item.id = self._counter
        self._store.append(item)
        return item


item_repo = ItemRepository()
