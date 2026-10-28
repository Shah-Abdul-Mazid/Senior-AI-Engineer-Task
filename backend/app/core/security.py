import hashlib
import hmac


def get_password_hash(password: str) -> str:
    salt = "fastapi_struct_salt"
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hmac.compare_digest(get_password_hash(plain_password), hashed_password)
