from __future__ import annotations

import sys

from dotkit import progress, system
from dotkit.apt import apt_status
from dotkit.progress import Progress


def test_apt_status_lines_become_percentages():
    assert apt_status("pmstatus:cuda-nvcc-13-4:42.5:Unpacking cuda-nvcc-13-4") == (
        0.425,
        "Unpacking cuda-nvcc-13-4",
    )
    assert apt_status("dlstatus:3:10:Retrieving file 3 of 30") == (
        0.1,
        "Downloading: Retrieving file 3 of 30",
    )
    assert apt_status("Setting up foo (1.0) ...") == (None, "Setting up foo (1.0) ...")
    assert apt_status("pmstatus:x:not-a-number:y") is None


def test_run_keeps_real_output_but_not_progress_reports():
    script = "echo pmstatus:p:50:Unpacking p; echo 'E: something broke'; printf 'a\\rb\\n'"
    result = system.run(["sh", "-c", script], progress=apt_status, check=False)
    assert result.stdout == "E: something broke\na\nb\n"


def test_run_feeds_input_and_reports_failures():
    result = system.run(["sh", "-c", "cat; exit 3"], input="hello\n", check=False)
    assert (result.returncode, result.stdout) == (3, "hello\n")


def test_render_shows_bar_elapsed_and_latest_line():
    bar = Progress()
    bar.update(0.5, "Unpacking   cuda-nvcc")
    line = bar.render(width=100)
    assert "[████████████░░░░░░░░░░░░]  50%" in line and line.endswith("Unpacking cuda-nvcc")
    assert len(bar.render(width=30)) <= 29  # never wraps the terminal


def test_nothing_is_drawn_without_a_terminal(capsys, monkeypatch):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    assert not progress.enabled()
    with Progress() as bar:
        bar.update(0.3, "x")
    assert capsys.readouterr().err == ""


def test_sizes_read_naturally():
    assert [progress.size(n) for n in (512, 2048, 5 * 1024**2, 3 * 1024**3)] == [
        "512 B",
        "2 KB",
        "5.0 MB",
        "3.0 GB",
    ]
