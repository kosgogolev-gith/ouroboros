def test_placeholder():
    import os
    os.environ["PATH"] = "/home/goga/ouroboros_repo/venv/bin:" + os.environ["PATH"]
    assert True