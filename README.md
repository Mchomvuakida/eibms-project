# ES & RI Integrated Business Management System (EIBMS)

A web-based business management system built for **ES & RI Enterprises**, a multi-branch construction materials company in Tanzania. Developed as a final-year diploma project at Warsaw University of Technology, 2026.

---

## What it does

EIBMS replaces manual paper records with a centralized digital system covering:

- **Multi-branch inventory management** — real-time stock tracking across Same and Ishinde branches with low-stock alerts
- **Production tracking** — records transformation of raw materials (cement, sand) into finished products (concrete blocks) with automatic stock deduction
- **Sales management** — records sales, handles cash/credit/partial payments, tracks customer balances
- **Expense management** — categorizes expenses for Tanzania Revenue Authority (TRA) tax reporting with CSV export
- **Fleet management** — tracks truck trips, fuel, maintenance costs and calculates per-truck profitability
- **Customer credit management** — monitors overdue balances and records repayments
- **Profit & Loss reports** — monthly financial performance using Pandas data analysis
- **REST API** — JWT-secured endpoints for future mobile app integration

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Django 5.2 LTS |
| Database | SQLite (development), PostgreSQL (production) |
| Data Analysis | Pandas |
| Frontend | HTML5, Bootstrap 5, Chart.js |
| API | Django REST Framework + JWT |
| Deployment | Railway |
| Version Control | Git & GitHub |

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Mchomvuakida/eibms-project.git
cd eibms-project
```

### 2. Create and activate virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your .env file

Create a file called `.env` in the project root with:

```
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=sqlite:///db.sqlite3
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create a superuser (admin account)

```bash
python manage.py createsuperuser
```

### 7. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

---

## User Roles

| Role | Access |
|---|---|
| **Admin** | Full access to everything including admin panel |
| **Owner** | Full access to all branches and all reports |
| **Branch Manager** | Full access to their branch + all reports for their branch |
| **Clerk** | Sales, expenses, stock purchase, production for their branch only |
| **Viewer** | Read-only access |

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/token/` | POST | Get JWT access token |
| `/api/token/refresh/` | POST | Refresh JWT token |
| `/api/dashboard/` | GET | Business summary (branch-filtered) |
| `/api/stock/` | GET | Current stock levels |

All API endpoints require JWT authentication. Get a token first via `/api/token/` with your username and password.

---

## Project Structure

```
eibms-project/
├── core/                   # Main application
│   ├── models.py           # Database models (11 models)
│   ├── views.py            # Business logic and views
│   ├── urls.py             # URL routing
│   ├── forms.py            # Django forms
│   ├── middleware.py       # Branch isolation middleware
│   └── admin.py            # Admin panel configuration
├── eibms/                  # Project settings
│   ├── settings.py
│   └── urls.py
├── templates/              # HTML templates
│   └── core/
├── static/                 # CSS, JS, images
├── media/                  # Uploaded receipt images
├── .env                    # Environment variables (not in git)
├── requirements.txt        # Python dependencies
└── manage.py
```

---

## Business Context

ES & RI Enterprises operates two construction materials branches in Tanzania:
- **Same Branch** — sales, hardware, timber
- **Ishinde Branch** — concrete block production, pebbles

Before this system, all records were kept on paper. The owner had no visibility into where cash was going, could not prove expenses to TRA, and had no way to track which truck or branch was most profitable.

---

## Author

**Akida Mchomvu**
Computer Science Diploma — Warsaw, 2026
Supervisor: dr. eng. Marcin Kacprowicz