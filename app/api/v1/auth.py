from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    get_database,
)
from app.core.security import create_access_token
from app.schemas.auth import (
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    register_patient,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: UserRegisterRequest,
    db: Session = Depends(get_database),
):
    try:
        user = register_patient(db, request)
        return user
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_database),
):
    user = authenticate_user(
        db,
        form_data.username,
        form_data.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user=Depends(get_current_user),
):
    return current_user