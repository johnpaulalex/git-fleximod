# A relative -C path must not be resolved twice once a submodule is populated.
import subprocess

import pytest

from git_fleximod.gitinterface import GitInterface

SUBMODULE_PATH = "modules/test"
# Same small public repo and layout as the other tests (tests/conftest.py). mpi-serial is an
# arbitrary but real repo: it is cloned over https and its tag MPIserial_2.4.0 is the fxtag.
GITMODULES = """
[submodule "test_submodule"]
    path = modules/test
    url = https://github.com/ESMCI/mpi-serial.git
    fxtag = MPIserial_2.4.0
    fxDONOTUSEurl = https://github.com/ESMCI/mpi-serial.git
"""
# A line each command prints for the populated submodule, so a run that silently did
# nothing fails the test instead of passing on exit code 0 alone.
PROCESSED = {"update": "up to date", "status": "at tag MPIserial_2.4.0"}


@pytest.fixture(name="populated_clone")
def fixture_populated_clone(tmp_path, logger):
    """A clone of a repo with one submodule, already populated by git-fleximod."""
    origin = tmp_path / "origin"
    origin.mkdir()
    gitp = GitInterface(str(origin), logger)
    (origin / "modules").mkdir()
    gitp.git_operation(
        "submodule",
        "add",
        "--depth",
        "1",
        "--name",
        "test_submodule",
        "https://github.com/ESMCI/mpi-serial.git",
        SUBMODULE_PATH,
    )
    gitp.git_operation("add", SUBMODULE_PATH)
    gitp.git_operation("commit", "-a", "-m", '"add submod"')
    clone = tmp_path / "clone"
    gitp.git_operation("clone", origin, clone)
    (clone / ".gitmodules").write_text(GITMODULES)
    return clone


@pytest.mark.parametrize("action", ["update", "status"])
def test_relative_C(git_fleximod, populated_clone, action):
    # Populate with no -C first, so the next run starts from a populated submodule.
    result = git_fleximod(populated_clone, "update")
    assert result.returncode == 0
    assert (populated_clone / SUBMODULE_PATH / ".git").exists()

    result = git_fleximod(populated_clone, f"-C . {action}")
    assert result.returncode == 0
    assert "NoSuchPathError" not in result.stderr
    assert PROCESSED[action] in result.stdout
    assert (populated_clone / SUBMODULE_PATH / ".git").exists()


def test_relative_C_in_worktree(git_fleximod, populated_clone, tmp_path):
    # Update the newly cloned repo (which has a submodule)
    result = git_fleximod(populated_clone, "update")
    assert result.returncode == 0

    # Create worktree for that repo
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", str(worktree)],
        cwd=populated_clone,
        check=True,
        capture_output=True,
    )
    # git worktree add leaves the submodule as an empty, uninitialised directory.
    assert not (worktree / SUBMODULE_PATH / ".git").exists()
    # The clone's .gitmodules with the fxtag is an uncommitted edit, so the worktree starts
    # from the committed one, which has no fxtag; copy the clone's over it.
    (worktree / ".gitmodules").write_text(GITMODULES)

    # The new worktree has no submodule checked out: this run checks it out and then runs
    # the post-checkout block in the same update() call.
    result = git_fleximod(worktree, "-C . update")
    assert result.returncode == 0
    assert "NoSuchPathError" not in result.stderr
    submodule_git = worktree / SUBMODULE_PATH / ".git"
    assert submodule_git.exists()
    populated_at = submodule_git.stat().st_mtime_ns

    # Second run starts from a populated submodule in the worktree, so update() has no
    # populating to do and only runs the post-checkout block.
    result = git_fleximod(worktree, "-C . update")
    assert result.returncode == 0
    # Only the post-checkout block prints "up to date", so this shows that it ran.
    assert PROCESSED["update"] in result.stdout
    # Populating writes the submodule's .git; an unchanged mtime shows nothing was re-cloned.
    assert submodule_git.stat().st_mtime_ns == populated_at
