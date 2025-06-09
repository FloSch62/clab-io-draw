import json
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_drawio() -> Path:
    """Return the draw.io binary path without downloading anything."""
    env_bin = os.environ.get("DRAWIO_BIN")
    if env_bin:
        return Path(env_bin)
    return Path("drawio")


def _debug_plugin_locations() -> None:
    """Debug function to log all potential plugin locations and their contents."""
    logger.info("=== Draw.io Plugin Debug Information ===")
    
    # Check environment variables
    logger.info("Environment variables:")
    for key in ["HOME", "DRAWIO_CONFIG", "DRAWIO_PLUGINS_DIR", "XDG_CONFIG_HOME", "USER"]:
        logger.info(f"  {key}={os.environ.get(key, 'NOT SET')}")
    
    # Check potential plugin directories - use actual home directory
    home = Path.home()
    potential_dirs = [
        home / ".config" / "draw.io" / "plugins",
        home / ".drawio" / "plugins",
        Path("/tmp") / ".mount_drawio*" / "plugins",  # AppImage mount
    ]
    
    # Only add system directories if we have permission
    if os.access("/opt", os.W_OK):
        potential_dirs.extend([
            Path("/opt/drawio-plugins"),
            Path("/opt/draw.io/plugins"),
        ])
    
    if os.access("/usr/share", os.W_OK):
        potential_dirs.append(Path("/usr/share/drawio/plugins"))
    
    logger.info("Checking plugin directories:")
    for dir_path in potential_dirs:
        # Handle glob patterns
        if "*" in str(dir_path):
            parent = dir_path.parent
            pattern = dir_path.name
            if parent.exists():
                matches = list(parent.glob(pattern))
                if matches:
                    for match in matches:
                        plugin_dir = match / "plugins"
                        if plugin_dir.exists():
                            logger.info(f"  ✓ {plugin_dir} exists")
                            logger.info(f"    Contents: {list(plugin_dir.glob('*'))}")
        elif dir_path.exists():
            logger.info(f"  ✓ {dir_path} exists")
            if dir_path.is_dir():
                contents = list(dir_path.glob("*"))
                logger.info(f"    Contents: {[f.name for f in contents]}")
                # Check if svgdata.js exists
                if (dir_path / "svgdata.js").exists():
                    logger.info(f"    → svgdata.js found! Size: {(dir_path / 'svgdata.js').stat().st_size} bytes")
        else:
            logger.info(f"  ✗ {dir_path} does not exist")
    
    # Check config files
    config_locations = [
        home / ".config" / "draw.io" / "config.json",
        home / ".drawio" / "config.json",
    ]
    
    logger.info("Checking config files:")
    for config_path in config_locations:
        if config_path.exists():
            logger.info(f"  ✓ {config_path} exists")
            try:
                with open(config_path) as f:
                    config = json.load(f)
                logger.info(f"    Config: {json.dumps(config, indent=2)}")
            except Exception as e:
                logger.info(f"    Error reading config: {e}")
        else:
            logger.info(f"  ✗ {config_path} does not exist")
    
    logger.info("=== End Plugin Debug Information ===")


def _create_config_with_plugin() -> Path:
    """Create a temporary config file that includes the plugin."""
    plugin_src = Path(__file__).with_name("svgdata.js")
    
    # Create temporary directory for this export
    tmpdir = tempfile.mkdtemp(prefix="drawio-plugin-")
    plugin_dst = Path(tmpdir) / "svgdata.js"
    config_dst = Path(tmpdir) / "config.json"
    
    # Copy plugin
    shutil.copy(plugin_src, plugin_dst)
    
    # Create config
    config = {
        "plugins": [
            {
                "url": f"file://{plugin_dst}",
                "enabled": True
            }
        ]
    }
    
    with open(config_dst, "w") as f:
        json.dump(config, f, indent=2)
    
    logger.debug(f"Created temporary config at {config_dst}")
    logger.debug(f"Config content: {json.dumps(config, indent=2)}")
    
    return config_dst


def _install_plugin() -> None:
    """Install plugin to user-accessible locations."""
    plugin_src = Path(__file__).with_name("svgdata.js")
    home = Path.home()
    
    # Try user's home directory locations
    locations = [
        home / ".config" / "draw.io" / "plugins",
        home / ".drawio" / "plugins",
    ]
    
    # Only try system locations if we have write permission
    if os.access("/opt", os.W_OK):
        locations.append(Path("/opt/drawio-plugins"))
    
    for plugin_dir in locations:
        try:
            plugin_dir.mkdir(parents=True, exist_ok=True)
            plugin_dst = plugin_dir / "svgdata.js"
            shutil.copy(plugin_src, plugin_dst)
            logger.debug(f"Copied plugin to {plugin_dst}")
        except Exception as exc:
            logger.debug(f"Could not copy plugin to {plugin_dir}: {exc}")


def _in_docker() -> bool:
    """Detect if running inside a Docker container."""
    return os.environ.get("IN_DOCKER", "").lower() in {"1", "true", "yes"}


def export_svg_with_metadata(drawio_file: str, svg_file: str, debug: bool = True) -> None:
    """Use draw.io CLI to export a diagram to SVG with metadata."""
    drawio_bin = _ensure_drawio()
    
    # Install plugin to user-accessible locations
    _install_plugin()
    
    # Debug plugin locations if requested
    if debug or logger.isEnabledFor(logging.DEBUG):
        _debug_plugin_locations()
    
    # Create temporary config with plugin
    config_file = _create_config_with_plugin()
    
    try:
        if _in_docker():
            # Try multiple approaches to ensure plugin is loaded
            cmd = [
                "xvfb-run",
                str(drawio_bin),
                "--appimage-extract-and-run",
                "--no-sandbox",
                "--export",
                "--format",
                "svg",
                "--enable-plugins",
                f"--config={config_file}",  # Use temporary config
                "--output",
                svg_file,
                drawio_file,
            ]
            
            # Use current environment, don't override HOME
            env = os.environ.copy()
            env["DRAWIO_CONFIG"] = str(config_file)
            
        else:
            # Non-Docker path: use Docker container
            image = os.environ.get("CLAB_IO_DRAW_IMAGE", "clab-io-draw:latest")
            logger.info(
                "Using Docker image %s with svgdata plugin (image will be pulled if missing)",
                image,
            )
            drawio_path = Path(drawio_file).resolve()
            svg_path = Path(svg_file).resolve()

            # Create temporary config in the same directory as the input file
            # This ensures the Docker container can access it
            temp_config_dir = drawio_path.parent / ".drawio-temp"
            temp_config_dir.mkdir(exist_ok=True)
            
            # Copy plugin to temp directory
            plugin_src = Path(__file__).with_name("svgdata.js")
            temp_plugin = temp_config_dir / "svgdata.js"
            shutil.copy(plugin_src, temp_plugin)
            
            # Create config in temp directory
            temp_config = temp_config_dir / "config.json"
            config_data = {
                "plugins": [
                    {
                        "url": f"file:///input/.drawio-temp/svgdata.js",
                        "enabled": True
                    }
                ]
            }
            with open(temp_config, "w") as f:
                json.dump(config_data, f)

            code = (
                "from clab_io_draw.core.svg.drawio_cli import export_svg_with_metadata;"
                f"export_svg_with_metadata('/input/{drawio_path.name}', '/output/{svg_path.name}', debug=False)"
            )
            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{drawio_path.parent}:/input",
                "-v",
                f"{svg_path.parent}:/output",
                "-e",
                f"DRAWIO_CONFIG=/input/.drawio-temp/config.json",
                "--entrypoint",
                "python",
                image,
                "-c",
                code,
            ]
            env = None

        logger.debug("Running: %s", " ".join(shlex.quote(part) for part in cmd))
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        
        if result.stdout:
            logger.debug("stdout: %s", result.stdout)
        if result.stderr:
            logger.debug("stderr: %s", result.stderr)
            
        # Verify the plugin worked
        if Path(svg_file).exists():
            with open(svg_file) as f:
                svg_content = f.read()
                if 'id="cell-' in svg_content:
                    logger.info("✓ Plugin successfully applied - found cell IDs in SVG")
                else:
                    logger.warning("⚠ SVG exported but plugin may not have been applied - no cell IDs found")
                    logger.debug("First 500 chars of SVG: %s", svg_content[:500])
                    
    finally:
        # Cleanup temporary files
        if config_file and config_file.exists():
            try:
                shutil.rmtree(config_file.parent)
            except Exception as e:
                logger.debug(f"Could not clean up temp dir: {e}")
        
        # Clean up temp directory if we created one for Docker
        if not _in_docker():
            temp_dir = Path(drawio_file).parent / ".drawio-temp"
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.debug(f"Could not clean up Docker temp dir: {e}")