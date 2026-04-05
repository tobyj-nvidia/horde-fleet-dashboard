# Accessing the Fleet Dashboard via SSH Tunnel

The fleet dashboard listens on `127.0.0.1:8080` and is **never exposed via Kubernetes NodePort or any public interface**. Access is localhost-only, forwarded over SSH.

## Quick Reference

### One-shot tunnel (foreground)
Opens the tunnel and keeps it alive in your terminal session. Close with Ctrl-C.

```sh
ssh -L 8080:127.0.0.1:8080 horde@<hub-ip>
```

Then open `http://localhost:8080` in your browser.

### Background tunnel
Forks into the background immediately after authenticating.

```sh
ssh -fNL 8080:127.0.0.1:8080 horde@<hub-ip>
```

To kill it later:

```sh
pkill -f "ssh -fNL 8080"
```

### Fleet SSH key variant
If you use a dedicated identity file for fleet hosts:

```sh
ssh -i ~/.ssh/horde_fleet_key -L 8080:127.0.0.1:8080 horde@<hub-ip>
```

### SSH config shortcut
Add an entry to `~/.ssh/config` to avoid repeating flags:

```
Host horde-hub
    HostName <hub-ip>
    User horde
    IdentityFile ~/.ssh/horde_fleet_key
    LocalForward 8080 127.0.0.1:8080
```

Then connect with:

```sh
ssh horde-hub
```

The `LocalForward` directive forwards `localhost:8080` on your machine to `127.0.0.1:8080` on the hub for the duration of the session.

## Security Note

The dashboard is intentionally localhost-only. Do not expose port 8080 via `0.0.0.0` binding, firewall rules, or K8s NodePort — the SSH tunnel is the intended access path.
