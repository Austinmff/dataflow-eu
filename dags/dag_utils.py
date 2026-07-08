"""Funções compartilhadas entre DAGs — sem instanciar nenhuma DAG aqui."""

def check_execution_mode(logical_date, **context):
    """
    Check if the DAG was triggered manually or scheduled.
    Como os horários foram alinhados para as 06:00, ambas usam o mesmo logical_date.
    """
    return logical_date