"""
Password Hasher
===============
Provides password hashing and verification using passlib with bcrypt.
This is an infrastructure service — business logic should not depend on it directly.
"""

from passlib.context import CryptContext

# bcrypt context with automatic salt generation
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plain-text password."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches the *hashed_password*."""
    return _pwd_context.verify(plain_password, hashed_password)
