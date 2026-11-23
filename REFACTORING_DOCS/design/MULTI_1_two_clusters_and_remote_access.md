# MULTI.1: two clusters at once, and working from home (proposed, 2026-11-23)

Status: **proposed**, a draft for Alexandre. Nothing here is accepted or implemented.

## The two needs

1. **Two clusters.** Flatiron has `rusty` and `popeye`. A large client run (many independent tasks, e.g. one star per
   task) should be able to use both at once, and AutoSlurm should keep track of what went where.
2. **Two places of work.** At the office, `ssh rusty` and `ssh popeye` reach the login nodes directly. From home, there
   is one more hop: first to Flatiron's SSH gateway, then from there to `rusty` or `popeye`. The same AutoSlurm
   commands, and the same recorded runs, should work in both places without editing profiles.

Constraints carried over: remote profiles hold only `ssh_alias` (HostName, User, keys stay in the operator's SSH
config); never fall back to local execution or to another profile silently; Flatiron's gateway is the only way in from
outside (never bypass it; no tunnels that let outside machines reach Flatiron's).

## Part A: working from home, with no change to profiles

### The idea

AutoSlurm already delegates every connection to `ssh`/`scp`/`rsync` with the profile's alias. So the place difference
belongs in the operator's `~/.ssh/config`, not in AutoSlurm: the alias `rusty` means "directly" at the office and
"through the gateway" at home. OpenSSH can choose by itself with `Match ... exec`, which runs a test command; the test
asks whether the login node answers directly.

### A sketch of `~/.ssh/config` (placeholders in angle brackets; names to be filled by Alexandre)

```sshconfig
# Connection sharing: one authentication per host and per day, reused by every ssh, scp and rsync AutoSlurm starts.
Host rusty popeye flatiron-gateway
    ControlMaster auto
    ControlPath ~/.ssh/control-%C
    ControlPersist 8h
    ServerAliveInterval 60

Host flatiron-gateway
    HostName <gateway host name>
    User <user>

# From home: the login node does not answer directly, so go through the gateway.
Match host rusty !exec "nc -z -G 2 <rusty login host> 22"
    ProxyJump flatiron-gateway
Match host popeye !exec "nc -z -G 2 <popeye login host> 22"
    ProxyJump flatiron-gateway

Host rusty
    HostName <rusty login host>
    User <user>
Host popeye
    HostName <popeye login host>
    User <user>
```

(`nc -z -G 2` is macOS's netcat: connect, two seconds' timeout, send nothing. At the office it succeeds and no jump is
added; at home it fails and `ProxyJump` routes through the gateway. Order matters: `Match` blocks come before the
`Host` blocks they amend, as OpenSSH takes the first value it meets.)

What this gives:

- The **same alias everywhere**, so a run submitted from the office and fetched from home uses its recorded transport
  (`ssh_alias: rusty`) unchanged. No `rusty-home` profile, no edits when moving.
- **One login a day.** AutoSlurm opens many short connections (status, logs, rsync of three directories, software
  update). Without connection sharing each could ask for the gateway's and the cluster's authentication again; with
  `ControlPersist`, the first `ssh rusty` of the day authenticates and the rest reuse it. The routine becomes: open a
  terminal, `ssh rusty` (and `ssh popeye`) once, then use `asl` and `gaia-seismo-jobs` as at the office.

### What AutoSlurm itself should add (small)

1. **Never wait on a prompt.** Pass `-o BatchMode=yes` to the `ssh`/`scp`/`rsync -e ssh` it starts, so a missing
   authentication fails at once instead of hanging in the background. The failure says what to do: "No open
   connection to `rusty` could be used without a password; run `ssh rusty` once in a terminal, then retry."
   (`transport.py`, `file_transfer.py`; the existing session-failure diagnostics in `errors.py`.)
2. **`asl connection check [--machine M | --all]`** (read-only): for each profile, `ssh -O check ALIAS` (is a shared
   connection open?) and, if not, a `BatchMode` probe `ssh ALIAS true` with a short timeout; it prints "ready",
   "needs login" or "unreachable". It never prompts and never starts a login itself.
3. **Documentation**: the SSH sketch above in the human docs (remote profiles), with the office/home behaviour and
   the rule that the gateway is the only way in.

Nothing in the profiles, run records or receipts changes.

### Open for Alexandre

- The gateway's host name and how it authenticates (key, password, second factor): `ControlPersist` covers all three,
  but whether Flatiron allows connection sharing through it should be checked with SCC.
- Whether AutoSlurm is driven from the laptop (both places) or sometimes from a login node (as `asl inspect` on
  `rusty4` today). From a login node no gateway is involved; from the laptop the sketch applies.

## Part B: both clusters at once

### What stays

- **One run, one machine.** A run, its bundle, its receipts and its software identity stay tied to one profile, as
  now. The 50-job limit and every scheduler rule are per cluster, so each machine's submission is checked on its own.
- Each cluster has its own profile: `ssh_alias`, `software_root` (its own single checkout, updated by
  `asl software update --machine M`), `results_root`, `venv_path`, `module_init`, `slurm_account`.

### What is new: a campaign

A **campaign** is a named group of runs of the same client work, one run per machine, with disjoint shares of the
array indices:

```text
campaign  grid-refinement-v1
  ├─ run grid-refinement-v1@rusty    indices 0–1499    (rusty profile, its bundle, receipts, code identity)
  └─ run grid-refinement-v1@popeye   indices 1500–1999 (popeye profile, …)
```

- **Planning** (client side, e.g. `gaia-seismo-jobs plan STUDY --machines rusty,popeye`): the client splits the
  indices by each pool's throughput (its cost model: tasks per hour per node type × the nodes it may use) and writes one
  ordinary run per machine plus a small campaign record (members, index ranges, the split's rationale). AutoSlurm
  provides the record type and its validation (ranges disjoint and covering, one machine per member), not the cost
  model.
- **Submitting**: one confirmation showing every member's resource view and the campaign total, then one ordinary
  submission per machine. A failure on one machine leaves the other's submission as it is and is reported per member;
  never retried blindly.
- **Software identity**: before submitting, `asl software status` (read-only) on each member's machine; the campaign
  requires the same commit on all, or says which machine is behind.
- **Following**: `asl inspect CAMPAIGN` aggregates members' states (and still shows each); `fetch` fetches each
  member from its own machine; `resubmit` rebuilds a member's bundle **on the machine where it runs, from the
  campaign record** (lesson of 2026-11-23: a resubmit from a stale run file ran yesterday's options).
- **Rebalancing** (later): move unstarted indices of a backlogged member to the other machine, as a new member over
  those indices; never two members over the same index.

### Data

Each member writes to its own machine's `results_root`. Steps that need everything in one place (a summary stage) run
after both members finish, from fetched outputs, as a separate run on one machine. Whether `rusty` and `popeye` share a
file system (ceph mounted on both, or not) decides whether inputs must be staged twice and how the summary gathers its
inputs: **open, to check.**

### Open for Alexandre

- Popeye's partitions, account and limits (the 50-job limit is assumed per cluster), its modules and a Python
  environment for client software (a second checkout under popeye's `software_root`).
- Shared file systems between the two clusters (above).
- Whether campaigns live in AutoSlurm (a new record type) or only in the client (which then calls AutoSlurm once per
  machine). The first gives one place to follow everything; the second keeps AutoSlurm's "one run, one machine" rule
  untouched. Proposed: the campaign record in AutoSlurm, as a thin grouping over unchanged runs.

## Order, if accepted

1. Part A's SSH config (operator only; no code) and `BatchMode` with its error message.
2. `asl connection check`.
3. The popeye profile and its checkout (operator), a smoke run there (one job), its log fetched from home.
4. The campaign record, then planning/submission/inspection over it, then client support in `gaia-seismo-jobs`.
