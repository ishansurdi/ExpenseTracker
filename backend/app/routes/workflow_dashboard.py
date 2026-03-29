from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db


router = APIRouter(prefix="/dashboard", tags=["Workflow Dashboard"])
security = HTTPBearer(auto_error=True)


class ApprovalDecisionRequest(BaseModel):
    decision: str
    comment: str | None = Field(default=None, max_length=1000)


class EmployeeApplicationRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    expense_date: str
    amount: float = Field(gt=0)
    currency_code: str = Field(min_length=1, max_length=10)
    converted_amount: float | None = Field(default=None, gt=0)
    conversion_rate: float | None = Field(default=None, gt=0)


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


def _get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)) -> dict:
    token_payload = _decode_access_token(credentials.credentials)

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT u.id, u.company_id, u.login_id, u.full_name, u.email, u.role, u.is_active,
                   c.name AS company_name, c.currency_code AS company_currency
            FROM users u
            JOIN companies c ON c.id = u.company_id
            WHERE u.id = %s
            LIMIT 1
            """,
            (token_payload["user_id"],),
        )
        user = cursor.fetchone()

    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def _get_leadership(db, company_id: str) -> dict:
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT finance_head_user_id, cfo_user_id
            FROM company_leadership
            WHERE company_id = %s
            LIMIT 1
            """,
            (company_id,),
        )
        row = cursor.fetchone()

    return {
        "finance_head_user_id": str(row["finance_head_user_id"]) if row and row["finance_head_user_id"] else None,
        "cfo_user_id": str(row["cfo_user_id"]) if row and row["cfo_user_id"] else None,
    }


def _get_approval_rows(db, expense_ids: list[str]) -> dict[str, list[dict]]:
    if not expense_ids:
        return {}

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT ea.expense_id, ea.stage, ea.decision, ea.comment, ea.decided_at,
                   u.full_name AS approver_name
            FROM expense_approvals ea
            JOIN users u ON u.id = ea.approver_user_id
            WHERE ea.expense_id = ANY(%s)
            ORDER BY ea.stage ASC
            """,
            (expense_ids,),
        )
        rows = cursor.fetchall()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["expense_id"])].append(
            {
                "stage": int(row["stage"]),
                "decision": row["decision"],
                "comment": row["comment"],
                "approver_name": row["approver_name"],
                "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None,
            }
        )
    return grouped


def _format_expense_rows(db, rows: list[dict], include_employee_name: bool = False) -> list[dict]:
    expense_ids = [str(row["id"]) for row in rows]
    approvals_map = _get_approval_rows(db, expense_ids)

    output = []
    for row in rows:
        expense = {
            "id": str(row["id"]),
            "title": row["title"],
            "description": row["description"],
            "expense_date": row["expense_date"].isoformat() if row["expense_date"] else None,
            "amount": float(row["amount"]),
            "currency_code": row["currency_code"],
            "status": row["status"],
            "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
            "approvals": approvals_map.get(str(row["id"]), []),
        }
        if include_employee_name:
            expense["employee_name"] = row["employee_name"]
        output.append(expense)
    return output


def _assert_manager_non_leadership(db, user: dict) -> None:
    if user["role"] != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")

    leadership = _get_leadership(db, user["company_id"])
    if leadership["finance_head_user_id"] == str(user["id"]) or leadership["cfo_user_id"] == str(user["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Use finance/CFO dashboard for this user")


def _get_leadership_mode(db, user: dict) -> str:
    if user["role"] != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leadership dashboard requires manager role")

    leadership = _get_leadership(db, user["company_id"])
    if leadership["finance_head_user_id"] == str(user["id"]):
        return "finance_head"
    if leadership["cfo_user_id"] == str(user["id"]):
        return "cfo"

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Current manager is not Finance Head/CFO")


@router.get("/me")
def dashboard_me(user=Depends(_get_current_user), db=Depends(get_db)):
    leadership = _get_leadership(db, user["company_id"])
    return {
        "user": {
            "id": str(user["id"]),
            "login_id": user["login_id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"],
        },
        "company": {
            "id": str(user["company_id"]),
            "name": user["company_name"],
            "currency_code": user["company_currency"],
        },
        "leadership": {
            "is_finance_head": leadership["finance_head_user_id"] == str(user["id"]),
            "is_cfo": leadership["cfo_user_id"] == str(user["id"]),
        },
    }


@router.get("/manager/overview")
def manager_overview(user=Depends(_get_current_user), db=Depends(get_db)):
    _assert_manager_non_leadership(db, user)

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, login_id, full_name, email
            FROM users
            WHERE company_id = %s AND role = 'employee' AND manager_id = %s AND is_active = TRUE
            ORDER BY full_name ASC
            """,
            (user["company_id"], user["id"]),
        )
        employees = cursor.fetchall()

        cursor.execute(
            """
            SELECT ex.id, ex.title, ex.description, ex.expense_date, ex.amount, ex.currency_code, ex.status, ex.submitted_at,
                   u.full_name AS employee_name
            FROM expenses ex
            JOIN users u ON u.id = ex.employee_user_id
            WHERE ex.company_id = %s AND u.manager_id = %s AND ex.status = 'submitted'
            ORDER BY ex.submitted_at ASC
            """,
            (user["company_id"], user["id"]),
        )
        pending = cursor.fetchall()

        cursor.execute(
            """
            SELECT ex.id, ex.title, ex.description, ex.expense_date, ex.amount, ex.currency_code, ex.status, ex.submitted_at,
                   u.full_name AS employee_name
            FROM expenses ex
            JOIN users u ON u.id = ex.employee_user_id
            WHERE ex.company_id = %s AND u.manager_id = %s
            ORDER BY ex.submitted_at DESC
            """,
            (user["company_id"], user["id"]),
        )
        all_applications = cursor.fetchall()

    return {
        "employees": [
            {
                "id": str(row["id"]),
                "login_id": row["login_id"],
                "full_name": row["full_name"],
                "email": row["email"],
            }
            for row in employees
        ],
        "pending_approvals": _format_expense_rows(db, pending, include_employee_name=True),
        "all_applications": _format_expense_rows(db, all_applications, include_employee_name=True),
        "summary": {
            "employee_count": len(employees),
            "pending_count": len(pending),
            "total_application_count": len(all_applications),
        },
    }


@router.get("/leadership/overview")
def leadership_overview(user=Depends(_get_current_user), db=Depends(get_db)):
    mode = _get_leadership_mode(db, user)
    expected_status = "manager_approved" if mode == "finance_head" else "finance_approved"

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT ex.id, ex.title, ex.description, ex.expense_date, ex.amount, ex.currency_code, ex.status, ex.submitted_at,
                   u.full_name AS employee_name
            FROM expenses ex
            JOIN users u ON u.id = ex.employee_user_id
            WHERE ex.company_id = %s AND ex.status = %s
            ORDER BY ex.submitted_at ASC
            """,
            (user["company_id"], expected_status),
        )
        pending = cursor.fetchall()

    return {
        "mode": mode,
        "pending_approvals": _format_expense_rows(db, pending, include_employee_name=True),
        "summary": {
            "pending_count": len(pending),
        },
    }


@router.get("/employee/overview")
def employee_overview(user=Depends(_get_current_user), db=Depends(get_db)):
    if user["role"] != "employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee access required")

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, title, description, expense_date, amount, currency_code, status, submitted_at
            FROM expenses
            WHERE company_id = %s AND employee_user_id = %s
            ORDER BY submitted_at DESC
            """,
            (user["company_id"], user["id"]),
        )
        rows = cursor.fetchall()

    all_items = _format_expense_rows(db, rows)
    active_statuses = {"submitted", "manager_approved", "finance_approved"}
    active = [item for item in all_items if item["status"] in active_statuses]
    history = [item for item in all_items if item["status"] not in active_statuses]

    return {
        "company_currency": user["company_currency"],
        "active_applications": active,
        "history": history,
        "summary": {
            "active_count": len(active),
            "total_count": len(all_items),
        },
    }


@router.post("/employee/applications")
def create_employee_application(payload: EmployeeApplicationRequest, user=Depends(_get_current_user), db=Depends(get_db)):
    if user["role"] != "employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee access required")

    try:
        parsed_date = datetime.fromisoformat(payload.expense_date).date()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid expense_date format. Use YYYY-MM-DD") from exc

    company_currency = str(user["company_currency"] or "USD").upper()
    source_currency = payload.currency_code.upper()

    description_parts = [payload.description.strip()] if payload.description else []
    final_amount = Decimal(str(payload.amount))
    final_currency = source_currency

    if source_currency != company_currency:
        if payload.converted_amount is None or payload.conversion_rate is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="converted_amount and conversion_rate are required when currency differs from company currency",
            )
        final_amount = Decimal(str(payload.converted_amount))
        final_currency = company_currency
        description_parts.append(
            f"Original amount: {payload.amount:.2f} {source_currency}; Conversion rate: {payload.conversion_rate:.6f}; Converted amount: {payload.converted_amount:.2f} {company_currency}"
        )

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO expenses (company_id, employee_user_id, title, description, expense_date, amount, currency_code, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'submitted')
                RETURNING id
                """,
                (
                    user["company_id"],
                    user["id"],
                    payload.title.strip(),
                    "\n".join(description_parts) if description_parts else None,
                    parsed_date,
                    final_amount,
                    final_currency,
                ),
            )
            created = cursor.fetchone()
        db.commit()
        return {"expense_id": str(created["id"]), "status": "submitted"}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to submit application: {exc}") from exc


@router.post("/approvals/{expense_id}/decision")
def decide_expense(expense_id: str, payload: ApprovalDecisionRequest, user=Depends(_get_current_user), db=Depends(get_db)):
    decision = payload.decision.strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decision must be approved or rejected")

    leadership = _get_leadership(db, user["company_id"])

    stage = None
    expected_status = None
    approved_next_status = None

    if user["role"] != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only manager/finance/CFO can approve")

    if leadership["cfo_user_id"] == str(user["id"]):
        stage = 3
        expected_status = "finance_approved"
        approved_next_status = "cfo_approved"
    elif leadership["finance_head_user_id"] == str(user["id"]):
        stage = 2
        expected_status = "manager_approved"
        approved_next_status = "finance_approved"
    else:
        stage = 1
        expected_status = "submitted"
        approved_next_status = "manager_approved"

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT ex.id, ex.status, ex.employee_user_id, u.manager_id
                FROM expenses ex
                JOIN users u ON u.id = ex.employee_user_id
                WHERE ex.id = %s AND ex.company_id = %s
                LIMIT 1
                """,
                (expense_id, user["company_id"]),
            )
            expense = cursor.fetchone()
            if not expense:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

            if stage == 1 and str(expense["manager_id"]) != str(user["id"]):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not manager for this employee")

            if expense["status"] != expected_status:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Expense is in status '{expense['status']}', expected '{expected_status}'",
                )

            cursor.execute(
                """
                INSERT INTO expense_approvals (expense_id, company_id, approver_user_id, stage, decision, comment, decided_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (expense_id, stage)
                DO UPDATE SET
                    decision = EXCLUDED.decision,
                    comment = EXCLUDED.comment,
                    approver_user_id = EXCLUDED.approver_user_id,
                    decided_at = EXCLUDED.decided_at
                """,
                (expense_id, user["company_id"], user["id"], stage, decision, payload.comment),
            )

            new_status = approved_next_status if decision == "approved" else "rejected"
            cursor.execute(
                "UPDATE expenses SET status = %s, updated_at = NOW() WHERE id = %s",
                (new_status, expense_id),
            )

        db.commit()
        return {
            "message": "Decision saved",
            "new_status": new_status,
            "closed": new_status in {"cfo_approved", "rejected", "overridden"},
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unable to save decision: {exc}") from exc
