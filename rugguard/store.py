import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LabelStore:
    def __init__(self, db_path: str = "rugguard.db"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                pair TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                token0 TEXT NOT NULL,
                token1 TEXT NOT NULL,
                block INTEGER NOT NULL,
                detected_at TEXT NOT NULL,
                initial_price REAL NOT NULL,
                label TEXT,
                label_price REAL,
                labeled_at TEXT,
                features TEXT,
                score INTEGER
            )
            """
        )
        # 舊版資料庫沒有 features/score 欄位，補上
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(tokens)")}
        for col, typ in (("features", "TEXT"), ("score", "INTEGER")):
            if col not in cols:
                self.conn.execute(f"ALTER TABLE tokens ADD COLUMN {col} {typ}")
        self.conn.commit()

    def add_token(
        self,
        pair: str,
        token: str,
        block: int,
        initial_price: float,
        token0: str = "",
        token1: str = "",
        detected_at: datetime | None = None,
        features: dict | None = None,
        score: int | None = None,
    ) -> None:
        detected = detected_at.isoformat() if detected_at else _now()
        # 重啟後同一交易對會再被掃到，保留第一次的快照
        self.conn.execute(
            "INSERT OR IGNORE INTO tokens (pair, token, token0, token1, block, detected_at, initial_price, features, score)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pair, token, token0, token1, block, detected, initial_price,
             json.dumps(features) if features is not None else None, score),
        )
        self.conn.commit()

    def get_pending_tokens(
        self, min_age_hours: int, now: datetime | None = None
    ) -> list[sqlite3.Row]:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=min_age_hours)
        rows = self.conn.execute(
            "SELECT * FROM tokens WHERE label IS NULL AND detected_at <= ?",
            (cutoff.isoformat(),),
        ).fetchall()
        return list(rows)

    def update_label(self, pair: str, label: str, label_price: float) -> None:
        self.conn.execute(
            "UPDATE tokens SET label = ?, label_price = ?, labeled_at = ? WHERE pair = ?",
            (label, label_price, _now(), pair),
        )
        self.conn.commit()

    def get_token(self, pair: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tokens WHERE pair = ?", (pair,)).fetchone()

    def get_training_rows(self) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT * FROM tokens WHERE label IS NOT NULL ORDER BY detected_at"
        ).fetchall()
        return list(rows)

    def get_all_tokens(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM tokens ORDER BY detected_at DESC"))
