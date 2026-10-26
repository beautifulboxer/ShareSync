""" ShareSync-integrated deadlock detection and safe recovery """

from datetime import date, timedelta
from typing import Any

# Name of the MySQL advisory lock that serialises detection/recovery so two
# students clicking at the same time cannot rebuild the OS tables together.
_LOCK_NAME = "sharesync_os_deadlock"

# Safety limit for the "recover until no cycle remains" loop.
_MAX_RECOVERY_ROUNDS = 20

# If True, only a student who is part of the deadlock cycle may run recovery.
# Left False so any logged-in student can demonstrate the feature.
RESTRICT_RECOVERY_TO_PARTICIPANTS = False


def _normalize(value):
    return " ".join((value or "").split()).casefold()


def ensure_os_tracking_schema(connection):
    """Create or migrate the OS tracking tables."""
    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS os_resources (
                resource_id INT AUTO_INCREMENT PRIMARY KEY,
                resource_name VARCHAR(150) NOT NULL,
                owner_student_id INT NULL,
                sharer_id INT NULL,
                share_item_key VARCHAR(300) NULL,
                active_transaction_id INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_os_resource_owner
                    FOREIGN KEY (owner_student_id)
                    REFERENCES students(student_id) ON DELETE SET NULL,
                CONSTRAINT fk_os_resource_sharer
                    FOREIGN KEY (sharer_id)
                    REFERENCES students(student_id) ON DELETE SET NULL
            ) ENGINE=InnoDB
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS os_resource_waits (
                wait_id INT AUTO_INCREMENT PRIMARY KEY,
                waiting_student_id INT NOT NULL,
                resource_id INT NOT NULL,
                request_id INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_os_wait_student_resource
                    (waiting_student_id, resource_id),
                CONSTRAINT fk_os_wait_student
                    FOREIGN KEY (waiting_student_id)
                    REFERENCES students(student_id) ON DELETE CASCADE,
                CONSTRAINT fk_os_wait_resource
                    FOREIGN KEY (resource_id)
                    REFERENCES os_resources(resource_id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)

        # Persist OS-simulation releases across synchronization.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS os_recovery_releases (
                sharer_id INT NOT NULL,
                share_item_key VARCHAR(300) NOT NULL,
                released_transaction_id INT NOT NULL,
                recovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (sharer_id, share_item_key)
            ) ENGINE=InnoDB
        """)

        # Migrate older OS tracking tables.
        for column, definition in (
            ("sharer_id", "INT NULL"),
            ("share_item_key", "VARCHAR(300) NULL"),
            ("active_transaction_id", "INT NULL"),
        ):
            cursor.execute(
                f"SHOW COLUMNS FROM os_resources LIKE '{column}'"
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE os_resources ADD COLUMN {column} {definition}"
                )

        cursor.execute(
            "SHOW COLUMNS FROM os_resource_waits LIKE 'request_id'"
        )
        if cursor.fetchone() is None:
            cursor.execute("""
                ALTER TABLE os_resource_waits
                ADD COLUMN request_id INT NULL
            """)

        cursor.execute("SHOW INDEX FROM os_resources")
        indexes = {row[2] for row in cursor.fetchall()}
        if "uq_os_resource_source" not in indexes:
            cursor.execute("""
                CREATE UNIQUE INDEX uq_os_resource_source
                ON os_resources (sharer_id, share_item_key)
            """)

        connection.commit()
    finally:
        cursor.close()


def sync_os_deadlock_from_sharesync (connection):
    """
    Synchronize ShareSync items and pending requests with the OS model.
    Ownership always mirrors the real ACTIVE transactions.
    """
    ensure_os_tracking_schema(connection)
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT offer_id, student_id, resource_name, share_item_key
            FROM resource_offers
            WHERE student_id IS NOT NULL
            ORDER BY offer_id
        """)
        offers = cursor.fetchall()

        cursor.execute("""
            SELECT transaction_id, offer_id, borrower_id
            FROM transactions
            WHERE transaction_status = 'ACTIVE'
            ORDER BY transaction_id
        """)
        active_transactions = cursor.fetchall()

        cursor.execute("""
            SELECT request_id, student_id, resource_name
            FROM student_resource_requests
            WHERE request_status = 'OPEN'
            ORDER BY request_id
        """)
        open_requests = cursor.fetchall()

        resources_by_key = {}
        key_by_offer_id = {}

        for offer in offers:
            sharer_id = int(offer["student_id"])
            item_key = (
                offer["share_item_key"]
                or _normalize(offer["resource_name"])
            )
            key = (sharer_id, item_key)
            key_by_offer_id[int(offer["offer_id"])] = key

            resources_by_key.setdefault(key, {
                "sharer_id": sharer_id,
                "share_item_key": item_key,
                "resource_name": offer["resource_name"],
                "owner_student_id": sharer_id,
                "active_transaction_id": None,
            })

        # Active loans normally assign the OS-model resource to the borrower.
        for transaction in active_transactions:
            key = key_by_offer_id.get(int(transaction["offer_id"]))
            if key is None:
                continue

            tracked = resources_by_key[key]
            tracked["owner_student_id"] = int(
                transaction["borrower_id"]
            )
            tracked["active_transaction_id"] = int(
                transaction["transaction_id"]
            )

        # Recovery now ends the victim's real loan, so the old simulated
        # release overrides are obsolete. Clear any legacy rows.
        cursor.execute("DELETE FROM os_recovery_releases")

        # Rebuild waits and remove obsolete simulation-only rows.
        cursor.execute("DELETE FROM os_resource_waits")
        cursor.execute("""
            DELETE FROM os_resources
            WHERE sharer_id IS NULL OR share_item_key IS NULL
        """)

        for tracked in resources_by_key.values():
            cursor.execute("""
                INSERT INTO os_resources
                    (resource_name, owner_student_id, sharer_id,
                     share_item_key, active_transaction_id)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    resource_name = VALUES(resource_name),
                    owner_student_id = VALUES(owner_student_id),
                    active_transaction_id = VALUES(active_transaction_id)
            """, (
                tracked["resource_name"],
                tracked["owner_student_id"],
                tracked["sharer_id"],
                tracked["share_item_key"],
                tracked["active_transaction_id"],
            ))

        cursor.execute("""
            SELECT resource_id, sharer_id, share_item_key
            FROM os_resources
            WHERE sharer_id IS NOT NULL
              AND share_item_key IS NOT NULL
        """)
        for row in cursor.fetchall():
            key = (int(row["sharer_id"]), row["share_item_key"])
            if key not in resources_by_key:
                cursor.execute("""
                    DELETE FROM os_resources
                    WHERE resource_id = %s
                """, (row["resource_id"],))

        cursor.execute("""
            SELECT resource_id, resource_name, owner_student_id,
                   sharer_id, share_item_key, active_transaction_id
            FROM os_resources
            WHERE sharer_id IS NOT NULL
              AND share_item_key IS NOT NULL
            ORDER BY resource_id
        """)
        current_resources = cursor.fetchall()

        by_name = {}
        for resource in current_resources:
            by_name.setdefault(
                _normalize(resource["resource_name"]), []
            ).append(resource)

        # A request waits only if matching items exist and all are allocated.
        for req in open_requests:
            requester_id = int(req["student_id"])
            matches = by_name.get(_normalize(req["resource_name"]), [])

            if not matches:
                continue

            if any(
                item["active_transaction_id"] is None
                for item in matches
            ):
                continue

            for item in matches:
                owner_id = item["owner_student_id"]

                if owner_id is None or int(owner_id) == requester_id:
                    continue

                cursor.execute("""
                    INSERT IGNORE INTO os_resource_waits
                        (waiting_student_id, resource_id, request_id)
                    VALUES (%s, %s, %s)
                """, (
                    requester_id,
                    item["resource_id"],
                    req["request_id"],
                ))

        connection.commit()

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _load_state (connection) -> dict[str, Any]:
    """Read resources, waits, and the wait-for graph."""
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT r.resource_id, r.resource_name,
                   r.owner_student_id, r.sharer_id,
                   r.share_item_key, r.active_transaction_id,
                   s.student_name AS owner_name
            FROM os_resources r
            LEFT JOIN students s
                ON s.student_id = r.owner_student_id
            ORDER BY r.resource_id
        """)
        resources = cursor.fetchall()

        cursor.execute("""
            SELECT w.wait_id, w.request_id, w.waiting_student_id,
                   waiting.student_name AS waiting_name,
                   w.resource_id, r.resource_name,
                   r.owner_student_id,
                   owner.student_name AS owner_name
            FROM os_resource_waits w
            JOIN students waiting
                ON waiting.student_id = w.waiting_student_id
            JOIN os_resources r
                ON r.resource_id = w.resource_id
            LEFT JOIN students owner
                ON owner.student_id = r.owner_student_id
            ORDER BY w.wait_id
        """)
        waits = cursor.fetchall()

        graph = {}
        names = {}

        for resource in resources:
            owner_id = resource["owner_student_id"]
            if owner_id is not None:
                owner_id = int(owner_id)
                graph.setdefault(owner_id, [])
                names[owner_id] = (
                    resource["owner_name"] or f"Student {owner_id}"
                )

        for wait in waits:
            waiter = int(wait["waiting_student_id"])
            graph.setdefault(waiter, [])
            names[waiter] = (
                wait["waiting_name"] or f"Student {waiter}"
            )

            owner_id = wait["owner_student_id"]
            if owner_id is not None and int(owner_id) != waiter:
                owner_id = int(owner_id)
                graph[waiter].append(owner_id)
                graph.setdefault(owner_id, [])
                names[owner_id] = (
                    wait["owner_name"] or f"Student {owner_id}"
                )

        resource_output = [
            {
                "resource_id": int(r["resource_id"]),
                "label": r["resource_name"],
                "owner_student_id": (
                    int(r["owner_student_id"])
                    if r["owner_student_id"] is not None else None
                ),
                "owner": r["owner_name"],
                "sharer_id": (
                    int(r["sharer_id"])
                    if r["sharer_id"] is not None else None
                ),
                "active_transaction_id": (
                    int(r["active_transaction_id"])
                    if r["active_transaction_id"] is not None else None
                ),
            }
            for r in resources
        ]

        waits_output = [
            {
                "wait_id": int(w["wait_id"]),
                "request_id": (
                    int(w["request_id"])
                    if w["request_id"] is not None else None
                ),
                "waiting_student_id": int(w["waiting_student_id"]),
                "waiting_student": w["waiting_name"],
                "resource_id": int(w["resource_id"]),
                "resource_name": w["resource_name"],
                "owner_student_id": (
                    int(w["owner_student_id"])
                    if w["owner_student_id"] is not None else None
                ),
            }
            for w in waits
        ]

        return {
            "resources": resource_output,
            "waits": waits_output,
            "graph": graph,
            "names": names,
        }
    finally:
        cursor.close()


def _find_cycle(graph: dict[int, list[int]]) -> list[int]:
    """Return one cycle in the wait-for graph, or an empty list."""
    visited = set()
    active = set()
    path = []

    def dfs(node):
        visited.add(node)
        active.add(node)
        path.append(node)

        for neighbour in graph.get(node, []):
            if neighbour not in visited:
                cycle = dfs(neighbour)
                if cycle:
                    return cycle
            elif neighbour in active:
                start = path.index(neighbour)
                return path[start:] + [neighbour]

        path.pop()
        active.remove(node)
        return []

    for node in graph:
        if node not in visited:
            cycle = dfs(node)
            if cycle:
                return cycle

    return []


def _graph_output(graph):
    return {
        str(student): [str(owner) for owner in owners]
        for student, owners in graph.items()
    }


def _find_current_deadlock(connection):
    state = _load_state(connection)
    return state, _find_cycle(state["graph"])


def _acquire_lock(connection, timeout=10):
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT GET_LOCK(%s, %s)", (_LOCK_NAME, timeout))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)
    finally:
        cursor.close()


def _release_lock(connection):
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT RELEASE_LOCK(%s)", (_LOCK_NAME,))
        cursor.fetchone()
        cursor.close()
    except Exception:
        pass


def detect_os_deadlock(connection) -> dict[str, Any]:
    """Synchronize ShareSync state, then detect deadlocks."""
    if not _acquire_lock(connection):
        return {
            "success": False,
            "message": "Deadlock check is busy. Please try again.",
        }

    try:
        sync_os_deadlock_from_sharesync(connection)
        state, cycle = _find_current_deadlock(connection)
    finally:
        _release_lock(connection)

    return {
        "success": True,
        "mode": "ShareSync-integrated deadlock detection",
        "source_table": (
            "resource_offers, transactions, student_resource_requests"
        ),
        "tracking_tables": "os_resources, os_resource_waits",
        # Only the OS tracking tables are refreshed by detection.
        "database_records_changed": True,
        "application_records_changed": False,
        "resources": state["resources"],
        "initial_allocation": state["resources"],
        "waits": state["waits"],
        "wait_for_graph": _graph_output(state["graph"]),
        "deadlock_detected": bool(cycle),
        "cycle": [str(student) for student in cycle],
        "cycle_names": [
            state["names"].get(student, f"Student {student}")
            for student in cycle
        ],
        "recovery": None,
        "message": (
            "Deadlock detected in the synchronized ShareSync state."
            if cycle else
            "No deadlock detected in the synchronized ShareSync state."
        ),
    }


def _pick_victim(state, cycle):
    """
    Victim policy (minimum cost): the cycle member holding the fewest
    resources; ties go to the member with the newest waiting request.
    The victim must have a waiting request and hold a loan that another
    cycle member is waiting for.
    """
    members = set(cycle[:-1])
    held = {}
    for resource in state["resources"]:
        owner = resource["owner_student_id"]
        if owner is not None:
            held[owner] = held.get(owner, 0) + 1

    candidates = []
    for member in members:
        own_wait = next(
            (w for w in state["waits"]
             if w["waiting_student_id"] == member
             and w["request_id"] is not None
             and w["owner_student_id"] in members),
            None,
        )
        wanted_wait = next(
            (w for w in state["waits"]
             if w["owner_student_id"] == member
             and w["waiting_student_id"] in members),
            None,
        )
        if own_wait is None or wanted_wait is None:
            continue

        resource = next(
            (r for r in state["resources"]
             if r["resource_id"] == wanted_wait["resource_id"]
             and r["owner_student_id"] == member
             and r["active_transaction_id"] is not None),
            None,
        )
        if resource is None:
            continue

        candidates.append((
            held.get(member, 0), -own_wait["request_id"],
            member, own_wait, resource,
        ))

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c[0], c[1]))
    _, _, victim_id, wait, resource = candidates[0]
    # The cycle member waiting for the victim's resource will receive it.
    waiter_wait = next(
        (w for w in state["waits"]
         if w["resource_id"] == resource["resource_id"]
         and w["waiting_student_id"] in members
         and w["request_id"] is not None),
        None,
    )
    if waiter_wait is None:
        return None
    return victim_id, wait, resource, waiter_wait


def _recover_one(connection, state, cycle):
    """Break one cycle: abort the victim's waiting request, preempt the
    victim's loan, and reallocate the freed item to the cycle member that
    was waiting for it (a new ACTIVE transaction with the same lender)."""
    picked = _pick_victim(state, cycle)
    if picked is None:
        return {
            "success": False,
            "deadlock_detected": True,
            "message": (
                "A cycle was detected, but no victim could be chosen "
                "safely. No changes were made."
            ),
            "cycle": [str(student) for student in cycle],
        }

    victim_id, wait, resource, waiter_wait = picked
    transaction_id = int(resource["active_transaction_id"])
    waiter_id = int(waiter_wait["waiting_student_id"])
    waiter_request_id = int(waiter_wait["request_id"])
    cursor = connection.cursor(dictionary=True)
    offer_lock = False

    try:
        cursor.execute("""
            SELECT t.transaction_id, t.lender_id, t.offer_id,
                   o.resource_name, o.description, o.share_item_key
            FROM transactions t
            JOIN resource_offers o ON o.offer_id = t.offer_id
            WHERE t.transaction_id = %s
              AND t.borrower_id = %s
              AND t.transaction_status = 'ACTIVE'
            FOR UPDATE
        """, (transaction_id, victim_id))
        loan = cursor.fetchone()
        if loan is None:
            connection.rollback()
            return {
                "success": False,
                "deadlock_detected": True,
                "message": (
                    "The victim's loan changed meanwhile. "
                    "Run detection again before recovery."
                ),
            }

        # Cancel every OPEN request of the victim for the blocked item
        # (a wait row stores only one request id per item).
        cursor.execute("""
            SELECT request_id, resource_name
            FROM student_resource_requests
            WHERE student_id = %s AND request_status = 'OPEN'
            FOR UPDATE
        """, (victim_id,))
        blocked_name = _normalize(wait["resource_name"])
        to_cancel = [
            int(row["request_id"]) for row in cursor.fetchall()
            if _normalize(row["resource_name"]) == blocked_name
        ]
        if not to_cancel:
            connection.rollback()
            return {
                "success": False,
                "deadlock_detected": True,
                "message": (
                    "The victim request is no longer OPEN. "
                    "Run detection again before recovering."
                ),
            }

        placeholders = ", ".join(["%s"] * len(to_cancel))
        cursor.execute(f"""
            UPDATE student_resource_requests
            SET request_status = 'CANCELLED'
            WHERE request_id IN ({placeholders})
              AND student_id = %s
              AND request_status = 'OPEN'
        """, (*to_cancel, victim_id))

        # Resource preemption: end the victim's loan first, so the lender
        # has no other ACTIVE loan of this item.
        cursor.execute("""
            UPDATE transactions
            SET transaction_status = 'RETURNED',
                returned_at = NOW()
            WHERE transaction_id = %s
              AND transaction_status = 'ACTIVE'
        """, (transaction_id,))
        if cursor.rowcount != 1:
            connection.rollback()
            return {
                "success": False,
                "deadlock_detected": True,
                "message": "The victim's loan could not be released.",
            }

        # Reallocation: give the freed item to the waiting cycle member.
        cursor.execute("""
            SELECT request_id, student_id, resource_name, description,
                   category, due_date
            FROM student_resource_requests
            WHERE request_id = %s
              AND student_id = %s
              AND request_status = 'OPEN'
            FOR UPDATE
        """, (waiter_request_id, waiter_id))
        waiting_request = cursor.fetchone()
        if waiting_request is None:
            connection.rollback()
            return {
                "success": False,
                "deadlock_detected": True,
                "message": (
                    "The waiting student's request is no longer OPEN. "
                    "Run detection again before recovering."
                ),
            }

        cursor.execute(
            "SELECT GET_LOCK(%s, 10) AS acquired",
            ("sharesync_resource_offer_id",)
        )
        lock_row = cursor.fetchone()
        if not lock_row or lock_row["acquired"] != 1:
            connection.rollback()
            return {
                "success": False,
                "deadlock_detected": True,
                "message": "The share offer is busy. Please try again.",
            }
        offer_lock = True

        lender_id = int(loan["lender_id"])
        item_key = loan["share_item_key"] or _normalize(loan["resource_name"])
        due_date = (
            waiting_request["due_date"] or date.today() + timedelta(days=7)
        )

        cursor.execute("""
            INSERT INTO borrow_requests
                (student_id, resource_name, description, category,
                 request_status)
            VALUES (%s, %s, %s, %s, 'ACCEPTED')
        """, (
            waiter_id,
            waiting_request["resource_name"],
            waiting_request["description"],
            waiting_request["category"],
        ))
        legacy_request_id = cursor.lastrowid

        cursor.execute("""
            SELECT COALESCE(MAX(offer_id), 0) + 1 AS next_offer_id
            FROM resource_offers
        """)
        new_offer_id = cursor.fetchone()["next_offer_id"]

        cursor.execute("""
            INSERT INTO resource_offers
                (offer_id, request_id, student_id, resource_name,
                 description, offer_status, share_item_key)
            VALUES (%s, %s, %s, %s, %s, 'Accepted', %s)
        """, (
            new_offer_id,
            legacy_request_id,
            lender_id,
            loan["resource_name"],
            loan["description"],
            item_key,
        ))

        cursor.execute("""
            INSERT INTO transactions
                (request_id, offer_id, borrower_id, lender_id, due_date,
                 transaction_status)
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
        """, (
            legacy_request_id,
            new_offer_id,
            waiter_id,
            lender_id,
            due_date,
        ))
        new_transaction_id = cursor.lastrowid

        cursor.execute("""
            UPDATE student_resource_requests
            SET request_status = 'ACCEPTED',
                accepted_by = %s,
                borrow_request_id = %s
            WHERE request_id = %s
              AND request_status = 'OPEN'
        """, (lender_id, legacy_request_id, waiter_request_id))
        if cursor.rowcount != 1:
            connection.rollback()
            return {
                "success": False,
                "deadlock_detected": True,
                "message": "The item could not be reallocated.",
            }

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if offer_lock:
            try:
                cursor.execute(
                    "SELECT RELEASE_LOCK(%s) AS released",
                    ("sharesync_resource_offer_id",)
                )
                cursor.fetchone()
            except Exception:
                pass
        cursor.close()

    waiter_name = state["names"].get(waiter_id, f"Student {waiter_id}")
    return {
        "success": True,
        "method": (
            "Abort the victim's waiting request, preempt the victim's "
            "loan, and reallocate the item to the waiting student "
            "(minimum-cost victim)"
        ),
        "victim_student_id": victim_id,
        "victim_name": state["names"].get(victim_id, f"Student {victim_id}"),
        "cancelled_request_id": to_cancel[0],
        "cancelled_request_ids": to_cancel,
        "reallocated_to_student_id": waiter_id,
        "reallocated_to_name": waiter_name,
        "new_transaction_id": int(new_transaction_id),
        "released_resources": [{
            "resource_id": int(resource["resource_id"]),
            "resource_name": resource["label"],
            "previous_owner_student_id": victim_id,
            "active_transaction_id": transaction_id,
            "reallocated_to_student_id": waiter_id,
            "reallocated_to_name": waiter_name,
            "new_transaction_id": int(new_transaction_id),
            "status": (
                "Victim loan ended (RETURNED); item reallocated to "
                f"{waiter_name}"
            ),
        }],
        "note": (
            "The victim's waiting request was cancelled, the victim's loan "
            "was ended, and the item was reallocated to the student who was "
            "waiting for it (same lender, new ACTIVE transaction). Other "
            "loans and requests were not changed."
        ),
    }


def recover_os_deadlock(connection, requested_by=None) -> dict[str, Any]:
    """
    Recover from deadlock: repeatedly pick a victim from a cycle, abort its
    waiting request, preempt its blocking loan and reallocate the item to
    the waiting student, then re-run detection until no cycle remains.
    Real ShareSync records are updated.
    """
    if not _acquire_lock(connection):
        return {
            "success": False,
            "message": "Deadlock recovery is busy. Please try again.",
        }

    try:
        sync_os_deadlock_from_sharesync(connection)
        initial_state, cycle = _find_current_deadlock(connection)

        if not cycle:
            return {
                "success": True,
                "deadlock_detected": False,
                "database_records_changed": False,
                "application_records_changed": False,
                "message": "No deadlock exists now. Nothing was changed.",
                "resources": initial_state["resources"],
                "resource_state_after_recovery": initial_state["resources"],
                "wait_for_graph": _graph_output(initial_state["graph"]),
                "wait_for_graph_after_recovery": _graph_output(
                    initial_state["graph"]
                ),
                "waits": initial_state["waits"],
                "waits_after_recovery": initial_state["waits"],
                "deadlock_remains_after_recovery": False,
                "recovery": None,
                "recoveries": [],
            }

        first_cycle = cycle
        state = initial_state
        recoveries = []
        blocked_message = None

        for _ in range(_MAX_RECOVERY_ROUNDS):
            if not cycle:
                break

            if (
                RESTRICT_RECOVERY_TO_PARTICIPANTS
                and requested_by is not None
                and int(requested_by) not in set(cycle[:-1])
            ):
                blocked_message = (
                    "Only students involved in the deadlock can "
                    "run recovery."
                )
                break

            result = _recover_one(connection, state, cycle)
            if not result["success"]:
                result["recoveries"] = recoveries
                return result

            recoveries.append(result)
            sync_os_deadlock_from_sharesync(connection)
            state, cycle = _find_current_deadlock(connection)

        if not recoveries:
            return {
                "success": False,
                "deadlock_detected": True,
                "message": blocked_message or "No recovery was performed.",
                "cycle": [str(student) for student in first_cycle],
            }
    finally:
        _release_lock(connection)

    remains = bool(cycle)
    return {
        "success": True,
        "mode": "Victim abort + preemption + reallocation",
        "database_records_changed": True,
        "application_records_changed": True,
        "deadlock_detected": True,
        "resources": initial_state["resources"],
        "initial_allocation": initial_state["resources"],
        "waits": initial_state["waits"],
        "wait_for_graph": _graph_output(initial_state["graph"]),
        "cycle": [str(student) for student in first_cycle],
        "recovery": recoveries[0],
        "recoveries": recoveries,
        "resource_state_after_recovery": state["resources"],
        "wait_for_graph_after_recovery": _graph_output(state["graph"]),
        "waits_after_recovery": state["waits"],
        "deadlock_remains_after_recovery": remains,
        "message": (
            "Recovery completed."
            if not remains
            else "A deadlock cycle remains after recovery."
        ),
    }


def run_os_deadlock_simulation(connection) -> dict[str, Any]:
    """Backwards-compatible name; performs detection only."""
    return detect_os_deadlock(connection)