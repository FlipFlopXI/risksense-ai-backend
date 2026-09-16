import os


def test_database_is_explicitly_isolated():
    test_database_url = os.environ["TEST_DATABASE_URL"]
    assert test_database_url.rsplit("/", 1)[-1] == "risksense_test"
    assert "supabase" not in test_database_url.lower()
