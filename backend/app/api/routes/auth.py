from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.schemas import CurrentUserResponse, LoginRequest, RegisterRequest, TokenResponse
from app.application.security import create_access_token, hash_password, verify_password
from app.infrastructure.persistence.models import User
from app.infrastructure.business_ownership import require_python_identity
from app.domain.errors import DomainError

router = APIRouter(prefix="/auth")


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(id=user.id, display_name=user.display_name, email=user.email)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    user = session.query(User).filter(User.email == payload.email).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    try:
        require_python_identity(session)
    except DomainError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": error.code, "message": error.message}) from None
    if session.query(User.id).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录")

    user = User(email=payload.email, display_name=payload.display_name, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录") from None
    return TokenResponse(access_token=create_access_token(user.id))
