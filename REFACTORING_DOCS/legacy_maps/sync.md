# Sync Flow

This chart shows how the current sync command discovers the remote storage root
and mirrors the remote storage directories locally.

```mermaid
flowchart TD
    A[autoslurm sync] --> B[apps/sync.py: main]
    B --> C[sync.sync_machine]

    C --> D[utils.machine_config]
    C --> E[_is_remote]
    C --> F[_remote_storage_root]
    C --> G[utils.activation_command_from_config]
    C --> H[_remote_ssh_command]
    C --> I[_remote_dir_exists]
    C --> J[_rsync_command]
    C --> K[storage.storage_root]
    C --> L[utils.scp_host_and_keypath_from_config]

    F --> M[ssh]
    F --> N[python -c 'from autoslurm.storage import storage_root']
    I --> O[ssh test -d]
    J --> P[rsync]
    J --> Q[ssh transport]
```

## Main Dependencies

- `apps/sync.py` is just the CLI wrapper.
- `sync.py` handles machine resolution, remote path discovery, and rsync calls.
- `utils.py` provides machine configuration and SSH helpers.
- `storage.py` provides the local root and directory layout.
- `ssh` and `rsync` are the external tools that actually move data.

