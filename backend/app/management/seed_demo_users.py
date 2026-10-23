"""Create the two v1 local demonstration accounts after running migrations."""

from app.application.security import hash_password
from app.core.db import SessionLocal
from app.infrastructure.persistence.models import User

DEMO_USERS = (
    ("submitter@example.local", "演示提交者", "demo-submitter"),
    ("reviewer@example.local", "演示审核者", "demo-reviewer"),
)


def main() -> None:
    with SessionLocal() as session:
        for email, display_name, password in DEMO_USERS:
            if session.query(User).filter_by(email=email).one_or_none() is None:
                session.add(User(email=email, display_name=display_name, password_hash=hash_password(password)))
        session.commit()
    print("演示账户已就绪：submitter@example.local 与 reviewer@example.local")


if __name__ == "__main__":
    main()
