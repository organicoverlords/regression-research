# Linux OMEN execution node

Status: connected LAN execution node; user-owned; not a public MCP endpoint or scheduler.
Work identity: organicoverlords/regression-research#651.

## Purpose

This HP OMEN laptop is an optional Linux execution/build node behind the existing Windows MCP route. ChatGPT and other agents reach the Windows machine through the normal MCP transport, then use SSH over the local LAN to this laptop. Do not add another public MCP/Caddy/WireGuard serving path for this node.

## Stable access route from the Windows stack machine

Use the existing local SSH key and the laptop mDNS name:

```powershell
ssh -F NUL -4 -i "$env:USERPROFILE\.ssh\chatgpt-linux-aatuska-ed25519" -o BatchMode=yes -o ConnectTimeout=5 -o HostKeyAlias=192.168.0.128 aatuska@aatuska-OMEN-by-HP-Laptop-15-dc0xxx.local "<command>"
```

`-F NUL` intentionally avoids dependence on a user SSH config file. `HostKeyAlias=192.168.0.128` reuses the host key already verified during bootstrap while the mDNS hostname supplies DHCP-tolerant address discovery.

Never read, print, commit, or copy the private key contents. The key path is only a route pointer.

## Network observations

- Linux hostname: `aatuska-OMEN-by-HP-Laptop-15-dc0xxx`
- Linux user: `aatuska`
- mDNS: `aatuska-OMEN-by-HP-Laptop-15-dc0xxx.local`
- IPv4 observed 2026-09-06: `192.168.0.128/24`
- Windows IPv4 observed during bootstrap: `192.168.0.127/24`
- SSH TCP 22 was proven reachable from Windows and key-auth command execution was proven.
- Linux firewall was configured during bootstrap to allow SSH from the then-current Windows address `192.168.0.127`. Treat that address as an observation, not permanent authority; if Windows DHCP changes, SSH can fail until the firewall source rule is adjusted locally.

Before claiming the node is available, run a bounded live SSH probe using the route above. Do not infer liveness from this file, DHCP history, worker reports, or past successful runs.

## Hardware / OS capability snapshot

Observed live 2026-09-06:

- HP OMEN by HP Laptop 15-dc0xxx, board 84DB, BIOS F.03
- Linux Mint 21.3 (Virginia), Ubuntu jammy base
- Linux 5.15.0-141-generic, x86-64
- Intel Core i7-8750H, 6 cores / 12 threads, AVX2, up to 4.1 GHz
- ~15 GiB RAM, ~2 GiB swap
- NVIDIA GeForce GTX 1070 Mobile (GP104BM)
- 1 TB HGST HDD (`/dev/sda`) hosting Linux root
- 256 GB Samsung NVMe (`/dev/nvme0n1`), currently mostly NTFS and not used for Linux root
- 5 GHz Wi-Fi

GPU state at observation: PCI hardware is present, but no NVIDIA/nouveau kernel module was loaded and `nvidia-smi` could not communicate with the driver. `ubuntu-drivers devices` reported `nvidia-driver-580` as the distro-recommended driver. Reverify before GPU/CUDA work; this is not proof that the driver is installed now.

## Disk state and current attribution

Observed root filesystem: `/dev/sda2`, about 916 GiB, about 794 GiB used, about 75 GiB free (92% used).

A bounded `du` attribution established that the main consumption is user data, not Timeshift:

- `/home/aatuska`: 776,924,368 KiB (~741 GiB)
- `/home/aatuska/Työpöytä`: 752,715,404 KiB (~718 GiB)
- `/home/aatuska/Työpöytä/ei sopinu`: 664,177,220 KiB (~633 GiB)
- `/home/aatuska/Työpöytä/Nimetön kansio`: 71,227,364 KiB (~67.9 GiB)
- Timeshift plus filesystem-accounting difference was only about 27 GiB; five Timeshift snapshots exist from 2024-08 through 2025-06.

Do not delete, move, deduplicate, compress, or repurpose any of these large folders merely because they are large. They are user-owned data unless the user explicitly identifies exact disposable content.

## Unreal Engine development state

The current P3 project reports `EngineAssociation: 5.8` on the Windows repo. The laptop initially had Python 3.10, GCC 11.4 and Make, but lacked Git, Git LFS, pip, g++, CMake, Ninja, Node, Docker/Podman, CUDA and Rust.

`/home/aatuska/ue-setup.sh` was staged to install the baseline Linux UE development packages. Its first privileged run stopped at `apt-get update` because the pre-existing Spotify apt repository has a missing signing key (`NO_PUBKEY 5384CE82BA52C83A`). Do not disable repository signature verification. Repair or disable only that stale third-party repository through the normal apt source owner before rerunning package installation.

UE-specific source/toolchain setup remains repo/engine-owned: once the UE 5.8 source tree is available on Linux, use Epic's `Setup.sh`/`GenerateProjectFiles.sh` path rather than substituting a guessed system compiler for the engine-provided Linux toolchain.

## Boundaries

- Optional compute/build node only; not current product authority, worker scheduler, queue, or shared production control plane.
- Windows MCP remains the ChatGPT transport owner. SSH is a hop behind it.
- No router port-forwarding or public TCP 22 exposure.
- No destructive disk cleanup without exact positive evidence that the target is disposable/recoverable.
- No assumption that claims, schedules, or this contract prove current worker activity or node liveness.
- Reverify GPU driver, free disk, RAM and SSH before heavy UE build/cook/render use.
- Avoid duplicate heavy UE builds; follow the owning repo's single-flight/build-admission contract.
