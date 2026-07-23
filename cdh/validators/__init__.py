from cdh.validators.ears import run_ears_check
from cdh.validators.fr_namespace import run_fr_check
from cdh.validators.bdd import run_bdd_check
from cdh.validators.dag import run_dag_check

__all__ = [
    "run_ears_check",
    "run_fr_check",
    "run_bdd_check",
    "run_dag_check",
]

_CHECK_RESULT_SCHEMA = {
    "passed": bool,
    "checks": list,
}
