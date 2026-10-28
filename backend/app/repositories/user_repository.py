"""User repository — encapsulates all DB queries for users."""
from typing import List, Optional
from app.models.user import User


class UserRepository:
    def __init__(self):
        self._store: List[User] = []
        self._counter: int = 0

    def get_all(self) -> List[User]:
        return self._store

    def get_by_id(self, user_id: int) -> Optional[User]:
        return next((u for u in self._store if u.id == user_id), None)

    def get_by_email(self, email: str) -> Optional[User]:
        return next((u for u in self._store if u.email == email), None)

    def create(self, user: User) -> User:
        self._counter += 1
        user.id = self._counter
        self._store.append(user)
        return user


user_repo = UserRepository()
