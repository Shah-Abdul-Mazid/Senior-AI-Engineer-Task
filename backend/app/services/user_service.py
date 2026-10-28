from typing import List, Optional
from app.schemas.user import UserCreate, UserResponse
from app.models.user import User
from app.repositories.user_repository import user_repo
from app.core.security import get_password_hash


class UserService:
    def list_users(self) -> List[UserResponse]:
        return [UserResponse(id=u.id, name=u.name, email=u.email) for u in user_repo.get_all()]

    def get_user(self, user_id: int) -> Optional[UserResponse]:
        user = user_repo.get_by_id(user_id)
        if not user:
            return None
        return UserResponse(id=user.id, name=user.name, email=user.email)

    def create_user(self, data: UserCreate) -> UserResponse:
        if user_repo.get_by_email(data.email):
            raise ValueError(f"User with email '{data.email}' already exists.")
        hashed = get_password_hash(data.password)
        user = User(name=data.name, email=data.email, hashed_password=hashed)
        saved = user_repo.create(user)
        return UserResponse(id=saved.id, name=saved.name, email=saved.email)


user_service = UserService()
