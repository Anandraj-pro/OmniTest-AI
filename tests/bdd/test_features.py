"""Binds every .feature under features/ into pytest test cases.

Add a new .feature file and it's automatically collected — no code change here.
"""
from pytest_bdd import scenarios

scenarios("features")
