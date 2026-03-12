"""Shared test configuration."""

import os

# Prevent tests from writing to Supabase
os.environ["TESTING"] = "1"
