"""CRUD wrappers for the estate-inventory tables.

Style mirrors `src/db/queries.py` — plain functions taking a sqlite3.Connection,
returning DTOs from `src/models/estate.py`. The mutation helpers commit before
returning so callers don't have to remember.

S2+ will introduce `services.audit_logger` to wrap these for NCAT-grade audit
trails. For now the bare CRUD is what the seed script and tests need.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields

from src.models.estate import (
    AccommodationBond,
    Account,
    DebtLiability,
    Investment,
    ManagedPerson,
    MotorVehicle,
    PrivateManager,
    RealEstate,
    SignificantPerson,
)


# ---------------------------------------------------------------------------
# Generic insert/list helpers (keep DRY)
# ---------------------------------------------------------------------------

def _insert(conn: sqlite3.Connection, table: str, dto, exclude: set[str] | None = None) -> int:
    """Insert dataclass `dto` into `table`, returning the new row id.

    `id` is always excluded. Additional fields can be excluded via `exclude`
    (useful for skipping auto-managed timestamps which the DB defaults).
    """
    exclude = (exclude or set()) | {"id"}
    data = {k: v for k, v in asdict(dto).items() if k not in exclude}
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def _update(
    conn: sqlite3.Connection,
    table: str,
    row_id: int,
    fields_dict: dict,
) -> None:
    """Generic UPDATE helper: sets `fields_dict` columns on the row with `row_id`.

    Always bumps `updated_at` to the current UTC timestamp. Commits before
    returning so callers don't need to.
    """
    # Marker key only; the SQL fragment is emitted by the updated_at branch
    # below, not from the value assigned here.
    fields_dict["updated_at"] = "datetime('now')"
    set_clauses = []
    params = []
    for col, val in fields_dict.items():
        if col == "updated_at":
            set_clauses.append(f"{col} = datetime('now')")
        else:
            set_clauses.append(f"{col} = ?")
            params.append(val)
    params.append(row_id)
    conn.execute(
        f"UPDATE {table} SET {', '.join(set_clauses)} WHERE id = ?",
        params,
    )
    conn.commit()


def _row_to_dto(row: sqlite3.Row, dto_class):
    """Convert a Row to a dataclass, dropping columns the dataclass doesn't define."""
    valid = {f.name for f in fields(dto_class)}
    kwargs = {k: row[k] for k in row.keys() if k in valid}
    return dto_class(**kwargs)


# ---------------------------------------------------------------------------
# managed_persons
# ---------------------------------------------------------------------------

def insert_managed_person(conn: sqlite3.Connection, mp: ManagedPerson) -> int:
    # interpreter_required is a bool in the DTO, int(0/1) in SQLite
    data = asdict(mp)
    data.pop("id", None)
    data["interpreter_required"] = int(data["interpreter_required"])
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO managed_persons ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def update_managed_person(conn: sqlite3.Connection, mp_id: int, mp: ManagedPerson) -> None:
    """Update all editable fields on a managed_persons row.

    interpreter_required is a bool in the DTO but stored as int(0/1) in SQLite.
    updated_at is bumped to NOW() by the generic _update helper.
    """
    data = asdict(mp)
    data.pop("id", None)
    data["interpreter_required"] = int(data["interpreter_required"])
    _update(conn, "managed_persons", mp_id, data)


def get_managed_person(conn: sqlite3.Connection, mp_id: int) -> ManagedPerson | None:
    row = conn.execute(
        "SELECT * FROM managed_persons WHERE id = ?", (mp_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dto(row, ManagedPerson)


def list_managed_persons(conn: sqlite3.Connection) -> list[ManagedPerson]:
    rows = conn.execute(
        "SELECT * FROM managed_persons ORDER BY surname, given_names"
    ).fetchall()
    return [_row_to_dto(r, ManagedPerson) for r in rows]


def bootstrap_managed_person_if_empty(
    conn: sqlite3.Connection,
    surname: str,
    given_names: str,
) -> int:
    """Insert a minimal ManagedPerson row only if the table is empty.

    Idempotent: if any row already exists, returns the id of the first row
    ordered by id without inserting. Used by the Identity view to ensure there
    is always a row to edit without duplicating data on re-runs.
    """
    row = conn.execute(
        "SELECT id FROM managed_persons ORDER BY id LIMIT 1"
    ).fetchone()
    if row is not None:
        return row["id"]
    return insert_managed_person(
        conn, ManagedPerson(surname=surname, given_names=given_names)
    )


# ---------------------------------------------------------------------------
# private_managers
# ---------------------------------------------------------------------------

def insert_private_manager(conn: sqlite3.Connection, pm: PrivateManager) -> int:
    return _insert(conn, "private_managers", pm)


def update_private_manager(conn: sqlite3.Connection, pm_id: int, pm: PrivateManager) -> None:
    """Update all editable fields on a private_managers row."""
    data = asdict(pm)
    data.pop("id", None)
    _update(conn, "private_managers", pm_id, data)


def list_private_managers(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[PrivateManager]:
    rows = conn.execute(
        "SELECT * FROM private_managers WHERE managed_person_id = ? ORDER BY surname, given_name",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, PrivateManager) for r in rows]


# ---------------------------------------------------------------------------
# significant_people
# ---------------------------------------------------------------------------

def insert_significant_person(conn: sqlite3.Connection, sp: SignificantPerson) -> int:
    return _insert(conn, "significant_people", sp)


def update_significant_person(
    conn: sqlite3.Connection, sp_id: int, sp: SignificantPerson
) -> None:
    """Update all editable fields on a significant_people row."""
    data = asdict(sp)
    data.pop("id", None)
    _update(conn, "significant_people", sp_id, data)


def get_significant_person(
    conn: sqlite3.Connection, sp_id: int
) -> SignificantPerson | None:
    """Fetch a single significant_people row by primary key."""
    row = conn.execute(
        "SELECT * FROM significant_people WHERE id = ?", (sp_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dto(row, SignificantPerson)


def list_significant_people(
    conn: sqlite3.Connection,
    managed_person_id: int,
    include_estranged: bool = True,
    include_deceased: bool = False,
) -> list[SignificantPerson]:
    statuses = ["active"]
    if include_estranged:
        statuses.append("estranged")
    if include_deceased:
        statuses.append("deceased")
    placeholders = ", ".join("?" for _ in statuses)
    rows = conn.execute(
        f"""
        SELECT * FROM significant_people
        WHERE managed_person_id = ?
          AND consultation_status IN ({placeholders})
        ORDER BY surname, given_name
        """,
        (managed_person_id, *statuses),
    ).fetchall()
    return [_row_to_dto(r, SignificantPerson) for r in rows]


def find_significant_person_by_name(
    conn: sqlite3.Connection,
    managed_person_id: int,
    given_name: str,
    surname: str,
) -> SignificantPerson | None:
    row = conn.execute(
        """
        SELECT * FROM significant_people
        WHERE managed_person_id = ?
          AND given_name = ?
          AND surname = ?
        """,
        (managed_person_id, given_name, surname),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dto(row, SignificantPerson)


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

def insert_account(conn: sqlite3.Connection, acc: Account) -> int:
    return _insert(conn, "accounts", acc)


def get_account_by_number(
    conn: sqlite3.Connection, account_number: str
) -> Account | None:
    row = conn.execute(
        "SELECT * FROM accounts WHERE account_number = ?", (account_number,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dto(row, Account)


def list_accounts(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[Account]:
    rows = conn.execute(
        "SELECT * FROM accounts WHERE managed_person_id = ? ORDER BY role_label, account_number",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, Account) for r in rows]


# ---------------------------------------------------------------------------
# real_estate / investments / motor_vehicles / accommodation_bonds / debts
# ---------------------------------------------------------------------------

def insert_real_estate(conn: sqlite3.Connection, re_: RealEstate) -> int:
    return _insert(conn, "real_estate", re_)


def list_real_estate(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[RealEstate]:
    rows = conn.execute(
        "SELECT * FROM real_estate WHERE managed_person_id = ?",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, RealEstate) for r in rows]


def insert_investment(conn: sqlite3.Connection, inv: Investment) -> int:
    return _insert(conn, "investments", inv)


def list_investments(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[Investment]:
    rows = conn.execute(
        "SELECT * FROM investments WHERE managed_person_id = ?",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, Investment) for r in rows]


def insert_motor_vehicle(conn: sqlite3.Connection, mv: MotorVehicle) -> int:
    return _insert(conn, "motor_vehicles", mv)


def list_motor_vehicles(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[MotorVehicle]:
    rows = conn.execute(
        "SELECT * FROM motor_vehicles WHERE managed_person_id = ?",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, MotorVehicle) for r in rows]


def insert_accommodation_bond(conn: sqlite3.Connection, bond: AccommodationBond) -> int:
    return _insert(conn, "accommodation_bonds", bond)


def list_accommodation_bonds(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[AccommodationBond]:
    rows = conn.execute(
        "SELECT * FROM accommodation_bonds WHERE managed_person_id = ?",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, AccommodationBond) for r in rows]


def insert_debt_liability(conn: sqlite3.Connection, debt: DebtLiability) -> int:
    return _insert(conn, "debts_liabilities", debt)


def list_debts_liabilities(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[DebtLiability]:
    rows = conn.execute(
        "SELECT * FROM debts_liabilities WHERE managed_person_id = ?",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, DebtLiability) for r in rows]


# ---------------------------------------------------------------------------
# Transactions ↔ account FK backfill
# ---------------------------------------------------------------------------

def backfill_transactions_account_id(conn: sqlite3.Connection) -> int:
    """Populate transactions.account_id from accounts.account_number.

    Idempotent — only updates rows where account_id is currently NULL and a
    matching account exists. Returns the number of rows updated.
    """
    cur = conn.execute(
        """
        UPDATE transactions
           SET account_id = (
               SELECT a.id FROM accounts a
                WHERE a.account_number = transactions.account_number
           )
         WHERE account_id IS NULL
           AND EXISTS (
               SELECT 1 FROM accounts a
                WHERE a.account_number = transactions.account_number
           )
        """
    )
    conn.commit()
    return cur.rowcount
