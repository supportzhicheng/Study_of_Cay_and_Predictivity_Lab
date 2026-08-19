"""Compatibility entry point for core project settings."""

from src.settings import PROJECT_ROOT, Settings, load_settings, main

__all__ = ["PROJECT_ROOT", "Settings", "load_settings"]


if __name__ == "__main__":
    main()
