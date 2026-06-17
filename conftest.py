"""Root conftest.

Its mere presence puts the project root on ``sys.path`` (pytest "prepend" import mode),
so tests can import top-level modules (``config``, ``llm.base``, ``brain.db``, ...)
without the project being installed as a package.
"""
