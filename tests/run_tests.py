#!/usr/bin/env python3
"""
Test runner script for Athena backend
Usage: python tests/run_tests.py [options]
"""
import sys
import subprocess
from pathlib import Path


def run_tests(args=None):
    """Run the test suite with pytest."""
    if args is None:
        args = []

    # Base pytest command
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "-v",  # Verbose
        "--tb=short",  # Short traceback format
        "--color=yes",  # Colored output
    ]

    # Add any additional arguments
    cmd.extend(args)

    print("=" * 70)
    print("Running Athena Backend Test Suite")
    print("=" * 70)
    print(f"Command: {' '.join(cmd)}\n")

    # Run tests
    result = subprocess.run(cmd)

    return result.returncode


def run_with_coverage():
    """Run tests with coverage report."""
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "-v",
        "--cov=app",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--tb=short"
    ]

    print("=" * 70)
    print("Running Tests with Coverage Analysis")
    print("=" * 70)

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "=" * 70)
        print("Coverage report generated in htmlcov/index.html")
        print("=" * 70)

    return result.returncode


def run_quick_tests():
    """Run only fast tests (skip slow integration tests)."""
    return run_tests(["-m", "not slow"])


def run_specific_test(test_name):
    """Run a specific test file or test function."""
    return run_tests(["-k", test_name])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--coverage":
            sys.exit(run_with_coverage())
        elif command == "--quick":
            sys.exit(run_quick_tests())
        elif command == "--test":
            if len(sys.argv) > 2:
                sys.exit(run_specific_test(sys.argv[2]))
            else:
                print("Error: --test requires a test name")
                sys.exit(1)
        elif command == "--help":
            print("""
Athena Backend Test Runner

Usage:
    python tests/run_tests.py [options]

Options:
    (none)          Run all tests
    --coverage      Run tests with coverage report
    --quick         Run only quick tests (skip slow ones)
    --test NAME     Run specific test matching NAME
    --help          Show this help message

Examples:
    python tests/run_tests.py
    python tests/run_tests.py --coverage
    python tests/run_tests.py --test test_reminders
    python tests/run_tests.py --quick
            """)
            sys.exit(0)
        else:
            # Pass unknown arguments directly to pytest
            sys.exit(run_tests(sys.argv[1:]))
    else:
        # Run all tests by default
        sys.exit(run_tests())
