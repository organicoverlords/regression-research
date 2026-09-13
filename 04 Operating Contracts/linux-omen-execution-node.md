# Linux OMEN execution node

Status: primary LAN execution node for swarm work; user-owned; not a public MCP endpoint or scheduler.
Work identity: organicoverlords/regression-research#651. NVMe production-storage work: #661.

## Purpose

This HP OMEN laptop is the **default execution node** for substantive swarm work that is not explicitly LowVRAM or genuinely Windows-only. Machine admission is owned by the shared routing cohort in `swarm-routing-cohort.md` / `tools/swarm_route.py`: workers reuse one sticky cohort decision instead of independently choosing a machine. When the live OMEN probe and the owning repository path admit the work, route it here first. Windows remains the MCP/control transport and LowVRAM service owner, but KONE is not a general swarm execution fallback. Only extremely light mandatory Windows CI may execute there; substantive work blocks/waits when OMEN cannot safely admit it unless another explicitly supported non-KONE lane applies. The VPS may take only cohort-approved supported light overflow plus its edge/coordination duties. Do not add another public MCP/Caddy/WireGuard serving path for this node.

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

GPU state verified 2026-09-06 after local authorization: Secure Boot remains enabled. The running kernel `5.15.0-141-generic` now resolves NVIDIA 535.230.02 to the Canonical-signed module under `/lib/modules/5.15.0-141-generic/kernel/nvidia-535/`; the conflicting current-kernel DKMS copy was removed. `nvidia-smi` successfully sees the NVIDIA GeForce GTX 1070 with Max-Q Design with 8192 MiB VRAM, and Xorg/Cinnamon are using the GPU. The staged 580.173.02 offline bundle remains available but is not required for the current working 535 path. Do not bypass Secure Boot or module-signature enforcement.

## Disk state and current attribution

Observed root filesystem: `/dev/sda2`, about 916 GiB, about 794 GiB used, about 75 GiB free (92% used).

A bounded `du` attribution established that the main consumption is user data, not Timeshift:

- `/home/aatuska`: 776,924,368 KiB (~741 GiB)
- `/home/aatuska/TyÃ¢â€Å“Ãƒâ€špÃ¢â€Å“Ãƒâ€šytÃ¢â€Å“ÃƒÂ±`: 752,715,404 KiB (~718 GiB)
- `/home/aatuska/TyÃ¢â€Å“Ãƒâ€špÃ¢â€Å“Ãƒâ€šytÃ¢â€Å“ÃƒÂ±/ei sopinu`: 664,177,220 KiB (~633 GiB)
- `/home/aatuska/TyÃ¢â€Å“Ãƒâ€špÃ¢â€Å“Ãƒâ€šytÃ¢â€Å“ÃƒÂ±/NimetÃ¢â€Å“Ãƒâ€šn kansio`: 71,227,364 KiB (~67.9 GiB)
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

The OMEN proof/runtime path is continuously hot. Live state on 2026-09-08 verifies `Linger=yes` for `aatuska`, and the P3 hot runtime controller installs an enabled user service with `Restart=always`, `StartLimitIntervalSec=0`, and `WantedBy=default.target`; this is the supported 24/7 supervision path rather than a transient `systemd-run` unit. The enabled-service configuration is live-proven, but do not claim a post-change reboot-start certificate until a later reboot actually demonstrates it. Do not reboot merely to certify the mechanism. `/mnt/ue` remains approved for live UE work because UUID-backed fstab, mount identity, write access, EFI preservation, and the readiness service pass in-session.

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

UE-specific source setup is now active on the NVMe lane. An authenticated EpicGames `5.8.1-release` source archive was SHA-256 verified and extracted at `/mnt/ue/engine/UnrealEngine-5.8.1`; its `Build.version` reports 5.8.1. Epic GitDependencies is hydrating a Linux-x64 dependency set with Windows/Mac/mobile and LinuxArm64 payload folders excluded. After dependencies and the Epic-required `build-essential` package are complete, use Epic's normal `Setup.sh`/`GenerateProjectFiles.sh` path and the v26 native toolchain rather than substituting an arbitrary compiler.

## Live UE offload pipeline (2026-09-07)

- `/mnt/ue` is the active fast lane. The clean committed P3 snapshot is `/mnt/ue/projects/p3-head`; `~/ue-work/p3-head` remains only as a compatibility symlink. The Windows `Sync-P3LinuxSource.ps1` default now resolves to this NVMe path, and a live sync + smoke run passed 65/65. The broad portable lane passed 348 tests on the same NVMe snapshot.
- UE 5.8.1 source is at `/mnt/ue/engine/UnrealEngine-5.8.1`; Epic clang 20.1.8 resolves through the existing `UE_CLANG`/`UE_CLANGXX` variables to the NVMe-backed toolchain.
- Epic GitDependencies is owned by the persistent user service `ue-gitdeps.service`. Do not launch ad-hoc parallel GitDependencies copies over SSH. Three orphaned copies from earlier disconnected SSH sessions were explicitly identified by PPID=1/session scopes and terminated; only the systemd-owned copy should run.
- The functional Linux prerequisite is GNU Make plus Epic's bundled compiler/toolchain. Epic's 5.8.1 `Linux/Setup.sh` comments that compiler and dotnet are bundled and `build-essential` is useful to ensure `make`; GNU Make 4.3 and Epic clang 20.1.8 are already verified. Post-hydration therefore runs `BuildThirdParty.sh`, marks `Engine/Build/OneTimeSetupPerformed`, and runs `GenerateProjectFiles.sh` without requiring the package-manager convenience check.
- GitDependencies/posthydrate advancement is readiness-marker driven, not generic systemd `OnSuccess` from a guarded/skipped unit: `run-ue-gitdeps.sh` starts posthydrate only after writing `UE_GITDEPS_READY`, and `run-ue-posthydrate.sh` starts UHT only after writing `UE_PROJECTFILES_READY`. An `ExecCondition` defer because a foreign hydration owns the engine tree must never advance the downstream build chain. `ue-uht-build.service` then hands successful UHT completion to `p3-linux-build.service`, which runs the Linux P3 editor build.
- The legacy single-build 60 GiB admission rule was superseded on 2026-09-07 by the isolated lane guards documented below. Lane admission remains fail-closed on disk/RAM pressure; ue-posthydrate.service and build services route failures to ue-pipeline-diagnose.service for bounded diagnostics.
- LowVRAM remains on the main Windows PC. Do not move or retarget LowVRAM to OMEN.

## Boundaries

- Primary execution target under the shared swarm routing cohort; not product authority, worker scheduler, repository queue, or public/shared production control plane. The routing cohort owns machine admission; repo-owned lanes still own build/runtime single-flight behavior.
- Windows MCP remains the ChatGPT transport owner. SSH is a hop behind it.
- No router port-forwarding or public TCP 22 exposure.
- No destructive disk cleanup without exact positive evidence that the target is disposable/recoverable.
- No assumption that claims, schedules, or this contract prove current worker activity or node liveness.
- Reverify GPU driver, free disk, RAM and SSH before heavy UE build/cook/render use.
- Avoid duplicate heavy UE builds; follow the owning repo's single-flight/build-admission contract.

## Live isolated P3 build lanes (2026-09-07)

OMEN now has three rootless isolated Unreal build lanes over one frozen partially-built UE 5.8.1 engine base. The base is `/mnt/ue/engine/UnrealEngine-5.8.1-base`; do not mutate or rename it while either lane is active. Each lane runs in its own user+mount namespace with an overlay upper/work tree and its own copied P3 project outputs, so concurrent UBT writers do not share `Engine/Intermediate`, `Engine/Binaries`, project `Intermediate`, project `Binaries`, or project `Saved` writes.

- Lane 1 compatibility owner: `p3-linux-build.service`; full `p3Editor Linux Development`; 4 actions; persistent upper at `/mnt/ue/build-lanes/lane1/engine-upper`.
- Lane 2 project lane: `p3-linux-lane@2.service`; `-Module=p3`; 2 actions; `-NoUBA`; persistent upper at `/mnt/ue/build-lanes/lane2/engine-upper`.
- Lane 3 light lane: `p3-linux-light.service`; `-Module=p3`; exactly 1 action; `-NoUBA`; persistent upper at `/mnt/ue/build-lanes/lane3/engine-upper`. The prior 45 GiB disk floor was rejected as inappropriate for a dedicated dev-scratch NVMe. Lane 3 now targets 20 GiB free, automatically reclaims inactive generated lane state when below target, and hard-refuses only below 12 GiB after that reclaim. Its 10 GiB `MemAvailable` guard remains because the earlier three-lane test at 6 GiB caused sustained swap-out.
- Shared lower/base was frozen after action 1086 of the first full editor build. Restart proof showed lane 1 planned 1659 remaining actions rather than rebuilding the original 2743 from zero.
- Lane 1 and lane 2 now target 24 GiB free and hard-refuse only below 16 GiB **after** one bounded scratch-recovery pass. The hot runtime targets 18 GiB and hard-refuses below 12 GiB after recovery. `/home/aatuska/ue-work/reclaim-p3-linux-scratch.sh` is the shared rootless recovery helper: it acquires a global reclaim lock plus each lane's `active.lock`, preserves any lane with an attributed process, and removes only inactive lane `engine-upper`, `engine-work`, lane temp, and project `Binaries`/`Intermediate`/`DerivedDataCache`. It never touches Content, Saved/proof/evidence, source snapshots, the frozen engine base, toolchains, or user data. If inactive scratch cannot recover the hard floor, admission still fails closed.
- `~/ue-work/run-p3-linux-lane.sh` and `run-p3-linux-lane-inner.sh` own the isolation. Do not launch a second ad-hoc UBT against the frozen base or the empty host mountpoint.
- Start the current synced P3 module lane with `systemctl --user start p3-linux-lane@2.service`. Check `systemctl --user status p3-linux-lane@2.service` and `~/ue-work/logs/p3-linux-lane2.log` for live activity. A busy lane must fail/queue elsewhere rather than sharing its writable trees.
- Source snapshots remain under `/mnt/ue/projects/p3-commits/<sha>` and `/mnt/ue/projects/p3-current` remains the current source pointer. Each lane copies source into its own project tree before build while preserving that lane's generated outputs.
- Queue additional pinned P3 module requests without a permanent scheduler using `~/ue-work/queue-p3-linux-build.sh /mnt/ue/projects/p3-commits/<sha> p3 2`. Each request runs as a transient user service, resolves/pins its source path before waiting, and blocks on lane 2's lock. The queue wrapper was live-proven while lane 2 was occupied; the proof request was then stopped so no duplicate build remained.

This is the swarm's default execution capacity, not a new product authority, public endpoint, recurring scheduler, or general-purpose repository queue. The shared routing cohort owns machine admission; Windows remains MCP/control transport and LowVRAM service ownership remains on Windows. KONE worker execution is limited to extremely light mandatory Windows CI; ordinary work never spills there when OMEN is unavailable.
