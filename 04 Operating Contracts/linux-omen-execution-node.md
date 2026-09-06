# Linux OMEN execution node

Status: connected LAN execution node; user-owned; not a public MCP endpoint or scheduler.
Work identity: organicoverlords/regression-research#651. NVMe production-storage work: #661.

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

GPU state verified 2026-09-06: the NVIDIA 535.230.02 userspace/DKMS stack is installed and current-kernel `nvidia*.ko` modules exist, but Secure Boot is enabled and the local MOK certificate used to sign the DKMS module is **not enrolled**. Kernel lockdown logged that unsigned module loading is restricted, so the NVIDIA module does not load and `nvidia-smi` cannot communicate with the GPU. `ubuntu-drivers devices` reports `nvidia-driver-580` as recommended; a 580.173.02 offline package bundle is staged under `~/.local/ue-bootstrap/debs/nvidia-driver-580.tar.gz`, but installing/upgrading the system driver and enrolling MOK require privileged/reboot-time interaction. Do not bypass Secure Boot or module-signature enforcement.

## Disk state and current attribution

Observed root filesystem: `/dev/sda2`, about 916 GiB, about 794 GiB used, about 75 GiB free (92% used).

A bounded `du` attribution established that the main consumption is user data, not Timeshift:

- `/home/aatuska`: 776,924,368 KiB (~741 GiB)
- `/home/aatuska/Ty├Âp├Âyt├ñ`: 752,715,404 KiB (~718 GiB)
- `/home/aatuska/Ty├Âp├Âyt├ñ/ei sopinu`: 664,177,220 KiB (~633 GiB)
- `/home/aatuska/Ty├Âp├Âyt├ñ/Nimet├Ân kansio`: 71,227,364 KiB (~67.9 GiB)
- Timeshift plus filesystem-accounting difference was only about 27 GiB; five Timeshift snapshots exist from 2024-08 through 2025-06.

Do not delete, move, deduplicate, compress, or repurpose any of these large folders merely because they are large. They are user-owned data unless the user explicitly identifies exact disposable content.

## NVMe production fast-storage lane

The Samsung NVMe fast-storage lane was provisioned on 2026-09-06 after NTFS consistency checks and pre-change GPT/partition-table backups:

- `/dev/nvme0n1`: 238.5 GiB total
- `p1`: 260 MiB FAT32 EFI, preserved and mounted at `/boot/efi`
- `p2`: 16 MiB Microsoft reserved, preserved
- `p3`: 90 GiB NTFS `Windows`, preserving partition UUID `190d7b09-e0d0-4d2a-87a1-a9593d888a1f`
- `p4`: 980 MiB NTFS Windows recovery, preserved
- `p5`: 147.2 GiB ext4 `UE_FAST`, UUID `a6c05af1-0ede-4327-9fec-0411ac6628ee`, mounted at `/mnt/ue`

`/mnt/ue` is persisted in `/etc/fstab` by filesystem UUID with `defaults,noatime,nofail,x-systemd.device-timeout=10s`. The user-owned directories are `/mnt/ue/engine`, `/mnt/ue/projects`, `/mnt/ue/build`, `/mnt/ue/cache`, `/mnt/ue/tmp`, `/mnt/ue/toolchains`, and `/mnt/ue/bootstrap`. It is the preferred fast-storage lane for UE source, build intermediates, Derived Data Cache / other rebuildable caches, project worktrees that explicitly opt into the node, the Epic native toolchain, and temporary build material. The HDD remains the Linux root and user-media owner; do not move or delete user media merely to make UE space.

Live post-provision checks passed for partition preservation, ext4 identity, UUID-backed `/mnt/ue`, user write/read/delete access, `/boot/efi`, `findmnt --verify`, and the enabled/active `omen-ue-fast-ready.service`. A root-owned fixed-action helper at `/usr/local/sbin/omen-agent-admin` exposes only `status`, `verify-storage`, `mount-ue`, and `restart-ready`; `aatuska` may invoke that exact helper through sudo without a password. This is intentionally not a general passwordless root shell. User login shells also place `~/.local/bin` first in `PATH`; `~/.local/bin/sudo` forces noninteractive `sudo -n`, so unsupported privileged commands fail immediately instead of opening another password prompt. Agents must use rootless tooling or the fixed-action helper rather than asking the user to authenticate repeatedly.

Reboot persistence is **explicitly deferred by current user instruction**. Do not reboot this laptop or ask for a reboot merely to continue development. `/mnt/ue` is approved for live UE work now because UUID-backed fstab, mount identity, write access, EFI preservation, and the readiness service all pass in-session. A future explicitly authorized reboot may certify post-boot recovery, but that deferred certification is not a development admission gate.

Future destructive partition changes remain local privileged operations. Do not bypass Secure Boot, filesystem consistency checks, partition-table safety checks, or local authorization. Preserve a pre-change GPT/partition-table backup before any future resize.
## Unreal Engine development state

The current P3 project reports `EngineAssociation: 5.8` on the Windows repo. The laptop initially had Python 3.10, GCC 11.4 and Make, but lacked Git, Git LFS, pip, g++, CMake, Ninja, Node, Docker/Podman, CUDA and Rust.

The first privileged baseline install attempt stopped at `apt-get update` because the pre-existing Spotify apt repository has a missing signing key (`NO_PUBKEY 5384CE82BA52C83A`). Repository signature verification was not bypassed and the system apt source was not silently rewritten.

A usable **rootless UE development baseline** now exists under the user account, so agents do not need root for ordinary source/build tooling:

- environment: `~/ue-dev-env.sh` (source it before Linux UE work)
- package prefix: `~/.local/ue-bootstrap/prefix`
- verified Git 2.34.1 + Git LFS 3.0.2
- verified CMake 3.22.1, Ninja 1.10.1, pip 22.0.2, ccache 4.5.1
- verified GCC/G++ 11.4 rootless compile+link probe
- Epic native UE 5.8 toolchain downloaded and extracted at `~/.local/ue-toolchains/v26_clang-20.1.8-rockylinux8`
- verified clang/clang++ 20.1.8 x86_64 compile+link probe using `--sysroot="$UE_SYSROOT"`

The logical paths ~/.local/ue-toolchains and ~/.local/ue-bootstrap are now symlinks backed by /mnt/ue/toolchains and /mnt/ue/bootstrap. The migration was verified with zero-difference rsync checks and a post-migration clang 20.1.8 compile/link probe. Verified HDD rollback copies ~/.local/ue-toolchains.hdd-backup-20260906T233258 and ~/.local/ue-bootstrap.hdd-backup-20260906T233258 are retained as rollback evidence; do not delete them without an explicit cleanup decision.

The Epic native toolchain archive is retained at `~/.local/ue-toolchains/native-linux-v26_clang-20.1.8-rockylinux8.tar.gz`. Do not redownload it unless integrity or version evidence requires replacement.

The HDD root remains tight at roughly 50 GiB free, but UE tooling/build paths now target the NVMe lane; the post-migration `/mnt/ue` reading was about **132 GiB free**. Keep heavy UE source/build/cache activity on `/mnt/ue` and continue to re-read capacity before a full engine hydration/build. The large Desktop/media folders remain user-owned and must not be deleted merely to make room.

UE-specific source setup remains repo/engine-owned: once an authorized UE 5.8 source tree is available on Linux and storage headroom is adequate, use Epic's normal `Setup.sh`/`GenerateProjectFiles.sh` path and the v26 native toolchain rather than substituting an arbitrary compiler.

## Boundaries

- Optional compute/build node only; not current product authority, worker scheduler, queue, or shared production control plane.
- Windows MCP remains the ChatGPT transport owner. SSH is a hop behind it.
- No router port-forwarding or public TCP 22 exposure.
- No destructive disk cleanup without exact positive evidence that the target is disposable/recoverable.
- No assumption that claims, schedules, or this contract prove current worker activity or node liveness.
- Reverify GPU driver, free disk, RAM and SSH before heavy UE build/cook/render use.
- Avoid duplicate heavy UE builds; follow the owning repo's single-flight/build-admission contract.
