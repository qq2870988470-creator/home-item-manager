import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

url = URL.create("postgresql+psycopg", username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"], host=os.getenv("POSTGRES_HOST", "postgres"),
    port=int(os.getenv("POSTGRES_PORT", "5432")), database=os.environ["POSTGRES_DB"])
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
Session = sessionmaker(engine, expire_on_commit=False)
def get_db():
    with Session() as session:
        yield session
