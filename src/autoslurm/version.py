"""One literal source for package, build and running-code version identity.

Keep this value static: setuptools reads it without importing the application.
"""

__all__ = ["__version__"]

__version__ = "0.2.0.dev8"
