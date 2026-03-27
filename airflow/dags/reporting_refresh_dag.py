"""
airflow/dags/reporting_refresh_dag.py
-
Schedule: Nightly at 2:00 AM local time
Strategy:
  - Splits locations into batches
  - Each batch runs in parallel via Playwright
  - Failed locations are retried up to 3 times with exponential backoff
  - A completion check validates overall success rate after all batches finish

Airflow Variables (set in UI → Admin → Variables):
  REFRESH_CONCURRENCY   Parallel browser sessions per batch (default: 10)
  REFRESH_BATCH_SIZE    Locations per task group (default: 200)
  REFRESH_TOTAL_LOCS    Total location count (default: 1800)
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup

log = logging.getLogger(__name__)

CONCURRENCY  = int(Variable.get("REFRESH_CONCURRENCY", default_var=5))
BATCH_SIZE   = int(Variable.get("REFRESH_BATCH_SIZE",  default_var=20))
TOTAL_LOCS   = int(Variable.get("REFRESH_TOTAL_LOCS",  default_var=20))

ALL_IDS = [str(i) for i in range(1, TOTAL_LOCS + 1)]
BATCHES = [ALL_IDS[i : i + BATCH_SIZE] for i in range(0, len(ALL_IDS), BATCH_SIZE)]

default_args = {
    "owner": "finance-ops",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}

def run_location_batch(batch_index: int, location_ids: list, **context):
    import asyncio, os, sys
    sys.path.insert(0, "/opt/airflow/dags")
    os.environ["REPORT_URL"]  = os.getenv("REPORT_URL",  "http://mock_portal:5001")
    os.environ["REPORT_USER"] = os.getenv("REPORT_USER", "admin")
    os.environ["REPORT_PASS"] = os.getenv("REPORT_PASS", "password")
    log.info("Batch %d: %d locations", batch_index, len(location_ids))
    from refresh_runner import run_batch
    asyncio.run(run_batch(location_ids, concurrency=CONCURRENCY, headless=True))

def check_completion(**context):
    import aiomysql, asyncio, os
    async def _check():
        pool = await aiomysql.create_pool(
            host=os.getenv("DB_HOST", "mysql"), user=os.getenv("DB_USER", "pipeline_user"),
            password=os.getenv("DB_PASS", "pipeline_pass"), db=os.getenv("DB_NAME", "refresh_jobs"),
            autocommit=True
        )
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT COUNT(*), SUM(status='complete'), SUM(status='error'), SUM(status='timeout')
                    FROM refresh_jobs WHERE DATE(started_at) = CURDATE()
                """)
                row = await cur.fetchone()
                pool.close()
                return row
    total, complete, errors, timeouts = asyncio.run(_check())
    rate = (complete / total * 100) if total else 0
    log.info("%.1f%% complete (%d/%d) | errors: %d | timeouts: %d", rate, complete, total, errors, timeouts)
    if rate < 95.0:
        raise ValueError(f"Success rate {rate:.1f}% below 95% threshold")

with DAG(
    dag_id="reporting_nightly_refresh",
    default_args=default_args,
    description="Nightly report refresh for all retail locations",
    schedule_interval="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["finance", "reporting", "automation"],
) as dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end")

    with TaskGroup("location_batches") as batch_group:
        for idx, batch in enumerate(BATCHES):
            PythonOperator(
                task_id=f"batch_{idx:03d}__locs_{batch[0]}_to_{batch[-1]}",
                python_callable=run_location_batch,
                op_kwargs={"batch_index": idx, "location_ids": batch},
                pool="refresh_browser_pool",
                execution_timeout=timedelta(hours=1),
            )

    completion_check = PythonOperator(
        task_id="completion_check",
        python_callable=check_completion,
        trigger_rule="all_done",
    )

    start >> batch_group >> completion_check >> end