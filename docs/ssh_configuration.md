# SSH configuration

AutoSlurm uses your existing SSH configuration. It stores an alias, while SSH
owns the actual server name, username, identity file, proxy settings and other
connection options. Prepare authentication through your normal cluster setup.

For example, an entry in `~/.ssh/config` can look like:

```sshconfig
Host research-cluster
    HostName login.example.edu
    User your-account
    IdentityFile ~/.ssh/your-existing-key
```

The `Host` label is the value to select in AutoSlurm:

```sh
asl config --machine cluster --ssh-alias research-cluster
```

```json
{
  "ssh_alias": "research-cluster"
}
```

SCP, rsync, status, log retrieval and submission use the same alias. AutoSlurm's
current profiles do not duplicate HostName, User or IdentityFile and do not read
private key contents. Normal SSH configuration (including any includes) is
interpreted by SSH, rather than reimplemented by AutoSlurm.

Before a remote submission session, AutoSlurm reads effective settings with
`ssh -G <alias>`; this does not connect. A configured ControlPath together with
`ControlMaster auto`/`autoask` or enabled ControlPersist makes connection sharing
user-owned. Submission adds no Control options and never explicitly starts or
closes that connection. SSH can reuse it or start it under your settings.

Otherwise AutoSlurm opens and closes its own temporary master. On POSIX its
socket lives at `/tmp/asl-ssh-*/cm-%C`, avoiding macOS's long default temporary
paths. If `/tmp` is absent it uses the default temporary directory. Only its own
session directory is removed. Failed or unreadable `ssh -G` output falls back to
this owned session once, without retrying the configuration check. This adds no
profile settings and does not change SSH configuration or authentication.

Owned-session failures now identify the alias, failed stage and local socket
path, with safe native error facts. The expanded POSIX socket path is checked
before opening; opening and closing have 30/10-second timeouts. Addressing is
validated before allocating a directory, and the destination/socket options are
kept fixed during the operation. Arbitrary SSH output is omitted from normal
diagnostics; this does not diagnose a particular password, gateway or 2FA issue.

Cleanup failures are reported, including a failed close command or directory
removal. **Jobs can already be accepted when cleanup fails.** In Python, retain
`SubmissionError.receipt` and check its state and IDs: a submitted receipt stays
submitted. The receipt's `session_cleanup_diagnostics` records local cleanup
issues, and a later receipt refresh preserves them. A removed socket directory
does not prove that the owned master closed; it may persist until ControlPersist
expires. Do not submit the same work again merely because cleanup failed.

If opening/submission already failed, that original failure stays primary;
cleanup details are secondary evidence. Direct session calls preserve original
bugs/interrupts, while tracked submission preserves them as the exception cause
alongside its receipt. AutoSlurm still attempts local directory cleanup after a
failed close, without closing another connection or retrying submission. See
[failure interpretation](errors.md#ssh-session-resources-and-cleanup).

Alias/root edits only save local configuration. The interactive config validation
checks SSH connectivity and environment activation/import. Complete path/access
checks are not yet implemented in config; see [config](configuration.md).

Saved runs retain their producing alias rather than adopting a new profile's
alias. Editing the SSH entry itself can change its destination; the record does
not pin the underlying server or credentials. Older recorded explicit transports
remain readable for historical job management.

Filesystem metadata checks (`path_exists` and sync directory probes) require
python3 through the selected SSH alias; they do not import or install AutoSlurm
on that host. A failed probe raises rather than claiming absence. Probe/mkdir
commands use 30-second timeouts; SCP/rsync use 300 seconds. A timed-out copy may
have left partial files; there is no automatic retry or rollback. `asl sync
--debug` exposes original causes. See [file-operation failures](errors.md#paths-transfers-and-sync-mvp104c).

## Check access without an interactive prompt

```sh
asl connection check --machine rusty
asl connection check --all --json
```

The check runs a bounded no-op from the host where AutoSlurm is running. Each
profile reports ready, local (no SSH needed), or unavailable with timestamp and
diagnostic; it checks neither Slurm nor your scientific environment. A failed
member does not discard the other results. JSON is available and partial checks
exit 1. The Python equivalent is check_connections; agents can use ACP action
check_connections or request the installed 19_connections recipe.

Ordinary SSH/SCP/rsync commands now use noninteractive authentication and a
10-second connection timeout; probes have a 12-second process deadline. Direct
remote sbatch has a 60-second deadline, the bulk driver 300 seconds. A submission
timeout is an uncertain outcome: preserve its receipt and inspect before retrying.
Configured connection-sharing ownership remains unchanged. SSH itself may create
operator-configured connection state. Arbitrary jump/proxy configurations need
both hops checked; an outer BatchMode flag alone is not proof of that behavior.

At home Alexandre currently uses ssh flatiron, authenticates there, then runs ssh
rusty or ssh popeye inside the gateway. This does not make ssh rusty on the laptop
work. AutoSlurm does not automate that interactive session or enter passwords/2FA.
`flatiron` is a jump point only; do not install or run AutoSlurm, agents or
helpers there, or use it for campaign storage. A permitted laptop jump route or
a controller on a permitted cluster login node still needs operator verification;
moving controllers also needs access to the run records. A cluster login node's
access to the other cluster is not assumed.
An SSH failure alone does not establish that authentication is the problem.
