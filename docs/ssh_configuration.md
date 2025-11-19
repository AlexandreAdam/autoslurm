# SSH Configuration

AutoSlurm stores SSH credentials so it can reach remote machines. Every remote machine you add must already accept key-based authentication before AutoSlurm can copy files or submit jobs.

## Generate SSH keys

Run `ssh-keygen` once on your workstation:

```bash
ssh-keygen -t rsa -b 4096 -C "you@example.com"
```

It produces two files under `~/.ssh/`: the private key (`id_rsa`) stays on your workstation, and the public key (`id_rsa.pub`) is safe to share. 
The private key must remain secret. Do not copy it to the remote host.

## Install the public key on the remote machine

Use `ssh-copy-id` to append your public key to the remote account’s `~/.ssh/authorized_keys`:

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub username@hostname
```

After this step you can ssh with your private key without a password:

```bash
ssh username@hostname
```

If you cannot run `ssh-copy-id`, paste the contents of `~/.ssh/id_rsa.pub` into the remote file manually:

```bash
cat ~/.ssh/id_rsa.pub | ssh username@hostname 'cat >> ~/.ssh/authorized_keys'
```

## Configure `~/.ssh/config`

Create an entry to avoid repeating the details:

```
Host myremote
    HostName hostname
    User username
    IdentityFile ~/.ssh/id_rsa
```

You can now ssh using only the host keyword

```bash
ssh myremote 
```

Use `myremote` as the `hostname` field inside `~/.autoslurmconfig`, and AutoSlurm will fill in the rest automatically.

### Optional: Keep-alive for 2FA

If the cluster enforces two-factor authentication, enable connection multiplexing so AutoSlurm can reuse a single authenticated session:

```
Host myremote
    HostName hostname
    User username
    IdentityFile ~/.ssh/id_rsa
    ServerAliveInterval 60
    ControlMaster auto
    ControlPersist yes
    ControlPath ~/.ssh/sockets/%r@%h-%p
```

`ServerAliveInterval` avoids timeouts and `ControlMaster`/`ControlPersist` let you run many jobs without re-entering credentials after each command.
