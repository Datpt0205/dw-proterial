# Ops hardening

A platform status review on 2026-09-22 found six gaps an enterprise buyer would
ask about. Đạt chose to close five of them before picking the first bounded
context. All five are done and on `main`. The full narrative is at
`git show 84e3f6a:.claude/PLAN.md`, sections "Ops hardening".

| Phase | Commit    | What                                                                        |
| ----- | --------- | --------------------------------------------------------------------------- |
| 1     | `091eb35` | Backup off-box copy (the run fails if upload fails); restore drill run live |
| 2     | `c97ee4e` | `retention@1.4.0.yaml`: `audit.enforced: true`, gated on phase 1            |
| 3     | `061267b` | Spend guard, mechanism only (`platform.tenant_daily_spend_guard`)           |
| 4     | `89b00b5` | Tenant offboarding + data export, end to end                                |
| 5     | `8cbbee6` | Prometheus + Alertmanager, verified against running containers              |
| —     | `2a87f58` | Image pins bumped; real CVE counts recorded                                 |

## What holds, and where it lives

- **One retention file.** `configs/policies/retention@1.8.0.yaml` feeds the
  memory, knowledge, audit, checkpoint (since 1.6.0), channel-delivery
  (since 1.7.0), offboarding-export and superseded-version (since 1.8.0)
  sweeps on the worker's hourly lanes.
    - Audit keeps 1095 days: Commercial Law Art. 319's two-year limitation plus a
      review margin. Decree 13/2023 requires deletion once the purpose ends.
    - Since 1.5.0 the only memory class is `default`; `legal_hold` left the
      file. A row still carrying it, like any class this build does not know,
      is kept and never swept.
- **Partition creation is one function**, `platform.ensure_time_partitions`
  (CLAUDE.md, Data model rules). A partition created later inherits neither
  RLS nor the audit revoke.
- **Offboarding discovers tables from the catalog** (`pg_policies`), not from a
  hand list.
    - `platform.audit_events` is exported but never purged.
    - The one FK chain is purged in hand-checked order.
    - Stale claims older than 30 minutes are reclaimed.
    - Feedback attachments live under the `feedback/{tenant_id}/` prefix.
- **Metrics:**
    - a Prometheus reader is always installed;
    - `dw-api` serves `/metrics` at the root;
    - `dw-worker` serves its own scrape port (9464);
    - seven alert rules, each against a metric the code really emits
      (`DwNodeRepeatedlyFailing` since 2026-10-15).
- **Object storage is SeaweedFS** (`chrislusf/seaweedfs:4.48`, `weed mini`;
  compose service `s3`), since 2026-09-29.
    - MinIO withdrew its images from Docker Hub and then quay.io. Đạt chose
      replacing it over mirroring the old image.
    - The code speaks plain S3, so the swap was compose-only.
    - Buckets and the backup scripts use `rclone/rclone:1.75.1`, a generic
      client, so the next swap touches neither.
    - A replacement must first pass
      `dw_knowledge/tests/integration/test_object_storage_contract.py`
      (5 tests). The last of them refuses unsigned requests: without
      credentials SeaweedFS allows everything, measured at 200 on an unsigned
      PUT.
    - The earlier `SignatureDoesNotMatch` failures in the `dw_knowledge`
      suite no longer reproduce: 37/37 passed on MinIO and on SeaweedFS.

## Open

- **The plant's hosts (Đạt, 2026-11-09, corrected the same day).** DW runs
  on its own Ubuntu Server, as designed. Bravo runs on-prem on a separate
  Windows Server (it has a desktop and can reach wifi). VPN will likely be
  refused; staff use desktop PCs only, no laptops.
    - **11-11, whiteboard with IT: Ubuntu may be refused, Windows Server
      instead.** The options on the board: run on Windows, confirm Linux, or
      a Windows intermediary. The network is split into a production LAN
      (172.x) and an office VLAN (83.x: Bravo, internet, O365).
    - **How Proterial's network works (Đạt, 11-11; deploy by this):**
        - Bravo and DW sit on the office VLAN and go out to the internet
          directly, **not through Cato**.
        - Cato is a client on staff PCs and iPhones. It brings them into the
          office LAN from outside, and lets the parent company see what they do
          on Bravo. It blocks neither their internet nor calls coming in.
        - **The host's own calls never pass Cato:** O365 for OneDrive, Apple
          for web push, Zalo if it returns. The Zalo worry (the bot token in
          the URL logged by Cato) does not apply to the host.
        - **People's calls to DW do pass Cato's client** (portal, chat; from
          home always). So the parent company sees DW's use as it sees
          Bravo's. That is acceptable: DW's URLs carry ids, never a secret, and
          the sign-in code is one-time (PKCE). If Cato inspects TLS on that
          traffic, it may buffer the chat's streamed words and re-sign the
          certificate. Measure both on a real iPhone at UAT.
        - Still to confirm with IT:
            - that the server's outbound is not held tighter than the PCs';
            - any office-side proxy (TLS inspection, credentials) on the host's
              path;
            - DW's names in Cato's DNS and routes, as for Bravo.

        **Decided 11-16 (Đạt): the host is Windows Server 2025 with Desktop
        Experience (the UI), not Ubuntu.** It settles the version owed below.
        DW's Linux images still need a Linux kernel there, so DW runs in (a), a
        Hyper-V VM with Ubuntu, or (b), WSL2 (GPU in WSL is documented for
        Server 2025); a native Windows install stays not proposed (`reader` is
        Linux-only). New question: does Strata run on Windows? If it does, it
        can use the GPU on the host and the DW VM reaches it over the host's
        network, so the VM needs no DDA at all; if not, Strata goes in the VM
        with the GPU by DDA (IOMMU on the Z890 board, unmeasured).

        **On site 11-16, 09:49 (BIOS photo): the host has no OS yet** ("cannot
        find any bootable devices"), past the contract's hardware-ready date
        (11-13, HĐ 5.1 has Bên A deliver it with its OS). Hardware read from
        the BIOS: ASUS TUF GAMING Z890-PLUS WIFI, BIOS 3012, Core Ultra 7
        270K Plus, 64 GB DDR5 at 4000 MHz (XMP off; kept off for stability).
        Owed by Proterial IT: the Windows Server 2025 ISO and licence (retail,
        OEM or volume/KMS; the 180-day evaluation converts by DISM if the key
        comes later) and who installs it. Given to Đạt: BIOS settings (Restore
        AC Power Loss = Power On, ErP off, VMX and VT-d on, Secure Boot),
        install "Standard (Desktop Experience)" not the Core default, the
        board's LAN driver on the USB. **Remote setup (Đạt, 11-16):** OpenSSH
        on the host, key only, port 22 open to any address while in dev
        (firewall rule `dw-setup-ssh`), a dedicated laptop key
        (`proterial_dw_ed25519`, outside the repo), then Tailscale on the host
        in unattended mode for support from outside the plant (login by URL,
        no auth key through chat; key expiry off for the node). Tailscale is
        Đạt's call; IT to be told. Not run yet: no OS.
        **Later 11-16: Windows Server installed, no network.** The board's
        NIC is an Intel I226-V (`DEV_125C`). Intel's own Server 2025 pack
        (`Wired_driver_31.3_x64.zip`, SHA512 checked against Intel's page;
        `PRO2500\Winx64\WS2022\e2f.inf`, DriverVer 1.1.4.46) lists 125C only
        in its workstation section (`NTamd64.10.0.1..17763`); the server
        section carries I226-LM (125B) and I226-IT (125D). Given to Đạt: Have
        Disk, untick compatible hardware, pick I226-LM (same driver, still
        signed). Not yet confirmed on the host; fallbacks Android USB
        tethering or a USB-to-LAN dongle. A long-run server on a NIC driver
        installed against its INF should be re-checked after each Windows
        Update; a supported PCIe NIC (I210/X550 class) is the clean fix.
        "Run with PowerShell" runs unelevated and closes on the first error:
        the SSH script is run from an Administrator window.
        Ran there at 10:54: sshd running and automatic, rule `dw-setup-ssh`
        on; no IPv4 address, so not reachable yet. Host name
        `WIN-3JN0TH0NE0H`, Server 2025 Standard build 26100, English. Disks:
        **one SSD and one 4 TB HDD** (not the two SSDs first assumed), so no
        RAID: SSD for Windows and the DW VM, HDD for backups only (nightly
        dump, continuous WAL, weekly VM export). Display on Microsoft Basic
        Display Adapter (code 10): no GPU driver yet.
        **Reached over SSH 11-16 ~10:35** (I226-LM driver took, 1 Gbps;
        Tailscale 1.104.7 on the host, `ssh dw-host` from the laptop). Read
        from the host: SSD KIOXIA EXCERIA BASIC 2 TB NVMe (C: is all of it),
        HDD WD40EZZX 4 TB with an empty NTFS volume; **the EFI system
        partition Windows boots from sits on the HDD**, so a dead HDD stops
        the host from booting and the HDD cannot be wiped for backups until
        an ESP is made on the SSD (`bcdboot`, owed, needs a person at the
        console for the reboot). NVIDIA `DEV_2C34` present, on Microsoft Basic
        Display; Intel chipset, MEI, iGPU, MediaTek WiFi and Bluetooth have no
        driver. VT-x, SLAT and Secure Boot on; Hyper-V not installed.
        Windows not activated (0xC004F056: a KMS client key, Proterial's
        part). DHCP 192.168.1.69 on a temporary network. Applied:
        Tailscale unattended (`ForceDaemon` true; key expiry still to turn
        off in the admin console) and `infra/onprem/windows-host/01-host-baseline.ps1`
        (High performance, no sleep or hibernate; Windows Update downloads
        and notifies, no restart with a session signed in, no drivers).
        **Boot move, in progress (11-16 10:50):** `02-boot-from-os-disk.ps1`
        shrank C: to 250 GB and made a 300 MB ESP on the SSD (bcdboot, then
        `{bootmgr}` set to it). Two reboots came back over Tailscale with
        nobody signing in (about 2 min each: unattended Tailscale and
        automatic sshd hold). The BIOS still started the HDD's ESP (BCD
        hive loaded from it), so Đạt is setting Boot Option #1 to the SSD
        in the BIOS. **Done 10:55:** with Boot Option #1 on the KIOXIA,
        the BCD hive loads from the SSD's ESP. `03-volumes.ps1` then made
        V: (ReFS, 1612 GB, `DW-VM`) on the SSD and B: (NTFS 64K, 3726 GB,
        `DW-BACKUP`) on the wiped HDD; one ESP left, on the SSD. WinRE
        came back only after clearing the old store's id in ReAgent.xml
        (now in the script); enabled on the SSD's recovery partition.
        **Decided 11-16 (Đạt): Strata runs on Windows, Qwen3.8 Q2 with its
        vision part.** So the GPU stays on the host: no DDA, and the VM can
        stop with ShutDown. Done: Hyper-V role (one reboot, `vmms` running);
        `04-gpu-driver.ps1` installed NVIDIA RTX Server Driver 597.30 (R595,
        pinned by SHA256, signature valid; `nvidia-smi`: RTX PRO 4000
        Blackwell, 24467 MiB, WDDM) and set TdrDelay/TdrDdiDelay to 60 s.
        Owed: Strata's Windows build and the Q2 model with its vision
        projector, from Giang (on 11-12 Strata listed the model as text
        only); WDDM vs TCC once Strata's backend is known (TCC breaks
        Vulkan/DirectML and needs no display on the card); Tailscale key
        expiry off (admin console, Đạt); Intel chipset/MEI/iGPU drivers
        (cosmetic, not installed); then vSwitch, Defender exclusions, the
        Ubuntu VM on V:.
        **Strata found and installed (11-16 ~11:15):** it is public, MIT,
        `github.com/Niko1221/Strata`, with a Windows build; nothing owed
        from Giang for it. `05-strata.ps1`: Terminal 0.1.60.1 from release
        v0.2.14 (installer pinned by SHA256; it checks the Terminal's SHA256
        and the signed feed), data in `C:\Strata`, models in `V:\Strata`,
        engine CUDA 13; serving Q2_0 (66 GB; experts in RAM, Strata's figure
        34 GB + ~10 GB for Windows), 64k context, 3 parallel (Strata: a
        24 GB card holds 3), vision on (the picture reader on the GPU),
        LAN with an API key made on the host and never printed
        (`DW_STRATA_API_KEY`, machine environment), firewall 8080 from the
        local subnet. Started by the `DW-Strata` task (S4U as Administrator,
        at startup and every 5 min: `strata-watchdog.ps1` relaunches when
        `/health` fails). Downloading at about 1 GB/min. Not yet measured:
        CUDA from the S4U (session 0) task, the server outliving the task,
        vision on the RTX PRO 4000. Strata vs vLLM (Đạt asked): different
        engines; vLLM wants the model in VRAM (66 GB does not fit 24 GB) and
        is Linux-first, so Strata stays; it serves 3 requests at once.
        **VM (11:34):** vSwitch `DW-External` on the I226 (host kept
        192.168.1.69); `06-dw-vm.ps1` made `dw-vm` from the Ubuntu 24.04
        cloud image (SHA256 checked, converted to VHDX by qemu-img), Gen 2
        Secure Boot, 12 vCPU, 16 GB static, 400 GB, start with host, stop by
        ShutDown, no checkpoints, cloud-init seed (user `dw`, key only,
        no auto-reboot, journald 1 GB); Defender excludes `V:\Hyper-V` and
        the Hyper-V processes. DHCP 192.168.1.10; `ssh dw-vm` jumps through
        the host. `vm/10-docker.sh`: Docker 29.9.3, Compose 5.7.1, held,
        live-restore. WSL2 instead (Đạt asked, fearing policy): advised
        against; it is the same Linux in a Hyper-V VM, and Proterial
        accepted the Hyper-V VM on 11-11. Next: the DW stack in the VM
        (code by git bundle, images built there, `.env`, onprem compose
        with Strata at the host, bge-m3 on CPU in the VM), backups to B:,
        the host watchdog, then the drills.
        **Held (Đạt, 11-16):** no code moves to the VM while he is still
        coding. The VM's MAC is pinned (`00-15-5D-F2-BC-00`; host
        `B0-82-E2-C5-77-92`) so IT can give both a fixed address when they
        move the host to the 83.x LAN after setup; the three DW names point
        at the VM. Owed by IT: the names in their DNS, the two addresses,
        DW's root certificate on the PCs. Proposed next without code: the
        host watchdog (VM off or hung, Strata, Tailscale, disk; restart what
        is safe and alert by mail or Teams, Đạt to choose), the Strata
        measurement once the model is down, VM hardening (ufw, security-only
        updates).
        **Decided (Đạt, 11-16):** no DW root certificate on the PCs for now
        (browsers will warn on a private CA: a publicly trusted certificate
        by DNS-01 is the way out, owed); alerts go to Đạt's own mail, not
        Proterial IT; the host keeps ordinary internet on the 83.x LAN.
        **Done 12:05:** `vm/11-harden.sh` (ufw 22/80/443, keys only, no
        root, security updates without reboot, 4 GB swap, chrony synced);
        `07-watchdog.ps1` + `host-watchdog.ps1` (SYSTEM task every 5 min:
        start a stopped VM, restart one with no heartbeat for 15 min,
        Strata health, restart Tailscale, disks 15 %, a restart pending
        3 days; mail on a change of state and a daily report from 08:00 as
        the dead man's switch). Drilled: VM stopped, running again after
        one round, "recovered" logged. Mail is set by Đạt on the host with
        `set-alert-mail.ps1` (a Gmail App Password, DPAPI LocalMachine).
        **Mail on (12:47):** set with `-FromStdin`; the test mail and the
        SYSTEM watchdog's daily report were both sent. The App Password
        went through the chat; **Đạt keeps it (11-16, risk accepted: a
        Gmail sender used only for alerts)**. Tailscale key expiry: **turned
        off by Đạt (11-16)**.
        **Status 11-16 evening (Đạt):** the mail flows (one Power Automate
        flow per PIC into the Team's folders, the OneDrive sync account on
        the host, a Sent Items flow) are set up on the server Tuesday or
        Wednesday evening (11-17/18), with ticket 23's measurement; Strata:
        ticket 01 closed by Đạt (11-16); the Bravo API waits on a
        three-party meeting (Proterial, the Bravo vendor, FPT) on the 11-13
        request; meanwhile Đạt exports the Bravo screens himself for the
        Excel stand-in (ticket 14).
        **Model and RAM (Đạt asked, 11-16):** Strata serves only
        Qwen3.8-Flash-Next (its variants: ISTA-DASLab, Unsloth, Gyro, Swift,
        Coder) and Qwen3.6-35B-A3B. Qwen3.8-27B (dense, vision, Apache 2.0,
        Aug 2026) runs on llama.cpp/vLLM, not Strata: its 8-bit (~28 GB) does
        not fit 24 GB of VRAM, its 4-bit does and would free the host's RAM.
        Advised: measure Q2_0's real RAM first; if tight, RAM to 128 GB, then
        Gyro-S in Strata (27.6 GB vs 37.6 GB, lower quality), then 27B Q4 on
        llama.cpp, which changes ADR 0025 and needs every DW step attested
        again. Owed: Đạt's choice after the measurement.
        **Strata measured on the plant host (11-16 13:45, Q2_0, VM running,
        not attested):** serving from the S4U task in session 0 on CUDA
        (`strata.exe` and `strata-vision.exe` on the GPU, 23.5 of 24 GB
        VRAM; the engine lives in Administrator's `%LOCALAPPDATA%\Strata`
        despite `STRATA_DATA_DIR`); API key enforced (401 without).
        `reasoning_effort: none` is needed or the answer is empty (thinking
        eats the tokens). Vietnamese summary 1.6 s, warm ~78 tok/s, 3 parallel
        requests all done in 2.1 s; vision: the mock scan
        `scan_BRN-PO-2610-027.pdf` page 1 at 150 dpi in 4.6 s, PO number,
        date, parties, 3 codes, quantities, prices and dates all as printed,
        but "6.100" written as a JSON number reads 6.1: vision output must keep
        numbers as strings for code to parse (DW's rule already); a user-guide
        screenshot was described as what it is, nothing invented. Memory:
        Strata ~33 GB resident, 59 GB committed; host available ~5-6 GB, no
        paging (pages input 0/s) even with 3 parallel; **commit stood at
        83.2 of 85 GB** with the automatic 22 GB page file, so `01` now sets
        a fixed 64 GB (limit 127 GB, 64 % used after restart) and the
        watchdog alerts at 92 % commit (it fired at 99.1 % before the fix).
        Verdict: Q2_0 stays; Gyro-S not needed on these figures.
        **Whole-host restart drill (13:49):** host on Tailscale at 111 s, VM
        at 122 s, Strata serving at 193 s (2 min delay + ~30 s load); the VM's
        previous boot ended in `poweroff.target` with no unclean-journal sign.
        Found and fixed in the watchdog: at boot it judged the VM before
        Hyper-V had started it (now 5 min grace), and a mail that failed
        before the network was up was lost (now queued and retried; drilled
        with a broken SMTP port, then sent).
        **While waiting for code (11-16 afternoon):** `09-internal-link.ps1`
        - `vm/14-internal-link.sh`: an Internal vSwitch `DW-Internal`, host
          10.250.0.1, VM 10.250.0.2 (`dwlink0`, fixed MAC); `dw-host` in the
          VM's /etc/hosts now names the link, so the backup mount and DW's
          model URL do not change when IT moves the LAN to 83.x. Strata 8080
          and SMB 445 allow 10.250.0.2 only: from the VM over the LAN, 8080
          times out. Tailscale's Windows client adds its own allow-all rule for
          its interface (the laptop reaches 8080 and 3389 over the tailnet), so
          the tailnet's membership and ACL are the control there; owed with the
          move to an FPT tailnet: an ACL to admin devices, port 22/3389.
          `windows-update.ps1` (installs every software update through a SYSTEM
          task, since the API refuses an SSH session; never restarts): round 1
          installed 5 (2026-09 security update, .NET, Defender, MSRT), round 2
          found the 2026-11 security update. `10-remote-and-devices.ps1`: RDP
          with NLA from 100.64.0.0/10 only (Windows' own RDP rules off), the
          MediaTek Wi-Fi and Bluetooth disabled. The watchdog reads each
          physical disk's health, SSD wear (80 %), heat (HDD 55 C, SSD 75 C)
          and the HDD's uncorrected read errors rising; its boot grace now
          covers Tailscale and lasts 10 minutes (an update boot took ~5 and
          reported Tailscale down twice).
          **Windows fully patched (14:45):** round 2 installed the 2026-11
          security update (KB5131080); after the third restart, build
          26100.33822 and nothing left. Each restart brought the VM and
          Strata back unattended (Strata serving 271 s after the last).
          **Live evals on the plant's Strata found a conflict (14:47):**
          `structured_extraction` asks `logprobs: true` on every call
          (onprem.yaml 1.4.0, ticket 44), and Strata with `--parallel 3`
          answers "400 invalid request: logprobs is available with parallel
          (batch slots) only for max_tokens 1" (its server log, `%LOCALAPPDATA%\Strata\runtime`).
          So every DW1 reading on that route failed and the breaker opened
          (`sales_descriptions` 0 of 67 lines; `sales_intent`, another route,
          passed 7/7 at 0.989). Giang's lab ran without `--parallel`, which
          is why it never showed. Strata now runs `--parallel 1`
          (`strata-watchdog.ps1`; a logprobs call answers 200); one slot is
          also faster per request (~190 tok/s alone vs ~76 with three
          sharing). **Decided by Đạt (11-16): one slot with logprobs**
          (ticket 44's auto-apply works, requests queue), over three without
          (every result to a person). **Run on one slot, 15:38:** 28 of
          31 sets passed every case; 12 bars met, 5 missed (reply intent,
          reply draft, RFQ, skill intents, thread agent); the two
          notation-record failures belong to ticket 37's uncommitted work,
          one of them a value settled by another customer's record. Figures
          in ticket 01's comments. Also: an eval run started while an update installed had
          its first calls fail; updates belong in the agreed window.
          **BIOS confirmed by Đạt (11-16):** Restore AC Power Loss = Power On,
          so after a power cut the host starts by itself and the VM, Strata
          and Tailscale follow. **Real power cut drilled (16:14, Đạt pulled
          the plug ~20 s):** power lost 16:14:34 (event 6008), the host
          started by itself at 16:14:55 with no button pressed, Tailscale at
          ~1 min, the VM at ~1.5 min, Strata serving at ~3 min (its 2-minute
          wait included). Kernel-Power 41 logged; C:, V:, B: not dirty, both
          disks Healthy; the VM's last journal stopped mid-run, it booted
          with no failed unit, Docker up, the backup share mounted, Strata
          answering over the link; no false alert (boot grace). Found: an
          unclean stop told nobody, since everything recovered; the watchdog
          now mails once per boot that follows a Kernel-Power 41 (sent after
          the drill, not repeated on the next round; clean restarts leave no
          41). Not yet drilled: a power cut with Postgres taking writes
          (with DW deployed). **Its pass criteria (agreed with Đạt 11-16):**
          a load script writes numbered rows and logs each one Postgres
          acknowledged, while DW works seeded mail, a pending approval and a
          queued send; the plug is pulled at a random moment, three times
          (heavy writes, during the nightly backup, idle). Pass: (1) every
          acknowledged row present; (2) no half transaction (a case without
          its lines); (3) Postgres recovers by itself, `amcheck` clean, a
          full `pg_dump` reads; (4) work in flight is reclaimed, one case per
          Message-ID, no outbound mail sent twice, no job stuck past its
          timeout; (5) the pending approval decides and resumes from its
          checkpoint; (6) mail that arrived while down is read once; (7) the
          WAL archive on B: has no gap and the archiver resumes with no
          failure; (8) a PITR restore from the base backup and WAL reaches
          within 15 minutes of the cut (measure the real figure); (9) Qdrant
          and SeaweedFS agree with Postgres; (10) the next nightly and its
          restore test pass; (11) the unclean-boot mail and no false alert;
          (12) the portal usable within ~10 minutes. If (1) fails, the
          consumer SSD lied about its flushes: a UPS and/or an SSD with
          power-loss protection, before go-live.
          **Mail-drop session prepared (17:05):** `11-mail-sync-session.ps1`:
          OneDrive 26.198 for all users and Sysinternals Autologon 3.10 (both
          Microsoft-signed), a standard user `dwmail` signed in at every boot
          and locked at once (task), OneDrive started in that session by its
          own logon task (the per-machine installer registers one only for
          the account that ran it; and `Start-Process -Wait` hung on the
          OneDrive.Sync.Service it leaves), Files On-Demand off, disconnected
          RDP sessions never ended. After a restart: dwmail on the console,
          LogonUI up, OneDrive running, with nobody touching it. The password
          is kept for the machine (DPAPI) and read by an administrator at the
          console with `show-dwmail-password.ps1`. Left for people (the
          flows are 11-17/18): the private Team and its folders, each
          person's flow, then a Team owner RDPs in as dwmail over Tailscale,
          signs OneDrive in (MFA), adds `DW-mail` with "Add shortcut to My
          files", leaves by Disconnect; then the read-only share to the VM
          and its mount (to build, after the folder exists). **Images
          pre-pulled in the VM:** all 18 pinned third-party images of the
          on-prem compose (Langfuse and ClickHouse left out) and the two
          bases DW's images build from (`python:3.12-slim-bookworm`,
          `node:22-alpine`), 20 of 20, 17.5 GB; run as a transient systemd
          unit (`dw-prepull`), since an SSH-held run was cut once. VM disk:
          364 GB free.
          **Decided (Đạt, 11-16 13:00): no RAM upgrade is possible; if Q2_0
          crowds the host, switch to Gyro-S.** Measure Q2_0 with the VM
          running first. Tailscale key expiry is off (checked from the laptop).
          Boot order fixed: `DW-Strata`'s startup trigger waits 2 minutes so
          the VM takes its fixed 16 GB first. The watchdog alerts when the
          host has under 2 GB available for 15 minutes. Found for the backup
          batch: valkey runs with `noeviction` and no `--maxmemory` under the
          production overlay's 256 MB cgroup limit, so a full cache is
          OOM-killed (and may reload its RDB into the same limit) instead of
          refusing writes; container memory against its limit is not
          alerted on yet.
          **Backups built and drilled (11-16 13:15, on the VM against a
          throwaway stack: the production images, the repo's init script):**
          `08-backup-share.ps1` (B:\DW-Backup, SMB encrypted, local
          `dwbackup` with a random password piped to the VM),
          `vm/12-backup-mount.sh` (cifs `seal`, automount, `dw-host` in
          /etc/hosts as the one place the host's address lives),
          `infra/compose/docker-compose.backup.yml` (archive_mode on, gzip
          per segment to the VM's disk, archive_timeout 900),
          `vm/backup/dw-backup.sh` + `vm/13-backup.sh` (timers: nightly 02:15
          dumps of dw, keycloak, roles; a base backup weekly; Qdrant full
          snapshot; objects by rclone sync with changed files kept aside;
          .env and Caddy's CA; SHA256SUMS; WAL hourly; restore test on the
          1st). Retention 7 daily, 4 Sundays, 12 firsts, 5 bases, WAL back to
          the oldest base, changed objects 90 days: drilled with back-dated
          folders, each dropped or kept as the rule says. Found and fixed:
          the database list was queried in a database that does not exist, so
          a "successful" nightly held no dump (the restore test now requires
          `databases.txt` and dw's tables); a failed restore test left its
          containers behind (cleanup on EXIT). Mutations: a changed byte, a
          Qdrant count above the snapshot's, a missing dw dump each failed the
          restore test. The host watchdog reads B:\DW-Backup\status (26 h
          nightly, 3 h WAL, 35 days or failed restore test): a 72-hour-old
          nightly mailed "PROBLEM: backup", then "OK again". Timers are
          disabled and the test data gone until DW is deployed. Owed at
          deploy: add `docker-compose.backup.yml` to the onprem compose
          command (`make onprem-up` does not yet), `13-backup.sh <dir> dw`,
          one PITR restore from a base backup and WAL in the drill, and the
          VM's pulls failing on IPv6 now and then (watch it).

        **Decided 11-11 (Proterial, through Đạt): Windows Server with
        virtualisation allowed; DW runs as (a), a Hyper-V VM with Ubuntu and
        the GPU by DDA.** Still owed: the Windows Server version (2025
        preferred: 2022 left mainstream support on 2026-10-13, security fixes
        only to 2031-10; 2025 mainstream to 2029-11, extended to 2034-11. DDA
        is the same in both; GPU-P, new in 2025, needs a data-centre card and
        does not apply to a consumer one. Standard edition is enough for one
        Ubuntu VM), IOMMU and DDA on the board, measured on the host. The
        options as weighed before:
        If Windows is imposed, in order of preference:
        - **(a) Hyper-V VM with Ubuntu and the GPU by DDA.** The VM starts at
          boot and has its own LAN IP. Needs IOMMU on a consumer Z890 board,
          and Windows Server drivers for that board's NIC: neither measured.
        - **(b) WSL2 with docker-ce inside the distro.** Docker Desktop is
          unsupported on Windows Server (Docker's install page). GPU in WSL is
          documented for Windows 11 and Server 2025; on Server 2022 it is
          unconfirmed and reported failing. Costs:
            - a boot task to start the distro;
            - NAT plus portproxy for 443, since mirrored mode fails on Server
              2025 (WSL #12569);
            - data kept in ext4, not `/mnt/c`;
            - the WSL hangs this dev machine has had (`sales.md`).

            Measured only on Windows 10 with Docker Desktop (10-19, README).

        Windows Server goes straight on the DW box. (a) and (b) are how DW's
        Linux images get a kernel there, not a second layer of servers; WSL2
        is itself a small Hyper-V VM.
        - A native Windows install of DW is not proposed: Postgres, Qdrant,
          Keycloak and the rest would need a second install path, and the
          `reader` sandbox (no network, `ulimit`, a Unix socket) is
          Linux-only.
        - Hyper-V is a built-in Windows Server role, and an Ubuntu guest needs
          no Windows licence. What remains to ask is whether Proterial's
          policy forbids the role on a server.
        - Also unmeasured: Windows Server drivers for a consumer Z890 board
          and its NIC.
        - **If Hyper-V is refused, WSL2 goes with it** (it runs on the same
          hypervisor), and Docker on Windows Server without them runs Windows
          containers only, never DW's Linux images (Đạt asked 11-11; not
          decided). In order:
            - ask why Linux is refused. If the reason is "IT cannot run it",
              propose the DW box as an FPT-run appliance: its OS is FPT's job,
              like a firewall's. If the reason is policy on Ubuntu, a supported
              enterprise distro (RHEL) with Podman is a smaller change than
              Windows;
            - only then a native Windows install. Mostly runs as Windows
              services: Postgres, Qdrant, SeaweedFS, Keycloak, Caddy, Ollama
              with CUDA, the llama.cpp reranker, ClamAV, Node, and the Python
              api/worker (the tests already pass on this Windows machine).
              Valkey ships no Windows build (Garnet or Memurai in its place,
              to measure). What does not carry over: the reader and docgen
              sandboxes (`ulimit`, `os.killpg`, a Unix socket, no network,
              read-only root; `dw_reader/settings.py` turns the limits off on
              Windows). They would need a new design (job objects, a
              low-privilege user, a firewall rule) with an ADR and its own
              security review, because parsing a customer's file in a sandbox
              is not negotiable. Compose's network isolation becomes localhost
              binding plus firewall rules (Qdrant and Valkey are
              unauthenticated). Weeks of work, not measured, so not before DW1
              go-live. The contract has Bên A deliver the server with its OS
              (HĐ Điều 5.1), so this is a change to write down and sign (Điều 7).

        Either way OneDrive can run on that Windows host and the separate
        mail-drop PC goes. That needs a session kept signed in (autologon,
        disconnect only) and the host reaching O365, so the host sits on, or
        routes to, the office VLAN. Web push needs the host to reach
        `web.push.apple.com` outbound. On the office VLAN, which has
        internet, that is likely already open: ask IT. Nothing inbound is
        needed, and the portal stays LAN- and Cato-only.
        - **Mail on that host (Đạt, 11-11).** A dedicated OneDrive account
          means asking Proterial to create one, which is slow. The Teams
          route (`infra/onprem/README.md`, measured on FPT's tenant 11-02)
          needs none: the files belong to the private team, and the Windows
          host plays the plant PC. It signs in to OneDrive as one of the
          team's owners (an existing person, or the sales account if that is
          an ordinary licensed user; an Exchange shared mailbox cannot sign
          in) and shares `DW-mail` over SMB, read-only, to the Ubuntu VM
          alone. If that person's password, MFA or job changes, sync stops;
          the lane then tells the mailbox's processors once a day.
        - **A customer who Cc's the shared sales mailbox** makes no
          duplicate: an exported mail is stored once by its Message-ID from
          the same sender (`dw_sales`/`dw_purchasing` `mail_drop.py`). Not
          yet measured on a real tenant with one mail To a PIC and Cc the
          shared box. A forward has a new Message-ID, so it is a new mail.
        - **The shared sales mailbox itself is read by nobody today:** a
          lane reads only the folders named by the address of a member
          holding its scope, and no one signs in to DW as the shared box.
          Customers who write only to it would be missed. Reading it needs a
          tenant setting naming the shared mailboxes each DW reads, and its
          flow on the "shared mailbox" trigger, run by someone with access.
          Not built; owed from Proterial: whether customers ever write only
          to the shared box.
        - **Decided 11-12 (Đạt): the Teams route, a flow per person, not the
          shared box as main source.** Each flow writes into the team's
          library under the person's own connection, so if the account
          signed in on the host fails, mail keeps landing on Teams. Another
          of the team's two owners signs in on the host, and the lane reads
          every file it has not handled yet. Nothing is lost, only delayed.
          The shared-box question stays open only for customers who write
          to it alone.
        - ~~The shared box as DW1's main source~~ (Đạt asked 11-11; dropped
          11-12, above):
          one flow, one account (which can also be the host's OneDrive
          sign-in), instead of a flow per PIC. It sees only what reaches the
          shared box: a customer mail sent to a PIC alone, PC's replies to a
          PIC (read for dates since 11-04) and every DW2 mail (buyers'
          boxes) would be missed. So: the shared box for customer mail, plus
          per-person flows only where mail bypasses it (PICs for PC's
          replies, buyers); the Message-ID dedupe makes the overlap safe.
          Hinges on Proterial: do customers always write to or Cc the shared
          box, and does PC Cc it.

    - Falls with no VPN: support over VPN (ADR 0024 open item 3), Grafana
      over an SSH tunnel from home, and question 49 (access from outside).
      Updates go in as an image bundle on site.
    - FPT proposes rather than asks (Đạt, 11-09): the host as sized; FPT
      installs Ubuntu 24.04, the driver and Docker on site; wired LAN, a
      fixed IP, 443 from the PC subnet and 22 from IT only; **no internet**
      for the host, updates as a monthly USB bundle; DW's own CA, its root
      put on the PCs; a separate plant PC for the OneDrive mail drop, never
      the Bravo server; DW accounts first, AD later; NTP from AD; the
      BIOS set to power on when power returns (no UPS asked for); backups
      on the host only, as built (Đạt, 11-09: a lost machine loses DW's own
      data, not Bravo's or the mail; the hand-over states UPS and off-host
      backup are Proterial's, so they do not count against the 99%); Grafana in the browser behind Keycloak (to build); alerts by
      internal SMTP; FPT on site for UAT and go-live week, Teams after;
      a step-by-step runbook and two training sessions.
    - Asked of Proterial (7, drafted, not yet in the workbook): IP, names
      and the PC subnet; domain-joined PCs; an SMTP relay;
      the screen-share tool; AD or not (q3); a security agent (q47).
      No longer asked: UPS, a backup share.
    - **Risk found 11-09, to test on UAT day 1:** `proterial.com` is on
      Exchange Online with SPF `-all`, DKIM and DMARC `p=none` (public DNS).
      DW2 reads a request only from a sender `Authentication-Results`
      verifies, unknown being unverified (`dw_platform.domain.messages`). A
      mail inside the tenant may carry no such header, which would send
      every internal request to a person. Measured so far only with outside
      senders (11-02). If it holds, the fix is to accept Exchange's own
      intra-org stamp, a change to the trust boundary that needs its own
      review and tests.
    - **UAT and production, drafted 11-09 for Proterial IT (not yet in the
      workbook):** Power Automate and Teams allowed or blocked by DLP (the
      mail drop's precondition, measured only on FPT's tenant); internal
      mail verification (above); a Bravo account on the test company and
      which Bravo role may import a file; software brought in on an
      encrypted SSD (no internet on the host); where FPT's engineer works on
      site; real-data defects fixed on site only; key-user accounts. At go-
      live on the same host: keep accounts, rules, master data and learned
      layouts, delete cases, mail and history. Master data re-exported from
      Bravo monthly by each department's admin; IT onboards and offboards
      people by runbook; cutover at a week's start, away from month-end
      close, two weeks in parallel; one Teams group for support.
    - **Bravo integration (11-09), first proposed as a read-only sync:** today
      DW neither reads nor writes Bravo; people move files both ways and
      type Bravo's numbers back. Proposed: read Bravo's database through
      views the vendor makes, with a read-only login, on a schedule (every
      15 min for order numbers and receipts, nightly for master data).
      Gains: DW1 compares the Bravo entry with the PO itself (O7/O9), DW2
      takes Bravo's PO number and received quantities, and master data stays
      current. Still no writes: Bravo is the ledger. Needs: the database
      kind, views and a read-only login from the vendor, port 1433 from the
      DW host to the Bravo server. Owed: whether a synced master-data change
      applies at once (proposed, with a change log) or waits for the second
      person's approval DW2 asks today. UAT keeps the manual path; build
      after go-live.
      **Confirmed by Proterial IT (11-09):** Bravo is two-tier, a client
      app on each PC talking straight to SQL Server on the Windows Server,
      no firewall between, roles inside Bravo; one database, nothing to
      sync. **Superseded the same day:** Proterial gives no database login;
      the Bravo vendor builds an API over its own stored procedures, so the
      business logic stays theirs. DW calls it through a Bravo port and
      adapter, no database access at all. FPT's part: the list of endpoints
      DW needs. Reads first (DW1: customers, items, conversions, valid
      prices, sales orders by the customer's PO; DW2: items, suppliers with
      email, prices paid, budgets left, POs and goods receipts). Writes
      later and only if Proterial wants them: create a sales order or a PO
      from DW's draft, called when a person presses, with an idempotency
      key. Plus: a DW-only key with least rights, HTTPS on the LAN, coded
      errors, the Bravo test company first, docs and versions. UAT keeps
      the manual path until the API exists.
      **The request, 11-09:** `docs/proterial/Danh-sach-bieu-mau-va-API-Bravo_DW1-DW2.xlsx`
      (gitignored, like the questions workbook): 40 forms and documents to
      ask for at once, 38 APIs (15 P1 before UAT: reads; validate-only
      calls P2; writes P3, each on a person's press, with an idempotency
      key) and 16 common requirements; yellow cells for Proterial and the
      vendor. Fields come from the import sheets and Bravo layouts in code.
      It supersedes the workbook's "Tài liệu cần gửi" sheet (10 rows).
    - **Cato (SASE) on the plant's PCs, heard 11-09:** DW is unaffected in
      principle. The API's rate limit keys on the bearer token and
      Keycloak's lockout on the account, so one shared plant IP throttles
      no one. IT to configure: PC-to-DW traffic bypassed locally (else DW
      depends on the internet), DW's three names in Cato's DNS, no TLS
      inspection on them (it may buffer the chat's frames and break the
      certificate). Proposed: a Cato account for FPT that reaches only the
      DW host, as the sanctioned way to support without a VPN.
      Close q49.
    - **Claude Code for support on site (asked 11-12, proposed):** Claude
      Code supports Windows Server 2019+ (its setup page; no sandbox on
      native Windows); VS Code lists Windows client only; the Claude
      desktop app has no stated Server support. But DW lives in the Ubuntu
      VM, so the work is there, not on the Windows host. Proposed: Claude
      Code on FPT's own machine reaching the VM over SSH with a limited
      account, changes made in the repo and shipped as the image bundle,
      prompts kept on (never bypass mode), the database read as
      `dw_agent_ro` if at all, and no real mail or rows read. Anything
      Claude Code reads goes to Anthropic, which breaks "nothing leaves the
      plant" (model on the host, 11-02) unless Proterial IT agrees: owed,
      with the Cato/SSH access above.

- **Offline install of the DW host (given to Đạt 11-10, not yet written into
  the README):** Ubuntu Server 24.04 LTS from USB (Rufus, GPT/UEFI), RAID 1
  in the installer, OpenSSH ticked, no snaps; the BIOS powers on after an
  outage. Driver (Blackwell needs 570+, `-open`, with Ubuntu's signed
  modules), Docker and the NVIDIA Container Toolkit as `.deb`s downloaded
  on a VM from the same ISO and installed with `apt-get install ./*.deb`;
  images by `docker save $(compose config --images)`; models by
  `fetch-models.sh --export/--import`; the repo by `git archive`. Not run
  end to end anywhere. Offered: `make onprem-bundle` to do the export.
  **Qwen3.8-Flash-Next** fits a disk (about 35–50 GB, to check) and needs
  the 64 GB of RAM, but runs on Strata, not Ollama: packaging Strata for
  offline use, its licence and a measurement on the RTX PRO 4000 are owed
  before it replaces Qwen3.5-9B, which ships first.
  **Đạt's chosen path (11-10):** install from USB, then fetch everything
  over the plant's guest wifi before the LAN is plugged in. Checks owed on
  site: a wifi card or a phone's USB tethering, no captive portal, IT's
  consent to wifi then LAN, wifi off before the LAN. The code must still
  come by USB (`git bundle`): `main` is 184 commits past GitHub. An SSD of
  saved images and models goes along as the fallback.

- **Contract baseline (11-10, for Linh's tracking tool):** `Downloads/proterial/Baseline_Proterial_DW1-DW2.xlsx`,
  outside the repo. Dates count working days from a kick-off cell set to
  11-09 (the rollout plan says 11-03; Đạt to confirm). Hardware ready by
  11-13 (contract 5.1); DW02 go-live 11-30–12-04 and DW01 12-14–12-18 by
  the contract (the rollout plan puts DW02 in week 6).

- **Chat that streams, and models kept loaded (2026-11-06, Đạt).**
    - **Built:** `POST /{sales,purchasing}/assistant/ask/stream` (SSE over
      `fetch`, because `EventSource` sends no bearer token). `/assistant/ask`
      reads the same stream to its end. `dw_agent_runtime.model.streaming`:
      `released` holds each word until the text so far passes the figure and
      amount check; `replace` puts code's sentence over words that stopped
      passing. Decisions: `dw_sales` ADR 0007 addendum, a rule in `CLAUDE.md`.
      The chat frame shows the step in progress, the words, and a stop button.
      This is the existing question list, streamed. It is **not** the agent
      with tools proposed below.
    - **Built:** `scripts/warm_model.py`, the `model-warm` service in the
      on-prem overlay (every 300 s), `make onprem-warm`; `make onprem-up`
      returns once the models are loaded. It fails on a model held on CPU.
    - **Ran:** Qwen3.5-9B on local Ollama behind a real browser: DW1 step at
      0.1 s, first word 3.9 s, whole 6.2 s (the intent call is 2.4 s of it);
      DW2 answer at 2.2 s; stop keeps the question, stores no turn, releases
      the key. LM Studio: first word 0.45 s, whole 1.2 s. The real app and
      the repository's Caddyfile on `caddy:2.11.7-alpine`: frames arrive as
      written, a client leaving stops the generator. Cold load by the script:
      110 s, fully on the GPU. The script also ran in `dw-worker:local`.
    - **Mutation:** 23 guards, each red. Three survived at first: two were
      missing tests, one a condition that did nothing (removed).
    - **Integration, 2026-11-06** (both DWs, platform, API, worker; run on the
      code before streaming): 2 not green, both old and neither the chat's.
      `test_sales_personas` read the roster's Purchasing roles against Sales'
      seed since 11-01 (fixed). `test_offboarding_memory_vectors` timed out:
      creating a Qdrant collection takes 7.6 s on this Docker volume, past the
      client's default 5 s (fixed in the test). The same default stands in the
      composition roots (`AsyncQdrantClient(url=..., api_key=...)`), so a slow
      plant disk could fail `ensure_ready` at start: measure it there.
      On the streaming code, the assistant integration files
      (`test_assistant_sessions_db`, `test_purchasing_assistant_db`,
      `test_sales_api_access`) passed 13 before the run outlived its session;
      a whole rerun is owed. The chat's unit, route and web tests passed, and
      the browser walk wrote through real Postgres.
    - **Open:** `sales_assistant` evals run through `interpret`, not the
      stream. DW1's `my_work` wording was replaced on its one live run, so
      that kind flashes words and then code's list; if it does so at the
      plant, skip the wording for lists. `model-warm` has not run inside the
      compose stack, nor anything here on the plant's host or on Qwen3.8.
      `request_timing` measures to the first event, so `route_latency.py`
      reads a stream as fast. The intent call has no words to show, so a
      cold or queued model still shows only the step.

- **Process deck for Proterial (2026-11-06, outside the repo).**
  `Downloads/proterial/DW1-DW2_Quy-trinh-va-luong-nghiep-vu_Proterial.pptx`,
  31 slides: as is, with DW and who stays, every status and move of orders,
  quotes and purchasing. Built by `DW-decks-src/build_flows.py` from
  `flow.json`, dumped from `process_settings.EDGES` and `STATUS_BUCKETS`; the
  build stops on a DW1 move not drawn. DW2's moves are read by hand from the
  application services (no move table in code). DW2's as-is is still assumed.
  The 11-05 survey deck's slide 4 promises a hand-off drawing it does not
  have; master deck slide 21 still lacks the plant GPU.

- **Reaching the portal on premises (2026-11-06, answered for Đạt).**
    - Staff open `https://<DW_WEB_HOST>` on the plant's network only; Caddy
      (ADR 0009) is the one door, no Cloudflare or CDN (a third party would
      see decrypted traffic). Outside the plant: the company VPN, not a
      published port. Mail is unaffected (Exchange Online, the flows run in
      Microsoft's cloud); only portal actions need the network.
    - Fixed: the README said `DW_CADDY_LOCAL_CERTS=1`; the Caddyfile pastes
      the value as a global option, so it is `local_certs` (`949472a9`).
    - Still not run: `make onprem-up` behind Caddy in the `uat` profile.
      Certificates from Proterial's own CA need a Caddyfile `tls` change.
    - Asked of Proterial (questions 48–50, `docs/proterial/`): the three DNS
      names and which CA; who needs access from outside and whether a VPN
      exists; whether email reminders are wanted (the process does not
      require them; the bell carries them today).
    - **Agent chat (Đạt, 2026-11-06):** Đạt plans a larger model at the
      plant (2-bit). Proposed, not built: measure it on the existing evals
      against 9B first (ADR 0007 rejected a tool loop because of 9B), then
      read-only tools, then drafts, then HITL cards in the chat that call
      the same approval API. The model never approves. The plant GPU is
      known: an RTX PRO 4000 Blackwell, 24 GB (`sales.md` State), so nothing
      is owed there; asking for it on 11-06 was a mistake.
    - **Measuring on Giang's home lab (2026-11-06):** keys in the local
      `.env` only (`GIANG_*`). The live lane now sends
      `DW_ONPREM_MODEL_API_KEY` (`d3621fda`). LM Studio
      (`qwen3.5-9b-mtp`, gemma-4-12b) answers and honours
      `reasoning_effort: none`; through it `sales_assistant` and
      `purchasing_assistant` were 5/5 each (DW1 p50 0.8 s). Strata, where
      Đạt expects the qwen3.8 model, answered Cloudflare 1033/530 (the
      tunnel is down; still down after 2 h of polling).
    - **Already measured, found 11-06 and missing from these plans:**
      Qwen3.8-Flash-Next 125B on Strata (RTX 3090 24 GB), 26/10, six DW1
      golden sets, `Downloads/DW1_Qwen3.8-Flash-Next-IQ3XXS_Strata_ket-qua-test_2026-10-26.xlsx`.
      Against 9B: PRV-code hints 0.978 vs 0.711, mail intent 1.0 vs 0.898,
      RFQ 0.917 vs 0.946; 0 dangerous errors; all six bars passed; p50
      3.3–19.8 s. Q2_0: same bars, about half the time. Not measured:
      DW2's sets, the Q&A sets, security cases, tool calling, the plant's
      GPU. Next, when Giang's tunnel is up: those, through the scratch
      runner, field by field against the 9B reports.
    - **Content guardrails (2026-11-06, asked by Đạt):** today's holds by
      allow-list, not by topic: a closed intent schema (`out_of_scope` gets
      the fixed catalog), ADR 0010 input framing, code-written or
      figure-checked answers, no tools. Open: no content classifier on the
      two free-text surfaces (DW1's worded answer, drafted mails); no eval
      case for sexual, political, abusive or chit-chat jailbreak questions
      (offered to Đạt, not added). A free agent chat needs an on-prem guard
      model (e.g. Qwen3Guard, measured in VI/EN/JA first), failing closed.

- **Logs, traces, Grafana (2026-11-05, Đạt: everything on Proterial's
  server, no cloud).**
    - **Built:** `observability` is now Prometheus (with a volume, 30 days)
        - Alertmanager + Loki 3.7.9 + Alloy v1.21.3 + Tempo 2.10.10 + Grafana
          13.2.5. Langfuse moved to its own `langfuse` profile, for UAT or
          debugging only.
            - Four provisioned dashboards (`infra/grafana/dashboards`).
            - New metrics `dw_model_calls_total` and `dw_model_call_seconds_total`
              by prompt and model.
            - Alert `DwTelemetryStoreDown`, the 8th rule.
            - Every service uses json-file rotation (5 × 10 MB) with its service
              label; Alloy reads the files, not the socket.
            - `make onprem-up` runs the profile. README: "Watching it run".
    - **Ran on Docker Desktop:**
        - Loki labels only this project's lines.
        - Real `dw.model.call` spans from the worker reached Tempo with
          metadata only.
        - `sales.morning_brief` calls showed on the AI dashboard.
        - Every panel query returned `success`.
        - Stopping Tempo put the alert in `pending`.
        - Grafana took 4.5 minutes on its first start and 39 s after that.
        - postgres-exporter's WAL collector failed on every scrape
          (`pg_ls_waldir`); it is now off.
    - **Log audit before shipping:** the API runs without uvicorn's access
      log, every runtime engine sets `hide_parameters` (invariant check 4),
      a refused outbox payload names fields not values, and the reader
      mismatch is no longer chained.
        - **Still open:**
            - Postgres's own error text can quote one value (a bad cast, a
              unique-key DETAIL), measured with `hide_parameters` on. A
              formatter that reduces a DB error to its SQLSTATE is owed.
            - Model output chained under `ModelOutputInvalidError`.
            - `str(refused)` used as a reader refusal reason.
            - OSError paths naming a mailbox address or attachment.
            - The knowledge parser's filename.
            - docgen's document name.
        - The API configures no logging (only uvicorn's).
    - **trivy 0.74.0, HIGH, fixed upstream:**
        - Loki 0; Tempo 1 (go-jose); Alloy 2 (apt).
        - Grafana 35, almost all Go stdlib/x/net in bundled datasource
          plugins; 13.3.0 has 39 and Tempo 3.1.1 still has 1, so the pins
          stay.
        - Grafana is on loopback and reads only internal stores.
    - **Owed:**
        - Grafana behind Caddy with Keycloak sign-in; today it is loopback
          plus an SSH tunnel.
        - Retention per store (question 40).
        - AGPL of Grafana, Loki and Tempo for FPT legal.
        - DW1's accepted vs to-a-person rate stays on the portal, read from
          `sales.step_outcomes`; DW2 records no per-step outcome.
        - Model call failures are not counted, only answered calls.
        - No link yet from an alert to the same run's log lines.
- **On premises (2026-10-18, `7eabeb4`, `2338aec`).** `infra/onprem/README.md`
  and `docker-compose.onprem.yml`: Ollama 0.34.4 (qwen3.5-9b-dw, bge-m3) and
  llama.cpp b11146 (bge-reranker-v2-m3) on dw-internal, pinned by digest;
  the deployed check takes `onprem` as a real provider; embeddings follow the
  route's provider; a keyless reranker over http only as an allow-listed
  host; realm: 5-minute access tokens, lockout, password floor (the host
  overlay had counted on a brute-force detection nobody enabled); the web
  manifest.
    - **Ran locally on 2026-10-19.** `onprem-models`, plus the compose files in the `local` profile: rerank through `build_reranker`, bge-m3 through `build_embeddings`, and chat with 32/33 layers on the GPU.
    - **trivy:** llama.cpp has 2 HIGH, Ollama 0.34.4 has 50 HIGH, all fixable; moving the pin is Đạt's call.
    - **Measured problems:** GPU discovery can time out to CPU behind a healthy check; the first load takes minutes; qwen35 takes no parallel slots. All in `infra/onprem/README.md`.
    - **Still owed:** `onprem-up` in `uat` behind Caddy, and the realm applied to an existing Keycloak by hand.

- **Offboarding exported each row of a partitioned table twice** (fixed
  2026-10-15, `953086f`). Every partition carries its own tenant policy, so
  the catalog query listed it beside its parent, and the export (and purge)
  read the audit log and the ledger through both. Partitions are left out;
  `test_export_holds_each_row_of_a_partitioned_table_once`. Platform code:
  owed upstream to `Datpt0205/codebase`.
- **Offboarding loses in-app notifications unexported** (measured 2026-10-03,
  `workspace-scope-offboarding/01` step 4; fixed 2026-10-15, `fb3fefb`,
  migration `2e0354b50d10`: the notifications SELECT policy is tenant AND
  (recipient OR `app.workspace_scope`), only SELECT widened; reusing
  `app.workspace_scope` rather than a second lane setting was decided by the
  agent, Đạt: làm luôn, and `CLAUDE.md` Tenancy records it. Owed on
  Docker/CI: `test_offboarding.py`, `test_rls_coverage.py`,
  `test_privileges.py`, `test_notifications.py`, the round trip, and the
  mutation run: downgrade the revision, then
  `test_export_holds_every_persons_notifications_of_the_tenant` and
  `test_a_narrowed_table_lets_offboarding_read_every_row_of_the_tenant` go
  red). `platform.notifications` is read
  only by its recipient (`app.user_id`), so the lane's export lists the table
  with 0 rows and its purge deletes none; the purge of `platform.workspaces`
  then CASCADEs them away. Measured on the test database: a tenant with one
  notification exported `[0]` rows and kept none after purge. The workspace
  scope does not help, since the policy narrows by user, not workspace. Needs
  an export path that reads them (a scope the lane sets, like the workspace
  one, under the same tenant-clause rule) before a real offboarding.
- **Spend guard quotas are unset.** Every plan's `spend_usd_per_day` is `None`,
  so nothing is metered until Đạt gives dollar thresholds.
- **Offboarding export bundles in `dw-exports` are never deleted.** Closed
  2026-10-18 (`981f3a1`; decided by Đạt: 30 days after they are written).
  `offboarding_exports.retain_days: 30` in retention 1.8.0 (required,
  1..365). Lane `offboarding_exports_retention` (hourly, only with object
  storage) lists the bucket through the port, reads tenant and write time
  from the key (`export_key_for`/`export_written`), keeps keys of any other
  shape, and deletes inside the transaction that writes its lane audit row
  (`SqlOffboardingExportAudit`, in the workspace the purge record names; no
  row, no deletion). Owed on Docker/CI: 3 tests in `test_offboarding.py`
  (`test_an_export_deletion_is_on_its_tenants_log_as_the_lane_beside_the_purge`,
  `test_a_deletion_that_fails_leaves_no_audit_row`,
  `test_a_tenant_with_nothing_to_record_against_keeps_its_bundle`). Still open:
  the request row keeps `export_key` after the bundle is gone, so the operator's
  status read names a deleted object; the audit row is the record.
- **Superseded documents: keep the newest five.** Closed 2026-10-18
  (`981f3a1`; decided by Đạt). `knowledge.superseded_versions_kept: 5`
  (required, 1..100). `SqlSupersededVersionRetention`, lane
  `retention_knowledge_versions` (only with object storage): ranks superseded
  versions per (tenant, workspace, `doc_key`) by `effective_to`, deletes points,
  the stored text (`document_storage_key`, shared with ingest), then rows
  (chunks cascade), re-checked in the deleting transaction; cited versions held
  and counted; one lane audit row each. Owed on Docker/CI: 5 tests in
  `test_knowledge_retention_db.py`, and a SQL-level mutation (drop `tenant_id`
  from the window partition, see
  `test_another_tenants_versions_are_ranked_apart_and_untouched` go red); the
  window scans every superseded row each hour (no index carries it; fine at
  today's sizes, measure before a large library). Still open: the
  deleted-document sweep removes rows and points but not the stored text, and
  no sweep removes staged uploads (`{tenant}/{workspace}/uploads/{job}/...`).
- **The restore drill is same-cluster only.** A from-scratch DR drill (new
  host, roles provisioned from zero) has not been done.
- **Alert thresholds are starting points, not measurements:** outbox backlog
  500, reaper 20/hour, run failure rate 0.2/s, DB connections 80%.
- **The reaper alert can fire only where DW1 is mounted.** None was registered
  on 2026-09-29. Since `8adbe08` Sales registers a `ReapTarget` for its
  processing lane (`dw_worker/main.py`), but only when `s3_endpoint_url` is
  set and `SALES_DEMO_*` mounts DW1; a deployed profile without it still
  registers none. The header of `infra/prometheus/alerts.yml` says so since
  `5f59855` (2026-10-17).
- **`dw_node_failure_total` is declared and emitted by nothing**
  (`dw_observability/metrics.py`), so no rule uses it. Closed 2026-10-15
  (`fbe99ac`, `c732366`): the runner counts it once per failed run (not a
  cancellation), with the worker-graph node read from LangGraph's exception
  note (`test_node_failure_metric.py` pins it against the real library),
  after the run is settled, so a raising sink cannot leave a run RUNNING;
  alert `DwNodeRepeatedlyFailing` reads it. Owed: promtool on
  `infra/prometheus/alerts.yml` (or the file loaded in the observability
  profile), and the series on a live `/metrics` after a failing run.
- **No Grafana dashboards.**
- **Image pins (2026-10-15, `f14490f`).** Every third-party compose image is
  exact-pinned (postgres `16.15-alpine`, valkey `8.1.10-alpine`, clickhouse
  `24.8.14.39-alpine`, langfuse and langfuse-worker `3.225.11`, alpine
  `3.20.10`), each the version its floating tag resolved to that day. Still
  open: no check stops a floating tag coming back (a `verify_invariants.py`
  check would be its own item); the Dockerfile bases float
  (`python:3.12-slim-bookworm` in api/docgen/worker, `node:22-alpine` in
  web). Owed on Docker: pull the pinned images and run trivy; re-measure the
  Vietnamese collation (Đ after D, measured on 16.14) on 16.15, which CI has
  run since 2026-09-21, ideally as an integration test. The worker image
  drops docling and torch (`e0f8ed3`): rebuild, trivy, compose smoke owed.
  ClamAV's pin moves by a weekly workflow (`clamav-bump.yml`, sales ticket
  25), built, not yet run: Đạt allows Actions to create pull requests.
- **Accepted CVEs.** About 39–44 HIGH/CRITICAL remain per image, mostly
  transitive Go stdlib/x code. Pins: `prometheus:v3.6.0` (a newer tag did not
  help), `postgres-exporter:v0.17.1`, `alertmanager:v0.28.1`. Re-scan on every
  bump.
    - `chrislusf/seaweedfs:4.48`: none (trivy 0.74.0, 2026-09-29).
    - `rclone/rclone:1.75.1` carries 3 fixable HIGH, all denial of service:
      CVE-2026-14456 in libcrypto3 (twice) and CVE-2026-84445 in grpc.
      Accepted: rclone runs as a one-shot client on the internal network and
      opens no listener. Move to the next rclone release that clears them.
