from audioharbor.media.filename import output_name, safe_component


def test_filename_removes_traversal_and_control_chars():
    result = safe_component('../a/\x00b\n')
    assert '/' not in result and '\x00' not in result and '..' not in result


def test_output_layout():
    assert str(output_name('Song', 'youtube', 'abc')) == 'Song [youtube-abc].mp3'
    assert str(output_name('Song', 'youtube', 'abc', 'Mix', 2)) == '002 - Song [youtube-abc].mp3'

