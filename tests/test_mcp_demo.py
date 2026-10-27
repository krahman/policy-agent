import subprocess
import sys

from policy_agent.ingest.paths import ROOT


def test_protocol_demo_passes_every_check():
    """Step 7 exit criterion: the demo prints the full lifecycle and every negative case behaves as designed."""
    out = subprocess.run(
        [sys.executable, "scripts/mcp_protocol_demo.py", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )  # noqa: E501
    assert out.returncode == 0, out.stdout[-1500:]
    assert "checks passed" in out.stdout and "FAIL" not in out.stdout
