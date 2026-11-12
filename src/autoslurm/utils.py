"""Compatibility imports; configuration and transport have dedicated owners."""

from datetime import datetime
from .definitions import DATE_FORMAT
from .configuration import load_config, save_config, machine_config, activation_command_from_config
from .transport import ssh_host_from_config, scp_host_and_keypath_from_config, remote_storage_root_from_config
from .bundle_metadata import update_job_info_with_id, update_job_metadata

__all__ = ["load_config", "save_config", "machine_config", "remote_storage_root_from_config", "activation_command_from_config"]


def name_slurm_script(job: dict, date: datetime):
    name = job["name"]
    identity = job.get("_autoslurm_submission", {}).get("submission_id")
    if identity:
        return f"{name}_{identity}.sh"
    return f"{name}_{date.strftime(DATE_FORMAT)}.sh"
