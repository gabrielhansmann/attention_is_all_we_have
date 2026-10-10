"""Sign in, sign out, and who am I. Only POST /auth/login is public."""
from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from app.auth import service
from app.config import get_settings

from .deps import User, bearer_token, get_conn
from .schemas import LoginIn, LoginOut, UserOut

public = APIRouter(prefix="/auth", tags=["auth"])
private = APIRouter(prefix="/auth", tags=["auth"])
Conn = Annotated[psycopg.Connection, Depends(get_conn)]

_BAD_LOGIN = "invalid email or password"


@public.post("/login", response_model=LoginOut)
def login(body: LoginIn, conn: Conn) -> LoginOut:
    """Exchange email and password for a session token. Every failure reads the same, so the response does not
    reveal which emails have accounts. Five wrong passwords lock the account for 15 minutes."""
    try:
        try:
            user = service.authenticate(conn, body.email, body.password)
        except service.InvalidCredentials:
            conn.commit()                       # the failed-attempt counter must persist
            raise HTTPException(status_code=401, detail=_BAD_LOGIN)
        except service.AccountLocked as e:
            conn.commit()
            raise HTTPException(status_code=429, detail="too many failed attempts, try again later",
                                headers={"Retry-After": str(e.retry_after_seconds)})
        token, expires = service.create_session(conn, user["id"], get_settings().session_hours)
        conn.commit()
    except psycopg.Error:
        conn.rollback()
        raise HTTPException(status_code=503, detail="database unavailable")
    return LoginOut(token=token, expires_at=expires, user=service.public_user(user))


@private.get("/me", response_model=UserOut)
def me(user: User) -> dict:
    return service.public_user(user)


@private.post("/logout", status_code=204)
def logout(user: User, token: Annotated[str, Depends(bearer_token)], conn: Conn) -> None:
    """Revoke the session this token belongs to."""
    service.revoke_token(conn, token)
    conn.commit()
