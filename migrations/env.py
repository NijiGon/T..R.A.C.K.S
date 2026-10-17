from logging.config import fileConfig

from alembic import context

from krl import db
from krl.config import load_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run `alembic upgrade head` against the database.")

engine = db.make_engine(load_settings())
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
