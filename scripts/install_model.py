#!/usr/bin/env python3
"""Downloads the local model used by scripts/rewrite.py. Only once, ~4.6 GB.
Works the same on macOS, Linux and Windows (no extra packages).

  - Qwen3-4B-Base as GGUF Q8_0 (4.3 GB, Apache-2.0), from Hugging Face
  - the HIP adapter of Xu et al. 2026 already converted to GGUF (280 MB, Apache-2.0),
    from this repo's downloads (see THIRD_PARTY.md)

Needs llama.cpp:
  macOS and Linux:  brew install llama.cpp
  Windows:          winget install llama.cpp   (and open a new terminal afterwards)

Already have Qwen3-4B-Base? Point HUMANIZE_BASE_MODEL at its .gguf (any quantization):
only the 280 MB adapter is downloaded, and the file is checked to be Qwen3-4B. A model in
Hugging Face format (safetensors) becomes a .gguf with llama.cpp's convert_hf_to_gguf.py.

A bigger model: HUMANIZE_BASE_MODEL a .gguf of Qwen3-8B-Base (say) and HUMANIZE_ADAPTER the
adapter trained for it, in GGUF (nothing is downloaded; the README says how to make it).

Destination: $HUMANIZE_MODEL_DIR or ~/.cache/humanizar-es/hip. If the
files are already there, it only verifies them. If it gets cut off, run it again: it
resumes where it stopped. It checks the free space first. Where huggingface.co is
blocked, HF_ENDPOINT points it to a mirror (the same variable huggingface_hub uses);
the sha256 check still applies.

It runs on the CPU. HUMANIZE_GPU=1 runs it on the GPU, and this checks that llama.cpp
sees one: a build for the CPU alone does not (rebuild it with -DGGML_VULKAN=ON for most
GPUs, NVIDIA included, or -DGGML_CUDA=ON with CUDA 12.8+ for an RTX 50; a Mac build uses
Metal already).

Then it rewrites one short sentence, so a llama.cpp that rejects a flag or cannot load
the model fails here, with its error, and not in the middle of a text (--no-test skips it).

usage:
  python3 scripts/install_model.py        (on Windows: python or py)
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rewrite  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

HF = (os.environ.get("HF_ENDPOINT") or "https://huggingface.co").rstrip("/")
BASE_URL = HF + "/mradermacher/Qwen3-4B-Base-GGUF/resolve/main/Qwen3-4B-Base.Q8_0.gguf"
BASE_SHA = "4498bfc249d7597bef6e4bff1637c4cb9c6434974cada81b68a26974e23be977"
ADAPTER_URL = "https://github.com/ervin-mo/humanizar-es/releases/download/modelo-hip/hip-qwen3-4b-base-q8_0.gguf"
ADAPTER_SHA = "2f120a1f9e1f7d97e5a011a13c6dde127ce08c12edc96efba4bf97542ffdd99c"
CHUNK = 1 << 20
SIZES = {rewrite.BASE: 4.4e9, rewrite.ADAPTER: 0.3e9}  # rounded up, for the space check


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for piece in iter(lambda: fh.read(CHUNK * 8), b""):
            h.update(piece)
    return h.hexdigest()


def download(name, url, sha, tries=3):
    final = os.path.join(rewrite.MODEL_DIR, name)
    if os.path.isfile(final):
        print(f"verifying {name} ...", flush=True)
        if sha256(final) == sha:
            print(f"already there: {name}")
            return
        aside = final + ".mismatch"  # never delete a file someone may have put there
        os.replace(final, aside)
        print(f"{final} is not the expected file; it is now {aside}. If it is your own copy of "
              "Qwen3-4B-Base, delete the download and set HUMANIZE_BASE_MODEL to that file.")
    partial = final + ".part"
    expected = 0  # the full size, as the server last reported it
    for attempt in range(1, tries + 1):
        have = os.path.getsize(partial) if os.path.isfile(partial) else 0
        req = urllib.request.Request(url, headers={"User-Agent": "humanize-research"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:  # the server does not resume: from scratch
                    have = 0
                total = have + int(r.headers.get("Content-Length") or 0)
                expected = total if total > have else expected
                print(f"Downloading {name} ({total / 1e9:.2f} GB) ...", flush=True)
                with open(partial, "ab" if have else "wb") as fh:
                    done, t0, last = have, time.time(), 0.0
                    for piece in iter(lambda: r.read(CHUNK), b""):
                        fh.write(piece)
                        done += len(piece)
                        if time.time() - last > 2:
                            last = time.time()
                            speed = (done - have) / max(last - t0, 1e-3) / 1e6
                            pct = f"{100 * done / total:5.1f}%" if total else ""
                            print(f"\r  {pct} {done / 1e9:.2f} GB  {speed:.1f} MB/s   ",
                                  end="", flush=True)
            if total and done < total:  # the server closed early without an error: resume
                raise OSError(f"closed at {done / 1e9:.2f} of {total / 1e9:.2f} GB")
            print()
            break
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:  # it was already complete
                break
            print(f"\n  HTTP error {e.code}; retry {attempt} of {tries} ...", flush=True)
            time.sleep(3)
        except OSError as e:
            print(f"\n  connection dropped ({e}); retry {attempt} of {tries} ...", flush=True)
            time.sleep(3)
    else:
        sys.exit(f"ERROR: could not download {name}. Check the connection and run it again.")
    print(f"verifying {name} ...", flush=True)
    if sha256(partial) != sha:
        size = os.path.getsize(partial)
        if expected and size < expected:  # incomplete, not corrupted: keep it to resume
            sys.exit(f"ERROR: {name} is incomplete ({size / 1e9:.2f} GB). Run it again: it "
                     "resumes from there.")
        os.remove(partial)
        sys.exit(f"ERROR: {name} arrived corrupted (sha256 mismatch). Run it again.")
    os.replace(partial, final)


GGUF_TYPES = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?",
              10: "<Q", 11: "<q", 12: "<d"}
WANTED = ("general.architecture", "general.name", "general.basename", "general.finetune",
          "general.size_label", "qwen3.embedding_length", "qwen3.block_count", "adapter.type")


def gguf_info(path):
    """A few header values of a GGUF file (architecture, name, size), read without loading
    the model: enough to tell Qwen3-4B-Base from another model."""
    info = {}
    with open(path, "rb") as fh:
        if fh.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        version, _tensors, count = struct.unpack("<IQQ", fh.read(20))
        if version < 2:
            raise ValueError(f"GGUF version {version} is too old")

        def string():
            n = struct.unpack("<Q", fh.read(8))[0]
            return fh.read(n).decode("utf-8", "replace")

        def value(kind):
            if kind == 8:
                return string()
            if kind == 9:  # an array: skipped, it is the tokenizer's
                sub, n = struct.unpack("<IQ", fh.read(12))
                for _ in range(n):
                    value(sub)
                return None
            fmt = GGUF_TYPES[kind]
            return struct.unpack(fmt, fh.read(struct.calcsize(fmt)))[0]

        for _ in range(count):
            key = string()
            v = value(struct.unpack("<I", fh.read(4))[0])
            if key in WANTED:
                info[key] = v
                if all(k in info for k in WANTED[:2] + WANTED[5:6]):
                    break
    return info


def check_adapter(path):
    """(problem, architecture) of an adapter the user brings: a LoRA in GGUF."""
    try:
        info = gguf_info(path)
    except (OSError, ValueError, struct.error, KeyError) as e:
        return f"{path} could not be read as a GGUF file ({e})", None
    if info.get("adapter.type") != "lora":
        return (f"{path} is not a LoRA adapter in GGUF. Convert the adapter's safetensors with "
                "llama.cpp's convert_lora_to_gguf.py (see the README)."), None
    return None, info.get("general.architecture")


def check_base(path, adapter_arch=None):
    """(problem, warning) about a base model the user brings. Without an adapter of their own
    the HIP adapter needs Qwen3-4B; with one (adapter_arch is its architecture) the model must
    be the one it was trained on, which llama.cpp checks when it loads them. The method needs
    the base model, not the chat one."""
    try:
        info = gguf_info(path)
    except (OSError, ValueError, struct.error, KeyError) as e:
        return f"{path} could not be read as a GGUF model ({e})", None
    arch, width = info.get("general.architecture"), info.get("qwen3.embedding_length")
    if adapter_arch:
        if arch != adapter_arch:
            return f"{path} is {arch or 'an unknown architecture'}, and your adapter is {adapter_arch}.", None
    elif arch != "qwen3" or (width and width != 2560):
        return (f"{path} is {arch or 'an unknown architecture'}"
                + (f" with width {width}" if width else "")
                + "; the HIP adapter needs Qwen3-4B (qwen3, width 2560)."), None
    label = " ".join(str(info.get(k, "")) for k in ("general.name", "general.basename",
                                                     "general.finetune")).lower()
    chat = "instruct" in label or "chat" in label or (arch == "qwen3" and "base" not in label)
    if chat:
        return None, (f"{path} calls itself «{info.get('general.name', '?')}», not a base model. "
                      "A chat model's training is what detectors recognize: the method needs the "
                      "base model (Qwen3-8B-Base, not Qwen3-8B).")
    return None, None


def bytes_missing(folder, own_base=False, own_adapter=False):
    """What is left to download, counting what a cut download already saved."""
    need = 0
    for name, size in SIZES.items():
        if (own_base and name == rewrite.BASE) or (own_adapter and name == rewrite.ADAPTER):
            continue
        final = os.path.join(folder, name)
        if not os.path.isfile(final):
            part = final + ".part"
            need += max(0, size - (os.path.getsize(part) if os.path.isfile(part) else 0))
    return need


def gpu_devices():
    """The GPUs this llama.cpp can use («CUDA0: NVIDIA GeForce RTX 3060 (12 GB …)»), [] when
    it was built for the CPU alone, None when it cannot say (no --list-devices)."""
    llama = rewrite.llama_binary()
    cmd = ([sys.executable] if llama.endswith(".py") else []) + [llama, "--list-devices"]
    try:
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for out in (r.stdout, r.stderr):
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if line.strip() == "Available devices:":
                return [x.strip() for x in lines[i + 1:]  # a CPU build lists «(none)»
                        if x[:1].isspace() and x.strip() and x.strip() != "(none)"]
    return None


def smoke_test():
    """One short rewrite with the real model: 0 if llama.cpp runs it, 1 with its error."""
    sentence = "The small town hosts a market every Saturday morning in the main square."
    print("\nTesting one rewrite (10-60 s) ...", flush=True)
    try:
        out = rewrite.rewrite_paragraph(sentence, threads=4)
    except rewrite.LlamaError as e:
        print(f"ERROR: the model is downloaded but llama.cpp could not run it.\n{e}")
        return 1
    if len(out.split()) < 5:
        print(f"WARNING: llama.cpp ran but wrote almost nothing: {out!r}. Update llama.cpp.")
        return 1
    print(f"  {sentence}\n  -> {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Downloads and checks the local model.")
    ap.add_argument("--no-test", action="store_true", help="skip the test rewrite at the end")
    args = ap.parse_args()
    if not rewrite.llama_binary():
        print("ERROR: llama.cpp is missing. " + rewrite.HOW_TO_INSTALL_LLAMA)
        return 1
    os.makedirs(rewrite.MODEL_DIR, exist_ok=True)
    own = os.environ.get("HUMANIZE_BASE_MODEL")
    own_adapter = os.environ.get("HUMANIZE_ADAPTER")
    adapter_arch = None
    if own_adapter:
        if not os.path.isfile(own_adapter):
            print(f"ERROR: HUMANIZE_ADAPTER is {own_adapter}, and there is no file there.")
            return 1
        if not own:
            print("ERROR: HUMANIZE_ADAPTER needs HUMANIZE_BASE_MODEL: the base model it was "
                  "trained for (the 4.3 GB download is Qwen3-4B-Base only).")
            return 1
        problem, adapter_arch = check_adapter(own_adapter)
        if problem:
            print(f"ERROR: {problem}")
            return 1
        print(f"Your adapter: {own_adapter}")
    if own:
        if not os.path.isfile(own):
            print(f"ERROR: HUMANIZE_BASE_MODEL is {own}, and there is no file there.")
            return 1
        problem, warning = check_base(own, adapter_arch)
        if problem:
            print(f"ERROR: {problem}")
            return 1
        print(f"Your base model: {own}" + (f"\nWARNING: {warning}" if warning else ""))
    need = bytes_missing(rewrite.MODEL_DIR, own_base=bool(own), own_adapter=bool(own_adapter))
    free = shutil.disk_usage(rewrite.MODEL_DIR).free
    if need > free:
        print(f"ERROR: the model needs {need / 1e9:.1f} GB more and {rewrite.MODEL_DIR} has "
              f"{free / 1e9:.1f} GB free. Free some space, or set HUMANIZE_MODEL_DIR to a "
              "folder on another disk.")
        return 1
    if not own_adapter:
        download(rewrite.ADAPTER, ADAPTER_URL, ADAPTER_SHA)
    if not own:
        download(rewrite.BASE, BASE_URL, BASE_SHA)
    print(f"\nReady: {rewrite.MODEL_DIR}")
    for path in (rewrite.adapter_path(), rewrite.base_model_path()):
        print(f"  {path}  {os.path.getsize(path) / 1e9:.2f} GB")
    print(f"  llama.cpp: {rewrite.llama_binary()}")
    found = None if rewrite.device_args()[1] == "0" else gpu_devices()
    if rewrite.device_args()[1] == "0":
        print("  runs on: the CPU (HUMANIZE_GPU=1 runs it on a GPU)")
    elif found == []:
        print("  runs on: the CPU\nWARNING: HUMANIZE_GPU is set, but this llama.cpp sees no GPU: "
              "it was built for the CPU alone. Rebuild it with -DGGML_VULKAN=ON (most GPUs, "
              "NVIDIA included) or -DGGML_CUDA=ON (NVIDIA; an RTX 50 needs CUDA 12.8+).")
    else:
        print("  runs on: the GPU" + (f" ({'; '.join(found)})" if found else ""))
    return 0 if args.no_test else smoke_test()


if __name__ == "__main__":
    sys.exit(main())
