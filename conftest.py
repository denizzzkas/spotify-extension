# Makes soundcloud-extension/ the package root for pytest.
# pytest adds this directory to sys.path so imports like
# `from handlers.auth import ...` and `from config import ...` work in tests.
