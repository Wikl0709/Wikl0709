"""
将输出目录打包为 zip（排除 PackageAllLogs.zip 等）
"""
import zipfile
from pathlib import Path
from datetime import datetime


def create_output_bundle_zip(
    output_root: Path,
    test_mode: str,
    ts: str | None = None,
    version: str | None = None,
) -> Path:
    """
    将 output_root 下除 PackageAllLogs.zip 外的所有文件/文件夹打包成一个 zip。
    zip 文件名包含 local/cloud 与时间戳，避免重复。
    """
    mode = (test_mode or "cloud").strip().lower()
    if mode not in {"local", "cloud"}:
        mode = "cloud"

    ts = ts or datetime.now().strftime("%Y%m%d_%H%M%S")
    ver = (version or "").strip()
    if ver:
        bundle_name = f"TestResult_{ver}_{mode}_{ts}.zip"
    else:
        bundle_name = f"TestResult_{mode}_{ts}.zip"
    bundle_path = output_root / bundle_name

    output_root.mkdir(parents=True, exist_ok=True)

    def _should_exclude(p: Path) -> bool:
        if p.name == "PackageAllLogs.zip":
            return True
        if p.name == bundle_name:
            return True
        if p.suffix.lower() == ".zip" and p.name.startswith("TestResult_"):
            return True
        return False

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in output_root.rglob("*"):
            if p.is_dir():
                continue
            if _should_exclude(p):
                continue
            try:
                arcname = p.relative_to(output_root).as_posix()
            except Exception:
                arcname = p.name
            zf.write(p, arcname)

    return bundle_path
