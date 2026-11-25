"""The reorder buffer's files agree with each other: spec.yaml with the RTL, spec.md with spec.yaml, Verilator -Wall lint at every point, the generated register wrappers and
build.yaml files (arith brief 148)."""
from __future__ import annotations

from arith.tools import suite


def test_spec_yaml_matches_the_rtl_headers():
    suite.check_spec_matches_rtl("fft_reorder")


def test_spec_md_is_generated_from_spec_yaml():
    suite.check_spec_md("fft_reorder")


def test_every_variant_lints_clean_at_every_point():
    suite.check_lint_clean("fft_reorder")


def test_build_files_are_current_and_the_wrappers_lint_clean():
    suite.check_build_files("fft_reorder")


def test_readme_links_the_function():
    suite.check_readme("fft_reorder")
