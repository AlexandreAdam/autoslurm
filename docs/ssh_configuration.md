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

Alias/root edits only save local configuration. The interactive config validation
checks SSH connectivity and environment activation/import. Complete path/access
checks are not yet implemented in config; see [config](configuration.md).

Saved runs retain their producing alias rather than adopting a new profile's
alias. Editing the SSH entry itself can change its destination; the record does
not pin the underlying server or credentials. Older recorded explicit transports
remain readable for historical job management.
