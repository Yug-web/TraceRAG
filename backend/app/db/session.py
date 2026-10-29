from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_session_factory(url: str):
    engine = create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    return engine, sessionmaker(engine, expire_on_commit=False)
