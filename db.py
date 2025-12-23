import os
import json
import sqlite3
from typing import Dict, List, Optional

DB_PATH = r"C:\Users\TimK\OneDrive\Documents\Work\CI\APScans\invoice_system.db"
SUPPLIER_JSON = (
    r"C:\Users\TimK\OneDrive\Documents\Work\CI\APScans\supplier_profiles.json"
)
PO_DETECTION_JSON = (
    r"C:\Users\TimK\OneDrive\Documents\Work\CI\APScans\po_detection_profiles.json"
)


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Classification samples table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_samples (
            supplier_code TEXT,
            sample_text TEXT
        )
        """
    )
    # PO detection profiles table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS po_profiles (
            supplier_code TEXT PRIMARY KEY,
            po_patterns TEXT,
            amount_patterns TEXT
        )
        """
    )
    # Supplier profiles table - identifies suppliers from filename
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_profiles (
            supplier_code TEXT PRIMARY KEY,
            name TEXT,
            description TEXT
        )
        """
    )
    # Results table - tracks extracted PO/amount data
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            file_path TEXT,
            supplier_code TEXT,
            po_number TEXT,
            amount REAL,
            check_no TEXT,
            receiver_id TEXT,
            invoice_no TEXT,
            human_field TEXT DEFAULT 'N',
            status TEXT DEFAULT 'pending',
            extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_code) REFERENCES supplier_profiles(supplier_code)
        )
        """
    )
    # Progress tracking table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_progress (
            filename TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            processed_date TIMESTAMP,
            notes TEXT
        )
        """
    )

    # Add missing columns to existing tables (migration support)
    try:
        cur.execute("ALTER TABLE extraction_results ADD COLUMN invoice_no TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()


def get_classification_profiles(db_path: str = DB_PATH) -> Dict[str, List[str]]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT supplier_code, sample_text FROM classification_samples")
    rows = cur.fetchall()
    conn.close()
    profiles: Dict[str, List[str]] = {}
    for supplier, text in rows:
        profiles.setdefault(supplier, []).append(text)
    return profiles


def save_classification_profiles(
    profiles: Dict[str, List[str]], db_path: str = DB_PATH
):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Simple replace strategy: delete all and re-insert
    cur.execute("DELETE FROM classification_samples")
    for supplier, texts in profiles.items():
        for t in texts:
            cur.execute(
                "INSERT INTO classification_samples (supplier_code, sample_text) VALUES (?, ?)",
                (supplier, t),
            )
    conn.commit()
    conn.close()


def add_classification_samples(
    supplier: str, samples: List[str], db_path: str = DB_PATH
):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for t in samples:
        cur.execute(
            "INSERT INTO classification_samples (supplier_code, sample_text) VALUES (?, ?)",
            (supplier, t),
        )
    conn.commit()
    conn.close()


def get_po_profiles(db_path: str = DB_PATH) -> Dict[str, Dict]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT supplier_code, po_patterns, amount_patterns FROM po_profiles")
    rows = cur.fetchall()
    conn.close()
    profiles: Dict[str, Dict] = {}
    for supplier, po_json, amt_json in rows:
        try:
            po_list = json.loads(po_json) if po_json else []
        except Exception:
            po_list = []
        try:
            amt_list = json.loads(amt_json) if amt_json else []
        except Exception:
            amt_list = []
        profiles[supplier] = {
            "po_patterns": po_list,
            "amount_patterns": amt_list,
        }
    return profiles


def save_po_profiles(profiles: Dict[str, Dict], db_path: str = DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for supplier, profile in profiles.items():
        po_patterns = json.dumps(profile.get("po_patterns", []))
        amount_patterns = json.dumps(profile.get("amount_patterns", []))
        cur.execute(
            "INSERT OR REPLACE INTO po_profiles (supplier_code, po_patterns, amount_patterns) VALUES (?, ?, ?)",
            (supplier, po_patterns, amount_patterns),
        )
    conn.commit()
    conn.close()


def add_supplier_profile(
    supplier_code: str, name: str = "", description: str = "", db_path: str = DB_PATH
):
    """Add or update a supplier profile."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO supplier_profiles (supplier_code, name, description) VALUES (?, ?, ?)",
        (supplier_code, name, description),
    )
    conn.commit()
    conn.close()


def get_supplier_profile(supplier_code: str, db_path: str = DB_PATH) -> Optional[Dict]:
    """Get a supplier profile by code."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT supplier_code, name, description FROM supplier_profiles WHERE supplier_code = ?",
        (supplier_code,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "supplier_code": row[0],
            "name": row[1],
            "description": row[2],
        }
    return None


def get_all_supplier_profiles(db_path: str = DB_PATH) -> List[Dict]:
    """Get all supplier profiles."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT supplier_code, name, description FROM supplier_profiles")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "supplier_code": row[0],
            "name": row[1],
            "description": row[2],
        }
        for row in rows
    ]


def save_extraction_result(
    filename: str,
    file_path: str,
    supplier_code: Optional[str] = None,
    po_number: Optional[str] = None,
    amount: Optional[float] = None,
    check_no: Optional[str] = None,
    receiver_id: Optional[str] = None,
    invoice_no: Optional[str] = None,
    human_field: str = "N",
    status: str = "pending",
    db_path: str = DB_PATH,
):
    """Save an extraction result to the database."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO extraction_results 
        (filename, file_path, supplier_code, po_number, amount, check_no, receiver_id, invoice_no, human_field, status, extraction_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            filename,
            file_path,
            supplier_code,
            po_number,
            amount,
            check_no,
            receiver_id,
            invoice_no,
            human_field,
            status,
        ),
    )
    conn.commit()
    conn.close()


def get_extraction_result(filename: str, db_path: str = DB_PATH) -> Optional[Dict]:
    """Get an extraction result by filename."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, filename, file_path, supplier_code, po_number, amount, check_no, 
                 receiver_id, human_field, status, extraction_date FROM extraction_results WHERE filename = ?""",
        (filename,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "filename": row[1],
            "file_path": row[2],
            "supplier_code": row[3],
            "po_number": row[4],
            "amount": row[5],
            "check_no": row[6],
            "receiver_id": row[7],
            "human_field": row[8],
            "status": row[9],
            "extraction_date": row[10],
        }
    return None


def get_unprocessed_files(db_path: str = DB_PATH) -> List[str]:
    """Get list of files not yet processed."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT filename FROM extraction_results WHERE status = 'pending' ORDER BY filename"
    )
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def update_extraction_status(
    filename: str, status: str, notes: str = "", db_path: str = DB_PATH
):
    """Update processing progress for a file."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO processing_progress (filename, status, processed_date, notes) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
        (filename, status, notes),
    )
    conn.commit()
    conn.close()


def migrate_jsons_to_db(
    db_path: str = DB_PATH,
    supplier_json: str = SUPPLIER_JSON,
    po_json: str = PO_DETECTION_JSON,
):
    init_db(db_path)
    # Migrate supplier_profiles.json
    if os.path.exists(supplier_json):
        try:
            with open(supplier_json, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    # Insert into classification_samples
                    conn = sqlite3.connect(db_path)
                    cur = conn.cursor()
                    for supplier, texts in data.items():
                        for t in texts:
                            cur.execute(
                                "INSERT INTO classification_samples (supplier_code, sample_text) VALUES (?, ?)",
                                (supplier, t),
                            )
                    conn.commit()
                    conn.close()
        except Exception:
            pass

    # Migrate po_detection_profiles.json
    if os.path.exists(po_json):
        try:
            with open(po_json, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    conn = sqlite3.connect(db_path)
                    cur = conn.cursor()
                    for supplier, profile in data.items():
                        po_patterns = json.dumps(profile.get("po_patterns", []))
                        amount_patterns = json.dumps(profile.get("amount_patterns", []))
                        cur.execute(
                            "INSERT OR REPLACE INTO po_profiles (supplier_code, po_patterns, amount_patterns) VALUES (?, ?, ?)",
                            (supplier, po_patterns, amount_patterns),
                        )
                    conn.commit()
                    conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    # Quick test: initialize DB
    init_db()
