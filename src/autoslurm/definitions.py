from .storage import config_file_path


__all__ = ["CONFIG_FILE_PATH", "MACHINE_KEYS", "DATE_FORMAT"]


DATE_FORMAT = "%Y%m%d%H%M%S"
CONFIG_FILE_PATH = config_file_path()
MACHINE_KEYS = [
    "ssh_alias",
    "results_root",
    "software_root",
    "storage_root",
    "venv_path",
    "env_command",
    "slurm_account",
]
