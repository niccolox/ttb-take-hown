# Local Dev: NVIDIA Docker (Container Toolkit) Install — Ubuntu 24.04

Source: official install guide, fetched 2026-08-02 —
https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
Current toolkit version per the guide: **1.19.1**. Companion docs:
`nemotron-ocr-local-dev.md` (what to run once this is set up).

**This machine's status (checked 2026-08-02):** Docker 29.4.1 with the
`nvidia` runtime already registered, nvidia-container-toolkit **1.19.0
already installed** — steps 1-4 below are effectively done here and kept for
reference/repeatability (a 1.19.0→1.19.1 bump is optional). What's actually
broken locally is the **driver** (kernel modules missing for kernel
7.0.0-28) — see "Step 0" below.

---

## Step 0 — Prerequisite: a working NVIDIA driver

The toolkit is useless without the driver. The guide's prerequisite is
"install the NVIDIA GPU driver via your distribution's package manager."

On THIS machine the driver package (`nvidia-driver-580-open`) is installed
but the prebuilt kernel-module package for the running kernel never got
installed after a kernel upgrade (Secure Boot is off — not a signing
issue). Fix:

```bash
sudo apt install -y \
  linux-modules-nvidia-580-open-7.0.0-28-generic \
  linux-modules-nvidia-580-open-generic-hwe-24.04
sudo modprobe nvidia
nvidia-smi    # must show the RTX 3050 Ti before proceeding
```

(Generic fresh-machine path instead: `sudo ubuntu-drivers install` — it
picks the recommended, Canonical-signed driver.)

Known issue flagged in the guide: `systemctl daemon-reload` can cause
running containers to lose GPU access on systemd-cgroup systems — restart
affected containers if that happens.

## Step 1 — Prereq packages

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends \
   ca-certificates \
   curl \
   gnupg2
```

## Step 2 — NVIDIA repository + GPG key (verbatim from the guide)

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

Optional experimental channel (not needed for this project):
```bash
sudo sed -i -e '/experimental/ s/^#//g' /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

## Step 3 — Install, version-pinned (the guide pins; so do we)

```bash
sudo apt-get update
export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.19.1-1
sudo apt-get install -y \
    nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}
```

Pinning rationale matches this repo's supply-chain posture (hash/version
pins everywhere): an unpinned `apt-get install nvidia-container-toolkit`
floats with the repo.

## Step 4 — Wire the Docker runtime

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

This writes the `nvidia` runtime into `/etc/docker/daemon.json`. (Already
done on this machine — `docker info` shows `Runtimes: … nvidia …`.)

Rootless Docker variant (if you run rootless):
```bash
nvidia-ctk runtime configure --runtime=docker --config=$HOME/.config/docker/daemon.json
systemctl --user restart docker
sudo nvidia-ctk config --set nvidia-container-cli.no-cgroups --in-place
```

Other runtimes, for reference: `--runtime=containerd` +
`systemctl restart containerd` (writes
`/etc/containerd/conf.d/99-nvidia.toml`); `--runtime=crio`; Podman should
use CDI instead.

## Step 5 — Verify the full chain

```bash
# 1. driver
nvidia-smi
# 2. GPU visible inside a container (sample-workload check; image per the
#    companion sample-workloads page)
sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
# 3. the actual dev target (from nemotron-ocr-local-dev.md): the HF repo's
#    own image sees the GPU
docker run --rm --gpus all nvcr.io/nvidia/pytorch:25.09-py3 nvidia-smi
```

All three must show the RTX 3050 Ti. After that, the Nemotron OCR v2 local
build proceeds per `nemotron-ocr-local-dev.md` (docker compose build with
`TORCH_CUDA_ARCH_LIST=8.6`, English variant).

## Gotchas log (this machine)

- Kernel upgrades can silently strand the driver again — the
  `-generic-hwe-24.04` modules meta package in Step 0 is what prevents a
  repeat.
- Hybrid graphics (Intel iGPU renders the desktop): irrelevant to
  containers — once the module loads, `--gpus all` sees the dGPU. First
  `nvidia-smi` after idle can be slow (runtime power management waking the
  card).
- `docker compose` GPU access uses the `deploy.resources.reservations.
  devices` block (compose snippet in `nemotron-ocr-local-dev.md`) — no
  `--gpus` flag exists in compose files.
