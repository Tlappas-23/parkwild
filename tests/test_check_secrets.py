import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_secrets", Path(__file__).parents[1] / "scripts" / "check_secrets.py")
check_secrets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_secrets)


def test_scan_flags_tokens_and_env_files():
    files = {
        "src/ok.py": "token = os.environ['MAPILLARY_TOKEN']\n",
        "notes.md": "MLY|1234567890123|0123456789abcdef0123456789abcdef\n",  # secret-scan:ignore
        ".env": "MAPILLARY_TOKEN=x\n",
        ".env.example": "MAPILLARY_TOKEN=\n",
        "key.pem": "-----BEGIN RSA PRIVATE KEY-----\n",  # secret-scan:ignore
        "img.jpg": "MLY|1234567890123|0123456789abcdef0123456789abcdef",   # binary suffix skipped  secret-scan:ignore
        "marked.py": "TOKEN = 'MLY|1234567890123|0123456789abcdef0123456789abcdef'  # secret-scan:ignore\n",
    }
    findings = check_secrets.scan(list(files), lambda p: files[p])
    assert any(f.startswith("notes.md") for f in findings)
    assert any(f.startswith(".env:") for f in findings)
    assert any(f.startswith("key.pem") for f in findings)
    assert not any(f.startswith(("src/ok.py", ".env.example", "img.jpg", "marked.py")) for f in findings)
