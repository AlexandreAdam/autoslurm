"""Compatibility imports; config owns machine configuration."""

from .config import load_config, save_config, machine_config, activation_command_from_config, is_remote_machine

__all__ = ["load_config", "save_config", "machine_config", "activation_command_from_config"]
