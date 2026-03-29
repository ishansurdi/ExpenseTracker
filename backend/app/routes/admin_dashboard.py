from datetime import date, datetime, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, Field

from app.auth import hash_password
from app.config import settings
from app.database import get_db


router = APIRouter(prefix="/admin-dashboard", tags=["Admin Dashboard"])
security = HTTPBearer(auto_error=True)


class DashboardUserCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=5, max_length=255)


class EmployeeCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=5, max_length=255)
    manager_id: str


class ManagerAssignRequest(BaseModel):
    manager_id: str


class RoleUpdateRequest(BaseModel):
    role: str


class OverrideRequest(BaseModel):
    action: str
    reason: str = Field(min_length=2, max_length=1000)


class LeadershipResponse(BaseModel):
    finance_head: dict | None
    cfo: dict | None


class DashboardBootstrapResponse(BaseModel):
    leadership: LeadershipResponse
    managers: list[dict]
    employees: list[dict]
    expenses: list[dict]


def _has_is_leadership_column(db) -> bool:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'users'
                  AND column_name = 'is_leadership'
            ) AS exists_col
            """
        )
        result = cursor.fetchone()
    return bool(result and result["exists_col"])


def _has_manager_m_sequence(db) -> bool:
    with db.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.manager_m_login_seq') AS sequence_name")
        result = cursor.fetchone()
    return bool(result and result["sequence_name"])


def _decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token expired. Please sign in again.") from exc
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token. Please sign in again.") from exc

    subject = payload.get("sub")
    role = payload.get("role")
    if not subject or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    return {"user_id": str(subject), "role": str(role)}


def _get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)) -> dict:
    token_payload = _decode_access_token(credentials.credentials)
    if token_payload["role"].lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, company_id, login_id, full_name, email, role, is_active
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (token_payload["user_id"],),
        )
        admin_user = cursor.fetchone()

    if not admin_user or not admin_user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user not found or inactive")

    return admin_user


def _generate_login_id(connection, role: str, is_leadership: bool = False) -> str:
    if role == "admin":
        sequence_name = "admin_login_seq"
        prefix = "A"
    elif role == "manager" and is_leadership:
        sequence_name = "manager_login_seq"
        prefix = "MAN"
    elif role == "manager":
        if _has_manager_m_sequence(connection):
            sequence_name = "manager_m_login_seq"
            prefix = "M"
        else:
            sequence_name = "manager_login_seq"
            prefix = "MAN"
    else:
        sequence_name = "employee_login_seq"
        prefix = "E"

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{sequence_name}') AS sequence_value")
        sequence_value = cursor.fetchone()["sequence_value"]

    return f"{prefix}{sequence_value:04d}"


def _create_or_pick_user(db, company_id: str, full_name: str, email: str, role: str, is_leadership: bool) -> dict:
    normalized_email = email.strip().lower()
    normalized_name = full_name.strip()
    has_is_leadership = _has_is_leadership_column(db)

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, company_id, login_id, full_name, email, role
            FROM users
            WHERE lower(email) = %s
            LIMIT 1
            """,
            (normalized_email,),
        )
        existing = cursor.fetchone()

        if existing:
            if str(existing["company_id"]) != str(company_id):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already belongs to another company")

            if existing["role"] == "employee" and role == "manager":
                if has_is_leadership:
                    cursor.execute(
                        "UPDATE users SET role = 'manager', is_leadership = %s, updated_at = %s WHERE id = %s",
                        (is_leadership, datetime.now(timezone.utc), existing["id"]),
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET role = 'manager', updated_at = %s WHERE id = %s",
                        (datetime.now(timezone.utc), existing["id"]),
                    )
                existing["role"] = "manager"
            elif existing["role"] == "manager" and has_is_leadership:
                cursor.execute(
                    "UPDATE users SET is_leadership = %s, updated_at = %s WHERE id = %s",
                    (is_leadership, datetime.now(timezone.utc), existing["id"]),
                )

            if existing["full_name"] != normalized_name:
                cursor.execute(
                    "UPDATE users SET full_name = %s, updated_at = %s WHERE id = %s",
                    (normalized_name, datetime.now(timezone.utc), existing["id"]),
                )
                existing["full_name"] = normalized_name

            return {
                "id": str(existing["id"]),
                "login_id": existing["login_id"],
                "full_name": existing["full_name"],
                "email": existing["email"],
                "role": existing["role"],
                "temporary_password": None,
            }

        temporary_password = f"Temp@{token_urlsafe(7)}"
        login_id = _generate_login_id(db, role, is_leadership=is_leadership)

        if has_is_leadership:
            cursor.execute(
                """
                INSERT INTO users (company_id, login_id, full_name, email, password_hash, role, is_email_verified, is_active, is_leadership)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE, %s)
                RETURNING id, login_id, full_name, email, role
                """,
                (
                    company_id,
                    login_id,
                    normalized_name,
                    normalized_email,
                    hash_password(temporary_password),
                    role,
                    is_leadership,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO users (company_id, login_id, full_name, email, password_hash, role, is_email_verified, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE)
                RETURNING id, login_id, full_name, email, role
                """,
                (
                    company_id,
                    login_id,
                    normalized_name,
                    normalized_email,
                    hash_password(temporary_password),
                    role,
                ),
            )
        created = cursor.fetchone()

    return {
        "id": str(created["id"]),
        "login_id": created["login_id"],
        "full_name": created["full_name"],
        "email": created["email"],
        "role": created["role"],
        "temporary_password": temporary_password,
    }


def _get_leadership(db, company_id: str) -> dict:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                cl.company_id,
                fh.id AS finance_head_id,
                fh.full_name AS finance_head_name,
                fh.email AS finance_head_email,
                cfo.id AS cfo_id,
                cfo.full_name AS cfo_name,
                cfo.email AS cfo_email
            FROM company_leadership cl
            LEFT JOIN users fh ON fh.id = cl.finance_head_user_id
            LEFT JOIN users cfo ON cfo.id = cl.cfo_user_id
            WHERE cl.company_id = %s
            LIMIT 1
            """,
            (company_id,),
        )
        row = cursor.fetchone()

    if not row:
        return {"finance_head": None, "cfo": None}

    return {
        "finance_head": (
            {
                "id": str(row["finance_head_id"]),
                "full_name": row["finance_head_name"],
                "email": row["finance_head_email"],
            }
            if row["finance_head_id"]
            else None
        ),
        "cfo": (
            {
                "id": str(row["cfo_id"]),
                "full_name": row["cfo_name"],
                "email": row["cfo_email"],
            }
            if row["cfo_id"]
            else None
        ),
    }


@router.get("/bootstrap", response_model=DashboardBootstrapResponse)
def bootstrap_dashboard(admin=Depends(_get_current_admin), db=Depends(get_db)):
    company_id = admin["company_id"]
    has_is_leadership = _has_is_leadership_column(db)

    leadership = _get_leadership(db, company_id)

    with db.cursor() as cursor:
        if has_is_leadership:
            cursor.execute(
                """
                SELECT id, login_id, full_name, email, role
                FROM users
                WHERE company_id = %s AND role = 'manager' AND is_active = TRUE AND COALESCE(is_leadership, FALSE) = FALSE
                ORDER BY full_name ASC
                """,
                (company_id,),
            )
        else:
            cursor.execute(
                """
                SELECT u.id, u.login_id, u.full_name, u.email, u.role
                FROM users u
                LEFT JOIN company_leadership cl ON cl.company_id = u.company_id
                WHERE u.company_id = %s
                  AND u.role = 'manager'
                  AND u.is_active = TRUE
                  AND (cl.finance_head_user_id IS NULL OR u.id <> cl.finance_head_user_id)
                  AND (cl.cfo_user_id IS NULL OR u.id <> cl.cfo_user_id)
                ORDER BY u.full_name ASC
                """,
                (company_id,),
            )
        manager_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.id, e.login_id, e.full_name, e.email, e.role,
                   m.id AS manager_id, m.full_name AS manager_name
            FROM users e
            LEFT JOIN users m ON m.id = e.manager_id
            WHERE e.company_id = %s AND e.role = 'employee' AND e.is_active = TRUE
            ORDER BY e.full_name ASC
            """,
            (company_id,),
        )
        employee_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT ex.id, ex.amount, ex.currency_code, ex.status, ex.submitted_at,
                   u.full_name AS employee_name
            FROM expenses ex
            JOIN users u ON u.id = ex.employee_user_id
            WHERE ex.company_id = %s
            ORDER BY ex.submitted_at DESC
            LIMIT 100
            """,
            (company_id,),
        )
        expense_rows = cursor.fetchall()

    managers = [
        {
            "id": str(row["id"]),
            "login_id": row["login_id"],
            "full_name": row["full_name"],
            "email": row["email"],
            "role": row["role"],
        }
        for row in manager_rows
    ]

    employees = [
        {
            "id": str(row["id"]),
            "login_id": row["login_id"],
            "full_name": row["full_name"],
            "email": row["email"],
            "role": row["role"],
            "manager_id": str(row["manager_id"]) if row["manager_id"] else None,
            "manager_name": row["manager_name"],
            "finance_head_name": leadership["finance_head"]["full_name"] if leadership["finance_head"] else None,
            "cfo_name": leadership["cfo"]["full_name"] if leadership["cfo"] else None,
        }
        for row in employee_rows
    ]

    expenses = [
        {
            "id": str(row["id"]),
            "employee_name": row["employee_name"],
            "amount": float(row["amount"]),
            "currency_code": row["currency_code"],
            "status": row["status"],
            "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        }
        for row in expense_rows
    ]

    return {
        "leadership": leadership,
        "managers": managers,
        "employees": employees,
        "expenses": expenses,
    }


@router.post("/leadership/finance-head")
def set_finance_head(payload: DashboardUserCreateRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    try:
        user_data = _create_or_pick_user(
            db,
            str(admin["company_id"]),
            payload.full_name,
            payload.email,
            "manager",
            is_leadership=True,
        )

        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO company_leadership (company_id, finance_head_user_id, updated_by_user_id, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (company_id)
                DO UPDATE SET
                    finance_head_user_id = EXCLUDED.finance_head_user_id,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (admin["company_id"], user_data["id"], admin["id"], datetime.now(timezone.utc)),
            )
        db.commit()
        return {"finance_head": user_data}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to set finance head: {exc}") from exc


@router.post("/leadership/cfo")
def set_cfo(payload: DashboardUserCreateRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    try:
        user_data = _create_or_pick_user(
            db,
            str(admin["company_id"]),
            payload.full_name,
            payload.email,
            "manager",
            is_leadership=True,
        )

        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO company_leadership (company_id, cfo_user_id, updated_by_user_id, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (company_id)
                DO UPDATE SET
                    cfo_user_id = EXCLUDED.cfo_user_id,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (admin["company_id"], user_data["id"], admin["id"], datetime.now(timezone.utc)),
            )
        db.commit()
        return {"cfo": user_data}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to set CFO: {exc}") from exc


@router.post("/managers")
def create_manager(payload: DashboardUserCreateRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    try:
        manager = _create_or_pick_user(
            db,
            str(admin["company_id"]),
            payload.full_name,
            payload.email,
            "manager",
            is_leadership=False,
        )
        db.commit()
        return {"manager": manager}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to create manager: {exc}") from exc


@router.post("/employees")
def create_employee(payload: EmployeeCreateRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    has_is_leadership = _has_is_leadership_column(db)
    try:
        with db.cursor() as cursor:
            if has_is_leadership:
                cursor.execute(
                    """
                    SELECT id, full_name, role
                    FROM users
                    WHERE id = %s AND company_id = %s AND role = 'manager' AND is_active = TRUE AND COALESCE(is_leadership, FALSE) = FALSE
                    LIMIT 1
                    """,
                    (payload.manager_id, admin["company_id"]),
                )
            else:
                cursor.execute(
                    """
                    SELECT u.id, u.full_name, u.role
                    FROM users u
                    LEFT JOIN company_leadership cl ON cl.company_id = u.company_id
                    WHERE u.id = %s
                      AND u.company_id = %s
                      AND u.role = 'manager'
                      AND u.is_active = TRUE
                      AND (cl.finance_head_user_id IS NULL OR u.id <> cl.finance_head_user_id)
                      AND (cl.cfo_user_id IS NULL OR u.id <> cl.cfo_user_id)
                    LIMIT 1
                    """,
                    (payload.manager_id, admin["company_id"]),
                )
            manager = cursor.fetchone()
            if not manager:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")

        employee = _create_or_pick_user(
            db,
            str(admin["company_id"]),
            payload.full_name,
            payload.email,
            "employee",
            is_leadership=False,
        )

        with db.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET manager_id = %s, updated_at = %s WHERE id = %s",
                (payload.manager_id, datetime.now(timezone.utc), employee["id"]),
            )

        db.commit()
        return {"employee": employee}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to create employee: {exc}") from exc


@router.patch("/employees/{employee_id}/manager")
def assign_employee_manager(employee_id: str, payload: ManagerAssignRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    has_is_leadership = _has_is_leadership_column(db)
    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE id = %s AND company_id = %s AND role = 'employee' AND is_active = TRUE
                LIMIT 1
                """,
                (employee_id, admin["company_id"]),
            )
            employee_row = cursor.fetchone()
            if not employee_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

            if has_is_leadership:
                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE id = %s AND company_id = %s AND role = 'manager' AND is_active = TRUE AND COALESCE(is_leadership, FALSE) = FALSE
                    LIMIT 1
                    """,
                    (payload.manager_id, admin["company_id"]),
                )
            else:
                cursor.execute(
                    """
                    SELECT u.id
                    FROM users u
                    LEFT JOIN company_leadership cl ON cl.company_id = u.company_id
                    WHERE u.id = %s
                      AND u.company_id = %s
                      AND u.role = 'manager'
                      AND u.is_active = TRUE
                      AND (cl.finance_head_user_id IS NULL OR u.id <> cl.finance_head_user_id)
                      AND (cl.cfo_user_id IS NULL OR u.id <> cl.cfo_user_id)
                    LIMIT 1
                    """,
                    (payload.manager_id, admin["company_id"]),
                )
            manager_row = cursor.fetchone()
            if not manager_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")

            cursor.execute(
                "UPDATE users SET manager_id = %s, updated_at = %s WHERE id = %s",
                (payload.manager_id, datetime.now(timezone.utc), employee_id),
            )

        db.commit()
        return {"message": "Manager assignment updated"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to assign manager: {exc}") from exc


@router.patch("/employees/{employee_id}/role")
def update_employee_role(employee_id: str, payload: RoleUpdateRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    allowed_roles = {"employee", "manager"}
    role_value = payload.role.strip().lower()
    if role_value not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allowed roles: employee, manager")

    try:
        with db.cursor() as cursor:
            if _has_is_leadership_column(db):
                cursor.execute(
                    """
                    UPDATE users
                    SET role = %s, is_leadership = FALSE, updated_at = %s
                    WHERE id = %s AND company_id = %s AND is_active = TRUE
                    RETURNING id
                    """,
                    (role_value, datetime.now(timezone.utc), employee_id, admin["company_id"]),
                )
            else:
                cursor.execute(
                    """
                    UPDATE users
                    SET role = %s, updated_at = %s
                    WHERE id = %s AND company_id = %s AND is_active = TRUE
                    RETURNING id
                    """,
                    (role_value, datetime.now(timezone.utc), employee_id, admin["company_id"]),
                )
            updated = cursor.fetchone()
            if not updated:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        db.commit()
        return {"message": "Role updated"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to update role: {exc}") from exc


@router.post("/expenses/{expense_id}/override")
def override_expense(expense_id: str, payload: OverrideRequest, admin=Depends(_get_current_admin), db=Depends(get_db)):
    action = payload.action.strip().lower()
    if action not in {"force_approve", "force_reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action must be force_approve or force_reject")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM expenses
                WHERE id = %s AND company_id = %s
                LIMIT 1
                """,
                (expense_id, admin["company_id"]),
            )
            expense_row = cursor.fetchone()
            if not expense_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

            cursor.execute(
                """
                INSERT INTO expense_overrides (expense_id, company_id, admin_user_id, action, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (expense_id, admin["company_id"], admin["id"], action, payload.reason.strip()),
            )

            cursor.execute(
                "UPDATE expenses SET status = 'overridden', updated_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), expense_id),
            )

        db.commit()
        return {"message": "Override applied"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to override expense: {exc}") from exc


@router.post("/seed-expense")
def seed_expense_for_testing(admin=Depends(_get_current_admin), db=Depends(get_db)):
    """Small helper for local testing dashboard expenses."""
    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE company_id = %s AND role = 'employee' AND is_active = TRUE
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (admin["company_id"],),
            )
            employee = cursor.fetchone()
            if not employee:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Create an employee first")

            cursor.execute(
                """
                INSERT INTO expenses (company_id, employee_user_id, title, description, expense_date, amount, currency_code, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'submitted')
                RETURNING id
                """,
                (
                    admin["company_id"],
                    employee["id"],
                    "Travel reimbursement",
                    "Taxi and meals",
                    date.today(),
                    245.50,
                    "USD",
                ),
            )
            created = cursor.fetchone()
        db.commit()
        return {"expense_id": str(created["id"])}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to seed expense: {exc}") from exc
