"""Occupation context lookup. Profiles are illustrative, not risk scores."""


def get_profile(profiles, occupation):
    return profiles.get(occupation)
