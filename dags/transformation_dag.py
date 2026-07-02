from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.sensors.external_task import ExternalTaskSensor

default_args = {
    "owner": "dataflow-eu",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}

def _run_dbt(command: str, select: str | None = None) -> dict:
    import shutil
    import subprocess
    import structlog

    log = structlog.get_logger("transformation_pipeline")

    dbt_bin = shutil.which("dbt")
    if not dbt_bin:
        raise RuntimeError("Binário 'dbt' não encontrado no PATH do container.")

    cmd = [
        dbt_bin,
        command,
        "--project-dir",
        "/opt/airflow/dbt",
        "--profiles-dir",
        "/opt/airflow/dbt",
        "--target",
        os.environ.get("DBT_TARGET", "prod"),
    ]
    if select:
        cmd += ["--select", select]

    log.info("dbt_command_started", command=command, select=select, dbt_bin=dbt_bin)
    result = subprocess.run(cmd, capture_output=True, text=True)

    log.info("dbt_stdout", command=command, output=result.stdout[-3000:])
    if result.stderr:
        log.info("dbt_stderr", command=command, output=result.stderr[-3000:])

    if result.returncode != 0:
        error_output = result.stderr.strip() or result.stdout.strip() or "sem output capturado"
        raise RuntimeError(f"dbt {command} failed (returncode={result.returncode}):\n{error_output[-3000:]}")

    log.info("dbt_command_succeeded", command=command, select=select)
    return {"command": command, "select": select, "status": "success"}

# CORREÇÃO: Como os horários agora são iguais, o sensor deve olhar a mesma data!
def check_execution_mode(logical_date, **context):
    """
    Check if the DAG was triggered manually or scheduled.
    Como os horários foram alinhados para as 06:00, ambas usam o mesmo logical_date.
    """
    return logical_date

@dag(
    dag_id="transformation_pipeline",
    description="Run dbt Bronze -> Silver -> Gold transformations after extraction",
    start_date=datetime(2019, 1, 1),
    schedule_interval="0 6 1 * *",
    catchup=True,                  
    max_active_runs=1,
    default_args=default_args,
    tags=["silver", "gold", "dbt", "transformation"],
)
def transformation_pipeline():
    wait_for_extraction = ExternalTaskSensor(
        task_id="wait_for_extraction",
        external_dag_id="extraction_pipeline",
        external_task_id="summarize_extraction",
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        execution_date_fn=check_execution_mode, # CORREÇÃO: Usa a função inteligente
        timeout=3600,
        poke_interval=60,
        mode="reschedule",
    )

    @task(task_id="dbt_deps")
    def dbt_deps() -> dict:
        return _run_dbt("deps")

    @task(task_id="dbt_run_bronze")
    def dbt_run_bronze() -> dict:
        return _run_dbt("run", select="tag:bronze")

    @task(task_id="dbt_run_silver")
    def dbt_run_silver() -> dict:
        return _run_dbt("run", select="tag:silver")

    @task(task_id="dbt_run_gold")
    def dbt_run_gold() -> dict:
        return _run_dbt("run", select="tag:gold")

    @task(task_id="dbt_test_all")
    def dbt_test_all() -> dict:
        return _run_dbt("test")

    @task(task_id="summarize_transformation")
    def summarize_transformation(bronze: dict, silver: dict, gold: dict, tests: dict) -> None:
        import structlog
        structlog.get_logger("transformation_pipeline").info(
            "transformation_summary", bronze=bronze, silver=silver, gold=gold, tests=tests
        )
    deps = dbt_deps()
    bronze = dbt_run_bronze()
    silver = dbt_run_silver()
    gold = dbt_run_gold()
    tests = dbt_test_all()
    summary = summarize_transformation(bronze, silver, gold, tests)
    wait_for_extraction >> bronze >> silver >> gold >> tests >> summary

transformation_pipeline()