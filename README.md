# 💰 Expense Reimbursement Management System

A simple and powerful system for employees to submit expense reports and for managers/finance teams to approve and track them.

## 🎯 What is This?

This is a web application that helps companies manage employee expense reimbursements. It replaces the manual spreadsheet process with an organized, automated workflow.

**For Employees:** Submit your business expenses and track approval status  
**For Managers:** Review and approve employee expenses  
**For Finance:** Process approved expenses and generate reports  
**For Admins:** Manage company policies and user access  

## 🚀 Key Features

- **User Roles:** Employees, Managers, Finance Team, CFO, Admins
- **Approval Workflow:** Multi-stage approval process (Manager → Finance → CFO)
- **Expense Tracking:** Submit, track, and manage reimbursement requests
- **Dashboard:** Different views for each user role
- **Audit Trail:** Login history and expense approval records
- **Company Management:** Multi-company support with separate data isolation

## 🛠️ Tech Stack

**Backend:** Python FastAPI  
**Database:** PostgreSQL  
**Frontend:** HTML + Tailwind CSS  
**Authentication:** JWT tokens with refresh tokens  

## 📋 Quick Start

### Setup Requirements
- Python 3.8+
- PostgreSQL database
- `.env` file configured (see `.env.example`)

### Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create PostgreSQL database and run schema:**
   ```bash
   psql -U your_user -d your_database -f schema.sql
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

4. **Start the backend:**
   ```bash
   uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
   ```

5. **Open in browser:**
   ```
   http://localhost:8000
   ```

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app setup
│   ├── database.py          # PostgreSQL connection
│   ├── auth.py              # Login & password hashing
│   ├── models.py            # Database tables
│   ├── schemas.py           # Request/response formats
│   ├── config.py            # Settings & env variables
│   └── routes/              # API endpoints
│       ├── auth.py          # Login/signup
│       ├── users.py         # User management
│       ├── expenses.py      # Submit & list expenses
│       ├── approvals.py     # Approve/reject expenses
│       ├── admin_dashboard.py
│       ├── workflow_dashboard.py
│       └── health.py        # Health check
├── schema.sql               # Database setup
├── requirements.txt         # Python dependencies
└── .env.example             # Environment template

frontend/
├── index.html               # Home page
├── login.html               # Login page
├── signup.html              # Registration
├── employee-dashboard.html  # Employee view
├── manager-dashboard.html   # Manager view
├── finance-dashboard.html   # Finance view
└── admin-dashboard.html     # Admin view
```

## 🤝 How It Works

1. **Employee** submits an expense report with details
2. **Manager** reviews and approves/rejects (Stage 1)
3. **Finance Team** reviews and approves/rejects (Stage 2)
4. **CFO** does final approval if needed (Stage 3)
5. **System** processes reimbursement once fully approved

## 📝 Notes

- All data is multi-company isolated (companies have separate data)
- Passwords are hashed using bcrypt for security
- Session tokens expire automatically
- Full audit trail of all approvals and login attempts
