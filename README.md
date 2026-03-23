# mock-automation
    A scalable browser automation pipeline that solves
    a foreseeable problem with a web-based system that requires a manual refresh.

    This project demonstrates how to automate, orchestrate, and monitor that process.
    Adaptable to almost any systems.

# Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Airflow     │──▶│  Playwright  │───▶│   Mock Reporting │   │
│  │  Scheduler   │    │  Automation  │    │   Portal (Flask) │   │
│  │  (DAG)       │    │  (Python)    │    │                  │   │
│  └──────┬───────┘    └──────────────┘    └──────────────────┘   │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │    MySQL     │◀───│  Tableau Monitoring Dashboard        │  │
│  │  Job Tracker │    │  (read-only connection)              │   │
│  └──────────────┘    └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

| Component | Technology | Purpose |
|---|---|---|
| Browser Automation | Python + Playwright | Logs in, clicks refresh per location |
| Orchestration | Apache Airflow | Nightly scheduling, batching, retries |
| Job Tracking | MySQL | Per-location run status and audit log |
| Containerization | Docker / Docker Compose | Fully self-hosted, no external SaaS |
| Monitoring | Tableau | Dashboard for ops and finance leadership |
| Mock Portal | Flask | Simulates the legacy reporting system |

---

# Decision-making Process

*Playwright over Selenium*
    Selenium requires server configuration,
    potential security risk.

*Airflow over cron* 
    Scales automatically to any location count.
    UI lets non-technical ops staff monitor runs.
    Exponential backoff retry logic to handle failures.

*Self-hosted, no third-party SaaS*
The entire pipeline runs on-premises or within owned cloud account.
No data transits external platforms. 
Critical for PHI/HIPAA, CLIA.


# HIPAA / Data Governance Sensitivity Layer

This automation layer is designed with compliance in mind:

| Control | Implementation |
|---|---|
| No sensitive data in the pipeline | Automation only *triggers* refreshes — it never reads, stores, or transmits report content |
| Audit logging | Every action (login, refresh start, complete) written to `audit_log` with timestamp and actor |
| Encrypted connections | HTTPS for the target portal; SSL-capable MySQL connections |
| On-premises execution | Docker stack runs entirely within the organization's own infrastructure |
| Least-privilege DB access | Tableau uses a read-only MySQL account; Airflow uses a separate write account |
| No credentials in code | All secrets passed via environment variables or Docker secrets |

---

# Project Structure
```
mock-automation/
├── mock_app/                        # Simulated legacy reporting portal
│   ├── app.py                       # Flask app: login, dashboard, refresh endpoint
│   ├── Dockerfile
│   └── requirements.txt
│
├── automation/                      # Core Playwright automation layer
│   ├── refresh_runner.py            # Async batch runner with MySQL job logging
│   ├── Dockerfile
│   └── requirements.txt
│
├── airflow/
│   └── dags/
│       └── reporting_refresh_dag.py # Nightly DAG batching, retries, completion check
│
├── db/
│   └── migrations/
│       └── 001_initial_schema.sql   # locations, refresh_jobs, run_summaries, audit_log
│
├── tableau/
│   └── queries.sql                  # MySQL views for Tableau monitoring dashboard
│
├── docker-compose.yml               # Full stack — one command startup
├── .env.example                     # Credential template (never commit .env)
└── README.md
```

# Running the Project

## Prerequisites
- Docker Desktop
- Git

## Start the stack
```bash
git clone https://github.com/devbrown272/mock-automation.git
cd mock-automation
docker compose up --build
```

| Interface | URL | Credentials |
|---|---|---|
| Mock Reporting Portal | http://localhost:5001 | admin / password |
| Airflow UI | http://localhost:8080 | admin / admin |

### Trigger a manual run

In Airflow UI: **DAGs → reporting_nightly_refresh → Trigger DAG**

Or run directly:
```bash
docker exec refresh_automation python refresh_runner.py --locations 1,2,3 --concurrency 3
```

# Scalability

Designed for 2,000+ locations with no architectural changes:

- `REFRESH_BATCH_SIZE` and `REFRESH_CONCURRENCY` are Airflow Variables — adjustable from the UI with no redeployment
- Each Playwright session is stateless and independently retryable
- At 10 concurrent sessions and ~3 seconds per location, 1,800 locations complete in roughly 9 minutes

# Extending This Project

- **Alerting** — Add email or alerts in `completion_check` when success rate drops below threshold
- **Delta refresh** — Track which locations had data changes and only refresh those
- **API layer** — If the target system exposes undocumented endpoints, replace browser automation with direct HTTP calls for significant speed gains
- **Tableau Server** — Publish the monitoring dashboard so leadership has live visibility without desktop access