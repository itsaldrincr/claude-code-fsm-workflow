"""Tests for install.sh skill copy functionality and init-workflow skill-self-install."""

import shutil
import subprocess
import tempfile
from pathlib import Path


class TestInstallSkills:
    """Test skill installation in install.sh."""

    def test_install_skills_creates_directory(self) -> None:
        """install.sh creates .claude/skills directory."""
        with tempfile.TemporaryDirectory() as fake_home:
            fake_home_path = Path(fake_home)
            skills_dir = fake_home_path / ".claude" / "skills"

            repo_root = Path(__file__).parent.parent
            result = subprocess.run(
                ["bash", str(repo_root / "install.sh")],
                env={"HOME": fake_home},
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"install.sh failed: {result.stderr}"
            assert skills_dir.exists(), f"{skills_dir} not created"

    def test_install_skills_copies_all_six_files(self) -> None:
        """install.sh copies all six skill files to .claude/skills."""
        with tempfile.TemporaryDirectory() as fake_home:
            fake_home_path = Path(fake_home)
            skills_dir = fake_home_path / ".claude" / "skills"

            repo_root = Path(__file__).parent.parent
            result = subprocess.run(
                ["bash", str(repo_root / "install.sh")],
                env={"HOME": fake_home},
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            skill_files = list(skills_dir.glob("*.md"))
            assert len(skill_files) == 6, f"Expected 6 skills, found {len(skill_files)}"

    def test_install_skills_idempotent_no_duplicates(self) -> None:
        """install.sh run twice creates no duplicate skill files."""
        with tempfile.TemporaryDirectory() as fake_home:
            fake_home_path = Path(fake_home)
            skills_dir = fake_home_path / ".claude" / "skills"

            repo_root = Path(__file__).parent.parent
            install_script = str(repo_root / "install.sh")

            # First run
            result1 = subprocess.run(
                ["bash", install_script],
                env={"HOME": fake_home},
                capture_output=True,
                text=True,
            )
            assert result1.returncode == 0

            skill_files_first = list(skills_dir.glob("*.md"))
            count_first = len(skill_files_first)
            assert count_first == 6

            # Second run
            result2 = subprocess.run(
                ["bash", install_script],
                env={"HOME": fake_home},
                capture_output=True,
                text=True,
            )
            assert result2.returncode == 0

            skill_files_second = list(skills_dir.glob("*.md"))
            count_second = len(skill_files_second)
            assert count_second == 6, (
                f"Second run produced {count_second} files, "
                f"expected 6 (idempotency violated)"
            )

    def test_install_skills_output_message(self) -> None:
        """install.sh outputs correct skill installation message."""
        with tempfile.TemporaryDirectory() as fake_home:
            repo_root = Path(__file__).parent.parent
            result = subprocess.run(
                ["bash", str(repo_root / "install.sh")],
                env={"HOME": fake_home},
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "Installed 6 skills to" in result.stdout, (
                f"Expected output containing 'Installed 6 skills to', "
                f"got: {result.stdout}"
            )


class TestInitWorkflowSkillsCopy:
    """Test init-workflow's skill-self-install logic."""

    def _copy_skills_idempotent(
        self, skills_source: Path, skills_target: Path
    ) -> None:
        """Copy skill files from source to target directory, idempotently.

        Mirrors the install.sh skill-copy block logic for use in init-workflow.
        """
        skills_target.mkdir(parents=True, exist_ok=True)
        for skill_file in skills_source.glob("*.md"):
            target_file = skills_target / skill_file.name
            if not target_file.exists():
                shutil.copy2(skill_file, target_file)

    def test_init_workflow_skill_copy_to_fresh_project(self) -> None:
        """init-workflow copies skills to .claude/skills in fresh project."""
        with tempfile.TemporaryDirectory() as fake_home:
            fake_home_path = Path(fake_home)
            with tempfile.TemporaryDirectory() as fake_cwd:
                fake_cwd_path = Path(fake_cwd)

                repo_root = Path(__file__).parent.parent
                skills_source = repo_root / "plugins" / "fsm-workflow" / "skills"
                skills_target = fake_cwd_path / ".claude" / "skills"

                # Simulate init-workflow skill-copy logic
                self._copy_skills_idempotent(skills_source, skills_target)

                # Verify all six skills are in the target
                skill_files = list(skills_target.glob("*.md"))
                assert len(skill_files) == 6, (
                    f"Expected 6 skills in {skills_target}, found {len(skill_files)}"
                )

                expected_skills = {
                    "fsm-roles.md",
                    "fsm-task-format.md",
                    "fsm-map-format.md",
                    "fsm-hook-enforcement.md",
                    "model-tier-routing.md",
                    "fsm-workflow-phases.md",
                }
                actual_skills = {f.name for f in skill_files}
                assert actual_skills == expected_skills, (
                    f"Expected skills {expected_skills}, got {actual_skills}"
                )

    def test_init_workflow_skill_copy_idempotent(self) -> None:
        """init-workflow skill-copy logic is idempotent on re-run."""
        with tempfile.TemporaryDirectory() as fake_cwd:
            fake_cwd_path = Path(fake_cwd)

            repo_root = Path(__file__).parent.parent
            skills_source = repo_root / "plugins" / "fsm-workflow" / "skills"
            skills_target = fake_cwd_path / ".claude" / "skills"

            # First copy
            self._copy_skills_idempotent(skills_source, skills_target)
            skill_files_first = sorted(
                [f.name for f in skills_target.glob("*.md")]
            )
            count_first = len(skill_files_first)

            # Second copy (should not duplicate)
            self._copy_skills_idempotent(skills_source, skills_target)
            skill_files_second = sorted(
                [f.name for f in skills_target.glob("*.md")]
            )
            count_second = len(skill_files_second)

            assert count_second == 6, (
                f"Second copy produced {count_second} files, "
                f"expected 6 (idempotency violated)"
            )
            assert skill_files_first == skill_files_second, (
                f"File lists differ after second copy: "
                f"{skill_files_first} vs {skill_files_second}"
            )

    def test_init_workflow_self_install_skills_to_user_level(self) -> None:
        """init-workflow copies skills to ~/.claude/skills in fresh HOME."""
        with tempfile.TemporaryDirectory() as fake_home:
            fake_home_path = Path(fake_home)

            repo_root = Path(__file__).parent.parent
            skills_source = repo_root / "plugins" / "fsm-workflow" / "skills"
            skills_target = fake_home_path / ".claude" / "skills"

            # Simulate init-workflow step 5: copy from package into user ~/.claude/skills
            self._copy_skills_idempotent(skills_source, skills_target)

            # Verify all six skills landed in fake HOME
            skill_files = sorted([f.name for f in skills_target.glob("*.md")])
            assert len(skill_files) == 6, (
                f"Expected 6 skills in {skills_target}, found {len(skill_files)}"
            )

            expected_skills = {
                "fsm-roles.md",
                "fsm-task-format.md",
                "fsm-map-format.md",
                "fsm-hook-enforcement.md",
                "model-tier-routing.md",
                "fsm-workflow-phases.md",
            }
            actual_skills = set(skill_files)
            assert actual_skills == expected_skills, (
                f"Expected {expected_skills}, got {actual_skills}"
            )

            # Test idempotency: re-run and verify no duplicates
            self._copy_skills_idempotent(skills_source, skills_target)
            skill_files_second = sorted(
                [f.name for f in skills_target.glob("*.md")]
            )
            assert len(skill_files_second) == 6, (
                f"Second run produced {len(skill_files_second)} files, "
                f"expected 6 (idempotency violated)"
            )
            assert skill_files == skill_files_second, (
                f"File lists differ after second run"
            )
