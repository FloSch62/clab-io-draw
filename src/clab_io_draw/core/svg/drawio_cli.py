import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_drawio() -> Path:
    """Return the draw.io binary path without downloading anything."""
    env_bin = os.environ.get("DRAWIO_BIN")
    if env_bin:
        return Path(env_bin)
    return Path("drawio")


def _install_plugin() -> None:
    plugin_src = Path(__file__).with_name("svgdata.js")
    plugin_dir = Path.home() / ".config" / "draw.io" / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_dst = plugin_dir / "svgdata.js"
    try:
        shutil.copy(plugin_src, plugin_dst)
    except Exception as exc:
        logger.debug(f"Could not copy plugin: {exc}")


def _in_docker() -> bool:
    """Detect if running inside a Docker container.

    This relies on the ``IN_DOCKER`` environment variable, which is set in the
    official Docker image. Any truthy value (``"1"``, ``"true"`` or ``"yes"``)
    will trigger Docker mode.
    """

    return os.environ.get("IN_DOCKER", "").lower() in {"1", "true", "yes"}


def export_svg_with_metadata(drawio_file: str, svg_file: str) -> None:
    """Use draw.io CLI to export a diagram to SVG with metadata."""
    drawio_bin = _ensure_drawio()
    _install_plugin()

    if _in_docker():
        cmd = [
            "xvfb-run",
            str(drawio_bin),
            "--appimage-extract-and-run",
            "--no-sandbox",
            "--export",
            "--format",
            "svg",
            "--enable-plugins",
            "--output",
            svg_file,
            drawio_file,
        ]
    else:
        image = os.environ.get("CLAB_IO_DRAW_IMAGE", "clab-io-draw:latest")
        logger.info(
            "Using Docker image %s with svgdata plugin (image will be pulled if missing)",
            image,
        )
        drawio_path = Path(drawio_file).resolve()
        svg_path = Path(svg_file).resolve()

        code = (
            "from clab_io_draw.core.svg.drawio_cli import export_svg_with_metadata;"
            f"export_svg_with_metadata('/input/{drawio_path.name}', '/output/{svg_path.name}')"
        )
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{drawio_path.parent}:/input",
            "-v",
            f"{svg_path.parent}:/output",
            "--entrypoint",
            "python",
            image,
            "-c",
            code,
        ]

    logger.debug("Running: %s", " ".join(shlex.quote(part) for part in cmd))
    result = subprocess.run(  # noqa: S603
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logger.debug(result.stdout)
    if result.stderr:
        logger.debug(result.stderr)
