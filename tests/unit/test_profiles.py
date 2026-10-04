from audioharbor.domain.profiles import profile_hash


def test_profile_hash_is_stable_and_changes_with_quality():
    assert profile_hash({'quality_mode':'vbr','vbr_quality':2}) == profile_hash({'vbr_quality':2,'quality_mode':'vbr'})
    assert profile_hash({'quality_mode':'vbr','vbr_quality':2}) != profile_hash({'quality_mode':'vbr','vbr_quality':5})

