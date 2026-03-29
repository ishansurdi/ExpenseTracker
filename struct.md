Optimizing tool selection...**Winning First Structure (Simple + Creative + Working)**

You should build this as a **single-product monolith** with a strong workflow core, not as many microservices.  
That gives you speed, stability, and a cleaner demo.

## 1. Product Shape You Should Submit
1. One web app with 3 role-based experiences:
   1. Admin workspace
   2. Manager workspace
   3. Employee workspace
2. One approval engine that supports:
   1. Sequential approvers
   2. Percentage rules
   3. Specific approver shortcut (example: CFO)
   4. Hybrid combinations
3. One transparency layer:
   1. Full approval timeline
   2. Who approved/rejected and when
   3. Rule that triggered final decision

This transparency layer is what will beat many submissions.

---

## 2. Recommended Tech Stack (Fast to build, easy to demo)
1. Backend:
   1. Python + FastAPI
   2. PostgreSQL
   3. JWT auth + refresh tokens
   4. Background worker using simple job queue table in DB (no Redis needed)
2. Frontend:
   1. Server-rendered HTML pages
   2. Tailwind CSS
   3. Minimal Alpine.js for interactivity
3. OCR:
   1. Tesseract OCR (or cloud OCR if allowed)
   2. Parsing layer to extract amount/date/vendor/category
4. External APIs:
   1. RestCountries for country + currency seed
   2. ExchangeRate API for conversion at submit and approval time snapshots

---

## 3. Core Domain Modules
1. Identity and Company Bootstrap
   1. Signup creates company + admin user automatically
   2. Company default currency based on selected country
2. User and Role Management
   1. Admin creates users
   2. Assign Employee or Manager role
   3. Set manager relationship
3. Expense Management
   1. Draft expense
   2. Submit expense
   3. Attach receipt
   4. OCR assisted autofill
4. Approval Configuration
   1. Template of approvers
   2. Sequence ordering
   3. Is manager approver switch
   4. Conditional logic builder
5. Approval Execution Engine
   1. Creates approval tasks
   2. Moves request between levels
   3. Evaluates conditional rules live
6. Currency Service
   1. Stores original amount and currency
   2. Stores converted amount in company currency
   3. Keeps conversion rate snapshot for audit
7. Audit and Timeline
   1. Immutable event history
   2. Every state change logged

---

## 4. Data Model You Need
1. Company
   1. Name
   2. Country
   3. Default currency
2. User
   1. Company id
   2. Role (Admin, Manager, Employee)
   3. Manager id (nullable)
   4. Active flag
3. Expense
   1. Employee id
   2. Original amount + currency
   3. Converted amount in company currency
   4. Category, date, description
   5. Status (Draft, Submitted, InReview, Approved, Rejected)
4. Receipt
   1. Expense id
   2. File URL/path
   3. OCR raw text
   4. OCR confidence
5. Approval Policy
   1. Company id
   2. Name
   3. Is manager approver
   4. Min approval percentage
   5. Specific approver id (optional)
   6. Rule mode (Sequential, Conditional, Hybrid)
6. Policy Approver Step
   1. Policy id
   2. Step number
   3. Approver user id or role target
   4. Required flag
7. Approval Task
   1. Expense id
   2. Step number
   3. Assigned approver
   4. Status (Pending, Approved, Rejected, Skipped)
   5. Comment
8. Approval Event
   1. Expense id
   2. Actor
   3. Action
   4. Metadata JSON
   5. Timestamp
9. Exchange Rate Snapshot
   1. Base currency
   2. Target currency
   3. Rate
   4. Source and timestamp

---

## 5. Approval Engine Logic (Important)
1. On submit:
   1. Load policy
   2. Build candidate approvers list (manager + configured steps)
   3. Create first pending task only (for strict sequence) or batch tasks (for percentage mode)
2. On each decision:
   1. Write approval event
   2. Recompute decision state:
      1. If specific approver approved and rule allows shortcut -> final approve
      2. If rejection from required approver -> final reject
      3. If percentage threshold reached -> final approve
      4. Else move/generate next task(s)
3. Always keep:
   1. Current active step
   2. Decision reason (which rule caused final outcome)

This “decision reason” is a judge-winning feature.

---

## 6. Role Permissions Matrix
1. Admin:
   1. Manage company users and hierarchy
   2. Configure policies
   3. View all expenses
   4. Override decisions with reason
2. Manager:
   1. View team expenses
   2. Approve/reject assigned tasks
   3. Add comments
3. Employee:
   1. Submit expense
   2. Track status
   3. View own history

---

## 7. UI Structure (Aligned to your mockup)
1. Auth:
   1. Sign up company admin
   2. Sign in
   3. Forgot password
2. Admin:
   1. User table with role + manager mapping
   2. Approval rule editor
   3. Expense oversight
3. Employee:
   1. Expense list with filters and status chips
   2. Create expense form with receipt upload + OCR autofill
   3. Approval timeline drawer
4. Manager:
   1. Approval inbox
   2. Approve/reject modal with comments
   3. Team expense view

---

## 8. API Surface (Minimum)
1. Auth:
   1. Signup company admin
   2. Login
2. Users:
   1. Create/update users
   2. Set role
   3. Set manager
3. Policies:
   1. Create/update approval policy
   2. Add approvers and sequence
4. Expenses:
   1. Create draft
   2. OCR parse receipt
   3. Submit
   4. Get history
5. Approvals:
   1. My pending approvals
   2. Approve
   3. Reject
   4. Timeline fetch
6. Currency:
   1. Country to currency seed
   2. Convert and snapshot

---

## 9. Build Plan (to beat 100+ submissions)
1. Phase 1 (MVP):
   1. Auth + company bootstrap
   2. User roles + manager mapping
   3. Expense submit/history
   4. Sequential approvals
2. Phase 2 (Differentiator):
   1. Conditional rules (percentage/specific/hybrid)
   2. Timeline with rule-trigger reason
   3. Currency snapshots
3. Phase 3 (Polish):
   1. OCR autofill
   2. Override flow with audit reason
   3. Demo seed data + clean dashboards

---

## 10. Creative Touches That Stay Simple
1. Explainable Decision Card on each expense:
   1. “Approved because 2/3 approvers approved (66.7%)”
   2. Or “Approved because CFO approved”
2. Approval Progress Rail:
   1. Shows steps completed and current owner
3. Currency Trust Label:
   1. “Converted at submit time: rate X from source Y”
4. OCR Confidence Meter:
   1. Highlights fields that need user confirmation

These are small to build but high impact in judging.

---

If you want, next I can give you the **exact project scaffold** (folders, module boundaries, endpoint contracts, DB tables with SQL) as Step 2 so you can start coding immediately.

---

## FastAPI Backend Scaffold (Step 2)

Use this as the first working structure:

reimbursment/
- backend/
   - app/
      - main.py
      - core/
         - config.py
         - security.py
      - db/
         - base.py
         - session.py
      - api/
         - v1/
            - router.py
            - endpoints/
               - health.py
               - auth.py
               - users.py
               - expenses.py
               - approvals.py
               - policies.py
      - models/
         - company.py
         - user.py
         - expense.py
         - approval.py
         - policy.py
         - exchange_rate.py
      - schemas/
         - auth.py
         - user.py
         - expense.py
         - approval.py
         - policy.py
      - services/
         - approval_engine.py
         - currency_service.py
         - ocr_service.py
   - requirements.txt
   - .env.example
   - README.md

Execution commands:
- pip install -r backend/requirements.txt
- uvicorn app.main:app --reload --app-dir backend