# Configuration

Run `autoslurm-configuration` to interactively define one or more machines and choose which one is considered the default. You can also inspect the current configuration without entering the menu by passing `--view`.

```bash
autoslurm-configuration --view
```
The default machine is the one AutoSlurm uses whenever `--machine` is omitted.

```bash
autoslurm-configuration
```

The first time you run the command it immediately prompts for the information needed to create a `local` machine (path, environment activation command, SLURM account) and stores it in `~/.autoslurmconfig`. 
On subsequent runs you get a menu:

1. **Update an existing machine** – edit the stored fields for any configured machine.
2. **Add a new machine** – create another entry (remote or local) and optionally mark it as the default.
3. **Change the default machine** – switch which machine auto-start routines and `autoslurm` commands use when no `--machine` flag is present.
4. **Exit** – leave the configuration untouched.

After you finish the menu, AutoSlurm ensures two directories exist inside its storage root: `jobs/` (job metadata) and `slurm/` (generated SLURM scripts). You can override the storage location by setting `AUTOSLURM_STORAGE_ROOT` before running the configuration command:

```bash
export AUTOSLURM_STORAGE_ROOT=/tmp/autoslurm_storage
autoslurm-configuration
```

The same command also creates those directories on every remote machine under `~/.autoslurm/` (the storage root is constant unless you configure a custom `path` per machine). When a remote machine is added the wizard asks whether you want to reference it via an SSH config alias or by providing the host URL plus username; whichever option you choose determines the fields that must be filled. Re-run `autoslurm-configuration` whenever you need to refresh credentials, add more machines, or change the default profile—it will recreate or synchronize the storage directories for you.

Refer to [SSH Configuration](ssh_configuration.md) for help preparing SSH keys, `ssh_config`, and common flags when defining remote machines.
