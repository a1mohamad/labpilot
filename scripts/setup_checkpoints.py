from dotenv import load_dotenv

from labpilot.api.checkpoints import open_saver
from labpilot.store import connect

load_dotenv()

with connect(autocommit=True) as conn:
    open_saver(conn).setup()

print("chat tables are ready")
