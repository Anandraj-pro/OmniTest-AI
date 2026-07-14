"""Make the shared step library visible to every feature under tests/bdd/.

Importing the module runs its @given/@when/@then decorators, registering the
steps with pytest-bdd. Story-specific steps can still be added in their own
test modules.
"""
from tests.bdd.steps.common_steps import *  # noqa: F401,F403
