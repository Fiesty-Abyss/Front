import importlib.util
import os
from pathlib import Path
import zipfile


def test_portable_zip_keeps_bytes_with_old_upstream_license_timestamp(tmp_path):
    script=Path(__file__).resolve().parents[2]/'desktop/archive_tools.py'
    spec=importlib.util.spec_from_file_location('front_archive_tools',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=tmp_path/'generated-package';source.mkdir()
    license_file=source/'LICENSE';license_file.write_bytes(b'Generated license fixture')
    os.utime(license_file,(1,1))
    destination=tmp_path/'preview.zip';module.portable_zip(source,destination)
    with zipfile.ZipFile(destination) as archive:
        assert archive.read('LICENSE')==license_file.read_bytes()
        assert archive.getinfo('LICENSE').date_time[0]==1980 and archive.testzip() is None
    assert license_file.stat().st_mtime<315532800  # Source timestamp is not rewritten.
