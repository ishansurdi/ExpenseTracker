# Backend Structure

Simple FastAPI backend structure (student-friendly).

## Folder Layout

- app/
	- main.py
	- config.py
	- database.py
	- models.py
	- schemas.py
	- auth.py
	- routes/
		- health.py
		- auth.py
		- users.py
		- expenses.py
		- approvals.py
		- policies.py
- requirements.txt
- .env.example

## Run

uvicorn app.main:app --reload --app-dir backend
