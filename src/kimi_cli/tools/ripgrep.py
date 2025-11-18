from __future__ import annotations

import asyncio
import hashlib
import platform
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

import aiohttp

import kimi_cli
from kimi_cli.config import Config
from kimi_cli.share import get_share_dir
from kimi_cli.soul.approval import Approval
from kimi_cli.utils.aiohttp import new_client_session
from kimi_cli.utils.logging import logger

RG_VERSION = "15.0.0"
RG_BASE_URL = "https://cdn.kimi.com/binaries/kimi-cli/rg"
_RG_DOWNLOAD_LOCK = asyncio.Lock()
_RG_PATH_CACHE: str | None = None

# `filename` -> sha256 checksum collected from the CDN artifacts.
_RG_SHA256 = {
    "ripgrep-15.0.0-x86_64-apple-darwin.tar.gz": "44128c733d127ddbda461e01225a68b5f9997cfe7635242a797f645ca674a71a",
    "ripgrep-15.0.0-aarch64-apple-darwin.tar.gz": "98bb2e61e7277ba0ea72d2ae2592497fd8d2940934a16b122448d302a6637e3b",
    "ripgrep-15.0.0-x86_64-unknown-linux-musl.tar.gz": "253ad0fd5fef0d64cba56c70dccdacc1916d4ed70ad057cc525fcdb0c3bbd2a7",
    "ripgrep-15.0.0-aarch64-unknown-linux-gnu.tar.gz": "15f8cc2fab12d88491c54d49f38589922a9d6a7353c29b0a0856727bcdf80754",
    "ripgrep-15.0.0-x86_64-pc-windows-msvc.zip": "21a98bf42c4da97ca543c010e764cc6dec8b9b7538d05f8d21874016385e0860",
    "ripgrep-15.0.0-aarch64-pc-windows-msvc.zip": "572709c8770cb7f9385d725cb06d2bcd9537ec24d4dd17b1be1d65a876f8b591",
}
_GREP_SUPPORT_CACHE: dict[str, bool] = {}


class RipgrepAvailabilityError(RuntimeError):
    """Raised when ripgrep cannot be provided to the caller."""


def _rg_binary_name() -> str:
    return "rg.exe" if platform.system() == "Windows" else "rg"


def _find_existing_rg(bin_name: str) -> Path | None:
    share_bin = get_share_dir() / "bin" / bin_name
    if share_bin.is_file():
        return share_bin

    local_dep = Path(kimi_cli.__file__).parent / "deps" / "bin" / bin_name
    if local_dep.is_file():
        return local_dep

    system_rg = shutil.which("rg")
    if system_rg:
        return Path(system_rg)

    return None


def _detect_target() -> tuple[str, str] | None:
    sys_name = platform.system()
    mach = platform.machine().lower()

    if mach in ("x86_64", "amd64"):
        arch = "x86_64"
    elif mach in ("arm64", "aarch64"):
        arch = "aarch64"
    else:
        logger.error("Unsupported architecture for ripgrep: {mach}", mach=mach)
        return None

    if sys_name == "Darwin":
        target = f"{arch}-apple-darwin"
        archive_ext = "tar.gz"
    elif sys_name == "Linux":
        os_name = "unknown-linux-musl" if arch == "x86_64" else "unknown-linux-gnu"
        target = f"{arch}-{os_name}"
        archive_ext = "tar.gz"
    elif sys_name == "Windows":
        target = f"{arch}-pc-windows-msvc"
        archive_ext = "zip"
    else:
        logger.error("Unsupported operating system for ripgrep: {sys_name}", sys_name=sys_name)
        return None

    return target, archive_ext


async def ensure_ripgrep_path(config: Config, approval: Approval) -> str:
    """Ensure the ripgrep binary is available and return its absolute path."""

    global _RG_PATH_CACHE
    if _RG_PATH_CACHE:
        return _RG_PATH_CACHE

    bin_name = _rg_binary_name()
    existing = _find_existing_rg(bin_name)
    if existing:
        _RG_PATH_CACHE = str(existing)
        return _RG_PATH_CACHE

    async with _RG_DOWNLOAD_LOCK:
        if _RG_PATH_CACHE:
            return _RG_PATH_CACHE

        existing = _find_existing_rg(bin_name)
        if existing:
            _RG_PATH_CACHE = str(existing)
            return _RG_PATH_CACHE

        downloaded = await _download_and_install_rg(bin_name, config, approval)
        _RG_PATH_CACHE = str(downloaded)
        return _RG_PATH_CACHE


async def _download_and_install_rg(bin_name: str, config: Config, approval: Approval) -> Path:
    target_info = _detect_target()
    if not target_info:
        raise RipgrepAvailabilityError("Unsupported platform for ripgrep download")

    target, archive_ext = target_info
    filename = f"ripgrep-{RG_VERSION}-{target}.{archive_ext}"
    expected_hash = _RG_SHA256.get(filename)
    if expected_hash is None:
        raise RipgrepAvailabilityError("Unknown ripgrep build for this platform")

    if not config.cli_output.auto_install_ripgrep:
        approved = await approval.request(
            "Ripgrep",
            "download ripgrep",
            (
                f"Download ripgrep {RG_VERSION} (~20MB) from the official CDN to "
                "speed up search commands"
            ),
        )
        if not approved:
            raise RipgrepAvailabilityError(
                "ripgrep is required but the download was rejected. "
                "Install ripgrep manually and make sure `rg` is on PATH."
            )

    share_bin_dir = get_share_dir() / "bin"
    share_bin_dir.mkdir(parents=True, exist_ok=True)
    destination = share_bin_dir / bin_name

    url = f"{RG_BASE_URL}/{filename}"
    logger.info("Downloading ripgrep from {url}", url=url)

    async with new_client_session() as session:
        with tempfile.TemporaryDirectory(prefix="kimi-rg-") as tmpdir:
            archive_path = Path(tmpdir) / filename

            try:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    hasher = hashlib.sha256()
                    with open(archive_path, "wb") as fh:
                        async for chunk in resp.content.iter_chunked(1024 * 64):
                            if chunk:
                                fh.write(chunk)
                                hasher.update(chunk)
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise RipgrepAvailabilityError("Failed to download ripgrep binary") from exc

            digest = hasher.hexdigest()
            if digest != expected_hash:
                raise RipgrepAvailabilityError(
                    "Ripgrep download failed integrity verification. "
                    "Please retry or install ripgrep manually."
                )

            try:
                if archive_ext == "zip":
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        member_name = next(
                            (name for name in zf.namelist() if Path(name).name == bin_name),
                            None,
                        )
                        if not member_name:
                            raise RipgrepAvailabilityError("Ripgrep binary not found in archive")
                        with zf.open(member_name) as source, open(destination, "wb") as dest_fh:
                            shutil.copyfileobj(source, dest_fh)
                else:
                    with tarfile.open(archive_path, "r:gz") as tar:
                        member = next(
                            (m for m in tar.getmembers() if Path(m.name).name == bin_name),
                            None,
                        )
                        if not member:
                            raise RipgrepAvailabilityError("Ripgrep binary not found in archive")
                        extracted = tar.extractfile(member)
                        if not extracted:
                            raise RipgrepAvailabilityError("Failed to extract ripgrep binary")
                        with open(destination, "wb") as dest_fh:
                            shutil.copyfileobj(extracted, dest_fh)
            except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
                raise RipgrepAvailabilityError("Failed to extract ripgrep archive") from exc

    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    logger.info("Installed ripgrep to {destination}", destination=destination)
    return destination


async def ensure_supported_grep_binary(cmd_name: str) -> bool:
    """Return True if the resolved grep binary looks like GNU grep."""

    resolved = shutil.which(cmd_name)
    if not resolved:
        return False

    cached = _GREP_SUPPORT_CACHE.get(resolved)
    if cached is not None:
        return cached

    try:
        process = await asyncio.create_subprocess_exec(
            resolved,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
    except FileNotFoundError:
        _GREP_SUPPORT_CACHE[resolved] = False
        return False

    combined = (stdout + stderr).decode("utf-8", errors="ignore").lower()
    contains_gnu = "gnu grep" in combined or "gnu compatible" in combined or "grep (gnu" in combined
    is_busybox = "busybox" in combined
    contains_bsd = "bsd grep" in combined
    is_gnu = contains_gnu and not is_busybox
    if contains_bsd and not contains_gnu:
        is_gnu = False

    _GREP_SUPPORT_CACHE[resolved] = is_gnu
    if not is_gnu:
        logger.warning(
            "Detected unsupported grep implementation at {path}: {version}",
            path=resolved,
            version=combined.strip().splitlines()[0] if combined else "unknown",
        )
    return is_gnu


def describe_manual_installation() -> str:
    return (
        "Please install ripgrep manually from https://github.com/BurntSushi/ripgrep/releases "
        "and ensure the `rg` binary is on PATH so Bash/Grep tools can reuse it."
    )
