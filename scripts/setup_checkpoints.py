from dotenv import load_dotenv

from labpilot.api.checkpoints import lock_tables, open_saver
from labpilot.store import connect

load_dotenv()

with connect(autocommit=True) as conn:
    open_saver(conn).setup()
    lock_tables(conn)

print("chat tables are ready")
