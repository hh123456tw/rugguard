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
        # 蒐集程式與回補程式會同時寫入，等鎖久一點
        self.conn = sqlite3.connect(db_path, timeout=60)
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
                score INTEGER,
                buy_score INTEGER
            )
            """
        )
        # 舊版資料庫沒有 features/score/buy_score 欄位，補上
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(tokens)")}
        for col, typ in (("features", "TEXT"), ("score", "INTEGER"), ("buy_score", "INTEGER")):
            if col not in cols:
                self.conn.execute(f"ALTER TABLE tokens ADD COLUMN {col} {typ}")
        # 進場後 24h 內每輪取樣的價格與兩邊儲備（分辨撤池 vs 倒貨）
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                pair TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                opened_block INTEGER NOT NULL,
                opened_at TEXT NOT NULL,
                entry_price REAL NOT NULL,
                cost REAL NOT NULL,
                expires_block INTEGER NOT NULL,
                closed_block INTEGER,
                closed_at TEXT,
                reason TEXT,
                net_return REAL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backfill_chunks (
                pair TEXT NOT NULL,
                start_block INTEGER NOT NULL,
                PRIMARY KEY (pair, start_block)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_path (
                pair TEXT NOT NULL,
                block INTEGER NOT NULL,
                price REAL NOT NULL,
                reserve_alt REAL NOT NULL,
                reserve_bnb REAL NOT NULL,
                PRIMARY KEY (pair, block)
            )
            """
        )
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
        buy_score: int | None = None,
    ) -> None:
        detected = detected_at.isoformat() if detected_at else _now()
        # 重啟後同一交易對會再被掃到，保留第一次的快照
        self.conn.execute(
            "INSERT OR IGNORE INTO tokens"
            " (pair, token, token0, token1, block, detected_at, initial_price, features, score, buy_score)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pair, token, token0, token1, block, detected, initial_price,
             json.dumps(features) if features is not None else None, score, buy_score),
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

    def set_label(self, pair: str, label: str) -> None:
        self.conn.execute("UPDATE tokens SET label = ? WHERE pair = ?", (label, pair))
        self.conn.commit()

    def get_tracking_pairs(self, hours: int = 24, now: datetime | None = None) -> list[sqlite3.Row]:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
        return list(self.conn.execute(
            "SELECT pair, token0, token1 FROM tokens WHERE initial_price > 0 AND detected_at >= ?",
            (cutoff.isoformat(),),
        ))

    def add_path_points(self, points: list[tuple]) -> None:
        # 交易對地址統一存小寫，方便和 tokens.pair 對照時用 lower()
        self.conn.executemany(
            "INSERT OR IGNORE INTO price_path (pair, block, price, reserve_alt, reserve_bnb) VALUES (?, ?, ?, ?, ?)",
            points,
        )
        self.conn.commit()

    def get_path(self, pair: str) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT block, price, reserve_alt, reserve_bnb FROM price_path WHERE pair = ? ORDER BY block",
            (pair.lower(),),
        ))

    def update_features(self, pair: str, features: dict) -> None:
        self.conn.execute("UPDATE tokens SET features = ? WHERE pair = ?", (json.dumps(features), pair))
        self.conn.commit()

    def get_done_chunks(self, pair: str) -> set[int]:
        return {r["start_block"] for r in self.conn.execute(
            "SELECT start_block FROM backfill_chunks WHERE pair = ?", (pair,))}

    def mark_chunk_done(self, pair: str, start_block: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO backfill_chunks VALUES (?, ?)", (pair, start_block))
        self.conn.commit()

    def creator_history(self, creator: str) -> tuple[int, int]:
        """同一個創建者之前在資料庫裡的 (代幣數, rug 數)。只看已存的列，沒有未來資訊。"""
        if not creator:
            return 0, 0
        pattern = '%"creator_address": "' + creator.lower() + '"%'
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(label = 'rug'), 0) FROM tokens WHERE lower(features) LIKE ?",
            (pattern,),
        ).fetchone()
        return int(row[0]), int(row[1])

    def open_position(self, pair: str, token: str, block: int, price: float, cost: float, expires_block: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO positions (pair, token, opened_block, opened_at, entry_price, cost, expires_block)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pair, token, block, _now(), price, cost, expires_block),
        )
        self.conn.commit()

    def get_open_positions(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM positions WHERE closed_block IS NULL"))

    def close_position(self, pair: str, block: int, reason: str, net_return: float) -> None:
        self.conn.execute(
            "UPDATE positions SET closed_block = ?, closed_at = ?, reason = ?, net_return = ? WHERE pair = ?",
            (block, _now(), reason, net_return, pair),
        )
        self.conn.commit()

    def get_positions(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM positions ORDER BY opened_at DESC"))

    def get_token(self, pair: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tokens WHERE pair = ?", (pair,)).fetchone()

    def get_training_rows(self) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT * FROM tokens WHERE label IS NOT NULL ORDER BY detected_at"
        ).fetchall()
        return list(rows)

    def get_all_tokens(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM tokens ORDER BY detected_at DESC"))
