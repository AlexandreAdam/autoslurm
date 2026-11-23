# Connection reachability from this controller

Use public `check_connections(machine=None, all_machines=False)` or
`asl connection check --machine NAME` / `--all` (`--json` for evidence).
ACP action check_connections accepts machine or all_machines. Bare connection
prints help. Invalid selection is an operation diagnostic; expected per-machine
failures remain rows beside successful observations. CLI exits 1 when any probe
is unavailable. Unexpected bugs/interrupts remain visible.

Result state observed/partial, machines rows with machine, ssh_alias, timestamp,
state ready/local/unavailable and optional diagnostic. Local means no SSH probe
was needed; ready proves only a noninteractive no-op at the observation time.
It does not establish Slurm/environment/GPU readiness or a reusable master.
No env_command, activation or scientific imports. At most 32 profiles, each
SSH probe capped at 12 seconds, connection timeout 10 seconds, discarded output.
No scheduler calls or persistent AutoSlurm observations are written.

All ordinary SSH/SCP/rsync adapters now supply BatchMode=yes and ConnectTimeout=10.
Owned/borrowed submission-session ownership and recorded destinations remain.
Operator SSH configuration may create its usual connection state; arbitrary
ProxyCommand/ProxyJump behavior is operator-owned and must be verified on both hops.
No keys/passwords/codes, SSH config edits, retry or fallback are managed here.

Alexandre's current home route is laptop ssh flatiron, then ssh rusty or ssh
popeye from the gateway. A gateway shell does not give subsequent laptop commands
that route. A permitted working jump configuration or an explicitly selected
controller inside the network is still needed. A failed SSH command (including
exit 255) does not prove authentication is the cause. Preserve that uncertainty.
